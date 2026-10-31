# Testing & CI

Each repository has its own GitHub Actions CI. Core tests the stack itself, the
templates repo tests every template against a pinned core version, and the Hub
tests and signs its image.

| Repo | Workflow | Jobs |
|------|----------|------|
| core (`porelli/portcullis`) | `.github/workflows/ci.yml`, `release.yml` | `unit-tests`, `build-and-test`, `e2e`; release: `preflight` → `ci` (reusable `ci.yml`) → `release` |
| templates (`porelli/portcullis-templates`) | `lint.yml`, `test-apps.yml`, `docs-dispatch.yml` | `lint`; `gate` → `changes` → `fetch-core` (+ `app-images` on push to `main`) → `test`; `dispatch` |
| Hub (`porelli/portcullis-hub`) | `build.yml` | `test`, `build` |
| docs (`porelli/portcullis-docs`) | `deploy.yml` | `deploy` (`zensical build --strict`, publish to `gh-pages`) |

## Core CI

Runs on pushes to `main`, on pull requests, and as a reusable workflow (`workflow_call`) from `release.yml`. Secrets are not configured in
the workflow: `./portcullis init --env-only` generates them into `.env`,
exactly as on a real install. Every step drives the stack through
`./portcullis`.

### `unit-tests` (no containers)

- **shellcheck** of `portcullis`, `scripts/lib/*.sh`, `tests/*.sh` and `vault/entrypoint.sh`.
- **CLI help.** Every command listed by `./portcullis help` must print a `Usage: portcullis <cmd>` line for `--help`.
- **`tests/test_cli.sh`.** Argument parsing, dispatch and `init --env-only`, with a stub `docker`.
- **`tests/test_shell_libs.sh`.** Shell-library tests against stub `docker`/`vault`:
    - `.env` handling and secret generation
    - network validation
    - `cert sync`, which must never empty the revoked list when Vault fails
    - `pki setup` idempotency, including resuming a partial run
- **`tests/test_group_gate.py`.** group-gate unit tests:
    - host normalisation and the case/port bypass regression
    - merging the map file with the Hub's `groups`
    - fail-closed policies and the reserved deny group
    - `path_groups`, including bypass variants
    - the mTLS binding
    - revocation by serial list and by a real openssl-generated CRL
    - the identity headers returned on allow
- **Compose validity and wiring**, against a generated `.env`. `docker compose config -q` must pass for the core, apps and test compose files. It also checks:
    - `HUB_PROXY_SECRET` is generated, and an empty one is rejected
    - the public default forward-auth secret is gone
    - only the two socket proxies mount `docker.sock`; Traefik and the Hub use their proxies, and each proxy network has exactly its two members
    - the Hub router carries `hub-proxy-secret@docker` with the right secret
    - every core image is pinned by digest, and `enroll/Dockerfile` bases too
    - every service has `no-new-privileges`, `cap_drop: ALL` and memory/pid limits
    - Keycloak's `--proxy-trusted-addresses` is Traefik's `portcullis-auth` IP, and only Keycloak and Traefik are on that network
- **Pin enforcement.** Every image in every compose file, under every profile (`--profile '*'`), must be pinned `tag@sha256:…`, apart from the Hub, which comes from `HUB_IMAGE`. The same goes for the `enroll/Dockerfile` bases, the image constants the CLI runs itself (`*_IMAGE=` in `scripts/lib`, e.g. the restic and helper images), and inline images in the workflows. Every action must be pinned by full commit SHA with a `# vX.Y.Z` comment.
- **Monitoring config.** It runs, in the pinned images:
    - `promtool check config` and `check rules`, plus `promtool test rules` (the alert unit tests)
    - `amtool check-config` for a generated Alertmanager config with no receiver, a webhook, ntfy and SMTP
    - `blackbox_exporter --config.check`
    - a sanity check of the provisioned dashboard JSON
