# Testing & CI

Each repository has its own GitHub Actions CI. Core tests the stack itself, the
templates repo tests every template against a pinned core version, and the Hub
tests and signs its image.

| Repo | Workflow | Jobs |
|------|----------|------|
| core (`porelli/portcullis`) | `.github/workflows/ci.yml`, `release.yml` | `unit-tests`, `build-and-test`, `e2e`, `e2e-instances`, `e2e-signin`, `e2e-settings`, `e2e-folders`, `e2e-filesharing`, `e2e-mail`, `e2e-ai`, `e2e-podman`, `e2e-vpn`, `e2e-k3s`, `e2e-servers`, `e2e-servers-podman`, `e2e-ssh`; release: `preflight` → `ci` (reusable `ci.yml`) → `release` |
| templates (`porelli/portcullis-templates`) | `lint.yml`, `test-apps.yml`, `docs-dispatch.yml` | `lint`; `gate` → `changes` → `fetch-core` (+ `app-images` on push to `main`) → `test`; `dispatch` |
| Hub (`porelli/portcullis-hub`) | `build.yml` | `test`, `build` |
| Keycloak image (`porelli/portcullis-keycloak`) | `build.yml` | `test`, `vectors`, `smoke`, `publish` |
| docs (`porelli/portcullis-docs`) | `deploy.yml` | `deploy` (`scripts/check-branding.sh`, `zensical build --strict`, publish to `gh-pages`) |

## Core CI

Runs on pushes to `main`, on pull requests, and as a reusable workflow (`workflow_call`) from `release.yml`. Secrets are not configured in
the workflow: `./portcullis init --env-only` generates them into `.env`,
exactly as on a real install. Every step drives the stack through
`./portcullis`.

### `unit-tests` (no containers)

- **shellcheck** of `portcullis`, `scripts/lib/*.sh`, `tests/*.sh` and `vault/entrypoint.sh`.
- **ci.yml size.** `tests/lint_ci_size.sh` keeps `ci.yml` under 450,000 bytes (GitHub refuses a workflow over 500 KB with a startup failure and no jobs); long step scripts live in `.github/ci/*.sh`, which shellcheck and the image greps cover too.
- **CLI help.** Every command listed by `./portcullis help` must print a `Usage: portcullis <cmd>` line for `--help`.
- **`tests/test_cli.sh`.** Argument parsing, dispatch and `init --env-only`, with a stub `docker`. Also:
    - `init --env-only` generates `FORWARD_AUTH_REDIS_PASSWORD` and `FORWARD_AUTH_EXT_REDIS_PASSWORD` (40 `[A-Za-z0-9]`, different), both core secrets (never shared with the Hub) and rotatable (`upgrade` generates them); `init`, `up` and `upgrade` run the session store's restart check before `docker compose up`
    - `keycloak configure` against a stub admin API: the realm PUT carries brute force and an empty `acr.loa.map`, the forward-auth client loses `default.acr.values`, the two-factor `webauthn-register` is disabled, the AMR check walks `portcullis-universal`, the X.509 settings go onto the `portcullis-x509` execution; it never writes the Hub's AI clients or `mcp:*` scopes
    - the realm export's sign-in flows (contract §8.1): `portcullis-universal` = REQUIRED `portcullis-authenticate` + REQUIRED `portcullis-template`, `portcullis-signin` (x509 · passkey sub-flow · password form), one conditional sub-flow per passkey kind with its `kind` and `method` configs, no `conditional-level-of-authentication` anywhere, `acr.loa.map` `{}`, every reference config `maxAge` 36000, the invite configs `inv`, brute force, the passwordless policy, every config used once
    - `docker-compose.yml`: the keycloak image is `${KEYCLOAK_IMAGE:-ghcr.io/porelli/portcullis-keycloak:edge}` and it mounts `hub_data:/hub-data:ro`; the theme's `webauthn-register.ftl` passes `portcullisHints` and `webauthnRegister.js` asks for direct attestation and sets `hints`
    - `version` shows the Keycloak image and honours `KEYCLOAK_IMAGE`
    - static TLS options (contract §5 "TLS tier per host"): `MTLS_ENABLED` appears nowhere in `portcullis`, `scripts/lib`, `docker-compose.yml` or `.env.example`; tracked `traefik/dynamic/tls.yml` defines exactly `protected` (`RequireAndVerifyClientCert`, `caFiles` exactly `/certs/ca-chain-yubikey.crt`), `protected-any` (`RequireAndVerifyClientCert`, `caFiles` exactly `/certs/ca-chain.crt`), `authaware` (`VerifyClientCertIfGiven`, `/certs/ca-chain.crt`) and `public` (no `clientAuth`), each `VersionTLS12`, `sniStrict: false`; `config apply` leaves it byte-identical and writes nothing else under `traefik/`; every core router in `docker-compose.yml` uses `authaware@file`; the Hub mounts the checkout read-only, no writable mount of the hub service (short or long syntax: bind, volume, tmpfs) has `traefik` in its source or target, the writable ones are exactly `./templates`, `./appfiles`, the two masking tmpfs, `hub_data` and `hub_secrets`, and the check itself catches a planted short- and long-syntax rw bind of `./traefik`
    - enroll's Vault policy `vault/policies/enroll.hcl` grants exactly the contract §8.1 paths (sign with `client-cert` / `browser-cert`, list and read certificates, revoke and rotate the CRL, on `pki_int` and `pki_file`) and nothing else; its SSH part is exactly contract §18.7's (role TTLs exactly the twelve whole hours up to 12 h)
    - `ssh_setup` (stub vault): a fresh Vault gets both mounts, caps, CAs and the host role; a second run creates nothing; another cap, CA key type or engine at `ssh_user` / `ssh_host` fails naming it and changes nothing
    - `cert list --all` (stub `vault`) shows KIND `YubiKey` / `Browser` and revoked rows; `cert revoke` finds a `pki_file` serial after `pki_int`, revokes it there and rotates `pki_file`'s CRL; `cert enroll`'s renewal hint names `https://people.<domain>/signin`
    - `signin reset-core` (stubbed `docker compose`): without `--yes` and a terminal it refuses (exit 2, nothing run); `--yes` runs `stop hub`, `run --rm --no-deps -T --user 10001:10001 --label traefik.enable=false --entrypoint /usr/local/bin/hub hub signin reset-core`, `start hub` and shows the Hub's output; a failed run still starts the Hub and exits 1 with the exit status, the Hub's own message and "the Hub was started again" (never "nothing was reset"); a failed stop starts the Hub again and runs nothing; a failed start says so
    - the runtime: every `--help` works with no engine (a stub that fails any call is never called), `init --help` documents `--runtime`, no `ct_own "$(id -u)…"` is left in the CLI, and the engine-socket mount string appears exactly twice in `docker-compose.yml`
