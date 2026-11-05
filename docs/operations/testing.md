# Testing & CI

Each repository has its own GitHub Actions CI. Core tests the stack itself, the
templates repo tests every template against a pinned core version, and the Hub
tests and signs its image.

| Repo | Workflow | Jobs |
|------|----------|------|
| core (`porelli/portcullis`) | `.github/workflows/ci.yml`, `release.yml` | `unit-tests`, `build-and-test`, `e2e`, `e2e-instances`, `e2e-settings`, `e2e-folders`, `e2e-filesharing`; release: `preflight` → `ci` (reusable `ci.yml`) → `release` |
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
    - `keycloak configure`'s `portcullis-forward-auth` patch: the main callback plus every `https://<valid hostname>/oauth2/callback` the Hub added (extra-domain hosts), nothing else, idempotent
    - the realm export's invite post-broker flow `portcullis-invite-session`: client-scope check (`portcullis-invite-client`, not negated), deny unless admitted, then LoA 1 (`portcullis-invite-loa-1`) and LoA 2 (`portcullis-invite-loa`), amr `hwk`; the marker scope is no default anywhere in the export
- **`tests/test_group_gate.py`.** group-gate unit tests (run in a venv with `pip install --require-hashes -r group-gate/requirements.txt`):
    - policy file v5: maps keyed by full hostname (exact match after lowercasing and stripping a numeric port and trailing dots; never a subdomain or parent fallback), keys that aren't valid hostnames deny, v4 and older deny, `extra_domains` (malformed or overlapping the main domain's core hosts → deny), hosts outside the main and enrolled domains denied
    - core hosts from the map file (`<sub>` → `<sub>.<domain>`, the apex included), never from the policy file; merging the map file with the Hub's `groups`
    - step-up URLs: `auth.<domain>` for main-domain and core hosts, the host itself with `rd=/` for extra-domain hosts; attribute headers and the public guard on extra-domain hosts; the portal shows only URLs on the main domain and the portal file's `domains`
    - fail-closed policies (version without `version` key → deny) and the reserved deny group
    - `path_groups`, including bypass variants
    - the mTLS binding
    - revocation by serial list and by a real openssl-generated CRL
    - the identity headers and attribute headers returned on allow
    - `expiring` array: membership treated as absent once `now >= at`, token withholding (`Authorization` and `X-Forwarded-Access-Token` withheld when an expired membership is stripped)