- **enroll** `go vet` + `go test` in the pinned Go image: CSR validation, admin requirement, content type, AppRole login and re-login, self-service renewal.

### `build-and-test` (whole stack)

It boots the stack with a CI override (no ACME; self-signed server cert from
the internal PKI) and verifies:

- **Vault**
    - server-mode init and unseal, and the permissions on `secrets/`
    - after a restart it auto-unseals and the CA is unchanged
    - the enroll AppRole can only sign, list and read certs
- **PKI**
    - the CA chain is created and valid
    - Vault issues client certificates
- **Keycloak**
    - the OIDC discovery and SAML descriptor endpoints
    - the WebAuthn policy
    - the `portcullis-forward-auth` client
    - LLDAP users show up through the federation
    - the `email-unverified` scope has exactly one mapper (`email`), also after a second `keycloak configure`; a throwaway direct-grant client with that scope instead of `email` gets `email` but no `email_verified` in the ID token, access token and userinfo, while the built-in `email` scope sends `email_verified: false`
- **mTLS**
    - requests with no cert, or a cert from another CA, are rejected
    - cert info, including the serial, reaches the backend
    - requests arrive from Traefik's static IP
- **X.509 login**
    - a login via Traefik with a real cert succeeds
    - the same cert as a forged header sent straight to Keycloak (from the
      `portcullis` and `portcullis-auth` networks and from `127.0.0.1:8080`)
      must **not** yield an authorization code
- **Header spoofing.** Client-supplied cert headers and their aliases are
  dropped, and group-gate's path rules see `X-Forwarded-Uri`.
- **Socket proxies.** A real `docker compose` project runs through
  `socket-proxy-hub`, and the denied sections (build, swarm, plugins, secrets,
  system, ...) fail. Traefik's proxy is read-only.
- **Hub**
    - runs as non-root
    - talks to Docker only via its proxy
    - answers 403 without the proxy secret
- **Enrollment UI and API.** List users, sign a CSR with the AppRole token, list certs.
- **Revocation end to end**, once through `./portcullis cert revoke` and once through Vault's CRL alone.
- **CLI.** `./portcullis status`.
- **Backup round-trip.** It runs, in order:
    - `./portcullis backup` with nothing stopped, then `backup verify --local`. A deliberately damaged backup must fail verification.
    - `status --textfile`.
    - `backup --offsite` twice to a local restic repository. The second run must be incremental, and retention must collapse same-day snapshots under `keep-daily`.
    - `backup verify` (off-host). A wrong `BACKUP_PASSWORD` must fail, and neither the root token nor the `.env` secrets may appear in the encrypted repository.
    - **Restore into a fresh stack.** Containers, volumes, `.env`, `secrets/`, `certs/` and local backups are all deleted, as on a new host. Then `restore --yes --from-offsite` must bring back an active Vault, the Keycloak realm, the forward-auth client and the LLDAP user.

### `e2e` (browser)

`tests/e2e/e2e_login.py` runs Playwright Chromium (pinned in
`tests/e2e/requirements.txt`) with a CDP virtual WebAuthn authenticator against
the full chain: Traefik → oauth2-proxy → Keycloak (LLDAP users, WebAuthn, X.509)
→ group-gate. A `whoami` test app has three hosts: `app.` (group `users_e2e`,
`/admin` → `admin_e2e`), `hwk.` (WebAuthn policy) and `mtls.` (mTLS policy).

Scenarios:

1. An unauthenticated request is redirected to Keycloak.
2. A password login with passkey registration (required action) reaches the app.
3. Apps get the **username** as `X-Forwarded-User`, and spoofed identity headers are dropped.
4. `path_groups`: `/admin` needs `admin_e2e`. `/%61dmin`, `//admin`, `/x/../admin` and `/ADMIN` are denied, while `/administrator` is allowed.
5. Step-up: a WebAuthn policy after a password login.
6. Group denial for a user not in `users_e2e`.
7. X.509 login via Keycloak satisfies an mTLS policy.
8. An mTLS session without the cert on the request is refused (mTLS binding).
9. A revoked client cert is rejected.
10. A client cert from a foreign CA is rejected in the TLS handshake.

