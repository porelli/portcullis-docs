# Testing & CI

Each repository has its own GitHub Actions CI. Core tests the stack itself, the
templates repo tests every template against a pinned core version, and the Hub
tests and signs its image.

| Repo | Workflow | Jobs |
|------|----------|------|
| core (`porelli/portcullis`) | `.github/workflows/ci.yml` | `unit-tests`, `build-and-test`, `e2e` |
| templates (`porelli/portcullis-templates`) | `lint.yml`, `test-apps.yml`, `docs-dispatch.yml` | `lint`; `gate` → `changes` → `fetch-core` → `test`; `dispatch` |
| Hub (`porelli/portcullis-hub`) | `build.yml` | `test`, `build` |
| docs (`porelli/portcullis-docs`) | `deploy.yml` | `deploy` (`zensical build --strict`, publish to `gh-pages`) |

## Core CI

Runs on pushes to `main` and on pull requests. Secrets are not configured in
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
- **CLI.** `./portcullis status` and `./portcullis backup`.

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

On failure, screenshots, HTML, traces and service logs are uploaded as
artifacts. The test needs a live stack and is not collected by pytest.

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
| `fetch-core` | `PORTCULLIS_PAT` (the **only** job that references it) | Checks out nothing from the PR except `.core-ref`, read from a trusted commit (for a dispatched PR run: the PR's *base*, so a PR can't point CI at another core ref). Clones core at that ref, resolves the infra image list with `docker compose config --images` against a throwaway `.env` from `portcullis init --env-only` (failing on an empty list), packs core as an artifact, and is the only job that writes the image cache |
| `test` (matrix per app) | none | Downloads core by artifact ID with digest verification. Loads the cached images and **verifies each one**: the loaded image ID must equal the linux/amd64 config digest the registry reports for the `tag@sha256` pin in core's compose, otherwise it is removed and pulled fresh. Boots infra through the core CLI (`vault init`, `pki setup --with-server-cert`, `keycloak configure`, `oidc register`), checks Traefik got its static IP, and runs the app's test |

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