- **Compose validity and wiring**, against a generated `.env`. `docker compose config -q` must pass for the core, apps and test compose files. It also checks:
    - `HUB_PROXY_SECRET` is generated, and an empty one is rejected
    - the public default forward-auth secret is gone
    - only the two socket proxies mount `docker.sock`; Traefik and the Hub use their proxies, and each proxy network has exactly its two members
    - the Hub router carries `hub-proxy-secret@docker` with the right secret, and the people router carries the same middleware
    - every core image is pinned by digest, and `enroll/Dockerfile` + `group-gate/Dockerfile` bases too
    - every service has `no-new-privileges`, `cap_drop: ALL` and memory/pid limits
    - Keycloak's `--proxy-trusted-addresses` is Traefik's `portcullis-auth` IP, and only Keycloak and Traefik are on that network
    - `group-gate-map.conf` has `people=*`
    - `forward-auth-ext` mirrors `forward-auth` (image, command, secrets, trusted proxies; `portcullis-auth-ext` has every `portcullis-auth` forwardauth setting), defines no router, uses the relative callback `/oauth2/callback` and the host-only cookie `__Host-portcullis_ext` (`Secure`, `Path=/`, no cookie domain, no whitelist); `oauth2-proxy/alpha.yaml` sends PKCE S256
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
    - `portcullis-forward-auth` requires PKCE S256: an authorization request without a code challenge gets no code, the X.509 login with one does (oauth2-proxy's `alpha.yaml` must keep `code_challenge_method: S256`)
    - the invite post-broker flow admits only clients with the `portcullis-invite-client` scope (only `portcullis-forward-auth`, never a realm default), and a second `keycloak configure` keeps an extra-domain callback on `portcullis-forward-auth` while dropping a wildcard
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
- **Domains service (Pebble e2e).** The image is built with `GO_TAGS=testprovider`
  (adds provider `fake` with records in memory + a DNS server on `:8053`). CI
  runs Pebble (`-dnsserver domains:8053`) and configures the service to use
  `fake`, Pebble's minica root, and `DOMAINS_RESOLVERS=127.0.0.1:8053`. It checks:
    - enrolling a domain, the records check, ACME DNS-01 order, serving the certificate
    - `DELETE` stops serving it
    - the served document contains only `tls.certificates` (no routers, services, middlewares)
    - every served certificate's SANs are exactly `{<d>, *.<d>}` for an enrolled domain
    - Traefik picks up the certificate by SNI within ~25 s without restarting (`StartedAt` unchanged)
    - core hosts still serve the main-domain certificate, never a certificate from the HTTP provider
    - Traefik's API lists no `@http` object (routers, services, middlewares, serverstransports)
    - mTLS refusal: the endpoint refuses requests without the client certificate
    - a kept domain survives backup/restore
  
  **The production image is built without `testprovider`** (no fake provider).

- **Live Keycloak access role test (opt-in).** When `PORTCULLIS_KEYCLOAK_LIVE_URL`
  (e.g. `http://keycloak:8080`) and `PORTCULLIS_KEYCLOAK_LIVE_WIPE=portcullis`
  are set, the Hub runs `TestLiveClientAccess`: it **wipes realm `portcullis`**,
  rebuilds it from the export, creates an LDAP group and a test client with the
  access role enforced, and drives the flow to verify the role is checked and
  fails closed. This is the live proof of contract §8. It requires a running
  Keycloak and is off by default.

- **Hub**
    - runs as non-root
    - talks to Docker only via its proxy
    - answers 403 without the proxy secret
    - on a fresh install publishes the built-in default auth policy `{factors: [mtls, webauthn], op: any}` (either YubiKey method), which group-gate applies (step-up for a session with neither) to an app without its own policy
    - then gets a public default through `PUT /api/settings`, like an admin would; the revocation test checks that precondition, and every hand-written group-gate policy file in CI states its default explicitly
- **Enrollment UI and API.** List users, sign a CSR with the AppRole token, list certs.
- **Passkey-only sign-in and setup links.**
    - the browser flow has no password executor, has the identity-provider redirector, a passkey step and LoA 2 = allow-access; it carries the `[sync <hash>]` marker and a second `keycloak configure` rebuilds nothing
    - the LDAP federation has `cachePolicy` `NO_CACHE` (`tests/test_shell_libs.sh` also checks the realm export and that `keycloak configure`'s patch sets it idempotently)
    - the invite identity provider is enabled, hidden, links existing users only (`idp-detect-existing-broker-user`, `idp-auto-link`), back-channel `http://enroll:8445`, PKCE; the service account `portcullis-enroll` has exactly view-users + manage-users
    - `./portcullis invite`: link format, a new link revokes the older one, viewing doesn't consume it, a cross-site redeem is refused, `portcullis-hub` is refused, `admin` is allowed from the server
    - the Hub's invite API (`enroll:8444`, contract §9.4): 201 for a user, 409 for `admin` / `portcullis-hub`, 404 for an unknown user, 401 with a wrong secret; the Hub's copy of the secret matches; the JWKS serves an ES256 key
- **`./portcullis up` and the Hub's LLDAP account.** `portcullis-hub` is in `lldap_admin`, the 0640 / group 10001 password file logs in, a password changed in LLDAP is reset from the file on the next `up`, and the Hub sees `/run/portcullis/lldap` and `/run/portcullis/invite`.
- **Revocation end to end**, once through `./portcullis cert revoke` and once through Vault's CRL alone.
- **CLI.** `./portcullis status`.
- **Backup round-trip.** It runs, in order:
    - `./portcullis backup` with nothing stopped, then `backup verify --local`. A deliberately damaged backup must fail verification.
    - `status --textfile`.
    - `backup --offsite` twice to a local restic repository. The second run must be incremental, and retention must collapse same-day snapshots under `keep-daily`.
    - `backup verify` (off-host). A wrong `BACKUP_PASSWORD` must fail, and neither the root token nor the `.env` secrets may appear in the encrypted repository.
    - **Restore into a fresh stack.** Containers, volumes, `.env`, `secrets/`, `certs/` and local backups are all deleted, as on a new host. Then `restore --yes --from-offsite` must bring back an active Vault, the Keycloak realm, the forward-auth client and the LLDAP user.

The step "Test the public guard (public exceptions) through Traefik" routes a test host through `portcullis-public-guard@docker` only and checks: no version-3 entry → 403; published prefix / static paths → 200; other paths, encoded `/` or `#`, dot-segment escapes → 403; `Authorization`, `Proxy-Authorization`, a credential header, credential cookies and query keys in PHP-mangled spellings → 403. The guard's unit tests are in `tests/test_group_gate.py` (`PublicGuardTest`, `PhpVarNameTest`).

### `e2e` (browser)

`tests/e2e/e2e_login.py` runs Playwright Chromium (pinned in
`tests/e2e/requirements.txt`) with a CDP virtual WebAuthn authenticator against
the full chain: Traefik → oauth2-proxy → Keycloak (LLDAP users, WebAuthn, X.509)
→ group-gate. A `whoami` test app has three hosts: `app.` (group `users_e2e`,
`/admin` → `admin_e2e`), `hwk.` (WebAuthn policy) and `mtls.` (mTLS policy).

Scenarios:

No user has a password and nothing is pre-assigned in Keycloak: the job
creates one-time setup links with `./portcullis invite <user> --to <landing> --json`
(for `e2e`, `e2e-other`, `e2e-bypass` and the bootstrap `admin`) and the test starts from
them. Any password field fails the test.

1. An unauthenticated request is redirected to a passkey-only Keycloak sign-in page.
2. The setup link → **Register my key** → passkey registration → the webauthn-policy app (`hwk.`), with no second prompt.
3. The setup link works once.
4. The session reaches the app.
5. Apps get the **username** as `X-Forwarded-User`, and spoofed identity headers are dropped.
6. `path_groups`: `/admin` needs `admin_e2e`. `/%61dmin`, `//admin`, `/x/../admin` and `/ADMIN` are denied, while `/administrator` is allowed.
7. A second login in a fresh browser with the same key is one passkey assertion.
8. Group denial for a user not in `users_e2e` (also onboarded by setup link).
9. The bootstrap admin's link lands on the portal (`https://<domain>/`) with the Hub link.
10. An unused setup link, redeemed and then steered to another client's authorize endpoint with `kc_idp_hint=portcullis-invite` (client `e2e-invite-bypass`, created by the job), is denied by the invite post-broker flow: no code for the client, no passkey registered.
11. X.509 login via Keycloak satisfies an mTLS policy.
12. An mTLS session without the cert on the request is refused (mTLS binding).
13. A revoked client cert is rejected.
14. A client cert from a foreign CA is rejected in the TLS handshake.

`tests/e2e/e2e_invite.py <setup-link> <landing-url>` runs the setup-link
checks (registration, no password, `acr`/`amr` = `hwk`, single use, one-touch
second login, the invite identity provider refuses browsers without a link)
against any running install, e.g. a live server with a throwaway user
(`E2E_IGNORE_HTTPS_ERRORS=1` for ACME staging). With
`--reinvite-cmd "<command printing portcullis invite <same user> --json>"` it
also registers a second, new authenticator through a second link and checks
that both keys sign in — or, with `--replaced` (`--replace-keys`), that the
old one no longer does. The `e2e` job runs both variants after the browser
tests (users `e2e-spare`, `e2e-lost`). Dialogs are answered like a user
pressing OK (the default value).

After the browser tests, the job enables the **monitoring profile** and checks:

- all monitoring services become healthy, and every Prometheus target is up
- the Vault health probe and the enroll/forward-auth/LLDAP probes succeed
- group-gate, CRL, backup (textfile), CA-expiry, Traefik and Vault metrics are present
- the alert rules are loaded, and neither `VaultSealedOrDown` nor `CrlStale` is pending or firing
- Grafana at `metrics.<domain>` redirects unauthenticated users to sign in, and rejects a forged identity header that doesn't come from Traefik's IP

On failure, screenshots, HTML, traces and service logs are uploaded as
artifacts. The test needs a live stack and is not collected by pytest.

### `e2e-instances` (app instances, extra domains)

The whole stack plus the Hub, the domains service against Pebble with the fake
DNS provider, and the enrolled domain `team-b.test` (enrolled on the domains
API with the fake provider, which the Hub refuses; the Hub picks it up from the
service's list). The Hub's only template source is the CI template
`tests/e2e/apps/echo` (`traefik/whoami` behind Portcullis sign-in, plus a
`hold` service that ignores SIGTERM so a backup can be made slow), seeded into
`hub_data` as a local source. Through the Hub's API the job creates `echo-a`
and `echo-c` on `team-b.test` and `echo-b` on the main domain (`echo-c` with
policy mtls), checks the published policy file (v5, host keys, groups per
instance, `extra_domains`), the rendered labels (`portcullis-auth-ext` and the
`/oauth2/` router to `forward-auth-ext` on extra-domain hosts only), the
callbacks on `portcullis-forward-auth` and the SNI certificate. Then
`tests/e2e/e2e_instances.py`:

- cross-domain SSO: signed in on the main domain, `echo-a` opens with no
  further WebAuthn assertion, through the host's own callback, PKCE S256 and a
  host-only `__Host-portcullis_ext` cookie; a stale ext cookie signs in again
  without a loop; `echo-c` steps up to mtls exactly once (a returning user's
  passkey session, the client certificate available);
- two instances, two groups: each user reaches only their instance;
- a backup longer than 60 s through `hub.<domain>`: `202`, a concurrent
  request `409`, the op record ends ok (Traefik keeps its default timeouts).

Finally, on the real daemon: backup (the helper image pulled by digest,
helpers removed), the typed-id delete (refusals first, then containers,
volume and routing gone, the backup listed), restore into a new id (file and
volume-root owners and modes kept, the new volume labelled for its project,
the instance enables).

### `e2e-settings` (app settings panel)

The whole stack plus the Hub (built from the same-named Hub branch, like
`e2e-instances`) with one local template source: the templates repo's
`immich`, `grafana`, `nextcloud` and `firefox-sync` (from the same-named
templates branch, else `main`) and two CI fixtures, `tests/e2e/apps/settings-echo`
(`traefik/whoami` with a per-person option delivered as the header
`X-Forwarded-Attr-Tier`) and `settings-file` (per-person options in a data
file `people.json`, restart on membership changes, and a hook that stores
every input it gets). A Traefik alias override puts `auth.<domain>` and the
app hosts on `portcullis-proxy`, so Immich and Nextcloud reach Keycloak as
they would through public DNS. Users are created in LLDAP; groups,
memberships, enables and settings go through the Hub's API, the way an admin
makes them. Then `tests/e2e/e2e_settings.py` runs 19 checks in a real
browser with virtual passkeys:

- **Sign-in:** alice, bob and carol follow their setup links, register a
  passkey and reach the portal.
- **Claims (Immich):** alice (in `office_milan`, row 10 GiB) has
  `quotaSizeInBytes` 10 GiB in `/api/users/me` and in Immich's UI; bob (in
  `admin_immich`, the template's preset row) is an Immich admin with the
  100 GiB default.
- **Headers:** bob is a Grafana org Admin on his first and later requests,
  alice a Viewer; settings-echo receives alice's `gold` and bob's `bronze`
  tier, and never another host's header.
- **Data file:** `people.json` inside the settings-file container lists only
  the people with access.
- **Person-entered values (Firefox Sync):** alice enters her Mozilla account
  uid on `people.<domain>` (200); bob's identical uid is refused with 409
  and the answer doesn't name alice; carol, outside the access group, gets
  404. After the debounce, `allowlist.json` in `firefox-sync-init` lists only
  alice's uid, the init ran once, and on the real Postgres her uid gets a
  tokenserver row while an unlisted one is refused.
- **Membership changes:** one batch through the Hub (alice leaves
  `office_milan` and joins `admin_immich`, bob leaves `admin_grafana`,
  three people join `users_settings-file`). Both removals end the person's
  Keycloak session (the Hub signs removed members out), so alice and bob
  must sign in again, and any other sign-in prompt fails the test. Then:
  alice's next Immich sign-in has the 100 GiB default and admin rights (a
  role changed on an existing account), her tier is `bronze`, bob is a
  Grafana Viewer, `people.json` lists four people, settings-file restarted
  exactly once for the three joins (counted from a live `docker events`
  stream), and the hook got the full state with trigger
  `membership_change`.
- **My apps:** carol's `/api/me/apps` lists only settings-file with her
  values and no other username; `/api/instances/immich/settings` on
  `people.<domain>` is 404.
- **Leave and rejoin:** alice leaves `users_firefox-sync`: the file no
  longer lists her, her tokenserver rows are deleted and nobody can sync
  (an empty allowlist lets nobody in); she rejoins and syncs again.
- **Custom fields with `_`:** a field `cost_center` (LLDAP attribute
  `cost-center`) set on alice shows in the overview, fills a rule group
  `cost_center = "CC-42"`, reaches settings-echo as
  `X-Forwarded-Attr-Cost-Center` and Keycloak's example access token for
  Immich's client as `attr_cost_center`.
- **Hooks (Nextcloud):** the first install applied the default quota through
  the start hook (`occ config:app:get files default_quota` is `10 GB`).

Timing bounds come from the Hub: a membership delivery arrives within one
60 s debounce window plus the evaluator's minute and slack. Secrets reach
the test only through the environment or `curl -H @<(…)`, never on argv.
Failure artifacts hold the settings panels (secrets are write-only), the
policy and attributes files, the data files (never `*.secrets.json`),
container logs, screenshots and traces. The traces start after the
setup-link sign-in; the setup pages' screenshots still show the (consumed)
setup links, and traces carry session cookies of the throwaway stack.

### `e2e-folders` (shared folders and the doctor)

Built like `e2e-settings` (the same-named templates and Hub branches, else
`main`; the Traefik alias override; the Hub's data seeded with one local
source): the templates repo's `jellyfin` (the step fails if it has no
`folder` block) and the CI fixture `tests/e2e/apps/folder-writer` (alpine
as `user: "2001:2001"` with umask `022`, a read-only root filesystem and no
capabilities; its option `shared` has `folder: {access: write, runs_as:
{uid: 2001, gid: 2001}}`; it writes a new file into `/shared` at every start
and has a `lan_only` TCP port `WRITER_PORT`, default 18765). Before the
stack starts, the job installs `acl`, checks that `/srv` is ext4 and takes
ACLs, and builds `/srv/e2e-media`: 6 directories `0750` and 50 files
`0640`, all `1000:1000`.

`tests/e2e/e2e_folders.py` (Python standard library only, no browser) drives
the Hub's admin API, `sudo find` / `getfacl` and docker through 14
scenarios, every count exact:

| Scenario | Checks |
|----------|--------|
| tree | 50 files and 6 directories as built, no ACLs |
| enable | jellyfin and folder-writer enable; the writer can't write yet and created no file |
| check | Check path's summary is exactly `exists · ext4 · ACLs and xattrs supported · 50 files · owners 1000:1000 (all)` |
| create | folder `media` gets gid 60000, not adopted |
| preview | the preview's lines (gid allocated, "50 files and 6 folders change group 1000 → 60000", group 1000 keeps its access through an ACL on 56 entries, both apps stopped for under a minute); nothing changed on disk |
| apply | the operation succeeds: 56 entries, a snapshot, 2 uses added |
| host verify | every entry has gid 60000 and its old owner; directories `2770` with `group:1000:r-x` in the access ACL and a default ACL of `group::rwx`, `mask::rwx`, `other::---` and no entry for group 1000; files `0660` with `group:1000:r--` |
| writer file | the writer's new file is `2001:60000`, mode `660` despite umask `022` |
| jellyfin | its process has gid 60000, lists the library, and can't write (read-only file system) |
| no drift | a disk check newer than the request finds no `folder_owner` finding |
| drift | after a `chgrp 1000` of the writer's file, exactly one `folder_owner` Warning offering `reapply_folder` and `undo_folder` |
| undo | the preview says 56 entries go back, 0 changed since; after the undo every original entry has its exact original owner, group and mode and no ACL, and the folder has nothing left to undo |
| exposure | `WRITER_PORT` on `0.0.0.0` is one `lan_only_exposed` Warning; **Rebind…** to `127.0.0.1` leaves `docker port` showing only `127.0.0.1:18765`, and the finding is gone |
| proxy | the Hub's socket proxy is unchanged from `main`, the Hub has no Docker socket, and no fixer helper container is left |

A scenario that builds on a failed one fails too. On failure the job
uploads `e2e-folders-artifacts`: logs, API answers, the tree and
`getfacl -R`, the Hub's folder data, snapshots and the doctor cache.

### `e2e-filesharing` (file-share passwords, SMB3 hardening, revocation)

`tests/e2e/e2e_filesharing.py` (Playwright, smbclient 4.19.5) provisions a stack with Samba and Time Machine instances, tests per-person credential creation (fresh passkey touch, the password shown once), SMB3 connections with encryption required, revocation latencies (hub-made removal, LLDAP-direct removal, writer demoted to reader), instance and core restores voiding credentials, that no hash appears in any backup or log, and the F58 capability ruling (smbd signals work without `CAP_KILL`). Scenarios:

- Setup: connect_address, ports on 127.0.0.1, size_limit 500GiB / office_milan 10GiB, folder slot via assignment, readers / writers before enable, testparm hardening.
- Sign-in via setup links (alice, bob, carol); fresh auth popup flow (COOP, the authorize parameters, the password once, replay refused).
- SMB3 sessions: Time Machine and Samba list shares, carol writes as `21002:60000`, encryption required, SMB2/NTLMv1/guest/wrong password refused, outside-LAN client refused.
- Revocation: hub-made ≤ 10 s, LLDAP-direct ≤ 75 s, writer demoted ≤ 4 s (session gone, login refused). Measured at 0.8–0.9 s, 3.4–9.1 s, and about 3.6 s (task 18 report).
- Restore: instance restore → credential voided, card says "reset by a restore", re-create works. Core restore → no hash in 45 backup files, `hub_secrets` emptied, credentials voided, uid pool +1000, Samba restarted from Hub.
- No hash visible: `docker inspect`, container logs, `hub_data`, audit, ops, archives, `state.yaml`.

Built like `e2e-settings` (same-named Hub and templates branches, else `main`). Ubuntu 24.04 runners, smbclient pinned at `2:4.19.5+dfsg-4ubuntu9*`. On failure: policy/attributes files, data files, container logs, screenshots, no traces (DOM snapshots would carry the password).

**Cross-repo branches.** `ci.yml` also runs on `workflow_dispatch`. On a
branch whose name exists in porelli/portcullis-hub (not `main`, not a tag),
`.github/actions/hub-image` builds the Hub from that branch instead of pulling
`edge`; the Hub's `build.yml` likewise tests against the same-named branch of
the templates and core repos, else `main`.

### Caching

Core CI caches what it safely can. Caches are written only on pushes to `main`.

- **Infra and monitoring images:** cached by the local composite action `.github/actions/cached-images`.
    - The cache key is a hash of each job's pinned image list. Refs without a digest are refused.
    - After `docker load`, every name set by the tarball is removed. Each ref is then re-pulled by its pinned digest (with retry and backoff), so the engine reuses a loaded image only if its content-addressed ID matches the registry's config digest.
- **enroll and group-gate images:** buildx layer cache (`type=gha`).
- **Go:** module and build cache through `setup-go`, with `go mod verify`.
- **Python:** pip and Playwright browsers, cached on the pinned requirements file (`group-gate/requirements.txt` has `--require-hashes`).

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

Triggers: push to `main`, pull requests to `main` (from forks too: core is
public and no job uses a secret), and manual
`workflow_dispatch` (inputs `pr`, `ref`, `apps`; `apps = all` tests every
template). Dependabot's image bumps are pull requests, so each runs the tests of
the app it touches. It boots core infrastructure and, for the affected
templates, runs `tests/apps/<app>.sh` and then the [sign-in
e2e](#per-app-sign-in-e2e). The trust boundary is
per job:

| Job | Secrets | What it does |
|-----|---------|--------------|
| `gate` | none | Resolves what to test. Fork PRs run like any other PR (core is public; no job uses a secret), with `.core-ref` taken from the PR's base. For a manual run with `pr = <n>`, it resolves the PR head commit to test |
| `changes` | none | Verifies the commit under test. Picks the apps: changed `<app>/` directories and changed `tests/apps/<app>.sh`. A change to `tests/lib.sh`, `tests/app-images.sh`, `tests/e2e/`, `.github/` or `.core-ref` tests **all** apps. With no usable base, all apps are tested |
| `fetch-core` | none | Checks out nothing from the PR except `.core-ref`, read from a trusted commit (for PR runs: the PR's *base*, so a PR can't point CI at another core ref). Clones the public core repo anonymously at that ref, resolves the infra image list with `docker compose config --images` against a throwaway `.env` from `portcullis init --env-only` (failing on an empty list), packs core as an artifact, and writes the infra image cache |
| `app-images` (matrix per app, push to `main` only) | none | Never runs for PRs or manual runs. For each tested app whose test boots it, reads the image list from its `compose.yml` (`tests/app-images.sh`), pulls the pinned images and writes that app's image cache (key: hash of the list). Starts no container |
| `e2e-browser` (push to `main` only) | none | Installs the hash-pinned `tests/e2e/requirements.txt` and that Playwright version's Chromium and writes their cache (key: hash of the requirements). Runs no template code |
| `test` (matrix per app) | none | Downloads core by artifact ID with digest verification. Writes no cache. Loads the cached infra and app images as **untrusted**: removes every name a tarball sets, then binds each image (core's and the app's) with a `docker pull` of its `tag@sha256` pin. The pull checks the manifest against the pinned digest and reuses a loaded image only if its ID (the hash of its config, which pins every layer) is the one that manifest names; otherwise it downloads the image fresh. Boots infra like core's own CI: every secret generated by `portcullis init --env-only` (the workflow sets none, since the shell environment would override `.env`), Keycloak with its production `start` command, setup through the core CLI (`vault init`, `pki setup --with-server-cert`, `config apply --bundle-only`, `keycloak configure`, `oidc register`). Checks Traefik got its static IP and that forward-auth redirects an unauthenticated request to `auth.<domain>`, then runs the app's shell test and its sign-in e2e. Uploads `e2e-<app>` (screenshots, page HTML, traces, logs) on failure |

Every job has a read-only `contents: read` token. The workflow deliberately does
**not** use `pull_request_target`, which would run fork code with a write token.

**Fork PRs** get the full integration tests automatically. A maintainer can re-run one with **Actions → Test Apps → Run workflow**, `pr = <number>`. That run tests exactly the PR's head commit, and aborts if the head moved.

**`.core-ref`** holds the core ref the templates are tested against: a tag such
as `v1.4.0`, or `main` during development (today: `main`). Changing it
re-tests every template.

### Per-app sign-in e2e

`tests/e2e/app_signin.py` (Playwright with a CDP virtual WebAuthn
authenticator, like core's [`e2e` job](#e2e-browser)) proves a real person can
sign in to each app through Portcullis and gets the right role. Driven by the
manifest's [`tests.signin`](../guides/manifest-reference.md#testssignin), per app:

1. LLDAP users without passwords: `e2eadmin` (access + admin group),
   `e2emember` (access group), `e2eoutsider` (no group);
2. what the Hub would do: the template's Keycloak clients (secret = the app's
   generated env, which the workflow creates once for the shell test and the
   e2e), the group-gate policy file (`access_group` per host,
   `auth.admin_paths`; its version is read from core's group-gate);
3. the app started with `tests/lib.sh compose_up`, containers ready;
4. per user, `portcullis invite <user> --to https://<host><path> --json` opened
   in Chromium: passkey registration, then the app's own sign-in (its SSO
   button, the OIDC / SAML round trip, or forward-auth);
5. results: `member` signed in with its username and not admin, `admin` has
   admin rights, `outsider` refused (group-gate's 403 or the app's denial);
   any password field fails unless the manifest documents it; an outsider
   refusal when nobody could sign in is reported `inconclusive`.

`expected_fail` marks known failures: reported, not fatal, only when the
failure matches the entry's `match` (and not its `not_match`) in that check's
own evidence: its detail, the pages its flow saw, the app's logs since its
flow started. A flow the test broke (password field, Keycloak/enroll or browser
error, never on the app) or an exception fails, and a marked check that passes
fails the run so the marker is removed. Where group-gate decides (forward-auth,
header-auth, and the login-path gates of GitLab, LiteLLM and Vaultwarden) only
group-gate's own refusal counts for the outsider: its HTTP 403, its "not
authorized" page and its `DENIED user=… host=…` log line. Each setup link must
register exactly one passkey. Today: the outsider check of
the native-OIDC apps with no group restriction of their own that let every
test user in (Headscale/Headplane, Immich): with the Hub, its Keycloak access
role (`keycloak_access_role`) refuses outsiders at Keycloak, but CI has no Hub
(the test registers plain clients), so the role is not applied there; the
member check of the apps that admit only their first user (the
owner) and users the owner adds or approves (Actual Budget, NetBird); the
member and admin checks of Nextcloud, whose HTTP client refuses a local TLD
(`.local`) or private address for Keycloak (match: "violates local access
rules"; its outsider check is then `inconclusive`) — the
test never widens an app's access to make a check pass. `skip`: docs
(public), Plex (custom, plex.tv). Each run starts the app
from fresh volumes.

CI stand-ins for public DNS: every app hostname is a network alias of Traefik
on `portcullis-proxy` (apps reach `auth.<domain>` for OIDC discovery and the
token exchange) and is in the runner's `/etc/hosts` (the browser). Chromium
trusts core's root CA through an NSS database. Results go to the job summary;
on failure the `e2e-<app>` artifact holds every step's screenshot and HTML, a
Playwright trace per user (`playwright show-trace`), the app's container logs
and core's logs.

### `docs-dispatch.yml`

On push to `main` it sends a `templates-updated` `repository_dispatch` to this
docs repo, which regenerates the [App Catalog](../apps/index.md). It needs the
`DOCS_DISPATCH_TOKEN` secret. Without it the step is skipped with a notice, and
the docs pick the change up on their daily rebuild.

### `craft-releases.yml`

Weekly (and on dispatch), `tests/craft-releases.sh` bumps each Craft
template's pinned web release (`${CRAFT_VERSION:-…}` / `${CRAFT_SHA256:-…}`)
to the latest release of `storytold/<app>`, once the GitHub asset digest,
`SHA256SUMS.txt` and the download agree, and opens one PR per app on
`craft/<app>-<ver>`. It uses only `GITHUB_TOKEN` (`contents`, `pull-requests`,
`actions: write`). PRs opened with that token start no `pull_request`
workflows, so the script dispatches **Test Apps** (`pr=<n>`, `apps=<app>`,
core ref from the PR's base) and **Lint** (on the branch) for each PR it
opens; `workflow_dispatch` is the one event `GITHUB_TOKEN` may start. The
Test Apps run is dispatched on the base branch, so its check attaches to the
base commit, not the PR: the script links the run in the PR body.

### Test helpers (`tests/lib.sh`)

| Area | Functions |
|------|-----------|
| Output | `pass`, `fail`, `info`, `section`, `report` |
| Waiting | `wait_for_url URL TIMEOUT NAME`, `wait_for_container` |
| Keycloak | `keycloak_admin_token`, `keycloak_user_token`, `keycloak_enable_direct_grant`, `keycloak_register_client` |
| LLDAP | `lldap_token`, `lldap_graphql`, `lldap_create_user`, `lldap_create_group`, `lldap_add_to_group`, `lldap_sync_keycloak` |
| Compose | `compose_up APP`, `compose_down APP`, `app_container_ip APP`, `app_logs APP` |
| Assertions | `assert_http_code URL CODE`, `assert_redirect_to_keycloak URL`, `assert_redirect_contains URL STRING`, `assert_body_contains URL STRING`, `assert_container_can_reach CONTAINER URL` |
| Public exceptions | `public_routed_prefixes <manifest> <all\|listed> [token…]` prints what the Hub's public router opens; `write_public_override <app> <service> <host-arg> <tier> <out> <entry…>` writes the override labels the Hub would generate (tier for every router, public router behind `portcullis-public-guard@docker` with static-only supporting paths, exact paths, strip middleware); pass it to `compose_up` with `COMPOSE_OVERRIDE=<file>`. `write_public_policy <sub> <manifest> <mode>` writes the version-3 policy entry the Hub would publish into core's `hub_data` volume, so core's real public guard runs (`clear_public_policy` empties it). `assert_public_path <host> <path> [curl args]` / `assert_gated_path …` / `assert_public_refused …` send HTTPS requests through Traefik on the runner (no client certificate) and check the app answers / the request is redirected to `auth.<domain>` / the guard answers 403. `grafana.sh` uses them: a listed dashboard token is public; an unlisted token, `/`, `/api/user` and `/public/build/` stay gated; Grafana login cookies (also PHP-mangled spellings), `Authorization`, `X-Access-Token` and `auth_token` query variants are refused by the guard. It needs a core with `/public-guard` (`.core-ref`). `nextcloud.sh` and `immich.sh` check their path lists statically |
| Settings data files | `write_appfiles_override <app> <name> <json> <out>` writes `<name>.json` the way the Hub does (a directory per file, mode 0640 group 10001 where the runner can set it) and an override that bind-mounts that directory read-only at the `files[]` entry's mount; pass it with `COMPOSE_OVERRIDE=<file>`. `write_appfile <app> <name> <json>` rewrites the file atomically (restart the service after). `firefox-sync.sh` uses them to check that only the file's uids can sync and that a bad or missing file stops the instance. The public-exception override also strips the template's header deliveries, as the Hub's public router does |
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
    - `go test -race -count=1 ./...` (after installing `acl`, so the ACL
      codec is checked against the kernel's `setfacl` bytes)
    - **folderfix root tests:** `sudo go test -tags fixerroot
      ./internal/folderfix/` runs the shared-folder fixer as root on real
      files: ACLs, setgid, `must_own`, hard links, setid files, file
      capabilities, other mounts, devices, unreadable entries, apply,
      snapshot, restore and its dry run. Under CI these tests fail instead
      of skipping when root, ACLs, `getfacl` or `mount` are missing.
    - **fixer helper docker tests:** `go test -tags docker -run TestDocker
      ./internal/hub/` with a required Docker daemon builds a Hub-shaped
      image and runs the real fixer helper: scan, snapshot, apply, verify
      and restore on a real volume; its capabilities, no-new-privileges,
      uid, network, read-only root filesystem and process limit from inside;
      every capability dropped in turn (each mode needs exactly its set);
      and the Hub finding its own container ID from its mountinfo.
    - `go build ./cmd/hub`

    The unit tests cover validation, strict route parsing, the policy-file
    writer (collisions, deny group, snapshots, `expiring` array, `user-attributes.json`), middleware (proxy secret, CSRF), per-app locking, reconcile/drift, the Engine API client, the LLDAP client (GraphQL + LDAP Password Modify), the Keycloak client (attribute mappers), the rule parser, and the directory service (users, groups, fields, rule evaluator, exceptions, expiries, CSV import, delegated permissions, protected accounts parity).
    New packages: `internal/rules` (rule parser and evaluator), `internal/directory` (users, groups, fields, permissions, import, audit).
    `TestRealTemplates` loads a sibling `portcullis-templates` checkout if present.
    `TestPeopleListenerHasNoAppRoutes` checks that the people listener registers exactly the directory routes plus the five caller-only My apps routes (`GET /api/me/apps`, `PUT` and `DELETE /api/me/apps/{instance}/values/{key}`, `POST` and `DELETE /api/me/apps/{instance}/credentials/{key}`), and no app/policy/drift/compose/settings/Docker routes.
    The settings code is tested per package: the template settings validator, the setting types (parsing, rendering, resolution), the delivery engine (data files, claims, headers, hooks, reload, debounce, stale runs), person-entered values (uniqueness, population, purges, the refused-save limit) and the settings API (admins only, secrets never returned).
    A build-tagged harness (`go test -tags harness -run TestHarness -timeout 0 ./internal/httpapi`) serves the UI on `127.0.0.1:18888` (and the people page on `:18889`) against in-memory fakes, for checking the panels in a browser.
    `TestProtectedAccountsParity` reflects over `directory.Service` methods to check every user-targeting operation refuses `admin` and `portcullis-hub`.
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
act -W .github/workflows/test-apps.yml                         # integration (no secrets needed)
act -W .github/workflows/ci.yml                                # core CI (core repo)
```

The first run downloads the runner images, which can take a few minutes.