After the browser tests, the job enables the **monitoring profile** and checks:

- all monitoring services become healthy, and every Prometheus target is up
- the Vault health probe and the enroll/forward-auth/LLDAP probes succeed
- group-gate, CRL, backup (textfile), CA-expiry, Traefik and Vault metrics are present
- the alert rules are loaded, and neither `VaultSealedOrDown` nor `CrlStale` is pending or firing
- Grafana at `metrics.<domain>` redirects unauthenticated users to sign in, and rejects a forged identity header that doesn't come from Traefik's IP

On failure, screenshots, HTML, traces and service logs are uploaded as
artifacts. The test needs a live stack and is not collected by pytest.

### Caching

Core CI caches what it safely can. Caches are written only on pushes to `main`.

- **Infra and monitoring images:** cached by the local composite action `.github/actions/cached-images`.
    - The cache key is a hash of each job's pinned image list. Refs without a digest are refused.
    - After `docker load`, every name set by the tarball is removed. Each ref is then re-pulled by its pinned digest (with retry and backoff), so the engine reuses a loaded image only if its content-addressed ID matches the registry's config digest.
- **enroll image:** buildx layer cache (`type=gha`).
- **Go:** module and build cache through `setup-go`, with `go mod verify`.
- **Python:** pip and Playwright browsers, cached on the pinned requirements file.

The revocation check waits up to 180s, because Vault rebuilds delta CRLs at most once a minute.

### Releases (`release.yml`)

Runs on `v*` tags:

1. **`preflight`** checks two things:
    - The tag is `vMAJOR.MINOR.PATCH` and `CHANGELOG.md` has its `## [X.Y.Z]` section.
    - The `HUB_IMAGE` default in `docker-compose.yml` is `ghcr.io/porelli/portcullis-hub:A.B.C@sha256:…`, where `vA.B.C` is a published (non-draft, non-prerelease) Hub release and the tag still resolves to that digest.
2. **`ci`** runs the full `ci.yml` on the tagged commit.
3. **`release`** builds a reproducible `portcullis-X.Y.Z.tar.gz` (the checkout without `.git`, plus `VERSION`) and its `.sha256`. It then creates the GitHub release with the changelog section, the pinned Hub image and generated notes.