- **`tests/test_shell_libs.sh`.** Shell-library tests against stub `docker`/`podman`/`vault`:
    - the runtime ([Rootless Podman](rootless-podman.md)): detection (Docker without a Podman component, both present, `--runtime podman`, Podman as root refused, nothing answering), a missing `CONTAINER_RUNTIME` refused naming the variable, a contradicting engine refused, the Podman socket path (falling back to `/run/user/<uid>` without `XDG_RUNTIME_DIR`), the SELinux overlay kept beside `docker-compose.override.yml`, the id-map and host checks, local images built with `podman build` and `up --no-build`, init never switching the runtime, restore keeping the host's runtime keys, the ownership helpers (container 0 is the operator, host ids through the map, unmapped owners), restic as `0:0` with no capabilities, and the backup timer as user units
    - `.env` handling and secret generation
    - network validation
    - `cert sync`, which writes the union of both CAs' revoked serials and must never empty or change the list when either list fails
    - `pki setup` idempotency, including resuming a partial run: a fresh Vault gets `pki`, `pki_int` and `pki_file`; an install with `pki_int` only gets `pki_file` and both chain files and the truststore rewritten with `PKI_TRUSTSTORE_CHANGED=true`; a stale or missing `ca-chain-yubikey.crt` is rewritten (it holds `pki_int` alone); the handshake rule with Go's semantics (`openssl verify -partial_chain`, the client's chain untrusted): `ca-chain-yubikey.crt` refuses a browser leaf sending `pki_file` + root and accepts a YubiKey leaf, `ca-chain.crt` accepts both, and a root added to the YubiKey file is caught; `pki_files_reload` restarts Traefik, Keycloak and group-gate whenever the CA files differ from `certs/.pki-files.loaded`, writing it only after a successful restart; nothing changes (flag unset) when everything is current; equal intermediate CNs are refused; the `browser-cert` role and `pki_file`'s CRL settings
    - `invite --replace-keys` deletes every passkey kind (`webauthn`, `webauthn-passwordless`, `portcullis-device-passkey`, `portcullis-security-key`), never a password or OTP credential, then signs the person out
    - `keycloak configure` re-reads the passkey policy after its PUT and fails when it still differs; `status` fails on a drifted passkey policy (a ✗ line, `--json` `keycloak.passkey_policy`, the textfile gauge)
    - `keycloak configure` ensures the impersonation mapper on `acr` (once, by `protocolMapper`) and enables the `portcullis-impersonation-notice` required action, failing when the realm lacks it
    - `keycloak configure`'s `portcullis-forward-auth` patch: the main callback plus every `https://<valid hostname>/oauth2/callback` the Hub added (extra-domain hosts), nothing else, idempotent
    - the realm export's invite post-broker flow `portcullis-invite-session`: client-scope check (`portcullis-invite-client`, not negated), deny unless admitted, then amr `inv` (10 h) and `portcullis-template`; the marker scope is no default anywhere in the export
    - `dns plan / setup / check` (stub `docker`): the tool's stdin JSON maps each provider's `.env` variables to its credential keys and never puts a value on a command line; a missing credential fails naming the variable (never its value) before the tool starts, while `dns check` works without credentials; plan / confirm / `--yes` (required without a terminal), `--only`, `DNS_NOMAIL`, `DNS_CAA=yes` refused; a `--check` option on `dns setup` is a usage error pointing to `dns check`; the Traefik account URI read from an `acme.json` fixture (`dns setup` keeps Traefik's pin; an unreadable account leaves the live CAA alone); `config apply` on an `ACME_STAGING` flip relaxes the CAA **before** clearing `acme.json`, and refuses mixed Hetzner credentials; `up` writes `main-domain.env` (0600) and tightens the pin; `status`'s DNS block, its `--json` `dns` and the two textfile metrics, the lost-account Problem
    - backups' `MANIFEST.json` names the Hub and Keycloak images; `upgrade` warns about a pinned `HUB_IMAGE` or `KEYCLOAK_IMAGE`
    - `config_apply` with `ACME_STAGING=true` writes the staging `ACME_CA_SERVER` and touches no file under `traefik/`
    - the session store's config (`sessions_prepare`): `secrets/sessions` 0700, `valkey.conf` 0640 group 1000 through the helper; exactly three users — `default` off with no password, keys, channels or commands, `forward-auth` on `~_oauth2_proxy-*` and `forward-auth-ext` on `~__Host-portcullis_ext-*`, each `-@all` plus exactly `ping get set del evalsha eval msetnx mset getrange pexpire mget` and its password's SHA-256 —; no broad or dangerous grant, no cleartext password, nothing printed; no persistence, `maxmemory 64mb` `volatile-ttl`; an unchanged config is not rewritten, a rotated password rewrites it in place (same inode) and flags it; a missing password fails; `sessions_restart_if_changed` restarts only a running store and only when it changed; `secrets_fix_perms` repairs the modes; the compose `user` matches `CT_UID_SESSIONS:CT_GID_SESSIONS`
- **`tests/test_group_gate.py`.** group-gate unit tests (run in a venv with `pip install --require-hashes -r group-gate/requirements.txt`):
    - policy file v6 (contract §4): only version 6 (v5 and older, a float or string `6`, no `version`, a missing file → deny), every v6 key required (`methods` … `add_stronger`) and no unknown key, maps keyed by full hostname (exact match after lowercasing and stripping a numeric port and trailing dots; never a subdomain or parent fallback), keys that aren't valid hostnames deny, `extra_domains` (malformed or overlapping the main domain's core hosts → deny), hosts outside the main and added domains denied
    - compiled rules: an unknown leaf (`webauthn`, a family, `inv`, an amr value), a leaf that isn't switched on, an unknown `op`, 0 or > 8 items, > 4 levels, > 48 leaves, a template id, `default`, `hosts` or `core` reference that isn't published, `core` keys that aren't gated core hosts, bad `people` / `add_stronger` → deny (`policy_error`)
    - the shared rule vectors `tests/signin_vectors.json` (a byte copy of the Hub's `internal/signin/testdata/vectors.json`): every evaluated case's `satisfied` and `alternatives` (set of sets, each listed once), every `reject` case refused
    - session methods: amr through the method table, a switched-off method's amr ignored, `inv` meets nothing, a certificate method only with a bound certificate of its own kind on the request; `people` / `add_stronger` never change a decision
    - certificate binding by issuer (contract §4): `test_browser_leaf_never_binds_yubikey` (amr `mtls`, a leaf issued by the browser CA with the user's CN → no `yubikey_cert`), `test_yubikey_leaf_binds_only_yubikey`, `test_browser_cert_binds_with_file` (and nothing while `browser_cert` is off), `test_equal_or_missing_ca_files_count_nothing`
    - revocation of both kinds: `test_revoked_browser_cert_denied_by_pki_file_crl` (a serial only in the `pki_file` delta CRL → 403 on any host), `test_crl_lists_union` (both full and both delta CRLs and the serial file)
    - the opened log: `test_opened_log_first_request_per_session_host` (one line per session and host, the exact fields, `act` `""`, `ua` ≤ 256, file mode 0640; an unwritable directory still allows the request and counts `group_gate_opened_log_failures_total`)
    - the host's template: `core` for core hosts (missing → deny; `hosts` entries ignored), the Hub's core template for `auth.<domain>` (missing → deny), the portal checks its own; `enroll` is reserved but not gated (`test_enroll_not_gated_but_reserved`); the Sign-in paths on people.&lt;domain&gt; take any switched-on method only for exactly `/signin`, `/api/me/signin`, `/api/me/signin/…` and `/static/…` after normalising (`test_signin_paths_exact_after_normalising`: `/signin/../api/directory`, `/static/../api/directory`, `/api/me/signinx`, `/api/me/signin%2F..%2Fapps`, `/Signin` and the same paths on `hub.<d>` or an app host get the host's template; `test_signin_paths_any_switched_on_method`); the membership checks first (a non-member with an unmet template gets the plain group 403, no page or `X-Stepup-URL`); the request metric's `result` `stepup` / `needs_stronger` / `present_certificate`
    - the pages: present-certificate for both kinds (no `X-Stepup-URL`; `test_step_up_never_asks_held_cert_method`), the step-up candidate rules (`pc_method` = the first set-up candidate, `passkey` for an unknown person with two or more passkey kinds, never a certificate method whose amr the session holds), links to the Sign-in page (`test_pages_link_to_signin_page`: every "Set up …" and "Sign-in methods" href is `https://people.<d>/signin`; `test_no_enroll_links`: no `enroll.` and no `/self` on the portal), the needs-stronger copy word for word as the Keycloak extension's (`portcullis-needs-stronger.ftl`), every value escaped, no refresh, CSP
    - `oauth2-proxy/alpha.yaml`: `loginURLParameters` are exactly `pc_method` (the seven method ids and `passkey`), `kc_idp_hint`, `prompt`; no `acr_values`
    - step-up URLs (`/oauth2/start?pc_method=<method>`): `auth.<domain>` for main-domain and core hosts, the host itself with `rd=/` for extra-domain hosts; attribute headers and the public guard on extra-domain hosts; the portal shows only URLs on the main domain and the portal file's `domains`
    - the step-up returns to the requested page (contract §5 "Step-up URL"): `test_stepup_returns_to_page` (`rd` = `https://<host><path>?<query>`, or `<path>?<query>` on an extra domain, for a `GET`), and `test_stepup_return_rejects_offhost_paths` (`rd` stays the root for a non-`GET`, `//…`, `/\…`, `%5C`, a byte outside `0x21–0x7e` such as a tab or newline, or more than 2048 bytes)
    - the reserved deny group
    - impersonation: `test_imp_claims_parse`, `test_imp_malformed_claims_denied`, `test_imp_live_allows_with_headers`, `test_imp_ended_denied_at_once`, `test_imp_stale_file_denies`, `test_imp_cert_binds_admin_only`, `test_imp_never_steps_up`, `test_imp_signin_paths`, `test_imp_opened_log_act`, `test_client_sent_imp_headers_ignored`, `test_banner_names_validated`
    - `path_groups`, including bypass variants
    - the certificate binding (by issuer, both kinds)
    - revocation by serial list and by a real openssl-generated CRL
    - the identity headers and attribute headers returned on allow
    - `expiring` array: membership treated as absent once `now >= at`, token withholding (`Authorization` and `X-Forwarded-Access-Token` withheld when an expired membership is stripped)
    - branding (`BrandingTest`): the inline mark and `data:` favicon match the pinned sha256 of `concept-1-mark-dark.svg` and `favicon.svg`; every group-gate page (portal, step-up, present-certificate, needs-stronger in both forms, ended, deny) carries both; `PORTAL_CSP` and `SIGNIN_CSP` allow `img-src data:`; no page loads anything external
- **`tests/test_branding.py`** (step "branding copies"): the Keycloak login theme's favicon and mark are byte copies of the branding source (the pinned sha256 of `favicon.ico` and `concept-1-mark-dark.svg`), `theme.properties` loads `css/portcullis.css` after `css/styles.css`, and that stylesheet puts `../img/portcullis-mark.svg` in `#kc-header-wrapper::before`.
- **`tests/test_e2e_fsops.py`** (step "e2e helper unit tests"). It runs with the same venv's interpreter, and needs nothing but the standard library. It tests `run_op` from `tests/e2e/e2e_fsops.py`, the module `e2e_filesharing.py` takes it from, against a fake Hub API. No stack, network or Playwright is involved:
    - a busy `409` whose record is the Hub's own running `restart` is waited for, polled by that restart's `op_id`. If the restart ends ok, the operation is sent exactly once more; if it ends failed, the test fails with its record.
    - any other `409` fails at once: another op, a restart that is no longer running, plain text, or a second `409` after the resend.
    - a `202` whose `poll` isn't the op's own `?op_id=` record fails, and so does a poll that answers another op.
    - every failure message is scrubbed: a password or NT hash in a record never reaches the output.

- **`tests/test_e2e_mailcheck.py`** (step "e2e helper unit tests (e2e_mailcheck)"). Same venv, standard library only. It tests the pure helpers `e2e_mail.py` takes from `tests/e2e/e2e_mailcheck.py`:
    - `network_retries`: a browser step is retried only after Chromium aborted it on a network change on the runner (`net::ERR_NETWORK_CHANGED`, raised by `page.goto` itself or left as a `chrome-error://` page). It makes at most 4 attempts, notes each retry and waits between them. Any other failure is raised at once.
    - `switch_voided_problem`: after a provider switch, every row is `voided` with exactly "the mail server changed on <date>: create a new mail password" for an allowed date, and every required label is there. `active`, `provider_changed` as a status, another reason, another date or a missing row is named.
    - `navigate`: `page.goto` / `page.reload` through `network_retries` (checked with a fake page: a raised abort, a `chrome-error://` page, the reload, the bound, another error not retried).
    - `mail_status_view` / `sync_problem`: `./portcullis mail status --json` is read at exit 0 and 1 (1 only says a check is a Problem); exit 2, no JSON, or a document whose `problem` disagrees with the exit is a failed read. The sync has converged when the provider is wired, reachable, owes no void, isn't held, and has applied the Hub's generation.
    - `confirm_phrase` / `pending_uuids`: the phrase the Hub's `400` asks to be typed (also inside a JSON error body), and the pending removal's uuids. A missing, confirmed, empty or blank-uuid pending removal fails.

    The Python unit tests are plain `unittest` scripts, run one by one; CI has no pytest. Locally, `python3 -m pytest -q tests/` collects the same files.

- **Shared sign-in vectors match the Hub.** `tests/signin_vectors.json` must equal, byte for byte, the Hub's `internal/signin/testdata/vectors.json` on the same-named porelli/portcullis-hub branch when it exists (exactly `refs/heads/<branch>`), else `main`, fetched at the commit `git ls-remote` listed (like portcullis-keycloak's `vectors` job); a failed branch lookup fails the step.
- **Compose validity and wiring**, against a generated `.env`. `docker compose config -q` must pass for the core, apps and test compose files. It also checks:
    - `HUB_PROXY_SECRET` is generated, and an empty one is rejected
    - the public default forward-auth secret is gone
    - only the two socket proxies mount the engine socket, as exactly `${PORTCULLIS_ENGINE_SOCKET:-/var/run/docker.sock}:/var/run/docker.sock:ro` (checked on the default config and on a Podman config with a rootless `PORTCULLIS_ENGINE_SOCKET`); Traefik and the Hub use their proxies, and each proxy network has exactly its two members
    - the Hub's `HUB_CONTAINER_RUNTIME` equals the runtime given, and `docker compose config` fails with `CONTAINER_RUNTIME` empty
    - the SELinux overlay `docker-compose.podman-selinux.yml`: merged, every project bind has the narrowest label (`Z` for exclusive use, `z` only when shared), the Hub's `/project` is a tmpfs, nothing labels the checkout or `secrets/` or `backups/` or `.env`, the engine-socket bind has no label; without it, no bind has a `selinux` option; it names no service the base lacks; `label=disable` sits on exactly the two proxies, each keeping `no-new-privileges:true`; the hardening baseline below also holds on the merged config
    - no core service adds `NET_ADMIN` or `SYS_ADMIN`
    - the Hub router carries `hub-proxy-secret@docker` with the right secret, and the people router carries the same middleware
    - token headers: `portcullis-auth` and `portcullis-auth-ext` list `X-Forwarded-Access-Token` and `Authorization` in `authResponseHeaders` (Traefik deletes a client's copies; group-gate reads amr only from that token); `portcullis-auth-console` lists the access token but not `Authorization` (the Keycloak console keeps its own bearer)
    - every core image is pinned by digest, and `enroll/Dockerfile` + `group-gate/Dockerfile` bases too
    - every service has `no-new-privileges`, `cap_drop: ALL` and memory/pid limits
    - Keycloak's `--proxy-trusted-addresses` is Traefik's `portcullis-auth` IP, and only Keycloak and Traefik are on that network
    - Keycloak's image is `ghcr.io/porelli/portcullis-keycloak:…` and its only named volume is `hub_data:/hub-data` read-only; `hub_data` is mounted by exactly the Hub, group-gate, mcp-gate and Keycloak
    - `group-gate-map.conf` has `people=*`
    - `forward-auth-ext` mirrors `forward-auth` (image, command, secrets, trusted proxies; `portcullis-auth-ext` has every `portcullis-auth` forwardauth setting), defines no router, uses the relative callback `/oauth2/callback` and the host-only cookie `__Host-portcullis_ext` (`Secure`, `Path=/`, no cookie domain, no whitelist); `oauth2-proxy/alpha.yaml` sends PKCE S256
    - the session store: `sessions` is `valkey/valkey` pinned, `999:1000`, read-only with a tmpfs `/data`, no ports, environment or routers, mounts only `secrets/sessions/valkey.conf` read-only (and nobody else mounts `secrets/sessions/`), has the `NOAUTH` healthcheck and only the network `portcullis-sessions`, which is internal with exactly `sessions`, `forward-auth` and `forward-auth-ext` (like `portcullis-mcp`'s members); both oauth2-proxies use the `redis` store at `redis://sessions:6379` with their own user and a generated 40-character password (different, in no other service's environment), wait for `sessions` healthy, and keep the cookie name / domain; an empty `FORWARD_AUTH_REDIS_PASSWORD` or `FORWARD_AUTH_EXT_REDIS_PASSWORD` is rejected
    - the one-shot `dns-tool` (contract §12.1, on the `--profile '*'` config): image `portcullis-domains`, profile `tools`, entrypoint `domains dns`, user `10004:10004`, read-only, networks exactly `domains-egress`, no volumes, `environment`, `env_file`, ports or Traefik labels, and `domains` and `dns-tool` the only members of `domains-egress`; the pin check lets `dns-tool` use the locally built domains image
    - impersonation: the four forward-auth middlewares list `X-Forwarded-Impersonator` and `X-Forwarded-Impersonation`; Keycloak has `--features-disabled=impersonation` and no `--features`/`KC_FEATURES` enabling it; `PORTCULLIS_PORTAL_URL` = `https://<domain>/`; group-gate's `GATE_IMPERSONATION_FILE` = `/hub-data/impersonation.json`; the Hub's `HUB_IMPERSONATION_MAX_MINUTES` = 30
- **VPN** ([VPN-only access](vpn.md), contract §16):
    - **The VPN wiring check** (on the `--profile '*'` config, on Docker, Podman and the SELinux overlay): `wg` is `portcullis-wg`, profile `wg`, `10006:10006` with group `10007` only, read-only, no `cap_add` / `devices` / `sysctls` / `privileged` / `network_mode` / engine socket, exactly the volumes `vpn_doc` (ro), `wg_data` and the `people.key` bind (ro), the networks `portcullis-vpn`, `portcullis-vpn-edge`, `wg-egress` and `portcullis-metrics-wg` (alias `wg-metrics`), the edge caps' defaults and no secret in its environment but the key path; Traefik's `vpnsecure` on its `portcullis-vpn-edge` address, `PROXYPROTOCOL_TRUSTEDIPS` = `wg`'s edge address `/32`, `aliasHeadersStrategy: delete`, `strip-client-forwarded@file`, websecure's TLS domains and no other `vpnsecure` key; Traefik not on `portcullis-vpn`; `portcullis-vpn` = `wg`, `portcullis-vpn-edge` = `wg` + Traefik, `wg-egress` = `wg`; `wg_data` mounted by `wg` and (ro) the Hub, `vpn_doc` by the Hub (rw), `wg` and group-gate (ro), and group 10007 held by exactly those three; `people-vpn-enrol` = people's chain on `` PathPrefix(`/vpn/`) ``; the `-vpn` group-gate middlewares only on `vpnsecure`-only routers.
    - **No `NET_ADMIN` / `SYS_ADMIN`** in any core service (core stays userspace).
    - **wg unit tests** (`cd wg && go vet && go test -race`): the strict `vpn.json` reader on the shared vectors, real userspace WireGuard tunnels on loopback UDP (no TUN), the edge's accept rules, re-checks, caps and pressure eviction, the people role and the resolver. **forwarder** and **`tests/e2e/vpn-client`** unit tests the same way.
    - **Shared `vpn.json` vectors match the Hub**: `tests/vpn_json_vectors.json` is a byte copy of the same-named Hub branch's (else main's) `internal/vpn/testdata/vpn_json_vectors.json`; group-gate's reader runs them too (`tests/test_group_gate.py`).
    - `tests/test_cli.sh`: `vpn` argument parsing and help; `vpnsecure` trusts PROXY v2 only from `wg`'s edge address and never gets `forwardedHeaders.trustedIPs` / `insecure`; every core router uses its entrypoint variable.
    - `tests/test_shell_libs.sh`: the mode's entrypoint variables, `vpn init`'s subnet refusals and suggestion, `vpn add-device` (the config and QR from one config on stdin, no key on any logged command line, nothing run without the Hub), and the reserved ranges in `core.env` (`172.16.0.0/12 192.168.0.0/16 10.214.0.0/24` plus the core networks, and Podman's pools under Podman).
- **Mail** ([Mail server](../setup/mail.md), contract §19):
    - **The mail slot wiring check** (`.github/ci/unit-tests-mail-wiring.sh`): `portcullis-mail-api` (internal, the fixed subnet, the Hub's pinned address), `mail_slot` and `mail_provider_slot` mounted by the Hub only (and `mail_slot` by Prometheus read-only), the Hub's group 2000; no mail server in core.
    - **mailctl unit tests** (`cd mailctl && go vet && go test -race`, the adapter of the `stalwart` app): its config, the provider API guard (source subnet, bearer), the gate and the slot layout check, the JMAP envelope, the Stalwart schema snapshot (`internal/stalwart/testdata/schema-v1.1.0.json`), the base plan, the spam rules.
    - **mail-fake and the conformance suite**: `tests/e2e/mail-fake` (a CI-only provider: the provider API v1 over an in-memory store, honouring the gate, with no mail server behind it; `mail-fake mode honest|hostile`) with `go vet` and `go test -race`, and `tests/mail-conformance/test_run.py` for `tests/mail-conformance/run.py`, the provider conformance suite: `run.py --level api|full --api-url URL --secret-file FILE [--smtp-host H --imap-host H] [--ca-file PEM]` prints `PASS <name>` / `FAIL <name>: <why>` per check and exits 1 on any failure; `api` judges the provider API alone (any provider), `full` adds the mail protocol checks (never an open relay, a mail password opens only mail). Every provider template must pass it.
    - **MailState v2 and the mail DNS rule vectors match the Hub**: mailctl's `mailstate_v2.json` and the domains service's `mail_dns_vectors.json` are byte copies of the same-named Hub branch's (else main's) `internal/mailprovider/testdata/`.
- **Pin enforcement.** Every image in every compose file, under every profile (`--profile '*'`), must be pinned `tag@sha256:…`, apart from the Hub and Keycloak, which come from `HUB_IMAGE` and `KEYCLOAK_IMAGE` (our own `edge` images on `main`; the Keycloak image's Dockerfile pins Keycloak itself). The same goes for the `enroll/Dockerfile` bases and the pinned refs (`name:tag@sha256:<64 hex>`) the CLI (`scripts/lib/*.sh`: the helper, restic, lldap-ui forwarder constants) and the workflows / actions run inline, and inline images in the workflows. `tests/lint_images.sh` checks the Dockerfiles, the compose files (core and the CI templates `tests/e2e/apps/*/compose.yml`), and every pinned ref the CLI and workflows run. Every action must be pinned by full commit SHA with a `# vX.Y.Z` comment.
- **Monitoring config.** It runs, in the pinned images:
    - `promtool check config` and `check rules`, plus `promtool test rules` (the alert unit tests)
    - `amtool check-config` for a generated Alertmanager config with no receiver, a webhook, ntfy and SMTP
    - `blackbox_exporter --config.check`
    - a sanity check of the provisioned dashboard JSON
- **enroll** `go vet` + `go test` in the pinned Go image: CSR validation, content type, AppRole login and re-login, the renewal checks (`TestRenewChecksPresented`), browser certificates (`TestBrowserCertP12Decodes`: the `.p12` decodes with its password to an EC P-256 key matching a leaf with CN = the user issued by the browser CA, chain [browser CA, root]; `TestBrowserCertPasswordShape`; `TestBrowserCertTTLCeiling`; `TestBrowserCertMaxActive` and `TestBrowserCertMaxActiveConcurrent`: 10 parallel creates with a maximum of 3 → exactly 3; `TestBrowserCertSecretsNeverLogged`), the certificate actions (`TestCertAPINeedsBearer`, `TestCertAPIStrictBodies`, `TestCertAPIUnwired503`, `TestYubiKeyIssueValidatesCSR`, `TestRevokeFindsMountAndOwner`), the public mux (`TestPublicMuxOnlyInvite`: `/`, `/users`, `/certs`, `/self`, `/api/sign`, `/api/self/renew` → 404), the certificates API over both CAs (`TestCertificatesBothMountsKinds`) (`TestInternalCertificatesNeedsBearer`: 401 without, with an empty or wrong bearer or another scheme, not on the loopback listener; `TestInternalCertificatesLists`: only client-auth certificates, lowercase users, Vault serials, RFC 3339 UTC expiry, revocation state, no PEM, and `503` for the whole list when one serial, certificate or revocation state can't be read; `TestInternalCertificatesDeadline`: the deadline is at most 15 s, a listing that ignores its context still answers `503` at the deadline, and a Vault that never answers gets its call cancelled).
- **domains** (`domains/`): `go mod verify`, `go vet` (with and without the `testprovider` tag), `gofmt`, a check that the production build never links `internal/fakedns`, and `go test -race ./...` (in-process Pebble, the fake libdns provider and DNS server). **DNS hardening** (contract §12): `internal/dnsplan` (the record sets, the plan diff, the CAA merge rule — other CAs' entries kept, ours replaced, `TestMergeKeepsOtherIssuers` —, CAA values formatted differently from ours and the CA's judgement, `TestWouldIssueFormatting`, the RFC 8659 climb incl. an added child of the main domain, a CNAME blocking the address set, `TestCNAMEBlocksAddressApply`, a failed lookup reading `unknown`, never ok, `TestBuildLookupFailureUnknown`), `internal/dnssec` (the chain check's states on fakedns zones signed with miekg/dns: secure, unsigned, `ds_missing`, `ds_mismatch`, bogus by SERVFAIL then CD, an insecure parent), the account switch order (register → CAA → seen at **both** resolvers → order, `TestWaitCAABothResolvers`), `DELETE` and `DNS_CAA=false` removing only our CAA entries, the unknown CA skipping the set, per-record providers (cloudflare / porkbun) never dropping below our entries during a switch, the Cloudflare signer and Route 53 status reader against `httptest` fakes, DigitalOcean CAA through godo, and the one-shot tool (`domains dns plan|apply|check|dnssec-enable`: stdin only, unknown keys refused, credentials refused by `check`, the exit codes, `traefik-account-uri` printing only the URI). **HA certificates** (plan Task 29): `TestIssueMainPebble` (the front door's own account orders `<d>` + `*.<d>` against in-process Pebble, only TXT at `_acme-challenge.<d>` written and cleaned, a standby orders nothing, a renewal after the leader moved reuses the stored account), `TestRenewOnlySameAccount`, `TestFrontdoorAccountSeparate` (never the added-domains account), `TestFrontdoorControlClient` (`domains frontdoor account-uri | issue`), `TestServableHAIncludesMain` / `TestServableHAExcludesMailHost` / `TestServableNonHAUnchanged`, `TestHAServesFrontdoorCert` (the last good pair over a torn read); fix round 1: `TestAccountPerCARevertKeepsOld` (one account per CA: a flip to CA B and back keeps and renews with CA A's), `TestCertStatus`, `TestSealUnseal` (the backup's `frontdoor.age`), `frontdoor/TestNotDueReasonLoggedOnce`, and `issue` of a current certificate ordering nothing; `tests/test_shell_libs.sh` covers `dns_flip_main_account` (relax → settle → issue → re-pin; stops before the order when not settled, a saved settle point ahead or the public check refusing) and `config apply`'s HA flip (relax not settled → the front door's CA and account unchanged; settled → `.env` + the pending mark, `up` finishes; `ACME_STAGING` reverted mid-flip → the mark dropped), the backup / restore of `frontdoor.age`, the status line; `e2e-k3s-assert.sh` checks the chart's front-door RBAC live (`auth can-i`: get / update of its two Secrets only, no list; the Hub and Traefik read neither); promtool tests `PortcullisFrontdoorCertExpiring`; `tests/k8s_hardening.py` the front door's two Secrets (by name in its Role, `frontdoor-acme` mounted by nobody, `frontdoor-cert` by the domains service only, read-only).
- **mcp-gate** (`mcp-gate/`): `go mod verify`, `go vet`, `gofmt`, `go test -race ./...`. The shared test vector of contract §15.4 (`internal/config/testdata/mcp-gate.json` and `mcp-credentials.json`, byte-identical to the Hub's `internal/aigate/testdata/`; gate file v2) is decoded strictly and re-encoded byte for byte; `TestConfigV2Strict` refuses version 1, `acr_loa` / `min_loa`, a rule leaf outside `methods`, groups of 9, depth 5, more than 48 leaves and a companion whose rule needs a certificate. `internal/signin` runs the shared sign-in vectors (`internal/signin/testdata/signin_vectors.json`, a byte copy of the Hub's `internal/signin/testdata/vectors.json`): rule shapes, meeting a rule, alternatives, the reader rejects. The step after the tests ("mcp-gate shared vectors match the Hub") compares all three files with the same-named Hub branch, else main, the same way (exact branch, at the listed commit). The tests cover the token rules (signature, issuer, audience, scope, client, the sign-in rule over the token's `amr` — a certificate, `inv`, an unknown or switched-off method never counts (`TestTokenNeverCountsCertificates`), checked after the population and met or refused on the people and admin resources too (`TestPopulationBeforeSignInRule`) —, population, `Origin`; a rule that doesn't decode names its path, never its value), resource metadata, protocol versions, tool policy, confirmations and continuations, rate limits, the access log (refusing unloggable calls), the aggregate (names, collisions, per-upstream clients and sign-in rules — `TestAggregatePerUpstreamRule`, entries keyed on the token's method set), the Portcullis proxy, and the `impersonated` refusal: a token with an `act` or `pc_imp` claim is refused (`TestImpersonatedTokenRefused`). The gate writes a request's access-log line after the response has gone out. Before reading the log, the end-to-end tests therefore wait until every request they sent (except the open `GET` stream) has finished being handled, then flush the log's queue. A test never reads a line that is still on its way. The compose wiring check also asserts the gate's networks (exactly `portcullis-mcp` with the Hub and Keycloak, and `portcullis-proxy` at its fixed IP), its secret mounts, `mcp_gate_data` (read-only in the Hub) and that no router targets the Hub's port 8890. A second check (sign-in part 2) pins `group_gate_data` to exactly group-gate (read-write at `/data`, `10003:10003` + group `10001`) and the Hub (read-write at `/group-gate-data`), group-gate's two CA files (read-only under `/etc/group-gate/ca/`) and both CAs' CRL lists, the Hub's `HUB_CLIENT_CERT_TTL` / `HUB_CERT_EXPIRY_WARN_DAYS`, Keycloak's `PORTCULLIS_SIGNIN_URL`, no self-service middleware, and `enroll-invite` (`PathPrefix(/invite/)`) as the only router on `enroll.<domain>`; `tests/test_cli.sh` checks the same wiring in the files, the realm's two x509 executions and events settings, `keycloak configure` pushing each x509 config by its alias, and that no text names the retired `enroll.<domain>` self-service pages.

- **Kubernetes chart static checks** (`.github/ci/unit-tests-kube-static.sh`, [Kubernetes](kubernetes.md)): with pinned `helm` and `kubeconform`, `helm lint` and `helm template` of `charts/portcullis` through `kubeconform -strict` against the Kubernetes 1.33 schemas (the floor) and the pinned Traefik CRDs; `tests/k8s_parity.py` (the chart against compose, with the deltas in `tests/k8s_parity_deltas.yaml`), `tests/k8s_netpol_matrix.py` (every allowed and denied path), `tests/k8s_hardening.py` (the hardening baseline, every ServiceAccount's Secret access included), and the byte copies shared with the Hub: the Hub's two Roles in `charts/portcullis/files/` and `kube/admission/{policies,bindings,params}.yaml` against the Hub's `internal/runtime/kube/testdata/` (the same-named Hub branch, else main). Core is the only editor of `kube/admission/`; `charts/portcullis/images.yaml` must equal what `scripts/gen-images-yaml.py` generates from `docker-compose.yml`.

### `build-and-test` (whole stack)

It boots the stack with a CI override (no ACME; self-signed server cert from
the internal PKI) and verifies:

- **Rebuild and recreate.** After an `upgrade` that rebuilds a locally built service (`portcullis-enroll`), the running container uses the new image, and unchanged services (mcp-gate, postgres) keep their containers.

- **Vault**
    - server-mode init and unseal, and the permissions on `secrets/`
    - after a restart it auto-unseals and the CA is unchanged
    - the enroll AppRole can only sign, list, read and revoke certificates and rotate the CRLs, on both CAs
- **PKI**
    - both chain files are created and valid: `certs/ca-chain.crt` is exactly root + YubiKey CA + browser CA, `certs/ca-chain-yubikey.crt` exactly the YubiKey CA (no root, no browser CA)
    - Vault issues YubiKey certificates
- **Keycloak**
    - the OIDC discovery and SAML descriptor endpoints
    - the WebAuthn policy
    - the `portcullis-forward-auth` client
    - `portcullis-forward-auth` requires PKCE S256: an authorization request without a code challenge gets no code, the X.509 login with one does (oauth2-proxy's `alpha.yaml` must keep `code_challenge_method: S256`)
    - the invite post-broker flow admits only clients with the `portcullis-invite-client` scope (only `portcullis-forward-auth`, never a realm default), and a second `keycloak configure` keeps an extra-domain callback on `portcullis-forward-auth` while dropping a wildcard
    - LLDAP users show up through the federation
    - the `email-unverified` scope has exactly one mapper (`email`), also after a second `keycloak configure`; a throwaway direct-grant client with that scope instead of `email` gets `email` but no `email_verified` in the ID token, access token and userinfo, while the built-in `email` scope sends `email_verified: false`
- **YubiKey certificates at the handshake**
    - the Hub isn't running yet, so the step writes policy file v6 into `hub_data` (the starting methods, Standard the default, every gated core page on Standard; later steps add their keys to it): without a file group-gate denies everything
    - requests with no cert, or a cert from another CA, are rejected
    - cert info, including the serial, reaches the backend
    - requests arrive from Traefik's static IP
    - the group-gated test router (no forward-auth: the test sends the session headers itself, with an unsigned stand-in access token per method — group-gate reads only its `amr` / `preferred_username`) answers the step-up page to a cert without a session, the present-certificate page to an `mtls` session without the cert, and lets an `mtls` session with testuser's own unrevoked cert through
- **X.509 login**
    - a login via Traefik with a real cert (`pc_method=yubikey_cert`) succeeds; the Hub isn't running yet, so the step writes a minimal `signin-keycloak.json` (the starting methods) into `hub_data` first, or the sign-in extension would refuse everyone
    - the same cert as a forged header sent straight to Keycloak (from the
      `portcullis` and `portcullis-auth` networks and from `127.0.0.1:8080`)
      must **not** yield an authorization code
- **Header spoofing.** Client-supplied cert headers and their aliases are
  dropped, and group-gate's path rules see `X-Forwarded-Uri`.
- **Socket proxies.** A real `docker compose` project runs through
  `socket-proxy-hub`, and the denied sections (build, swarm, plugins, secrets,
  system, ...) fail. Traefik's proxy is read-only. Both proxies answer `403`
  to Podman's own API (`/libpod/info`, `/libpod/play/kube`,
  `/v5.0.0/libpod/containers/json`) and to `/build`.
- **Domains service (Pebble e2e).** The image is built with `GO_TAGS=testprovider`
  (adds provider `fake` with records in memory + a DNS server on `:8053`). CI
  runs Pebble (`-dnsserver domains:8053`) and configures the service to use
  `fake`, Pebble's minica root, and `DOMAINS_RESOLVERS=127.0.0.1:8053`. It checks:
    - adding a domain, the records check, ACME DNS-01 order, serving the certificate
    - `DELETE` stops serving it
    - the served document contains only `tls.certificates` (no routers, services, middlewares)
    - every served certificate's SANs are exactly `{<d>, *.<d>}` for an added domain
    - Traefik picks up the certificate by SNI within ~25 s without restarting (`StartedAt` unchanged)
    - core hosts still serve the main-domain certificate, never a certificate from the HTTP provider
    - Traefik's API lists no `@http` object (routers, services, middlewares, serverstransports)
    - mutual TLS: the endpoint refuses requests without Traefik's certificate
    - a kept domain survives backup/restore
    - **DNS hardening** (`DNS_CAA_ISSUER=pebble.test` in the CI override, as Pebble isn't Let's Encrypt): `GET /acme/account` names Pebble's directory, the issuer `pebble.test` and an account URI; the plan of the added domain (`/domains/<d>/dns?refresh=1`) has `can_write`, its `caa` set `ok`, `would_issue` and the pin naming the service's own account, its `address` set `ok`, and the domain object has `caa_ok: true`; `GET /main/dns` is the read-only main-domain plan (`can_write: false`); `domains report --main --json` (what `status` reads) has the main plan and exactly the added domain
    - the one-shot `dns-tool` (`docker compose run --rm -T dns-tool`, credentials on stdin): `apply --wait 60s` with the fake provider in the tool's own zone ends with `can_write`, `would_issue` and every `address` / `caa` item `ok`; `check` without credentials, against the domains service's fake DNS, judges the added domain's pin ok (exit 0, `can_write: false`); `check` with credentials is refused
    - Pebble doesn't enforce CAA, so CI checks that the records are written and the steps run in order, not a CA's refusal; that is checked by hand on the test server, with Let's Encrypt staging
  
  **The production image is built without `testprovider`** (no fake provider).

- **Live Keycloak access role test (opt-in).** When `PORTCULLIS_KEYCLOAK_LIVE_URL`
  (e.g. `http://keycloak:8080`) and `PORTCULLIS_KEYCLOAK_LIVE_WIPE=portcullis`
  are set, the Hub runs `TestLiveClientAccess`: it **wipes realm `portcullis`**,
  rebuilds it from the export, creates an LDAP group and a test client with the
  access role enforced, and drives the flow to verify the role is checked and
  fails closed. This is the live proof of contract §8. It requires a running
  Keycloak and is off by default.

- **Hub**
    - its LLDAP service account is set up first (the same `lldap_service_account` that `portcullis up` runs later in the job): the admin routes check the actor in LLDAP
    - runs as non-root
    - talks to Docker only via its proxy
    - answers 403 without the proxy secret
    - on a fresh install publishes policy file v6 with the four starting methods, Standard the default and Strong on `hub` / `people` (`GET /api/signin` agrees), which group-gate applies to an app without its own pick: a step-up for no session, through for a synced passkey, a security key or a bound certificate
    - an admin's `PUT /api/signin/default` to Strong reaches group-gate (a synced session gets the step-up or needs-stronger page, a bound certificate still opens the app), and back to Standard
    - the revocation test's precondition is live: testuser's bound `mtls` session opens the test router before the revocation, so only the revocation can turn 200 into 403
- **`signin reset-core` on the real Hub.** First `passkey_synced` is switched off through the Hub's API (`PUT /api/signin/methods/passkey_synced`), so the reset has something to undo. Without `--yes` and a terminal it exits exactly 2; `--yes` prints `method passkey_synced: off -> on` (never "nothing to change"), the Hub runs and answers `/healthz` again with `passkey_synced` on and `GET /api/signin` shows `hub` and `people` moved from Strong (the fresh install's) to `standard`, the files the reset wrote — `state.yaml` (rewritten atomically, so a new inode owned by the writer), `audit.jsonl`, `.hub.lock` — are `10001:10001` (a root run would leave `state.yaml` root's), and the audit log's last `signin.reset_core` entry is by `cli`, `ok`, naming the change.
- **enroll serves only setup links.** `https://enroll.<d>/` and every path but `/invite/…` answer Traefik's 404. On the container itself (step "Find enroll; its retired pages and APIs are gone") `:8443/healthz` answers 200 and `/`, `/users`, `/certs`, `/enroll/<u>`, `/api/users`, `/self`, `/api/self/renew` answer 404 (`POST /api/sign` 404 / 405).
- **enroll's YubiKey certificate API** (`POST enroll:8444/internal/yubikey-certificates`, contract §9.4, the admin CSR path that replaced `/api/sign`): with the bearer, testuser's CSR is signed on `pki_int` through enroll's AppRole (201, a PEM certificate issued by the YubiKey CA, chaining to `certs/ca-chain.crt`); no bearer or a wrong one is 401; the same CSR for `admin` is refused.
- **Sign-in flows and setup links.**
    - first the realm's passwordless passkey policy is drifted (conveyance `none`, attachment `cross-platform`), and `keycloak configure` must restore it
    - the browser flow is exactly the sign-in extension's tree (contract §8.1: cookie · invite redirector · {`portcullis-x509` (`x509-config`) · `portcullis-x509` (`x509-browser-config`) · passkey with one conditional sub-flow per kind · `portcullis-password-form`}, then `portcullis-template`), every reference config has a known amr and `maxAge` 36000; it carries the `[sync <hash>]` marker and a second `keycloak configure` rebuilds nothing
    - the two x509 configs on the live realm, as `keycloak configure` pushed them: `x509-config` (`yubikey_cert`, amr `mtls`, the YubiKey CA, `pki_int`'s CRLs) then `x509-browser-config` (`browser_cert`, `file`, the browser CA, `pki_file`'s CRLs), both aborting on a stale CRL; the realm's events config keeps `LOGIN`, `LOGIN_ERROR` and `IMPERSONATE`
    - `webauthn-register-passwordless` enabled, the two-factor `webauthn-register` disabled; the realm has `acr.loa.map` `{}`, brute force (10 / 60 s / 900 s, not permanent) and direct passkey attestation
    - the invite post-broker flow: admit / deny sub-flows, then amr `inv` and `portcullis-template`
    - the LDAP federation has `cachePolicy` `NO_CACHE` (`tests/test_shell_libs.sh` also checks the realm export and that `keycloak configure`'s patch sets it idempotently)
    - the invite identity provider is enabled, hidden, links existing users only (`idp-detect-existing-broker-user`, `idp-auto-link`), back-channel `http://enroll:8445`, PKCE; the service account `portcullis-enroll` has exactly view-users + manage-users
    - `./portcullis invite`: link format, a new link revokes the older one, viewing doesn't consume it, a cross-site redeem is refused, `portcullis-hub` is refused, `admin` is allowed from the server
    - the Hub's invite API (`enroll:8444`, contract §9.4): 201 for a user, 409 for `admin` / `portcullis-hub`, 404 for an unknown user, 401 with a wrong secret; the Hub's copy of the secret matches; the JWKS serves an ES256 key
- **Stock impersonation is off.** Keycloak's own `POST …/users/{id}/impersonation` answers non-2xx and names the feature.
- **acr scope has amr and impersonation.** The live `acr` scope has exactly one `amr` mapper and one `portcullis-impersonation` mapper (access token, ID token, userinfo), the notice required action is enabled, and a second `keycloak configure` adds no second mapper.
- **Client-sent impersonation headers.** `X-Forwarded-Impersonator` / `X-Forwarded-Impersonation` sent by the client never reach an app on the gated test router, and on people.&lt;domain&gt; `GET /api/me/impersonation` with forged headers answers `{"active": null}`.
- **`./portcullis up` and the Hub's LLDAP account.** `portcullis-hub` is in `lldap_admin`, the 0640 / group 10001 password file logs in, a password changed in LLDAP is reset from the file on the next `up`, and the Hub sees `/run/portcullis/lldap` and `/run/portcullis/invite`.
- **Revocation end to end**, once through `./portcullis cert revoke` and once through Vault's CRL alone.
- **enroll's certificates API** (`enroll:8444/internal/certificates`, contract §9.4): `401` without `Authorization`, with an empty or wrong bearer or another scheme; with the bearer `200` and exactly `{"certificates": [...]}`, each entry exactly `user` (lowercase), `serial`, `kind` (`yubikey` / `browser`), `not_before` and `not_after` (RFC 3339 UTC), `revoked` (boolean); the test YubiKey certificate revoked above is listed as `revoked: true` under Vault's serial; Traefik's server certificate (`*.portcullis.local`) is not listed; no PEM in the answer. enroll's Go tests cover the fail-closed side: a serial whose read fails, whose certificate is missing, or whose `revocation_time` is missing or unreadable answers `503` for the whole list.
- **Session store** (step "Test the session store"). `sessions` is healthy as
  `999:1000`, read-only, all capabilities dropped, on `portcullis-sessions`
  only; `secrets/sessions` is 0700 and `valkey.conf` 0640 group 1000 without
  either password in clear. The ACL, through `valkey-cli` in the container
  (the password by environment name, never on a command line): an
  unauthenticated `PING` gets `NOAUTH`, a wrong password `WRONGPASS`; each
  proxy's user reads and writes only its own keys (`_oauth2_proxy-*` /
  `__Host-portcullis_ext-*`), the other's are `NOPERM`; `keys`, `scan`,
  `flushall`, `config get` / `set`, `acl list`, `client list`, `info`,
  `shutdown`, `script flush` are `NOPERM`; a Lua script reads its own key but
  neither the other proxy's key nor `flushall`. Then a real sign-in through
  `forward-auth` with a fresh YubiKey certificate for testuser
  (`/oauth2/start?pc_method=yubikey_cert`, curl's cookie jar as the browser)
  ends at `/oauth2/auth` with 202; the jar holds exactly one `_oauth2_proxy`
  (no `_oauth2_proxy_0…`), under 512 bytes, whose value decodes to an
  oauth2-proxy ticket `v2.<id>.<secret>` with id `_oauth2_proxy-<32 hex>`,
  and the store holds that key (not readable by `forward-auth-ext`).
  `/oauth2/sign_out` deletes it, and the old cookie then gets 401.
- **CLI.** `./portcullis status`.
- **Backup round-trip.** It runs, in order:
    - `./portcullis backup` with nothing stopped, then `backup verify --local`. A deliberately damaged backup must fail verification.
    - `status --textfile`.
    - `backup --offsite` twice to a local restic repository. The second run must be incremental, and retention must collapse same-day snapshots under `keep-daily`.
    - `backup verify` (off-host). A wrong `BACKUP_PASSWORD` must fail, and neither the root token nor the `.env` secrets may appear in the encrypted repository.
    - **Restore into a fresh stack.** Containers, volumes, `.env`, `secrets/`, `certs/` and local backups are all deleted, as on a new host. Then `restore --yes --from-offsite` must bring back an active Vault, the Keycloak realm, the forward-auth client and the LLDAP user.

The step **"Test the VPN service"** (`.github/ci/build-and-test-vpn-service.sh`) runs `./portcullis vpn init` on Docker and checks:

- `wg` is added to `COMPOSE_PROFILES`, runs healthy as 10006 with group 10007 only, no capability, device, privilege or socket; `wg_data` is 2750 `10006:10001`, `status.json` 0640 group 10001, the people role is on, and `secrets/wg/people.key` is 0640 group 10006; the Hub reads `wg_data` and writes `vpn_doc`;
- a whoami on both entrypoints: forged forwarding headers (23 of them) never reach the backend, `X-Forwarded-For` holds exactly one address (the real peer) and `X-Real-Ip` is the peer; group-gate never logs a forged value;
- a PROXY header from a container on `portcullis-vpn` can't reach `vpnsecure` at all, and one from another `portcullis-vpn-edge` address is ignored; no edge port answers while no provider is wired;
- `vpn add-device` and `tests/e2e/vpn-client` through the tunnel: the backend sees exactly the device's tunnel address and Traefik's own forwarding headers.

`wg` then stays on for the rest of the job (`up`, `upgrade`, backup and restore).

The step **"Test the mail provider"** (`.github/ci/build-and-test-mail-service.sh setup`) opens the [mail slot](../setup/mail.md) and wires the `stalwart` app (`./portcullis mail enable --provider stalwart`; the mail certificate from a CI Pebble). The templates come from the same-named templates branch, else main (`.github/ci/mail-templates-checkout.sh`), loaded as the Hub's `portcullis` source, with two CI changes: the app's adapter image lines become the locally built `portcullis-mailctl:ci` (core CI tests the checkout's `mailctl/`, never the published image), and its resolver forwards every name to the domains service's fake DNS. It checks, failing with `FAIL: <what>`:

- **No outbound SMTP.** Outbound TCP 25, 465 and 587 is rejected first, for the containers, the template's egress network and the runner itself. Nothing is ever sent to an external domain: foreign recipients are only tried at RCPT (and refused).
- `stalwart` runs as 2000:2000, read-only, with `NET_BIND_SERVICE` only; the adapter as 10010 with no capability, from the checkout's mailctl.
- The bootstrap job ran the base plan once on the empty store and exited 0, the recovery login is refused, no container keeps a recovery variable, the store is marked and `api-key` is 0640 group 2010; a second run plans nothing.
- The management listener answers `404` from another address on the template's internal network (the API key too), and `stalwart` is on no core network.
- The certificate's SAN is `MAIL_HOSTNAME`, a second `mail cert` keeps the key, and 25, 465, 587 and 993 present it.
- `mail status --json`: wired, reachable, nothing owed or held, the certificate; the timer warning turning active after `mail schedule --systemd`.
- Port 25 offers no AUTH and relays nothing (from the host and from the egress network); submission refuses a foreign envelope sender and a foreign `From:`, and accepts the person's own mail.
- The gate: without `.present` in the slot volume a raw start of `stalwart` exits before serving; with it, healthy again.

After the backup step, **"Mail: the backup holds the provider's instance archive"** checks that `MANIFEST.json` names the provider's archive, that `hub_data` holds it, that `mail_tls` and `mail_acme` are archived and that `backup verify` checks it. After the restore into a fresh stack, **"Mail: the restore restored the provider and voided its mail passwords"** checks that the Hub verified the void (nothing owed), no hold file is left, the old mail password is refused and no credential is left.

The step "Test the public guard (public exceptions) through Traefik" routes a test host through `portcullis-public-guard@docker` only and checks: no version-3 entry → 403; published prefix / static paths → 200; other paths, encoded `/` or `#`, dot-segment escapes → 403; `Authorization`, `Proxy-Authorization`, a credential header, credential cookies and query keys in PHP-mangled spellings → 403. The guard's unit tests are in `tests/test_group_gate.py` (`PublicGuardTest`, `PhpVarNameTest`).

### `e2e` (browser)

`tests/e2e/e2e_login.py` runs Playwright Chromium (pinned in
`tests/e2e/requirements.txt`) with a CDP virtual WebAuthn authenticator against
the full chain: Traefik → oauth2-proxy → Keycloak (LLDAP users, WebAuthn, X.509)
→ group-gate. A `whoami` test app has three hosts: `app.` (group `users_e2e`,
`/admin` → `admin_e2e`, the default template Standard), `hwk.` (template
any[`security_key`]) and `mtls.` (template any[`yubikey_cert`]). With no Hub
in this job, the workflow writes policy file v6 and `signin-keycloak.json`
itself; the latter's trust list is the CI fixture
`tests/e2e/fixtures/virtual-authenticators.json`: Chromium's virtual CTAP2
authenticator (AAGUID `01020304-0506-0708-0102-030405060708`, `packed`
attestation with a self-signed "Batch Certificate", backup-eligible 0) as a
`security_key` with that certificate as its root, so the virtual key registers
as a security key (Keycloak's realm asks for direct attestation). The jobs
that run the Hub (`e2e-instances`, `e2e-signin`, `e2e-settings`, `e2e-folders`,
`e2e-filesharing`, `e2e-ai`) start it with `HUB_DEV=1` and
`HUB_SIGNIN_EXTRA_AUTHENTICATORS=/run/portcullis/signin/extra-authenticators.json`
through their CI-only compose override, which mounts the same fixture
read-only there (`e2e-signin` mounts a copy's directory instead, which its test rewrites) ([contract §8.1](../guides/integration-contracts.md#81-sign-in-methods-new-sign-in)
"Extra entries", development only), so their virtual keys are security keys
too (Strong on `hub` / `people`). Every setup-link sign-in in them walks the
step-up page with the shared `passkey_flow` helper of `e2e_login.py`; every caller states how many step-up pages it expects (one after a setup link, none for a later sign-in), and one more fails at once.

Scenarios:

No user has a password and nothing is pre-assigned in Keycloak: the job
creates one-time setup links with `./portcullis invite <user> --to <landing> --json`
(for `e2e`, `e2e-other`, `e2e-bypass` and the bootstrap `admin`) and the test starts from
them. Any password field fails the test.

1. An unauthenticated request is redirected to a passkey-only Keycloak sign-in page: it offers the passkey (`#authenticateWebAuthnButton`), no password field, and isn't Keycloak's error page.
2. The setup link → **Register my key** → passkey registration → group-gate's step-up page on `hwk.` (a setup-link session, amr `inv`, meets no template) asking for exactly `security_key` → **Continue** → one assertion of the new key → the app. Exactly one registration and one assertion; a needs-stronger page fails the test.
3. The setup link works once.
4. The session reaches the app.
5. Apps get the **username** as `X-Forwarded-User`, and spoofed identity headers are dropped. A forged unsigned `X-Forwarded-Access-Token` / `Authorization` (amr `hwk`, `mtls`, the user's own name) never reaches the app, and on `mtls.` the real session still gets group-gate's step-up to `yubikey_cert` (a forged amr `mtls` reaching group-gate would show present-certificate instead).
6. `path_groups`: `/admin` needs `admin_e2e`. `/%61dmin`, `//admin`, `/x/../admin` and `/ADMIN` are denied, while `/administrator` is allowed.
7. A second login in a fresh browser with the same key is one passkey assertion.
8. Group denial for a user not in `users_e2e` (also onboarded by setup link).
9. The bootstrap admin's link lands on the portal (`https://<domain>/`) with the Hub link, after one step-up asking for any passkey (`pc_method=passkey`).
10. An unused setup link, redeemed and then steered to another client's authorize endpoint with `kc_idp_hint=portcullis-invite` (client `e2e-invite-bypass`, created by the job), is denied by the invite post-broker flow: no code for the client, no passkey registered.
11. A YubiKey-certificate login via Keycloak satisfies the YubiKey-certificate template.
12. A YubiKey-certificate session without the certificate on the request is refused (certificate binding).
    The cert-only session opens a default-template app, and enroll's `/self` and `/api/self/renew` answer `404` for it (the cert-only renewal is `e2e-signin`'s `yubikey_cert_renew`: this job runs no Hub).
13. A revoked YubiKey certificate is rejected.
14. A certificate from a foreign CA is rejected in the TLS handshake.

`login_theme_brand`: on the first Keycloak sign-in page the `portcullis` theme loads `css/portcullis.css`, the header's `::before` shows `portcullis-mark.svg`, and the page's `link[rel=icon]` answers `200` with the pinned `favicon.ico` bytes.

`tests/e2e/e2e_invite.py <setup-link> <landing-url>` runs the setup-link
checks (registration, no password, `--expect-amr hwk` in CI: the token's passkey method is exactly that one; the re-invite counts one step-up click and one passkey click; the step-up after the link with one more
touch, a passkey method in the token's `amr`, single use, one-touch
second login, the invite identity provider refuses browsers without a link)
against any running install, e.g. a live server with a throwaway user
(`E2E_IGNORE_HTTPS_ERRORS=1` for ACME staging). With
`--reinvite-cmd "<command printing portcullis invite <same user> --json>"` it
also registers a second, new authenticator through a second link and checks
that both keys sign in — or, with `--replaced` (`--replace-keys`), that the
old one no longer does. With a spare key the step-up after the second link
counts two assertion events for one touch: the account holds two passkeys, and
Chromium silently probes a multi-entry `allowCredentials` list first (CDP
reports that probe as an assertion too). The `e2e` job runs both variants after the browser
tests (users `e2e-spare`, `e2e-lost`). Dialogs are answered like a user
pressing OK (the default value).

After the browser tests, the job enables the **monitoring profile** and checks:

- all monitoring services become healthy, and every Prometheus target is up
- the Vault health probe and the enroll, forward-auth and forward-auth-ext (`/ready`: the session store answers) and LLDAP probes succeed
- group-gate, CRL, backup (textfile), CA-expiry, Traefik and Vault metrics are present
- the alert rules are loaded, and neither `VaultSealedOrDown` nor `CrlStale` is pending or firing
- Grafana at `metrics.<domain>` redirects unauthenticated users to sign in, and rejects a forged identity header that doesn't come from Traefik's IP

On failure, screenshots, HTML, traces and service logs are uploaded as
artifacts. The test needs a live stack and is not collected by pytest.

### `e2e-instances` (app instances, extra domains)

The whole stack plus the Hub, the domains service against Pebble with the fake
DNS provider, and the added domain `team-b.test` (added on the domains
API with the fake provider, which the Hub refuses; the Hub picks it up from the
service's list). The Hub's only template source is the CI template
`tests/e2e/apps/echo` (`traefik/whoami` behind Portcullis sign-in, plus a
`hold` service that ignores SIGTERM so a backup can be made slow), seeded into
`hub_data` as a local source. Through the Hub's API the job creates `echo-a`
and `echo-c` on `team-b.test` and `echo-b` on the main domain (`echo-c` on a
template the job creates, `e2e-cert` = any[`yubikey_cert`], picked with
`PUT /api/instances/echo-c/settings` `{sign_in_template}`), checks the
published policy file (v6, host keys, groups per instance, `hosts` for
`echo-c` only, `extra_domains`), the rendered labels (`portcullis-auth-ext` and the
`/oauth2/` router to `forward-auth-ext` on extra-domain hosts only), the
callbacks on `portcullis-forward-auth` and the SNI certificate. Every create
carries a `label` ("Team A", …); a create without one is `400`, and so is a
host on a domain that isn't added. On `echo-b` the job checks the env
overrides ([contracts §11.9](../guides/integration-contracts.md#119-labels-groups-setup-choices-env-overrides-and-jobs-new-apps)):
a variable of the admin's own (`PUT /api/instances/echo-b/env/CI_MARKER`) is
stored and listed as a `custom` row, a Hub variable (`PORTCULLIS_INSTANCE`) and
a setting's variable (`ECHO_STOP_GRACE`) are refused with `400`, the reset
(`DELETE`) answers `row: null`, and the removed whole-file route
`/api/templates/env/<id>` answers `404` / `405`. Then
`tests/e2e/e2e_instances.py`:

- cross-domain SSO: signed in on the main domain, `echo-a` opens with no
  further WebAuthn assertion, through the host's own callback, PKCE S256 and a
  host-only `__Host-portcullis_ext` cookie; a stale ext cookie signs in again
  without a loop; `echo-c` steps up to the YubiKey certificate exactly once
  (`pc_method=yubikey_cert` on the host's own `/oauth2/start`; a returning
  user's passkey session, the YubiKey certificate available);
- two instances, two groups: each user reaches only their instance;
- a backup longer than 60 s through `hub.<domain>`: `202`, a concurrent
  request `409`, the op record ends ok (Traefik keeps its default timeouts);
- `domains_dns_panel`: in Settings → Domains, the **DNS** button of
  `team-b.test` opens its [DNS panel](hub.md#the-dns-panel); every `caa`
  row's status is `ok` and the CAA line says "would issue: yes" (the
  e2e-instances domains override sets `DNS_CAA_ISSUER=pebble.test`).

Finally, on the real daemon: backup (the helper image pulled by digest,
helpers removed), the typed-id delete (refusals first, then containers,
volume and routing gone, the backup listed), restore into a new id (file and
volume-root owners and modes kept, the new volume labelled for its project,
the instance enables), and **`stop_enable_mid_pull`**: the CI template
`tests/e2e/apps/slowpull` (GitLab CE's ~1.5 GB image, never cached on the
runner) is enabled through the API, the test waits for step `images` to be
running and POSTs the Stop (202), then waits for the record to end stopped.
Assertions: no containers or volumes left, no Keycloak client `slowpull`, no
groups `users_slowpull` / `admin_slowpull`, the instance disabled, and
`enable.stop` in the audit. Poll helpers: Python e2e scripts use the shared
module `tests/e2e/e2e_ops.py`; CI shell steps source `tests/e2e/hubop.sh`
(shellchecked by the unit-tests job). Both poll each operation's own record
every 2 s: the 202's `poll`, `/api/instances/<id>/op?op_id=<op_id>`, which
the Hub keeps after a newer op (such as its own queued restart) has replaced
the instance's current record. A `poll` that isn't of that form, or a record
of another op, fails at once. On failure both print the record's error,
hint, output and steps. Stop is sent with the enable's `op_id`. Folder and
doctor ops poll their own records (`/api/folders/<id>/op`, `/api/doctor/op`),
which have no history.

### `e2e-signin` (sign-in methods)

The whole stack plus the Hub and the Keycloak image (each built from its
same-named branch) with one local template source: the CI templates
`tests/e2e/apps/echo` (forward-auth) and `tests/e2e/apps/oidc-echo` (a
native-OIDC client the Hub registers; `traefik/whoami` only answers the
redirect URI — the test stops the browser there and redeems the code
itself). The Hub's trust-list fixture is a copy of
`tests/e2e/fixtures/virtual-authenticators.json` in `/tmp/signin-fixture`,
whose directory the CI override mounts read-only at
`/run/portcullis/signin`, so the test can rewrite the file in place. Through
the Hub's API the job enables Basic and YubiKey + certificate, checks that
`browser_cert` is off by default, switches it on, creates `e2e-cert` = any[`yubikey_cert`], `e2e-file` =
any[`browser_cert`] and `e2e-anycert` = any[`yubikey_cert`, `browser_cert`],
and the instances `echo-std` (the default, Standard), `echo-basic` (Basic),
`echo-cert` (`e2e-cert`, `protected@file`), `echo-file` (`e2e-file`) and
`echo-anycert` (`e2e-anycert`, both `protected-any@file`), `oidc-strong`
(Strong), `oidc-all` (YubiKey + certificate) and `oidc-cert` (`e2e-cert`), and checks what it published:
the picks in policy file v6, `hub` / `people` on Strong, and
`signin-keycloak.json` `clients` (`oidc-strong` / `oidc-all` with their
templates and names), the fixture's AAGUID, password off, `browser_cert` on.
People (created with the Hub's LLDAP service account): `root` and `sam`
(`lldap_admin`), `alice`, `bob` (a Vault certificate only), `pat` (a
Hub-generated password only, kept in a 0600 file, never printed), `rita` and
`carol`; `root` gets a certificate too. Setup links come from `./portcullis
invite` inside the test. The venv also gets `cryptography` (group-gate's
pinned, hashed wheels) for the `.p12`, the CSRs and the CA checks; keys,
certificates and `.p12` passwords live only in a 0700 temp directory and in
memory, and every password is `::add-mask::`ed.

`tests/e2e/e2e_signin.py` uses two kinds of CDP virtual authenticator:
backup eligibility 0 (Chromium's packed attestation, listed in the fixture:
a **security key**) and backup eligibility 1 (a **synced** passkey, contract
§8.1 "Passkey kinds"). An init script records the `allowCredentials` of every
`navigator.credentials.get`, so "only that kind's credentials" is checked on
what the browser was asked, not on Chromium's silent probe. Keycloak state is
read from its admin API (credential types, brute-force status, sessions) and
its log. Before the test, the job drifts the realm's passwordless passkey
policy (conveyance `none`, attachment `cross-platform`) and `keycloak
configure` must restore it (`passkey_kinds_identified` below needs the
restored policy). In order:

1. **Password off:** the cold sign-in offers the passkey only — no "Try
   another way", no password field —, also for a step-up with
   `pc_method=password` (the authorize request is checked to carry it).
2. **Reclassification, part 1:** the fixture rewritten to `{}` (a directory
   change through the Hub — a throwaway group — makes it publish:
   `signin-keycloak.json` loses the virtual key's entry — the real FIDO MDS's
   entries stay — and gets a higher `mds.serial`);
   rita's setup-link key registers as `webauthn-passwordless`
   (`passkey_synced`, logged by the extension); the fixture is put back at
   once (written atomically: temp file + rename in the mounted directory).
   **`pc_fresh` absent** for her setup-link session: an authorization through
   `portcullis-fresh-auth` (PKCE S256, SSO reused, no touch of the key) has no
   `pc_fresh`.
3. **Security key on Strong:** root's setup link → step-up
   `pc_method=security_key` → `hub.<d>` 200, amr `hwk`, credential type
   `portcullis-security-key`.
4. **Synced passkey refused on Strong:** sam's synced key
   (`webauthn-passwordless`, amr `spk`): once the Hub's inventory lists
   `people.sam = [passkey_synced]`, a later sign-in with it (one touch, amr
   without `inv`: a setup-link session counts as not known in `people`)
   gets `#needs-stronger` on `hub.<d>` (no step-up).
5. **Native-OIDC template enforced:** sam on `oidc-strong` gets Keycloak's
   `portcullis-needs-stronger.ftl` ("OIDC echo · OIDC Strong needs a stronger
   sign-in") in core's `portcullis` theme, no code. The screenshot and HTML are
   uploaded on every run (artifact `e2e-signin-needs-stronger`).
6. **`pc_method` for one kind:** sam's spare security key (a second setup
   link, landing on `hub.<d>`): the step-up asks `security_key` and the browser
   is asked for that key only, never the synced one.
7. **`pc_method` reaches Keycloak, amr accumulates:** sam's synced session (from 4) on
   `hub.<d>`, with `people.sam = [passkey_synced, security_key]`: step-up
   `pc_method=security_key`; Keycloak shows the passkey prompt only (no "Try
   another way", no password field) and asks for the security key only; the
   token's amr then has `spk` and `hwk`.
8. **Cross-user certificate:** alice signs up through a setup link (one
   step-up); her session is then exactly one small `_oauth2_proxy` ticket
   cookie, no `_oauth2_proxy_0…` (oauth2-proxy #3486: before the session
   store, this step-up looped). Her passkey session presenting bob's
   certificate, refused by Keycloak's X.509 user check or the extension's
   USER_CONFLICT (the log has the extension's line naming alice or a
   `LOGIN_ERROR` for bob's certificate with no user) — on `echo-cert`'s
   `yubikey_cert` step-up (no code reaches oauth2-proxy) and on `oidc-cert`, a
   native-OIDC client on `e2e-cert` = any[`yubikey_cert`] where a switch to bob
   would meet the template: without `pc_method` Keycloak's needs-stronger page
   (the certificate isn't alice's, so the template step doesn't ask for it),
   with `pc_method=yubikey_cert` the refusal; no code either way. Bob has no Keycloak session, and the forward-auth session
   is never bob's.
9. **An `all` template met step by step:** root with his certificate on
   `oidc-all` (all[`yubikey_cert`, `security_key`]): the certificate signs in,
   Keycloak asks for his security key itself (only it), then issues; the ID
   token's amr has `mtls` and `hwk`.
10. **`pc_fresh` present:** root's fresh passkey sign-in on
    `portcullis-fresh-auth` (`prompt=login`, `max_age=0`) has `pc_fresh` =
    `security_key`; an SSO reuse right after has none.
    **The hub core template governs admin confirmations:** sam calls
    `delete_group` on a throwaway group through the Hub's MCP listener
    (`:8890/mcp/admin`, the gate secret read from `secrets/mcp-gate/hub-secret`,
    never printed); his fresh sign-in on `portcullis-fresh-auth` with redirect
    `https://hub.<d>/` (the proof posted to `/api/me/confirmations/<id>` as
    the page does) with the synced passkey is refused (403 "a fresh sign-in
    is required"), with the security key approved; `ai.confirm` names
    `template strong` both times. The confirmation is never consumed.
11. **Password on:** pat signs in with his password ("Try another way" →
    Password) on `echo-basic` (Basic; amr `pwd`); once the inventory lists
    `people.pat = [password]`, `people.<d>` (Strong) answers `#needs-stronger`.
12. **Admin's password refused:** `admin` with LLDAP's admin password, 11
    times (above the realm's failure factor 10): "Password sign-in isn't
    available for this account" each time, Keycloak's brute-force status
    for admin shows 0 failures and not disabled, and admin's passkey still
    signs in.
13. **Password off again:** as in 1.
14. **Reclassification, part 2:** rita's credential type becomes
    `portcullis-security-key`, and the log's `PasskeyReclassified user rita …
    passkey_synced -> security_key` line (`docker compose logs -t`) is at most
    360 s after the fixture's return (a new mtime → a higher `mds.serial`; the
    extension's task runs every 5 min, plus slack).
15. **Sign-in page, part 2** (`browser_cert` on since the job's setup):
    - **`browser_cert_on`:** the switch is on in `GET /api/signin` and
      `signin-keycloak.json`; `echo-file` / `echo-anycert` carry
      `protected-any@file`, `echo-cert` `protected@file`.
    - **`browser_cert_create_download`:** alice signs in on
      `people.<d>/signin` with her virtual security key, does a fresh sign-in
      (the popup flow, redirect `https://people.<d>/signin`), then
      `POST https://people.<d>/api/me/signin/browser-certificates {days: 30}`
      through Traefik: `200` with `Cache-Control: no-store` and
      `Pragma: no-cache`; the password is 4 × 5 Crockford characters;
      `pkcs12.load_key_and_certificates(p12, password)` gives an EC P-256 key
      and a leaf with CN `alice`, issued (and signed) by the browser CA,
      `not_after` ≈ now + 30 days; the `.p12`'s chain holds the browser CA and
      the root (never the YubiKey CA); the filename and the row's serial
      match. The `cert.create` audit entries hold neither the password nor
      any base64 run. The policy file's `people` then lists `browser_cert`
      for alice.
    - **`browser_cert_fresh_refused_weak`:** sam's synced-passkey fresh
      sign-in (the people core template is Strong) gets `403` "a fresh
      sign-in is required"; nothing is created.
    - **`browser_cert_max_active`:** two more creates succeed and the fourth
      gets `409` (at most 3 active).
    - **`tls_protected_yubikey_ca_only`:** `echo-cert` (`protected@file`, the
      option `mtls` apps get): `openssl s_client`'s "Acceptable client
      certificate CA names" is exactly the YubiKey CA — no root, no browser
      CA.
    - **`tls_mtls_refuses_browser_cert`:** `curl` to `echo-cert` with alice's
      browser leaf followed by the `.p12`'s whole chain (`pki_file` + root,
      as a browser sends it) is refused in the handshake (curl exit 35 or 56,
      nothing else), while the same files complete it on `echo-anycert`; a
      Playwright context presenting the `.p12` itself is refused too (its
      synthetic 503 "client-certificate error" page, Chromium's
      `net::ERR_BAD_SSL_CLIENT_AUTH_CERT`, or `net::ERR_HTTP2_PROTOCOL_ERROR`
      when the TLS 1.3 refusal reaches Playwright's TLS proxy after it already
      answered the browser with h2 — that one only with a real answer for the
      same `.p12` from `echo-anycert` in the same context; any other error
      fails); root's
      YubiKey certificate completes the handshake.
    - **`tls_protected_any`:** `echo-anycert`'s CA names are the root and both
      CAs; the browser certificate (with its chain) completes the handshake,
      no certificate fails it.
    - **`browser_cert_signin_file`:** a new context with the `.p12` as its
      `client_certificates` and no authenticator: alice signs in with the
      certificate only and `echo-file` (any[`browser_cert`]) opens; the
      token's amr has `file` and never `mtls`; Keycloak's LOGIN events have
      `pc_methods` `browser_cert` (never `yubikey_cert`) and its log names no
      `mtls` / `yubikey_cert` for her.
    - **`browser_cert_not_yubikey`:** that session on `oidc-cert`
      (any[`yubikey_cert`]) gets Keycloak's needs-stronger page; with
      `pc_method=yubikey_cert` it signs nobody in (no code). A forward-auth
      any[`yubikey_cert`] host is `protected@file`, so there the handshake
      refuses the browser certificate (above).
    - **`browser_cert_cannot_renew`:** the browser certificate presented on
      `POST /api/me/signin/yubikey-certificate/renew` with a CSR for its key
      gets `403` "present your current YubiKey certificate"; nothing is
      issued.
    - **`browser_cert_off_counts_nothing`:** `echo-file` off `e2e-file`,
      `e2e-file` disabled, `browser_cert` switched off (both published files
      without it; `echo-anycert` on `protected@file`, since the switch drops
      `browser_cert` from every compiled rule and `e2e-anycert` becomes
      any[`yubikey_cert`]; `echo-file`, on the default Standard meanwhile,
      on `authaware@file`): on `echo-file` the same valid `.p12` alone leaves
      the browser on Keycloak's passkey prompt with no LOGIN event, and
      alice's earlier file session gets `403`.
      Everything is switched back in a `finally` (`echo-file` /
      `echo-anycert` back on `protected-any@file`).
    - **`yubikey_cert_still_mtls`:** a `pki_int` certificate CI issues for
      alice through Vault signs her in without an authenticator: amr `mtls`,
      never `file`; `echo-cert` opens.
    - **`yubikey_cert_renew`** (the cert-only renewal, moved here from
      `e2e`: enroll's `/self` is gone and the `e2e` job runs no Hub): that
      session renews on the Sign-in page —
      `POST https://people.<d>/api/me/signin/yubikey-certificate/renew` with
      a CSR for the same key → `200` no-store, CN `alice`, the YubiKey CA,
      the same key, a new serial.
    - **`forged_cert_headers`:** Traefik deletes client-sent
      `X-Forwarded-Tls-Client-Cert` / `-Info`: alice's `mtls` session without
      the certificate but with both headers forged (her real YubiKey
      certificate) stays on `#present-certificate` on `people.<d>/`, and a
      renewal from her passkey session with them forged gets `403`; the same
      header sent straight to the Hub's people listener (`:8889`, no Traefik)
      renews (`200`), so the `403` is Traefik deleting it.
    - **`browser_cert_revoked`:** `DELETE /api/me/signin/certificates/<serial>`
      (through Traefik, with that certificate) → `204`; within 70 s
      `echo-file` answers `403` (revoked) and `GET /api/me/signin` shows it
      `revoked`; a YubiKey certificate's serial on that route is `404`; she
      revokes her third one too.
    - **`signin_page_reachable_weak`:** password on, pat (a password only —
      bob has a YubiKey certificate, so `people.<d>` would offer him a
      step-up) signs in with a wrong password once, then his own:
      `/signin` and `/api/me/signin` answer `200`; `/api/directory` gets
      `#needs-stronger`; raw, unnormalised paths sent with `http.client`
      (the path written as is: `/signin/../api/directory`,
      `/api/me/signin/../../directory`, `/static/../api/directory` → `403`
      `#needs-stronger`; encoded dots, slashes and backslashes → refused,
      `400` / `403` / `404`, never the Hub). Password off again after.
    - **`sign_in_help_actions`:** group `hr` with carol,
      `PUT /api/directory/permissions/sign_in_help {group: "hr"}`; carol's
      view of alice's Sign-in tab may send a setup link, remove passkeys and
      revoke, not set a password or issue; she sends alice a setup link
      (`200`, masked), removes her passkeys (`200`, gone from Keycloak) and
      revokes her second browser certificate (`204`); she gets `403` for
      alice's password and for every action on root, `portcullis-hub` and
      herself (also revoking root's certificate); as an admin, issuing and
      revoking root's certificate get `409` "… managed from the server". The
      audit has `user.invite`, `user.remove_passkeys` and `cert.revoke` with
      `as sign_in_help`.
    - **`browser_cert_none_left`:** all three revoked, none active, and the
      policy file's `people` no longer lists `browser_cert` for alice.
    - **`history_entries`:** alice's `/api/me/signin/history` (no unknown
      source) has her setup-link `sign_in` (no methods, detail "Setup link
      used"), a `sign_in` with methods `[browser_cert]` and a non-empty
      browser, a `step_up`, an `opened` for `echo-file` with `browser_cert`,
      at least three `help` entries by carol and at least three
      `certificate` entries, and no `.p12` password; pat's has a `failed`
      entry (his wrong password); carol may read alice's history.
    - **`cert_and_password_kinds_identified`:** Keycloak's `LOGIN`
      `pc_methods` name `yubikey_cert` and `browser_cert` for alice's
      certificate sign-ins and `password` for pat's; `/api/me/signin`
      lists alice's `yubikey_cert` and pat's password (and nothing else
      for pat).
    - **`enroll_site_gone`:** `https://enroll.<d>/`, `/self`,
      `/api/self/renew`, `/api/sign`, `/api/users`, `/users` and `/certs`
      get Traefik's own `404` (no router), while `/invite/<bad token>`
      reaches enroll's invite page ("This setup link is invalid, expired or
      already used", `404`).
16. **TLS follows the switches** (last; it restarts apps): with both
    certificate methods on, `echo-std` and `echo-basic` are on
    `authaware@file` and `openssl s_client -servername <host>` shows
    "Acceptable client certificate CA names". Standard saved as
    any[`family:passkey`], the instances off the certificate templates,
    `hub` / `people` on `standard`, Strong, YubiKey + certificate,
    `e2e-cert`, `e2e-file` and `e2e-anycert` disabled → `echo-std` on
    `public@file` with no CA names; `echo-basic` (Basic still names
    `family:certificate`) stays on `authaware@file` while `browser_cert` alone
    is on — checked on six samples over 30 s once the Hub has applied
    `yubikey_cert` off (both published files without it, the Hub's own tier
    for `echo-basic` `authaware@file`, no `echo-basic` op running) — and moves only when both `yubikey_cert` and `browser_cert` are
    switched off. `auth.<d>` and `hub.<d>` keep their CA names (core routers
    stay on `authaware`). Then everything is put back (in a `finally`, also
    when a step failed) and compared with the snapshot taken before (methods,
    templates and rules, default, core pages, instance picks), and both apps
    are back on `authaware@file` with CA names.

17. **Signing in as someone else** (the job's `.env` sets
    `IMPERSONATION_MAX_MINUTES=2`, for every case). Each case starts with
    root's fresh sign-in with his security key, then POSTs the start route
    on the Hub listener; every case stops its own impersonation within 2
    minutes, except `imp_expiry` and the 125 s case of `imp_next_bound`,
    which run last among them, in parallel browser contexts. `sam` is the second
    administrator.
    - **`imp_start`:** root's YubiKey-certificate session; his fresh
      security-key sign-in leaves only `hwk` in the session, so he steps up
      to `yubikey_cert` before the start. Reason "checking quota", then
      `next`: root's browser lands on the portal as alice; the token has
      `preferred_username` alice, `act.sub` root, `pc_imp.id` = the id and
      root's amr (`mtls`, `hwk`); root has no Keycloak session left and
      alice has one, with the impersonator.
    - **`imp_banner_everywhere`:** `You are signed in as alice (by root) ·
      reason “checking quota” ·` … `min left` with a Stop control on the
      portal, on people.&lt;d&gt;'s My apps and `/signin` (after
      `impersonation.js` ran), on a group-gate needs-stronger page and on
      the extension's page.
    - **`imp_call5`:** an app on `e2e-cert` opens only while root's YubiKey
      certificate is presented; with alice's certificate it shows the
      impersonation needs page with no `X-Stepup-URL`. An app on Strong
      opens although alice's own methods don't meet Strong.
    - **`imp_people_read_only`:** `PUT /api/me/signin/password`,
      `POST /api/me/signin/browser-certificates` and
      `DELETE /api/me/ai/connections/x` get `403` "not while you are signed
      in as someone else: Stop first"; `GET /api/me/apps` is `200`.
    - **`imp_signin_page_read_only`:** the impersonating browser's
      `/signin` says "Changes are off while root is signed in as you." and
      offers no action (no `[data-msi-act]` element).
    - **`imp_ai_refused`:** the CI AI client's authorize in this browser
      shows `#impersonating` and issues no code; a token minted
      for alice before the start still works through `mcpclient`.
    - **`imp_refused_concurrent`:** root's second start → `409` "Stop it
      first"; sam on alice → `409` "root is signed in as alice right now".
    - **`imp_stop`:** Stop on the portal → the Stop page POSTs, the browser
      goes through `/oauth2/sign_out`, then to the sign-in page, or, since
      the browser presents root's YubiKey certificate, to the portal as root
      with no `act` / `pc_imp`; within 20 s alice has no impersonated
      Keycloak session; the old `_oauth2_proxy` cookie replayed on the app
      never gets `200`; `oidc-strong`'s refresh token is then
      `invalid_grant`; the audit has
      `impersonation.start` with the reason and `impersonation.end`
      "stopped" with the apps opened; alice's history has the
      `impersonation` entry by root with the reason and the apps.
    - **`imp_stop_elsewhere`:** sam's `stop_impersonation` (Hub MCP) ends
      it; root's browser gets group-gate's ended page within 5 s.
    - **`imp_notice_next_signin`:** after `imp_stop`, alice signs in herself
      in a new context: the notice reads "root signed in as you on … UTC
      for … min: checking quota.", Continue reaches her app, and her next
      sign-in shows no notice.
    - **`imp_refused_proofs`:** sam's synced-passkey proof, root's
      browser-certificate proof and bob's proof → `403`; reason "ab" →
      `400`. (The password case is the Hub's unit test: root has no
      password.)
    - **`imp_refused_targets`:** root himself, `sam` (an administrator),
      `portcullis-hub` and `admin` → `409`; a `sign_in_help` holder as the
      caller → `403`; the switch off → `409`, and a running impersonation
      ends.
    - **`imp_next_bound`:** `next` opened in bob's signed-in context →
      `403` page and bob's session intact; opened again in root's context
      after a successful use → `403`; a fresh start's `next` opened after
      125 s → `403`. Each time alice gets no session.
    - **`imp_expiry`:** after 2 min 10 s a request gets group-gate's ended
      page, the extension's ended page or Keycloak's sign-in page (never
      anything as alice),
      within a further 20 s Keycloak has no impersonated session, and the
      audit has "expired" by `portcullis`.
    - **`imp_stock_endpoint_off`:** Keycloak's own admin impersonation
      endpoint answers non-2xx.

    After these, before 16, **`passkey_kinds_identified`**: the realm's
    passwordless policy is the restored one, and a security key (rita,
    after `invite --replace-keys`), a synced passkey (bob) and a
    device-bound one (pat; the fixture kind `passkey_device`) are each
    identified by kind: credential type, log kind and AAGUID, the
    `/api/me/signin` row, the amr and `LOGIN` `pc_methods`.

Also in `e2e_signin.py`:

- **`stepup_returns_to_page`:** sam's synced session opens
  `https://hub.<d>/?from=stepup#x` (Strong); the step-up page's Continue has
  `rd` = `https://hub.<d>/?from=stepup`, and after the security-key touch the
  browser is back on that page.
- **`passkey_rename`:** sam renames his security key through
  `PUT /api/me/signin/passkeys/<id>/label` "CI key" → `204`, and Keycloak's
  credential has `userLabel` "CI key"; his synced passkey renamed "ci KEY"
  → `409`; root's credential id → `404`; the audit has
  `signin.passkey.label` with a detail ending `→ CI key`.

`tests/e2e/e2e_signin.py`'s and `e2e_filesharing.py`'s fresh sign-ins on
people.&lt;domain&gt; use the redirect `https://people.<d>/signin`.

The throwaway `ci-kick-<n>` groups are deleted at the end (best effort).
`./portcullis signin reset-core` is covered by `build-and-test` (above). The
setup link landing on the step-up page is `e2e` scenario 2. Failure artifacts:
screenshots, HTML and service logs; no Playwright traces (a DOM snapshot
would carry a typed password), the password pages are captured before
anything is typed, and no whoami page is captured (it echoes session cookies
and bearer tokens). Setup links are masked in the log (`::add-mask::`) and
redacted from failure messages; the screenshots / HTML of the setup pages
show the consumed links (nothing reusable).

#### `e2e_totp` (authenticator codes)

`tests/e2e/e2e_totp.py` runs inside the `e2e-signin` job, as its own step
("Authenticator codes", run on success or failure), after `e2e_signin.py`, on
the same stack: its users, pat's password file and the `hr` group. It adds no
CI job. It sets up what it needs itself, so it also runs alone after the
job's setup steps, and its setup and `finally` cope with re-runs on the same
stack. It imports `e2e_signin`'s helpers and `e2e_login` / `e2e_ops`.
`APP_HOSTS` has `echo-otp`.

- **Codes** come from `pyotp` (RFC 6238; `pyotp==2.9.0`, pinned with the
  hashes of both published files in `tests/e2e/requirements-totp.txt`,
  installed with `--require-hashes --only-binary=:all:` in the job's pip
  step and part of its cache key), never a hand-rolled HMAC.
- **The secret** is read from Keycloak's own manual-key element. CSS
  injected into every page before anything is shown hides the setup page's
  QR code and key. The secret is `::add-mask::`ed, kept in memory only and
  never printed or written. No screenshot or HTML is taken of a page that
  holds one, and no Playwright trace is recorded.
- **State:** `totp` is switched on (a setup link with the authenticator
  option is refused while it is off) and off again at the end; `password` is
  switched on for the run and put back as it was. It creates the template
  `e2e-otp` = `all[password, totp]` and the instance `echo-otp` on it (pat and
  alice members). The `people` core page is on `e2e-otp` for `fresh_one_code`
  only (Strong before and after).

The cases, in this order:

| Case | What it checks |
|---|---|
| `setup_link_refused_while_off` | an invite with `{"authenticator": true}` → `409` while `totp` is off |
| `setup` | `totp` and `password` on, `e2e-otp`, `echo-otp`, its members |
| `policy_read_back` | the realm OTP policy (HmacSHA1, 6 digits, 30 s, look-ahead 1, not reusable, initial counter 0) and the `max_auth_age` of both required actions |
| `editor_refuses_code_only` | `any[totp, security_key]`: save `400` with the text, preview `200` with `code_only` |
| `no_code_only_way_in` | a cold sign-in (also with `pc_method=totp`) shows no code field and its "Try another way" offers no code; pat's username with a code typed as the password gets no session, in the app or in Keycloak |
| `pat_cap_refused` | pat's password-only session: no "+ Add" on the Sign-in page, and a hand-made `kc_action=CONFIGURE_TOTP` refused by the cap |
| `pat_setup_link_authenticator` | the Hub's setup link with the authenticator option: a passkey, then Keycloak's authenticator setup |
| `password_then_code` | `echo-otp`: the password, then group-gate's step-up asks for the code; amr `pwd` + `otp`; a `sign_in` `LOGIN` with `password`, then a `step_up` `LOGIN` with `totp` (one `LOGIN` per authentication) |
| `sso_stepup_only_code` | pat's password session on `echo-basic`, then `echo-otp`: the step-up `pc_method=totp` asks only for the code |
| `wrong_code_failed` | a wrong code is refused: history "wrong authenticator code", brute-force count 1 |
| `replay_refused` | the same code on two sign-ins in one time step: the second is refused |
| `window` | the previous step's code (−30 s) accepted, a −90 s one refused |
| `fresh_one_code` | under `people` = `e2e-otp` the Hub's `fresh_auth` carries `pc_method=totp`; Keycloak asks for the password, then the code, in one authentication (`LOGIN` `pc_methods` `password,totp`) → `pc_fresh=totp` with `pwd` in `amr`; that proof sets pat's password; a password-only fresh proof → `403` |
| `add_replace_rename_remove` | the Sign-in page's popups with real Keycloak and a virtual key: **+ Add**, **Replace** (`CONFIGURE_TOTP:<id>`: the new code works, the old one is refused), rename (`404` for a passkey id), **Remove** (`delete_credential:<id>`, whose re-authentication never offers a code alone) |
| `fourth_refused` | at 3 the page offers no "+ Add"; a hand-made fourth is refused |
| `history_method_entries` | exactly one added / replaced / removed entry per change (none from `LOGIN` events) |
| `root_impersonating_pat` | root (his security key from `./portcullis invite root`, then the start route with a fresh security-key proof) signed in as pat: `echo-otp` shows the impersonation's needs page (no step-up), and a hand-made `CONFIGURE_TOTP` is refused ("Not while you are signed in as pat."), nothing stored |
| `carol_removes_alice` | alice's setup-link authenticator, removed by carol (`sign_in_help`); a `help` entry in alice's history |
| `admin_no_code_step` | `admin` never gets a code step, and `CONFIGURE_TOTP` is refused (CI only) |
| `no_secret_anywhere` | every secret, and its lowercase and unpadded forms, is absent from `docker compose logs`, the Hub's audit, the history answers and the artifacts |
| `finally` | `echo-otp`, `e2e-otp` and every authenticator removed; `totp` off; `password` and the `people` core page back |

Not in the e2e: that a fresh `totp` never approves a certificate (`409`) is a
Hub unit test (`TestCertFreshNeverTOTP`): under the default people pick a
`pc_fresh=totp` proof is already refused (`403`) by the governing check. That
the Hub refuses a `pc_fresh=totp` without a primary method in `amr` is also a
Hub unit test (a token can't be forged end to end); the e2e checks that every
`pc_fresh=totp` token it gets carries `pwd`. The restore's lost-devices note
(authenticator apps and passkeys removed since the backup work again) is
checked by `build-and-test`'s restore from off-host: the restore's last line
must be that note.

Right after a setup link, group-gate's `people` may lack the new
authenticator for up to about 30 s, so the test waits for it before opening
`echo-otp`.

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

`tests/e2e/e2e_filesharing.py` (Playwright, smbclient 4.19.5) provisions a stack with Samba and Time Machine instances, tests per-person credential creation (a fresh sign-in the app's template accepts — a passkey, or a password under a password-only template —, the password shown once), SMB3 connections with encryption required, revocation latencies (hub-made removal, LLDAP-direct removal, writer demoted to reader), instance and core restores voiding credentials, that no hash appears in any backup or log, and the F58 capability ruling (smbd signals work without `CAP_KILL`). Scenarios:

- Setup: connect_address, ports on 127.0.0.1, size_limit 500GiB / office_milan 10GiB, folder slot via assignment, readers / writers before enable, testparm hardening.
- Sign-in via setup links (alice, bob, carol); fresh auth popup flow (COOP, the authorize parameters, the password once, replay refused).
- SMB3 sessions: Time Machine and Samba list shares, carol writes as `21002:60000`, encryption required, SMB2/NTLMv1/guest/wrong password refused, outside-LAN client refused.
- Revocation: hub-made ≤ 10 s, LLDAP-direct ≤ 75 s, writer demoted ≤ 4 s (session gone, login refused). Measured at 0.8–0.9 s, 3.4–51.8 s, and about 3.6 s.
- Restore: instance restore → credential voided, card says "reset by a restore", re-create works. Core restore → no hash in 45 backup files, `hub_secrets` emptied, credentials voided, uid pool +1000, Samba restarted from Hub.
- Governing template: dave (users_samba, a Hub-set password only), with password on, signs in on `portcullis-fresh-auth` with his password (`prompt=login`, `max_age=0`) and the proof is posted to the people listener: refused (403) while the default (Samba takes no pick) is Standard, accepted once the default is a password-only template (`credential.create` audited with `template=e2e-pw`); his share then works. The default, the template and the password switch are restored in a `finally`.
- No hash visible: `docker inspect`, container logs, `hub_data`, audit, ops, archives, `state.yaml`.

Built like `e2e-settings` (same-named Hub and templates branches, else `main`). Ubuntu 24.04 runners, smbclient pinned at `2:4.19.5+dfsg-4ubuntu9*`. On failure: policy/attributes files, data files, container logs, screenshots, no traces (DOM snapshots would carry the password).

### `e2e-mail` (the mail server)

The whole core stack, the Hub and the domains service (Pebble, the CI-only
fake DNS provider: one fake zone shared by the dns tool and `mail-cert`),
with the `stalwart` app wired (`.github/ci/e2e-mail-start-stack.sh`: the
templates checkout as above, the adapter and `mail-fake` built from the
checkout), mail on for `ci.example.org` and the added domain `team-b.test`,
plus a second Stalwart ("remote", `remote.test`, `.github/ci/e2e-mail-remote.sh`)
on the wired app's egress network (disconnected and reconnected around every
switch; disconnected for good before the restore, since the Hub's void after
it recreates that network, and a foreign container on it would make that
fail). Every navigation of `e2e_mail.py` (`page.goto`, the reload, the fresh
sign-ins that wire, switch and confirm) goes through one helper
(`e2e_mailcheck.navigate`). It retries only when Chromium aborted the
navigation on a network change (`net::ERR_NETWORK_CHANGED`, raised or left on
`chrome-error://`: container starts change the runner's network), at most 4
attempts, each noted in the job summary. **Nothing leaves the runner:** outbound 25,
465 and 587 is rejected outside the stack's networks and every name is the
fake zone's. `tests/e2e/e2e_mail.py` runs, in order:

- **setup**: people in and out of `mail_users`, the list `team`, every account answering RCPT, DKIM Ed25519 and RSA active for both domains (`./portcullis mail rotate`), and the mail passwords created on the Sign-in page (fresh-auth popup, shown once).
- **1 exchange_both_ways**: the remote's `Authentication-Results` show `dkim=pass` for an Ed25519 and an RSA signature, `spf=pass` and `dmarc=pass`; mail from the remote arrives; the remote's DMARC aggregate report reaches `dmarc-reports@` and shows in `GET /api/mail/checks`.
- **2 enrolled_domain_alias**: a person receives at and sends as their `team-b.test` address.
- **3 gtube_rejected_at_data**: GTUBE in the Subject is refused with `550 5.7.1` at DATA; a message scoring between the thresholds lands in Junk with `X-Spam-*` (`between_thresholds_to_junk`).
- **4 mail_password_flow**: shown once and nowhere after the dialog; IMAP 993, SMTP 465 and 587 work; the LLDAP password fails IMAP and the mail password fails LLDAP; the management listener answers `404` from another address and a method-level `forbidden` from the adapter's own; the sixth password is `409`.
- **8 members_only_list**, **9 postmaster_to_admins**: the remote can't post to the members-only list (`550 5.7.1` at RCPT), a member can; `postmaster@` reaches the administrators.
- **5 revoke_within_8s**, **6 leave_ends_idle_session**, **7 recreated_username_fresh_mailbox**: an IMAP session fails within 8 s of the revoke; an IDLE session fails within 8 s of the person's removal from `mail_users`, whose address then gets `550 5.1.1`; a username deleted and created again gets an empty mailbox, the old passwords fail, and `former-<old uuid>` is listed.
- **13 wiring_guards**: wiring `mail-fake` (from a CI-only source) is refused without a fresh proof (403), with a wrong typed id (400), for an AI / MCP actor (403) and for a delegate (403); with all of them it succeeds.
- **11 switch_provider**: a switch to `mail-fake` (honest):
    - the sets are replaced per domain, with the old DKIM keys kept, retiring;
    - every mail password row is `voided` with "the mail server changed on <date>", including one made under `stalwart` just before the switch;
    - the ports reach the fake (no SMTP banner);
    - nothing of `stalwart` runs (the unwire is a compose down) and its volumes stay;
    - `mail.provider_switched` is audited;
    - then it switches back to `stalwart` (which voids again), and IMAP refuses both the old password and the one made before the switch.
- **12 hostile_provider_contained**: `mail-fake` in hostile mode while wired:
    - none of its forbidden records reaches the zone (`mail_records_wrong` names them), and no mass-removal document is sent;
    - the over-wide `allowed_ips` row is revoked (`mail_lan_only_unenforced`);
    - a void whose verification fails stops it (`mail_void_pending`, no container left running). The fake keeps its store in its data volume, so it survives the void-mode start, as a real provider's does. It keeps one password through the void and through the Hub's revoke of it.
- **14 template_change_holds**: the wired template's files change and the Hub syncs: no container is recreated, the provider is held (`mail_provider_refused`), and the mail routes still answer `200` (Ruling R-HH1: the held provider keeps serving); a confirmation clears the hold and the routes keep answering.
- **15 conformance_stalwart**: `run.py --level full` against the wired `stalwart`.
- **16 conformance_fake_api**: `run.py --level api` against `mail-fake`, wired for the run. Then the switch back to `stalwart`, whose store still holds the accounts of 15's conformance documents (Ruling R-SWITCH-BASE-3: kept, a real-world case):
    - its guard refuses the Hub's first document as a mass removal, and the Hub holds it as a pending removal (`mail_mass_removal_pending`);
    - `pending_removal.confirm_phrase` is `remove <n> mailboxes` (`remove 1 mailbox`);
    - `POST /api/mail/confirm-removal` is refused for a non-admin (`403`) and without a fresh sign-in even with the right phrase (`403`); with a proof and a wrong phrase it answers `400` naming the phrase;
    - that same proof with the phrase gets `204` (the phrase is checked before the proof is spent), and `mail.confirm_removal` is audited with the count and the uuids;
    - the sync converges: no pending removal, no `mail_sync_blocked`, the document applied.

Before the backup, alice makes a mail password and it logs in over IMAP: the one scenario 10 judges (every earlier one was voided by the switches).

Then the job runs `./portcullis backup` and `./portcullis restore --yes`, and
`e2e_mail.py restore` (**10 restore_voids_mail_passwords**) checks that the
password made before the backup is refused by IMAP and SMTP AUTH, its row is
voided "reset by a restore" (`mail_credential.void_restore` audited), and the
Sign-in page says "reset by a restore". On failure
it uploads the provider's, the remote's, the domains', Hub, Traefik and
Keycloak logs (never a password: every one is masked as soon as it is known,
and there are no Playwright traces). One scenario on its own:
`.github/ci/local/run-job.sh e2e-mail --scenario 11 --local <checkout>` on a
Docker host, or `-f scenarios="11 switch_provider"` on GitHub
([below](#single-scenario-reruns-scenarios)).

### `e2e-ai` (AI support through mcp-gate)

The first run of the whole chain: an MCP client on the runner host →
Traefik → mcp-gate → the Gitea companion (the official `gitea-mcp`, from the
templates repo) → Gitea, with Keycloak's OAuth (PKCE and `resource`, the Hub's
`portcullis-ai-claude-code` client and its `mcp:*` scopes) and the Hub (AI
settings, the companion switch, the gate files, lazy mint and revoke hooks).
The Hub's template source is the same-named templates branch (else `main`)
with gitea, grafana and the CI `echo` fixture; the CI fixtures declare
`ai.unsupported`. Setup goes through the Hub's admin API as the CI admin
`root`: instances `gitea-b` and a throwaway `echo-del`, gitea, gitea-b and
grafana enabled, alice / bob / carol in their groups, the master switch on
with Claude Code offered (admin flag on), Gitea's companion in read_write,
Grafana's (identity headers) read-only.

**`tests/e2e/mcpclient`** is a stand-in for Claude Code on the official MCP Go
SDK (pinned in its `go.mod`):

- `mcpclient login --client-id <id> --callback-port 33418 --resource <url> [--scope "<scopes>"] --token-file <f> [--ca-file <pem>] [--timeout 5m]`
  prints the authorize URL (Playwright opens it, signs in with a CDP virtual
  authenticator and consents), serves the loopback callback and writes the
  token to the file (0600; tokens are never printed or put on argv);
- `mcpclient call --url <url> --token-file <f> --method tools/list|tools/call [--tool <name> --args <json>] [--protocol <version>] [--elicitation url [--elicit-answer accept|decline|cancel]] [--ca-file <pem>]`
  prints one JSON document (the result, the negotiated protocol and any
  `elicitation/create` requests, or the HTTP status and `WWW-Authenticate`).
  `--elicitation url` declares URL-mode elicitation only and turns off the
  SDK's automatic retry, so a 2026-07-28 `input_required` is printed as sent.

`tests/e2e/e2e_ai.py` scenarios:

1. `gitea_as_alice`: a token for `https://gitea.<d>/mcp`, `tools/list`, and a
   repository listing that shows only alice's repositories.
2. `leaver_refused_and_revoked`: alice removed from `users_gitea` → `403`, and
   her `portcullis-ai-*` Gitea token deleted.
3. `audience_separation`: her Gitea token at gitea-b, `mcp.<d>`, `hub.<d>`
   and `people.<d>` → `401`; one token for two resources (both audiences asserted; Keycloak not minting it fails the scenario) → refused at both.
4. `no_token_crossing`: the MCP token on Gitea's and the people pages → a
   sign-in redirect or `401`, never a page; browser cookies on `/mcp` → `401`.
   This proves the apps refuse the MCP token; that the gate never forwards it
   rests on mcp-gate's unit tests.
5. `destructive_confirmation`: root's `delete_instance` on `hub.<d>/mcp` →
   the confirmation link; bob can't open it; root types the id and touches a
   fresh passkey → approved; the retry runs, a second one needs a new
   confirmation; audited `via: ai` with the client and the confirmation id.
6. `aggregate_lists`: on `mcp.<d>` carol sees `gitea__*`, `grafana__*` and
   `portcullis__my_apps` and calls Grafana through the gate (identity
   headers); bob sees no `grafana__*`; root sees no admin tool.
7. `ai_off`: the master switch off → every resource `503`. While the apps
   restart, a companion host answers `404` (its router is gone with the app),
   which fails closed too.
8. `companion_confirmation`: alice's `label_write` `delete_repo_label` → a
   `people.<d>` confirmation (typed check: the instance label); bob `404`;
   approved → runs once with the canonical arguments; changed arguments → a
   new one; the access log's `confirmation_id`.
9. `url_elicitation_2026`: with URL elicitation declared, a 2026-07-28 call
   gets `input_required` (a Hub D tool and a companion tool); a 2025-11-25
   session gets the gate's `elicitation/create` (mode url) and the Hub's text.
10. `gitea_isolation`: the `gitea-internal` and companion alias resolution, no
    `portcullis-hook-*` token left after mint and revoke, the switch-on's
    `revoke_all` succeeded.
11. `companion_alias_guard`: `./portcullis status` shows no name takeover
    for the real Gitea and Grafana companions; a container outside the
    instance's project answering to `portcullis-mcp-gitea--gitea` is
    flagged, and the real one with it as sharing the name.

Not covered: an approved 2026-07-28 round trip through `requestState`, the
gate's continuation of a confirmed call the companion then asks input for, and
token refresh. Built like `e2e-settings` (same-named Hub and templates
branches, else `main`). Tokens live only in a temp directory outside the
artifacts. On failure: logs, screenshots and traces.

`e2e-instances` runs on `ubuntu-latest`: the echo fixture's `hold` service has
its own pinned `busybox` image, so the Hub's helper image isn't in use when
the job removes it (Docker's containerd image store refuses to remove an image
in use).

**Cross-repo branches.** `ci.yml` also runs on `workflow_dispatch`. On a
branch whose name exists in porelli/portcullis-hub (not `main`, not a tag),
`.github/actions/hub-image` builds the Hub from that branch instead of pulling
`edge`. Likewise, on a branch whose name exists in porelli/portcullis-keycloak
(not `main`, not a tag), `.github/actions/keycloak-image` builds the Keycloak
image from it (`KEYCLOAK_IMAGE=portcullis-keycloak:ci`, `KEYCLOAK_LOCAL=1`);
otherwise it pulls the published `edge` and names its digest in the step
summary. Every job that runs Keycloak uses it, and the cached image lists leave
both images out (unpinned). The Hub's `build.yml` likewise tests against the same-named branch of
the templates and core repos, else `main`.

**Running some jobs only.** `workflow_dispatch` has an input `jobs`
(default `all`): `all`, or job names separated by commas and/or spaces —
`unit-tests`, `build-and-test`, `e2e`, `e2e-instances`, `e2e-signin`,
`e2e-settings`, `e2e-folders`, `e2e-filesharing`, `e2e-ai`. The names match
exactly (`e2e` doesn't run `e2e-ai`); the other jobs are skipped. Every job
needs the first job, `jobs-input`, which fails the run on an unknown name (or
`all` together with names); any subset of the other jobs runs. Push, pull request and `workflow_call`
always run every job (`release.yml` passes no `jobs`; the called workflow's
default is `all`).

```
gh workflow run ci.yml --ref <branch> -R porelli/portcullis -f jobs=build-and-test
gh workflow run ci.yml --ref <branch> -R porelli/portcullis -f jobs="e2e-signin e2e-settings"
```

**Timeouts.** Every job has `timeout-minutes` (about 1.5× its longest green
run, at least 20: 20 for most, `e2e-signin` 40, `e2e-settings` 30), and so
do the slow steps: image loads and local builds 15, the Hub / Keycloak image
20, Playwright installs 10, artifact uploads 10, backup / restore steps 15.
A step that runs out fails instead of hanging. The build-push action's
build-summary / build-record uploads are off (`DOCKER_BUILD_SUMMARY`,
`DOCKER_BUILD_RECORD_UPLOAD` false): nothing reads them, and a failing
artifact service once kept a finished `e2e-settings` job retrying them for
over 30 minutes.

### `e2e-podman` (rootless Podman)

The whole stack under rootless Podman on `ubuntu-26.04`, with the runner user
as the operator ([Rootless Podman](rootless-podman.md)). No artifact carries
`.env`, `secrets/` or a backup.

- **Docker phase** (while Docker still runs): `init --runtime docker` with the
  CI override, one LLDAP person created, `./portcullis backup` copied aside
  (mode `0700`), the sha256 of `certs/ca-chain.crt` recorded, then `down` and
  everything removed (volumes, `.env`, `secrets/`, `certs/`).
- **Setup.** The local, Hub and Keycloak images are built and moved into
  Podman (`docker save | podman load`). Docker is stopped and disabled, and
  the job checks its socket no longer answers. Then podman, passt and uidmap
  are installed, the runner gets 65536 subuids and subgids,
  `ip_unprivileged_port_start` is set to 80, lingering is on and the user
  `podman.socket` and `podman-restart.service` are enabled, and
  `ACME_STAGING=true ./portcullis init --runtime podman` runs with the CI
  override. The Hub's local template sources hold echo, folder-writer and
  scrutiny; `/srv/e2e-pod` is operator-owned with one root-owned child.
- **Checks**, each failing with `FAIL: <what>`:
    - `status --json` has no problems, `runtime.name` is `podman` and `runtime.port_start` is at most 80
    - every pinned network's subnet and range round-trip as in `.env`, and Traefik, Keycloak, the Hub and mcp-gate sit at their pinned addresses
    - every core container has a memory and a pids limit
    - the socket checks of `build-and-test`, the Podman API denials included
    - Traefik's Docker provider lists the `hub@docker` and `people@docker` routers
    - `secrets/hub/core.env` is the operator's on the host and `0:10001` inside the namespace (`podman unshare stat`)
    - the mTLS sign-in and the portal, as in `build-and-test`
    - forward-auth reaches `auth.<domain>` through `host-gateway`
    - `tests/e2e/e2e_podman.py`: `/api/runtime` says `podman`, verified, with the runner's uid as container 0's host id; an echo instance goes through create, enable, disable, backup and restore; the fixer applies on the operator-owned `/srv/e2e-pod` and refuses the root-owned child with `is owned by a host account outside Portcullis' id range` and its path; creating scrutiny answers `409` naming `SYS_RAWIO`
    - **Rebuild and recreate.** After an `up` that rebuilds enroll, the running container uses the new image, and unchanged services aren't recreated
    - **The VPN service** (`.github/ci/e2e-podman-vpn-service-on-rootless-podman.sh`): `vpn init` rootless, `wg` as 10006 without capabilities, `vpn add-device` for an LLDAP person, a `tests/e2e/vpn-client` handshake over the published UDP port and a GET of people.&lt;domain&gt; through the edge and `vpnsecure` (forward-auth's redirect). The host prep writes the operator's `containers.conf` pool line, and the job checks a new network lands in `10.89.0.0/16`
    - **reboot:** after `systemctl restart user@<uid>.service` (every container dies with the user manager), `podman-restart.service` brings the stack back and `status` is clean within 180 s
    - **Docker → Podman round trip:** after a wipe, `init --runtime podman` and `./portcullis restore --yes` of the Docker phase's backup: `.env` keeps `CONTAINER_RUNTIME=podman` and the rootless socket, `status` is clean, `certs/ca-chain.crt` has the recorded sha256, the Docker phase's LLDAP person exists, and the secrets are the operator's on the host
    - **Mail on rootless Podman** (`.github/ci/e2e-podman-mail.sh`): outbound 25 / 465 / 587 rejected for the runner and pasta; `mail enable` refused while `ip_unprivileged_port_start` is above 25 (nothing written), then 25 and `./portcullis mail enable --provider stalwart` (the templates checkout as the Hub's source, the adapter built here): wired, healthy, client addresses rewritten; a cold start keeps the store's key (no plan, no new key); a message from a CI container to the host's port 25 is delivered to an LLDAP person; the doctor names `mail_client_ip_rewritten`; no ban after 110 failed logins (with rewritten addresses every client is the gateway, so a ban would lock everyone out); the gate refuses a raw start without `.present` in the slot volume
- On failure it uploads the container logs only.

### `e2e-vpn` (VPN-only access)

The whole stack with the VPN service (`COMPOSE_PROFILES=wg`, `./portcullis vpn init`, `ACME_STAGING=true`, 45 min), the Hub (same-named Hub branch) with one local template source: the CI template echo (instance `echo-vpn`, VPN-only) and the templates repo's headscale (same-named templates branch, else main; the job fails without its `vpn:` block), wired as a provider with a 15 s refresh. A CoreDNS stub is the built-in resolver's upstream. Clients have no privileges: `tests/e2e/vpn-client` (a Go WireGuard client on the same wireguard-go / gVisor / miekg/dns pins, through a netstack tunnel, one JSON line per call) for the built-in VPN, and userspace `tailscaled` containers for the tailnet. `tests/e2e/e2e_vpn.py` (Playwright for setup links, the `/vpn/` fresh sign-in and Headscale's OIDC registration) runs these cases, each failing with `FAIL: <what>`:

| Case | Checks |
|------|--------|
| `websecure_vpn_required` | echo-vpn on `websecure` answers only `/vpn-required` |
| `builtin_signin_demanded` | alice's built-in device without a session: redirected to sign in |
| `builtin_opens` | alice's device with alice's session opens echo-vpn |
| `builtin_not_yours` | bob's device (made with the host CLI) with alice's session: "this device isn't yours" |
| `builtin_dns` | the built-in resolver: echo-vpn.&lt;d&gt; A `10.213.0.1`, AAAA no data, no AD |
| `tailnet_register` | a tailscaled node registered as alice through Keycloak |
| `tailnet_opens`, `tailnet_dns` | through the Headscale gateway with alice's session; MagicDNS points echo-vpn.&lt;d&gt; at the gateway |
| `via_builtin` | *Through* only the built-in VPN: the tailnet device 403, the built-in one opens |
| `tailnet_local_denied` | a node of a local (non-OIDC) Headscale user never opens |
| `gateway_claims_builtin`, `gateway_wrong_source`, `gateway_wrong_port` | a gateway claiming a built-in address is closed (`outside_ranges`); a valid header from another address is closed (`wrong_gateway`); nothing listens on other edge ports |
| `valid_until_expired` | the Hub stopped and `vpn.json` past its `valid_until`: open connections closed, no new ones |
| `builtin_revoked` | bob's device revoked: an open connection closed, the handshake fails within 5 s |
| `tailnet_node_deleted` | alice's node deleted in Headscale: an open connection closed, denied within refresh + 10 s |
| `gateway_stopped`, `identity_hook_broken`, `wg_stopped` | only that path fails; once stale the tailnet is denied and the built-in VPN isn't; with `wg` down echo-vpn is unreachable on both paths, never on the internet |
| `server_mode` | `vpn mode server --force`: on `websecure` only the public set answers; `vpn mode apps` with `wg` stopped restores everything |

Keys, configurations and cookies live only in a 0700 temp directory; setup links are masked and there are no Playwright traces. The artifacts are logs and `wg`'s status, never `vpn.json`'s keys, `.env`, `secrets/` or configurations.

### `e2e-servers` and `e2e-servers-podman` (multiple servers)

Two thin jobs (60 min each, `ubuntu-26.04`; the steps are
`.github/ci/e2e-servers-{setup,worker,rogue,asserts}.sh`) test [worker
servers](servers.md) end to end. The primary runs on Docker: the stack and
the Hub, with the CI template `servers-echo` (busybox httpd and a CGI that
echoes the request's `Cookie` header, sets a host-only and a parent-domain
cookie, prints a volume marker and streams a long response) and
`./portcullis link init`. `.github/actions/hub-image` builds the Hub, the
agent and the relay from the same-named Hub branch with `GO_TAGS=e2etest`
(the CI-only clock-offset and oversized-info hooks;
[contracts §17.3](../guides/integration-contracts.md#173-servers-in-the-hub)).

- **`e2e-servers`**: the workers are pinned `docker:dind` containers, each
  with a copy of the checkout. They run **privileged, in CI only**: the one
  reviewed exception (a `test_cli` lint allows `--privileged` only on a
  `# reviewed exception` line of `e2e-servers-worker.sh` and the local
  `e2e-k3s-local.sh`).
- **`e2e-servers-podman`**: the worker is rootless Podman as a second runner
  user, `worker`, with its own user socket and linger.

Each worker joins with `./portcullis worker join --runtime …`, the code on
stdin. `tests/e2e/e2e_servers.py` (Playwright for the setup links and the
Hub's fresh sign-ins, the Hub's API as admin) runs, in order:

| Case | Checks |
|------|--------|
| `join_ok`, `join_code_reused_refused`, `join_code_expired_refused` | a join works; a used code and an expired one (the Hub's clock moved 16 minutes on) are refused |
| `echo_on_worker_signed_in`, `echo_on_worker_denied_without_sign_in` | an echo on the worker answers through the primary after sign-in, with the same template and tier as one on the primary, its containers on the worker only; refused without sign-in |
| `stream_non_browser_clients` | `curl --http1.1` and `--http2` with alice's cookies (a 0600 header file) stream the echo's `?stream` through Traefik, forward-auth and the relay: the first ticks within 5 s |
| `no_portcullis_cookie_reaches_app`, `parent_domain_set_cookie_stripped` | the app never sees a Portcullis cookie; its `Set-Cookie; Domain=…` arrives host-only |
| `move_worker_primary_worker_keeps_data`, `move_back_onto_kept_copy_refused` | worker → primary → worker (*Undo move*) keeps the volume marker; a direct move onto a server holding a kept copy is `409` |
| `wg_stopped_fails_closed`, `wg_back_routes_again` | with `wg` stopped the worker app is unreachable and its containers still run; it routes again after |
| `worker_break_glass_stop_start` | `./portcullis worker stop` / `start` of the echo on the worker, as its operator (the rootless Podman user on the podman job); it routes again |
| `rogue_worker` | from the worker's own tunnel, 2000+ TCP ports of `10.214.0.1` all answer with a reset (`tests/e2e/vpn-client --probe`; a timeout doesn't count as closed); another worker's certificate makes the server offline (dind job), and a certificate `pki_node` issued for the worker's own name with another key and serial is refused by the pin (`server_identity_mismatch` in the Hub's log); the echo's own token tunnels (`200`, the control) and data CONNECTs without a token, with a bogus one or with another instance's are `403`; an oversized `/v1/info` makes it offline |
| `revoke_drops_handshake_and_rotates` | a revoke drops the worker from link within 15 s and changes an OIDC instance's Keycloak client secret |
| `revoke_cuts_relayed_stream` | a long-lived `fetch()` stream in alice's page through the relay ends at most 10 s after the revoke |
| `socket_rule_both_stacks` | live from each engine: on the primary only the two socket proxies mount the socket, on each worker only `socket-proxy-agent`, all read-only |

The join code is kept masked, in one 0600 file in a 0700 temp directory,
and piped to the worker script; the test checks it never shows in the
script's output, the op record or the Hub's and `wg`'s logs. On failure the
artifacts are logs only, and any file containing `pcj1.` is dropped.

### `e2e-k3s` (Kubernetes)

The whole stack on a real k3s on `ubuntu-26.04` (90 min), never kind or k3d ([Kubernetes](kubernetes.md)). No artifact carries `.env`, `secrets/` or a backup; on failure it uploads pods, events, logs and k3s's journal only.

- **Docker phase**: `init --runtime docker`, one LLDAP person, a `./portcullis backup` copied aside (mode `0700`), then everything wiped. This backup is the cross-runtime restore's input.
- **Install k3s** (`.github/ci/e2e-k3s-install.sh --netns-client`): k3s `v1.37.2+k3s1` (the default; `K3S_LINE=1.33` installs the floor's pin `v1.33.13+k3s2` instead, as the local runner can), `kubectl` and `helm` at pinned versions, each checked against its sha256, as a systemd unit with `--disable=traefik --secrets-encryption --kubelet-arg=pod-max-pids=1024`, the kubeconfig context `ci`. A network namespace `ext` (198.51.100.2) joined to the node (198.51.100.1, `--node-external-ip`) is an outside client.
- **init**: `init --runtime kubernetes --kube-context ci` with local images (`PORTCULLIS_KUBE_IMAGES=local`, the same-named Hub and Keycloak branches' images included).
- **Seed**: the templates (same-named branch, else main), a template source, the fixer's folder, a certificate to revoke.
- **Assertions** (`.github/ci/e2e-k3s-assert.sh`), each failing with `FAIL: <what>`: the NetworkPolicy probe; PSA `restricted` on core; Keycloak reachable only from Traefik and `kcinternal` only from the core clients; an app pod reaches no core service, `:6443` or `:10250`; the client address kept through ServiceLB from `ext`, and `status`'s `--node-external-ip` warning; PVC owners on the node, and a PVC without its annotations staying `Pending`; the admission guard per binding with the Hub's token, and `pods/exec` create-only; revocation within 10 s; the VPN port rules. It also runs:
    - `e2e-k3s-edge-admission.sh`: `portcullis-edge` as the Hub's ServiceAccount, each refusal from `portcullis-edge-guard-routes-<generation>`, each control admitted; the ExternalName Service vectors (another instance's name, a core name, an FQDN, an IP, a label or name mismatch, ports, a selector, `externalIPs`, deleting a core Service, relabelling) included, and a `parentRef` to a core IngressRoute, `ingressClassName`, another route syntax, `tls.domains` and a Middleware named after another instance refused;
    - `e2e-k3s-edge-route.sh`: a request routed end to end through Traefik → the Hub-shaped edge ExternalName Service → a pod in the apps namespace;
    - `e2e-k3s-apps-admission.sh`: the apps policies' ruled shapes (root helpers, one-shot Jobs, init containers; host-path pods without a non-root uid, with group 0 or with escalation; claims of the wrong class, name or mode, or changed by another identity than the volume binder and the PVC protection controller in their exact ways), each admitted or refused by its own binding, and the Hub's ServiceAccount unable to delete or rewrite the chart's `default-deny`;
    - `e2e-k3s-chart-admission.sh`: every chart object in the apps and edge namespaces admitted as the CLI's identity, and the ones the policies judge refused as the Hub's;
    - `e2e-k3s-rebind.sh`: while the Hub's ServiceAccount creates a route on a reserved host in a loop, two `up`s change the params generation; not one create may be admitted, and afterwards exactly one generation's six bindings exist.
- **The Hub** (`tests/e2e/e2e_k3s.py`): instances deployed, backed up, restored and deleted; the fixer.
- **VPN**: `vpn init` with the built-in VPN on, a device handshake through `wg-people`, `vpn mode admin` and the break-glass `vpn mode apps`.
- **Docker → Kubernetes restore**: the Docker phase's backup restored onto the cluster.

`.github/ci/e2e-k3s-local.sh steps [--from <n>] [--to <n>]` runs the job's `run:` steps locally on a Linux host (read from `ci.yml`, so they can't drift), amd64 or arm64.

### `e2e-ssh` (SSH access and the CLI)

The stack plus the Hub and two local sshd containers on `portcullis-proxy`
(`tests/e2e/sshd/Dockerfile`, a pinned `debian:13-slim`): `web-1` enrolled
as a managed host with `--service none`, `web-2` set up with `host trust`.
The CLI comes out of the Hub image under test and runs on the runner with
`--no-browser`; Playwright opens the printed URL with the virtual security
key, and the runner's own `ssh-agent` / `ssh` log in. The Hub's admin writes
that need a fresh sign-in (SSH on, a new host, the privileged grant, removing
a host) get one through the Hub listener's fresh-auth flow. Cases
(`tests/e2e/e2e_ssh.py`; each a `check()`, so `-f scenarios=` reruns one):
`setup` (`ssh_admins` → `all` with full sudo refused without the typed group
name), alice reaches both hosts without sudo and gets sudo on the managed
host within one long-poll after joining `ssh_admins` and logging in again;
bob's `s:deploy@web` shows `ID pc:bob:web:` in the sshd log and bob has no
account of his own; `root` is refused on both hosts; a sign-in code works
once at `POST ssh/certificates` and a key proof by another key is refused
(`403`); the CI Keycloak's `portcullis-cli` has the contract's shape
(`127.0.0.1:40000` and `localhost:38917` refused); leaving the groups
locks alice out of `web-1` within seconds and `web-2` after one
`host revoked-keys` pull; with the Hub stopped, bob's certificate and the
break-glass account's own key still work and `./portcullis ssh
breakglass-cert` signs one from Vault (audited at the Hub's next start);
and no sign-in code, PKCE verifier, enrolment code or private key appears in
the logs, the Hub's audit, `issued.jsonl` or the CLI's output. On failure
the logs are collected and withheld whole if anything looks like a secret
(`.github/ci/e2e-ssh-artifacts.sh`). Covered by the Hub's own tests instead
of here: password / authenticator-code / impersonated sign-ins getting
nothing, drift healing and the main-config override Problem (the real-sshd
container test), forged reports and oversized bundles.

**Hub-side tests.** `go test -tags sshd ./cmd/portcullis/internal/host/`
runs the host agent against real sshd in Debian, Ubuntu and Rocky containers
(the Hub CI's "host agent against real sshd" step, `PORTCULLIS_DOCKER_TEST=require`).
The opt-in live tests are `TestLiveCLIObjects` (Keycloak, the
`portcullis-cli` client and its refused redirect URIs) and core's
`TestLiveSSHVault` (`PORTCULLIS_VAULT_LIVE_ADDR` / `PORTCULLIS_VAULT_LIVE_TOKEN`:
the real `enroll.hcl` against Vault — every refusal of the spike, among them
no role above 12 h, the four key types, an empty principal list signing
nothing, `source-address` from the role, the host sign's `cert_type`). Core
CI's unit-tests runs it on every push against the compose pin of Vault in
dev mode (step "enroll SSH against a real Vault"), next to "Shared SSH
vectors match the Hub" (`enroll/testdata/ssh_vectors.json` = the Hub's
`internal/cliapi/testdata/vectors.json`); build-and-test's "Test enroll
AppRole is least-privilege" checks the SSH paths on the real stack after
`pki setup`.

### Caching

Core CI caches what it safely can. Caches are written only on pushes to `main`.

- **Infra and monitoring images:** cached by the local composite action `.github/actions/cached-images`.
    - The cache key is the runner image (`ImageOS`: `ubuntu24`, `ubuntu26`, …; `self-hosted` on the builder) and a hash of each job's pinned image list. Refs without a digest are refused. A tarball saved by one image's Docker doesn't load reliably on another's, so jobs on 24.04 and 26.04 never share one.
    - After `docker load`, every name set by the tarball is removed. Each ref is then re-pulled by its pinned digest (with retry and backoff), so the engine reuses a loaded image only if its content-addressed ID matches the registry's config digest.
- **enroll and group-gate images:** buildx layer cache (`type=gha`).
- **Go:** module and build cache through `setup-go`, with `go mod verify`.
- **Python:** pip and Playwright browsers, cached on the runner image (`ImageOS`, as above: Playwright's browser builds are per distro) and the pinned requirements file (`group-gate/requirements.txt` has `--require-hashes`).
- **Runner images:** every job that installs Playwright's system packages (`playwright install-deps`) runs on `ubuntu-24.04`; the 26.04 image lacks some of its font packages. e2e-podman, e2e-k3s and e2e-servers* stay on `ubuntu-26.04` (e2e-servers installs Playwright's deps there, which resolve).

The revocation check waits up to 180s, because Vault rebuilds delta CRLs at most once a minute.

### Releases (`release.yml`)

Runs on `v*` tags:

1. **`preflight`** checks four things:
    - The tag is `vMAJOR.MINOR.PATCH` and `CHANGELOG.md` has its `## [X.Y.Z]` section.
    - The `HUB_IMAGE` default in `docker-compose.yml` is `ghcr.io/porelli/portcullis-hub:A.B.C@sha256:…`, where `vA.B.C` is a published (non-draft, non-prerelease) Hub release and the tag still resolves to that digest.
    - The `KEYCLOAK_IMAGE` default is `ghcr.io/porelli/portcullis-keycloak:D.E.F@sha256:…` in the same way (a published portcullis-keycloak release whose tag still resolves to that digest).
    - The `AGENT_IMAGE` default (`docker-compose.worker.yml`) and the `RELAY_IMAGE` default (`docker-compose.yml`) are `ghcr.io/porelli/portcullis-agent:A.B.C@sha256:…` and `ghcr.io/porelli/portcullis-relay:A.B.C@sha256:…`, the same Hub release's version and digests ([Multiple servers](servers.md)).
2. **`ci`** runs the full `ci.yml` on the tagged commit.
3. **`release`** builds a reproducible `portcullis-X.Y.Z.tar.gz` (the checkout without `.git`, plus `VERSION`) and its `.sha256`. It then creates the GitHub release with the changelog section, the pinned Hub and Keycloak images and generated notes.

See [Upgrading & Releases](upgrading.md#core-releases).

### Dependabot

`.github/dependabot.yml` proposes weekly, grouped updates for:

- the compose images
- the enroll Dockerfile and Go modules
- the GitHub Actions
- the e2e Python requirements

Image constants in the CLI and inline images in workflows are not covered by
Dependabot. They are still checked by the pin-enforcement step.

#### Auto-merge

Core, the Hub and the templates share one auto-merge workflow,
`.github/workflows/dependabot-automerge.yml`. Its logic lives in
`.github/automerge/automerge.sh`, which is identical in all three repos and
tested by `.github/automerge/test.sh`. The workflow runs after the required
workflows finish on a Dependabot PR and never checks out PR code:

- **Patch, minor and digest-only** updates are squash-merged once every
  required workflow passed on the PR's head commit. The PR must be
  Dependabot's own single, GitHub-signed commit.
- **Majors** (or updates of unknown type) get the `major-update` label and stay
  open.
- **Pre-releases** are closed.
- **Red CI** opens an `update-failed` issue.

**A merge that fails although CI passed gets at most one re-attempt.** Only
GitHub's "Base branch was modified" error is re-attempted. It happens when
another PR merged at the same moment. The workflow waits about 10 seconds,
then tries the merge once more at the same tested commit. Anything else, such
as an HTTP 5xx, is not retried. If the merge still fails, the run fails and
its error names the cause and the command to retry by hand:

```bash
gh workflow run dependabot-automerge.yml -f pr=<n> -f dry_run=false
```

Run it from a checkout of the repo, or add `-R porelli/<repo>`. Check the PR
first: a 5xx can still have merged it. Leave out `-f dry_run=false` to see
the decision without acting on it.

The workflow doesn't ask Dependabot to rebase. Dependabot ignores
`@dependabot rebase` comments posted with the workflow's `GITHUB_TOKEN` (or by
any GitHub App) and replies "only users with push access can use that
command".

### Running the core tests locally

```bash
python3 tests/test_group_gate.py   # in a venv with group-gate/requirements.txt
python3 tests/test_e2e_fsops.py
python3 tests/test_e2e_mailcheck.py
bash tests/test_cli.sh
bash tests/test_shell_libs.sh
(cd enroll && go test ./...)
(cd mcp-gate && go vet ./... && go test -race ./...)
shellcheck -S warning portcullis scripts/lib/*.sh tests/*.sh tests/e2e/*.sh
# compose validity without Docker containers:
PORTCULLIS_ROOT=/tmp/x ./portcullis init --env-only --non-interactive --domain ci.example.org --dns-provider none
```

### Running a CI job on a Docker host (`run-job.sh`)

`.github/ci/local/run-job.sh <job>` runs one `ci.yml` job on a Linux host
with Docker (the shared dev builder), step by step as GitHub's runner does,
and cleans up after itself:

```bash
.github/ci/local/run-job.sh build-and-test                  # main, fresh clone from GitHub
.github/ci/local/run-job.sh e2e-mail --scenario 4           # one scenario (+ its setup)
.github/ci/local/run-job.sh e2e-signin --ref mybranch       # a pushed branch
.github/ci/local/run-job.sh e2e-ai --local ~/w/portcullis   # a working tree, uncommitted changes included
.github/ci/local/run-job.sh e2e --keep                      # keep the container to look around
.github/ci/local/run-job.sh --cleanup <container>           # …then remove it
```

- **Isolation.** Every run is its own privileged Ubuntu 24.04 system
  container `pcci-<job>-<id>` (`.github/ci/local/Dockerfile`: systemd, its
  own dockerd, user `runner` 1001 with passwordless sudo, Docker CE + buildx +
  compose, jq, yq, shellcheck, python3, gcc, Node.js LTS, Playwright's
  system packages) on its own bridge network (`10.250.<n>.0/24`), 4 CPUs /
  16 GB like a GitHub runner (`--cpus` / `--memory`); `/tmp`, `/srv` and the
  workspace are volumes (ext4 with ACLs, as on GitHub) and dockerd's
  data-root is `/var/lib/docker-store/docker` (a container's mountinfo names
  `…/docker/containers/<id>/`, as the Hub's tests expect). Every job and step
  `timeout-minutes` is multiplied by `--timeout-factor` (default 1.5: ci.yml's
  limits are sized for a fresh GitHub runner). The job's compose
  project, its fixed networks (172.30/172.31), published ports, `/etc/hosts`
  lines and `/tmp` files are the container's own, so several runs (and
  other work on the host) never collide; the compose project inside stays
  `portcullis` because the steps name `portcullis_*` volumes. The checkout
  is a fresh clone in `~/w/ci-local/<id>/`, copied into the workspace
  volume at `/home/runner/work/portcullis/portcullis`. Afterwards the
  container, its network and its volumes are removed and the clone deleted;
  `run.log` and uploaded artifacts stay in `~/w/ci-local/<id>/` (pruned
  after 7 days).
- **Steps.** `.github/ci/local/steps.py` reads the job from `ci.yml` (so
  it can't drift) and runs it like Actions: workflow / job / step `env`
  with `${{ }}` expressions, `if:` (default `success()`, `always()`,
  `failure()`), Actions' default shells, `working-directory`,
  `timeout-minutes`, `continue-on-error`, `GITHUB_ENV` / `GITHUB_OUTPUT` /
  `GITHUB_PATH` / `GITHUB_STEP_SUMMARY`, step outputs, and the local
  composite actions (`cached-images`, `hub-image`, `keycloak-image`). The
  event is a `workflow_dispatch` of the checked-out branch (nothing saves
  caches; same-named Hub / Keycloak / templates branches are used as in
  CI). `uses:` steps that need GitHub are emulated: `actions/checkout` (the
  workspace is already there; another repository is cloned),
  `actions/setup-go` (Go from go.dev, sha256-checked), `actions/cache*`
  (always a miss), `actions/upload-artifact` (copied to the run directory),
  `docker/setup-buildx-action` (no-op), `docker/build-push-action`
  (`docker buildx build --load`, no `gha` layer cache, never a push).
- **Caches.** Unless `--no-cache`: the job's image store (`pcci-cache-<job>-*`
  volumes; one run of a job at a time uses it, a concurrent one gets a
  throwaway store) — sanitized before every run: no container, volume or
  network survives, and every image name not backed by a registry pull of
  that repository is removed — and the shared pip / Playwright / go-build
  and Go module caches. The Go toolchain is downloaded every run.
- **Not here:** `e2e-podman` (stops the runner's Docker) and `e2e-k3s`
  (installs k3s; use `.github/ci/e2e-k3s-local.sh container`). The Actions
  layer cache (`type=gha`) and artifact service don't exist locally.

The builder (Ubuntu 24.04) also has rootless Podman for user `pcpodman`
(`sudo -iu pcpodman`; `DOCKER_HOST` is its user socket, so `docker` /
`docker compose` talk to Podman; netavark, pasta, slirp4netns; Ubuntu's
Podman 4.9 — CI's `e2e-podman` runs 26.04's 5.x), Node.js LTS (the Hub's
web tests) and `docker:dind` works privileged (e2e-servers' dind workers).

### Single-scenario reruns (`scenarios`)

`gh workflow run ci.yml --ref <branch> -f jobs=e2e-mail -f scenarios="4 members_only_list"`
runs only those scenarios of the e2e runners (`tests/e2e/*.py`), plus their
setup; empty = all. `E2E_SCENARIOS` (the workflow's env) carries it to the
runners, and `run-job.sh --scenario` sets the same. A scenario's name comes
from its `check()` name: the text before the first `:` (or the whole name),
parenthesised parts dropped, split on `,` `+` `/`, with an optional leading
number — `"4 mail_password_flow"` is `4` and `mail_password_flow`,
`"cross_domain_sso: …"` is `cross_domain_sso`; a check whose name gives no
identifier (`"alice, bob and carol: setup link → passkey → portal"`) is
setup and always runs, as do `setup`, `seed`, `finally` and what a runner
declares with `scenarios.always()` (e2e_ai's `ai_on`, e2e_instances'
`alice`). A named scenario also pulls in the scenarios whose checks set the
`state` keys it `needs()` (read from the source with `ast`, transitively);
state built any other way isn't seen — such a scenario fails closed with
"needs …": name that one too. `python3 tests/e2e/scenarios.py list` names
every scenario; `jobs-input` fails the run on a name none of the chosen
jobs' runners knows (`scenarios.py check`), and each runner fails at import
on a name no runner knows. Only the Python runners' checks are filtered:
the job's shell steps (stack start, backups, shell assertions) still run.

### The self-hosted builder runner (`runner: builder`)

`gh workflow run ci.yml --ref <branch> -f runner=builder [-f jobs=…]` (core)
or `gh workflow run build.yml --ref <branch> -f runner=builder` (Hub: the
`test` job only; `build` — GHCR push, cosign's OIDC token — never leaves
GitHub) runs the jobs on the dev builder's ephemeral runner instead of
`ubuntu-latest`. `runs-on` resolves to `[self-hosted, linux, x64,
pc-builder]` only when `github.event_name == 'workflow_dispatch'` and the
input is `builder`; push, pull_request and `workflow_call` (releases) always
get GitHub's runners, and `e2e-podman` / `e2e-k3s` never use it.

On the builder (`.github/ci/local/runner/`, installed by `sudo
.github/ci/local/runner/install.sh`): user `ghrunner` (system user, no
password, no sudo, in the `docker` group — root-equivalent on the host),
`pcci-runner@portcullis.service` and `pcci-runner@portcullis-hub.service`
(`runner-loop.sh`): each start registers one ephemeral runner
(`pc-builder-portcullis` / `pc-builder-portcullis-hub`, repo level, label
`pc-builder`, `--ephemeral`) inside a fresh privileged job container (the
`run-job.sh` image with the official actions/runner), takes one job, and is
removed with the container; systemd starts the next. Every job gets a fresh
workspace, `/srv`, image store and tool cache; only pip / Playwright /
go-build and the Go module cache (`GOFLAGS=-mod=readonly`) persist per repo.
The runner's `ACTIONS_RUNNER_HOOK_JOB_STARTED` hook
(`job-started-hook.sh`) refuses — before any step — every job that isn't a
`workflow_dispatch` of that repo's `ci.yml` / `build.yml` on a branch,
dispatched (actor and triggering actor) by the repository owner: the
privileged container and the shared caches are acceptable only under that
rule. Both repos require approval for fork pull-request workflows from all
outside contributors. A builder job never writes GitHub's shared Actions cache
(GitHub-hosted runs restore it): every cache-writing step of a
builder-switchable job carries `!(github.event_name == 'workflow_dispatch'
&& inputs.runner == 'builder')` or writes only on a push (setup-go's
`cache`, `actions/cache/save`, build-push's `cache-to`, cached-images'
`save`), checked by `tests/lint_builder_cache.sh` (core unit-tests; a byte
copy runs in the Hub's `test` job). Registration tokens come from `/etc/pcci-runner/gh-pat`
(a fine-grained token for the two repositories with Administration: read and
write; unattended) or, without it, a token dropped into
`/var/lib/pcci-runner/tokens/<repo>.json` (`gh api -X POST
repos/porelli/<repo>/actions/runners/registration-token`, one registration
each). Removal: `sudo .github/ci/local/runner/uninstall.sh`, then delete the
registrations (`gh api repos/porelli/<repo>/actions/runners` →
`gh api -X DELETE repos/porelli/<repo>/actions/runners/<id>`).

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
- `python -m unittest discover -s tests`: the validator's own tests, including
  `AITests` (the `ai:` block rule for rule with the Hub's `ValidateAI`: both
  forms, companions, identity modes, reserved names and variables, trust
  networks, the `ai.chat` rules) and `RuntimeCompatTests` (the shared runtime
  vectors for rootless Podman and Kubernetes, the committed classification,
  `PORTCULLIS_UNPRIVILEGED_PORT_START` refused in templates, the expected
  refusals and limits).
- **Runtime classification.** `python tests/validate.py --runtime` prints
  each template's status and reasons for rootless Podman (at port start 80)
  and for Kubernetes; it must equal the committed `tests/runtime.txt`, so a
  change to the classification shows up in review. "Runtime vectors match
  the Hub" compares `tests/runtime_vectors.json` byte for byte with the
  Hub's `internal/templates/testdata/runtime_vectors.json` on the
  same-named Hub branch, else main.
- **Mail providers.** `MailTests` checks the `mail:` block rule for rule with
  the Hub's `ValidateMail`, on the shared vectors `tests/mail_vectors.json`;
  "Mail vectors match the Hub" compares that file byte for byte with the
  Hub's `internal/templates/testdata/mail_vectors.json` on the same-named Hub
  branch, else main. "stalwart gate unit tests"
  (`tests/mail/test_gate_entrypoint.sh`, under `dash`) run the `stalwart`
  app's start gate with a stub server: every case of the slot predicate, the
  recovery-mode refusal, the job's own starts, `--check` and the store lock.
- `tests/trust/test_grafana_trust.sh`: Grafana's `trust.sh` (the AI trust
  network allowlist) against stubbed `ip` output, including the ambiguous
  layouts it must refuse.

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
3. the app started with `tests/lib.sh compose_up`, containers ready: every
   service without compose `profiles:` and those of the selected profiles
   (`COMPOSE_PROFILES` when set — `*` = every profile —, else the profiles the
   setup choices' defaults start, as the Hub does; `compose_up` starts the
   same);
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

**AI support in the app tests.** `gitea.sh`, `grafana.sh`, `nextcloud.sh` and
`homeassistant.sh` run their mint / revoke / `on_change` hooks the way the Hub
does (argv verbatim, JSON on stdin, split output) and check that a credential
never reaches an argv or a log. `nextcloud.sh` starts the companion and
checks per-person identity (one person's app password sees only their files;
no credential, nothing; a bad one, `401`). `grafana.sh` checks the trust
network (internal, exactly Grafana and the companion, Grafana's allowlist
without the gateway, broadcast and its own address) and that a spoofed
`X-Forwarded-User` from elsewhere on `portcullis-proxy` isn't signed in.

**Setup choices in the app tests.** `tests/lib.sh` `compose_up` selects the
compose profiles the setup choices' defaults start (`COMPOSE_PROFILES`, as the
Hub writes it; a test picks another choice by exporting `COMPOSE_PROFILES` and
the option's variable itself), and `compose_down` takes down every profile
(`--profile '*'`). `nextcloud.sh` runs its full suite on the default database,
PostgreSQL, then installs once more on MySQL / MariaDB and on SQLite: each
engine is the one Nextcloud uses (`dbtype`, `dbhost`, a `user_oidc` row it
reads back), only that engine's database server runs, and a marker written
before the whole project goes down is read back after it comes up again.
`ai-chat.sh` renders `librechat.yaml` from `ai-providers.json` (secrets only
as `${VAR}` references, a refused file fails closed), checks the access-group
restriction and the MCP OAuth callback. `write_ai_providers_override` (below)
emulates the Hub's delivery to an AI page.

### Test helpers (`tests/lib.sh`)

| Area | Functions |
|------|-----------|
| Output | `pass`, `fail`, `info`, `section`, `report` |
| Waiting | `wait_for_url URL TIMEOUT NAME`, `wait_for_container` |
| Keycloak | `keycloak_admin_token`, `keycloak_user_token`, `keycloak_enable_direct_grant`, `keycloak_register_client` |
| LLDAP | `lldap_token`, `lldap_graphql`, `lldap_create_user`, `lldap_create_group`, `lldap_add_to_group`, `lldap_sync_keycloak` |
| Compose | `compose_up APP`, `compose_down APP`, `app_container_ip APP`, `app_logs APP` |
| Assertions | `assert_http_code URL CODE`, `assert_redirect_to_keycloak URL`, `assert_redirect_contains URL STRING`, `assert_body_contains URL STRING`, `assert_container_can_reach CONTAINER URL` |
| Public exceptions | `public_routed_prefixes <manifest> <all\|listed> [token…]` prints what the Hub's public router opens; `write_public_override <app> <service> <host-arg> <tier> <out> <entry…>` writes the override labels the Hub would generate (tier for every router, public router behind `portcullis-public-guard@docker` with static-only supporting paths, exact paths, strip middleware); pass it to `compose_up` with `COMPOSE_OVERRIDE=<file>`. `write_public_policy <sub> <manifest> <mode>` writes the version-3 policy entry the Hub would publish into core's `hub_data` volume, so core's real public guard runs (`clear_public_policy` empties it). `assert_public_path <host> <path> [curl args]` / `assert_gated_path …` / `assert_public_refused …` send HTTPS requests through Traefik on the runner (no certificate) and check the app answers / the request is redirected to `auth.<domain>` / the guard answers 403. `grafana.sh` uses them: a listed dashboard token is public; an unlisted token, `/`, `/api/user` and `/public/build/` stay gated; Grafana login cookies (also PHP-mangled spellings), `Authorization`, `X-Access-Token` and `auth_token` query variants are refused by the guard. It needs a core with `/public-guard` (`.core-ref`). `nextcloud.sh` and `immich.sh` check their path lists statically |
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
A `workflow_dispatch` with `-f runner=builder` runs the `test` job on the
dev builder's ephemeral runner (see [the self-hosted builder
runner](#the-self-hosted-builder-runner-runner-builder)); `build` always
runs on GitHub.

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
    `TestPeopleListenerHasNoAppRoutes` checks that the people listener registers exactly the directory routes plus the nine caller-only My apps routes (`GET /api/me/apps`, `PUT` and `DELETE /api/me/apps/{instance}/values/{key}`, `POST` and `DELETE /api/me/apps/{instance}/credentials/{key}`, `GET /api/me/ai`, `DELETE /api/me/ai/connections/{client}`, `GET /confirm/{id}`, `POST /api/me/confirmations/{id}`), and no app/policy/drift/compose/settings/Docker routes.
    **Signing in as someone else** is tested in `internal/hub/impersonation*_test.go` (the start rules and refusal texts, the published file, stop, expiry, the apps opened and the person's notice), `internal/httpapi/impersonation_test.go` and `middleware_test.go` (the routes and the read-only rule), `webui_impersonation_test.go` (the banner, the Stop page, the Sign-in tab's dialog and the Settings switch) and `internal/signinhistory/impersonation_test.go` (the history entries).
    **AI support** is tested per package: `internal/aigate` decodes and re-encodes the shared §15.4 vector byte for byte (the same files as mcp-gate's `internal/config/testdata/`); the gate files (populations, clients, fail-closed rebuilds), the credential store (`TestHubHoldsNoAgeIdentity`: no Hub code can decrypt), mint and revoke (single flight, exit 3, leavers, `app_oauth` records), the switches, the confirmations, the Keycloak AI clients against the `kctest` realm, and the Portcullis MCP: every tool's twin both ways (`TestAdminToolsSameAsHTTP`, `TestPeopleToolParity`), no secret argument name (`TestNoSecretArgNames`), no token echoed by any tool (`TestTokenNotEchoed`), the per-call classes. `TestLiveAIObjects` runs the AI client checks against a real Keycloak when `PORTCULLIS_KEYCLOAK_LIVE_URL` and `PORTCULLIS_KEYCLOAK_LIVE_WIPE=portcullis` are set (not in CI; it wipes realm `portcullis`).
    **Docs copies.** The Hub ships some pages of this site as MCP resources (`portcullis://docs/<name>`), committed under `web/docs/` (`web/docs/sync.sh`: `integration-contracts.md`, `hub.md`, `auth-policies.md`, `groups.md`, `backups.md`, `file-sharing.md`). After changing one of them here, run `PORTCULLIS_DOCS_DIR=<docs checkout> go generate ./web` in the Hub and commit; `TestDocsCopiesInSync` fails on drift when `PORTCULLIS_DOCS_DIR` is set (CI doesn't set it). A new page goes into both `sync.sh` and `docsPages` in `web/web_test.go`.
    The harness also serves AI fixtures (the Hub listener has its own fake fresh-auth verifier at `/harness/authorize`, signing in as root, for the admin confirmation page): an app with token and identity-header companions, an `app_oauth` app, a fake connections store and access log, and the people MCP switched off for one user (no card).
    The settings code is tested per package: the template settings validator, the setting types (parsing, rendering, resolution), the delivery engine (data files, claims, headers, hooks, reload, debounce, stale runs), person-entered values (uniqueness, population, purges, the refused-save limit) and the settings API (admins only, secrets never returned).
    A build-tagged harness (`go test -tags harness -run TestHarness -timeout 0 ./internal/httpapi`) serves the UI on `127.0.0.1:18888` (and the people page on `:18889`) against in-memory fakes, for checking the panels in a browser.
    **Branding.** `TestBrandingCopies` (`web/web_test.go`) pins each embedded icon, the web manifest and `mark.svg` (= `concept-1-mark-dark.svg`) to its branding-source sha256; `TestPagesCarryBranding` checks that each HTML page links the favicon set and the manifest and has the mark in its `<h1>`; `TestStaticContentTypes` checks the `.svg`, `.png`, `.ico` and `.webmanifest` content types (with `nosniff`) on both listeners.
    **Rootless Podman** is tested in `internal/idmap` (the `uid_map` parser and its shapes), `internal/docker` (the runtime guard: retries until verified, a mismatch is permanent, the guarded transport passes only `/_ping` and `/version` before that, Podman's extra event actions are ignored), `internal/compose` (refuses while unverified, its own version check passes), `internal/folderfix` (the consistent mapping allowed, host ids in reports, unmapped owners counted and refused per path, the SELinux label), `internal/hub` (the fixer gate per runtime, the Podman container-id roots, the create, enable and restore-as refusals, the SELinux relabel of template binds), `internal/templates` (`RootlessCompat` against the shared vectors; with `PORTCULLIS_TEMPLATES_DIR` set, every real template against `tests/runtime.txt`), `internal/doctor` (the five kinds, silent under Docker) and `internal/httpapi` (`GET /api/runtime`, `get_runtime` in `TestAdminToolsSameAsHTTP`, the `503` mapping, the Marketplace badges).
    **Kubernetes** is tested in `internal/runtime/kube` (the translation, the ingress conversion, NetworkPolicies, helpers, the guard and its self-test, the admission vectors in CEL), `internal/templates` (the Kubernetes compatibility against the shared vectors) and `internal/hub` (`TestCreateRefusedOnKubernetes`, `TestRealTemplatesRuntimeClassification` against `tests/runtime.txt`). A separate step, **envtest (Kubernetes 1.33, the floor)**, runs `go test -tags envtest -run 'Admission|Translated|SelfTest|RoleIsEnough' ./internal/runtime/kube/` against a real API server (`setup-envtest` pinned by module version): the admission policies and their vectors, translated objects admitted, the self-test rejected only by its own binding, and the Hub's Roles being enough.
    **DNS hardening** is tested in `internal/domains` (the plan, apply and DNSSEC client calls against the fake domains service), `internal/hub` (`DomainPlan`, `MainDNSPlan`, `ApplyDomainDNS` and `EnableDomainDNSSEC`: sets validated, audit `domain.dns_apply` / `domain.dnssec_enable`, an AI caller needs the confirmation for signing; op keys `_domain.<name>` fail closed and DNS names never reach op paths, `TestDNSNamesNeverReachOpPaths`), `internal/httpapi` (the four routes and their MCP twins, `TestAdminToolsSameAsHTTP`) and `internal/doctor` (every DNS kind and its fingerprint's stability; the unknown-CA item is never `dns_caa_missing`, `TestDNSUnknownCANotCAAMissing`; `dns_unavailable` when the plans can't be read). The harness (`harness_dns_test.go`) seeds a fake domains service with every DNS panel row kind.
    `TestProtectedAccountsParity` reflects over `directory.Service` methods to check every user-targeting operation refuses `admin` and `portcullis-hub`.

    **Multiple servers** ([Multiple servers](servers.md)): the agent and the relay are built from the same tree (`cmd/portcullis-agent`, `cmd/portcullis-relay`). The step **e2etest hooks only with the tag** runs the `-tags e2etest` tests, then builds the three binaries as the Dockerfiles do (`GO_TAGS` empty) and fails if one carries the e2etest marker (the CI-only clock-offset and oversized-info hooks), and checks that tagged builds do. The unit tests cover the shared `link.json` and placement vectors, join codes and the enrolment proof, the agent's bundle and scope checks, the relay's cookie filter, moves with a failure at every step, revocation and the doctor kinds.

- **`build`** (after `test`), once per image: `portcullis-hub`, `portcullis-agent` (`Dockerfile.agent`) and `portcullis-relay` (`Dockerfile.relay`), each:
    - Multi-arch image (`linux/amd64`, `linux/arm64`) with SBOM and provenance (`mode=max`) attestations.
    - Tags `X.Y.Z`/`X.Y`/`X`/`sha-<short>` for release tags and `edge` for `main`. `latest` is disabled.
    - Pushed to GHCR and **signed with cosign** (keyless, GitHub OIDC) by digest. Pull requests build but don't push or sign.

Verify a published image with the command in
[Hub → Image tags](hub.md#image-tags-and-verification).

## Keycloak image CI (`build.yml`)

The extension's Gradle tests (`docker buildx build --target test`), the shared
rule vectors against the Hub's, the smoke realm against core's flows, then the
`smoke` job against a running image: the live sign-in run, "x509 kinds" and
"impersonation" (`.github/smoke/signin.py`). The impersonation step also
introspects the impersonated access token with a confidential client it
creates (its secret generated in-process and sent in a form body, never on
argv or in a log): the answer is `active` and carries `act` and `pc_imp`, and
its `exp` is at most `pc_imp.until`
([contract §8.1](../guides/integration-contracts.md#81-sign-in-methods-new-sign-in)
"Impersonation").
The authenticator-code smoke cases (`totp_override_marker`: the
`CONFIGURE_TOTP` override's operational info `portcullis: totp`;
`totp_signin`: a password sign-in, `kc_action=CONFIGURE_TOTP`, then a new
sign-in with the password and a `pyotp` code, amr `pwd` + `otp`;
`totp_replay_refused`; `totp_pc_method_only_code`) read the manual key from
Keycloak's page, mask it and take no screenshot while it is shown;
`PROVIDER_IDS` lists `portcullis-otp` and `CONFIGURE_TOTP`, and `pyotp` is
pinned with hashes in its own `.github/smoke/requirements-totp.txt`.

## AI support manual checklist

The checks CI can't make: real Claude clients, a hardware passkey and a live
Keycloak. Use throwaway users and instances on the test server and clean them
up afterwards.

1. **Deploy.** Merge in order docs → core → Hub → templates; deploy to the
   test server (`./portcullis upgrade`); confirm `mcp-gate` healthy and
   `./portcullis status` clean.
2. **Live checks:**
    1. Settings → AI on; Gitea AI support on (read_write); the People card
       for a test user shows the URLs.
    2. Claude Code on the operator's machine: the card's `claude mcp add`
       command, `/mcp` sign-in with the passkey; list the test user's
       issues; create one (write) and ask to delete a repo → confirmation
       page with passkey; remove the user from `users_gitea` → refused.
    3. claude.ai custom connector with "Use your own OAuth client"
       (`portcullis-ai-claude`, no secret): connects (spec call 40; if it
       demands a secret, apply call 40's fallback and note it).
    4. `hub.<d>/mcp` as an admin: `get_instance`, `doctor_findings`, delete a
       throwaway instance through the confirmation.
    5. An `ai-chat` instance with an OpenAI-compatible provider: a chat that
       lists the person's Gitea repos through the aggregate.
    6. The access log and `audit.jsonl` show the calls with `via: ai`; no
       secret in either (grep the markers used).
3. **Report** what passed, the builder verifications' results, anything
   deferred.

Also check, from the builders' reports:

- **Claude desktop** custom connector with "Use your own OAuth client"
  (public client, PKCE); **Claude Code** `claude mcp add` + `/mcp`; the
  card's steps as written, for the aggregate and one app.
- **The AI page** with an OpenAI-compatible Ollama and the Anthropic API,
  and with a LiteLLM instance:
    1. `getent hosts auth.<d> mcp.<d>` inside `<instance>-api-1` shows
       Traefik's IP;
    2. a member connects "All my apps": consent on the instance's
       `ai-chat-mcp` client, the callback, tools listed, a tool call as that
       person; the access log's `client` is the instance's `ai_client`;
    3. a second instance (`ai-research`): its own client
       `ai-research-ai-chat-mcp` and its own callback host;
    4. the refresh lifetime without `offline_access`: decide whether to add it;
    5. an outsider is refused by Keycloak's access role on the real Hub, not
       only by LibreChat (the `ai_client` keeps the instance's access role and
       flow: `EnsureClientAccess` on an AI client hasn't run against a real
       Keycloak yet);
    6. a provider change restarts the instance and the selector shows the new
       labels; a cleared key drops that endpoint.
- **Passkey sign-in** on an AI client gives `acr` / `amr` `hwk`
  (`TestLiveAIObjects` skips it: it needs a WebAuthn authenticator).
- **Fresh-auth popup on both hosts**: a confirmation approved on
  `people.<d>` and one on `hub.<d>` (the `https://hub.<d>/` redirect URI),
  with the passkey's `auth_time` and `amr` verified by the real Keycloak.
- **Home Assistant** (`app_oauth`): in claude.ai add a custom connector for
  `https://<host>/api/mcp`; Claude discovers the protected-resource and
  authorization-server metadata and uses its CIMD client id; the redirect
  goes Home Assistant `/auth/authorize` → auth_oidc → Keycloak (passkey) →
  "continue on this device" → Claude's callback; Assist tools appear
  (`GetLiveContext`); a non-admin member turns an exposed light on. The same
  with Claude Code (loopback, port 33418). Removing the person from the group
  ends the connection after the next reconcile (at most 10 minutes for a
  pending code). The host must be publicly reachable and not need a YubiKey or browser certificate.
- **Nextcloud**: AI on; alice uses claude.ai through
  `https://<nextcloud host>/mcp`; leaving revokes the app password (up to
  10 s of lag); a restore runs `revoke_all`.

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