See [Upgrading & Releases](upgrading.md#core-releases).

### Dependabot

`.github/dependabot.yml` proposes weekly, grouped updates for:

- the compose images
- the enroll Dockerfile and Go modules
- the GitHub Actions
- the e2e Python requirements

Image constants in the CLI and inline images in workflows are not covered by
Dependabot. They are still checked by the pin-enforcement step.

### Running the core tests locally

```bash
python3 tests/test_group_gate.py
bash tests/test_cli.sh
bash tests/test_shell_libs.sh
(cd enroll && go test ./...)
shellcheck -S warning portcullis scripts/lib/*.sh tests/*.sh
# compose validity without Docker containers:
PORTCULLIS_ROOT=/tmp/x ./portcullis init --env-only --non-interactive --domain ci.example.org --dns-provider none
```

## Templates CI

### `lint.yml`: every push and PR, forks included

No secrets, no core checkout, read-only token. Safe for fork pull requests, so
every contributor gets this feedback:

- `python tests/validate.py`: the manifest schema plus repo rules (networks,
  volumes, middlewares, required vars, mounts, image pinning, header trust,
  Dependabot coverage, `.core-ref`). See
  [Manifest Reference → Validation](../guides/manifest-reference.md#validation).
- `bash tests/compose-config.sh`: `docker compose config` for every template.
- `shellcheck` of the test scripts and template scripts.
- `actionlint` (pinned image).

### `test-apps.yml`: integration tests

Triggers: push to `main`, pull requests from branches of the repo, and manual
`workflow_dispatch` (inputs `pr`, `ref`, `apps`). It boots core infrastructure
and runs `tests/apps/<app>.sh` for the affected templates. The trust boundary is
per job:

| Job | Secrets | What it does |
|-----|---------|--------------|
| `gate` | Checks availability only | Decides whether the run may proceed. A **fork PR** has no secrets, so the run is skipped with a notice (not a failure). For a manual run with `pr = <n>`, it resolves the PR head commit to test |
| `changes` | none | Verifies the commit under test. Picks the apps: changed `<app>/` directories and changed `tests/apps/<app>.sh`. A change to `tests/lib.sh`, `.github/` or `.core-ref` tests **all** apps. With no usable base, all apps are tested |
| `fetch-core` | `PORTCULLIS_PAT` (the **only** job that references it) | Checks out nothing from the PR except `.core-ref`, read from a trusted commit (for a dispatched PR run: the PR's *base*, so a PR can't point CI at another core ref). Clones core at that ref, resolves the infra image list with `docker compose config --images` against a throwaway `.env` from `portcullis init --env-only` (failing on an empty list), packs core as an artifact, and writes the infra image cache |
| `app-images` (matrix per app, push to `main` only) | none | Never runs for PRs or manual runs. For each tested app whose test boots it, reads the image list from its `compose.yml` (`tests/app-images.sh`), pulls the pinned images and writes that app's image cache (key: hash of the list). Starts no container |
| `test` (matrix per app) | none | Downloads core by artifact ID with digest verification. Writes no cache. Loads the cached infra and app images as **untrusted**: removes every name a tarball sets, then binds each image (core's and the app's) with a `docker pull` of its `tag@sha256` pin. The pull checks the manifest against the pinned digest and reuses a loaded image only if its ID (the hash of its config, which pins every layer) is the one that manifest names; otherwise it downloads the image fresh. Boots infra through the core CLI (`vault init`, `pki setup --with-server-cert`, `keycloak configure`, `oidc register`), checks Traefik got its static IP, and runs the app's test |

Every job has a read-only `contents: read` token. The workflow deliberately does
**not** use `pull_request_target`, which would run fork code with secrets and a
write token.

**Fork PRs.** After reviewing the diff, a maintainer runs **Actions → Test Apps
→ Run workflow** with `pr = <number>`. The run tests exactly the reviewed
commit, and aborts if the PR head moved.

**`.core-ref`** holds the core ref the templates are tested against: a tag such
as `v1.4.0`, or `main` during development (today: `main`). Changing it
re-tests every template.

### `docs-dispatch.yml`

On push to `main` it sends a `templates-updated` `repository_dispatch` to this
docs repo, which regenerates the [App Catalog](../apps/index.md). It needs the
`DOCS_DISPATCH_TOKEN` secret. Without it the step is skipped with a notice, and
the docs pick the change up on their daily rebuild.

### Test helpers (`tests/lib.sh`)

| Area | Functions |
|------|-----------|
| Output | `pass`, `fail`, `info`, `section`, `report` |
| Waiting | `wait_for_url URL TIMEOUT NAME`, `wait_for_container` |
| Keycloak | `keycloak_admin_token`, `keycloak_user_token`, `keycloak_enable_direct_grant`, `keycloak_register_client` |
| LLDAP | `lldap_token`, `lldap_graphql`, `lldap_create_user`, `lldap_create_group`, `lldap_add_to_group`, `lldap_sync_keycloak` |
| Compose | `compose_up APP`, `compose_down APP`, `app_container_ip APP`, `app_logs APP` |
| Assertions | `assert_http_code URL CODE`, `assert_redirect_to_keycloak URL`, `assert_redirect_contains URL STRING`, `assert_body_contains URL STRING`, `assert_container_can_reach CONTAINER URL` |
| Public exceptions | `public_routed_prefixes <manifest> <all\|listed> [token…]` prints what the Hub's public router opens; `write_public_override <app> <service> <host-arg> <tier> <out> <entry…>` writes the override labels the Hub would generate (tier for every router, public router with static-only supporting paths, exact paths, credential exclusions, strip middleware); pass it to `compose_up` with `COMPOSE_OVERRIDE=<file>`. `assert_public_path <host> <path> [curl args]` / `assert_gated_path …` send HTTPS requests through Traefik on the runner (no client certificate) and check the app answers / the request is redirected to `auth.<domain>`. `grafana.sh` uses them: a listed dashboard token is public, an unlisted token, `/`, `/api/user`, `/public/build/` and requests with a (plain or percent-encoded) `grafana_session` cookie stay gated. `nextcloud.sh` and `immich.sh` check their path lists statically |
| Header trust | `assert_traefik_only_trust <compose> <SETTING>` checks statically that the trust setting uses `${PORTCULLIS_TRAEFIK_IP:-…}` and nothing trusts every peer. `assert_spoofed_identity_rejected <url> [expected]` sends a forged `X-Forwarded-User` from the CI host (never Traefik) and expects a rejection. **Required for header-auth templates** |

`compose_up` mirrors the Hub: before each compose call it exports a random
value for every manifest `env:` entry with `generate: random` that isn't set
yet. Templates reference those as `${VAR:?}`, so a missing value fails loudly.

Every template needs a `tests/apps/<app-id>.sh` (`validate.py` checks it). A
static test is the minimum; copy `tests/apps/scrutiny.sh`. What the tests
typically verify:

| Auth method | Checks |
|-------------|--------|
| forward-auth | Unauthenticated request redirects to Keycloak; container healthy; app endpoints respond |
| header-auth | The above, plus the Traefik-only trust setting and a rejected spoofed identity |
| native-oidc | Container reaches Keycloak's discovery endpoint; the app's SSO redirect points at Keycloak; gated login/admin paths redirect |
| public / custom | App responds without authentication; container healthy |

See [Adding an App](../guides/adding-an-app.md#step-6-add-a-test) for a
template.

## Hub CI (`build.yml`)

Triggers: pushes to `main`, tags `v*`, and pull requests. Every action is
pinned by commit SHA.

- **`test`**:
    - `gofmt -l .` must be empty
    - `go vet ./...`
    - `go test -race -count=1 ./...`
    - `go build ./cmd/hub`

    The unit tests cover validation, strict route parsing, the policy-file
    writer (collisions, deny group, snapshots), middleware (proxy secret,
    CSRF), per-app locking, reconcile/drift, and the Engine API client.
    `TestRealTemplates` loads a sibling `portcullis-templates` checkout if
    present.
- **`build`** (after `test`):
    - Multi-arch image (`linux/amd64`, `linux/arm64`) with SBOM and provenance (`mode=max`) attestations.
    - Tags `X.Y.Z`/`X.Y`/`X`/`sha-<short>` for release tags and `edge` for `main`. `latest` is disabled.
    - Pushed to GHCR and **signed with cosign** (keyless, GitHub OIDC) by digest. Pull requests build but don't push or sign.

Verify a published image with the command in
[Hub → Image tags](hub.md#image-tags-and-verification).

## Running workflows locally with act

[act](https://github.com/nektos/act) runs GitHub Actions workflows locally in
Docker:

```bash
act -l -W .github/workflows/test-apps.yml                     # list jobs (templates repo)
act -j lint -W .github/workflows/lint.yml                      # static checks, no secrets
act -W .github/workflows/test-apps.yml -s PORTCULLIS_PAT=<token>
act -W .github/workflows/ci.yml                                # core CI (core repo)
```

The first run downloads the runner images, which can take a few minutes.
