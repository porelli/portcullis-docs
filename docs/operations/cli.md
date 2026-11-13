# CLI Reference

Everything an operator does on the Portcullis host goes through one command in
the core checkout: `./portcullis`. There are no other scripts.

```bash
./portcullis help              # list every command
./portcullis <command> --help  # options of one command
```

`--help` works without `.env` or Docker. Argument errors exit with status 2.

!!! note "Generated from the real help text"
    This page restates the output of `./portcullis help` and
    `./portcullis <command> --help` in the core repo. If the two ever disagree,
    the CLI is right.

## Conventions

- **`.env` is parsed, never sourced.** Variables in your shell environment win
  over `.env`, the same way docker compose resolves them.
- **Secrets never go on the command line.** DNS credentials are read from the
  environment or a hidden prompt. The Vault admin token comes from `VAULT_TOKEN`
  or from `secrets/vault-init.json`.
- **Every setup step is idempotent.** `init`, `upgrade`, `vault init`,
  `pki setup`, `keycloak configure` and `oidc register` can be re-run safely.

## Command overview

| Area | Command | What it does |
|------|---------|--------------|
| Setup and lifecycle | [`init`](#init) | First-time setup: `.env` and secrets, Vault, PKI, Keycloak, start |
| | [`up`](#up) | Start or update the core stack and wait until it is healthy |
| | [`down`](#down) | Stop the core stack. Volumes and secrets are kept |
| | [`upgrade`](#upgrade) | Back up, pull, re-run the idempotent setup steps, restart |
| | [`status`](#status) | Health overview (`--json` for machines, `--textfile` for Prometheus) |
| | [`version`](#version) | Core version and the Hub and Keycloak images in use |
| Backups | [`backup`](#backup) | Consistent backup to `backups/` (`--offsite`: also restic, encrypted) |
| | [`backup verify`](#backup-verify) | `restic check` + restore + sanity checks (or `--local`) |
| | [`backup schedule`](#backup-schedule) | systemd timer for daily backups |
| | [`restore`](#restore) | Restore a local or off-host (`--from-offsite`) backup |
| Configuration | [`config apply`](#config-apply) | Apply `ACME_STAGING`, rebuild the CA bundle |
| | [`config init`](#config-init) | Keep your settings in `config/`, a separate git repo |
| | [`dns plan`](#dns-plan) | The domain's DNS plan: records, CAA pin, DNSSEC (changes nothing) |
| | [`dns setup`](#dns-setup) | Write the planned records (A/AAAA, CAA) through the DNS provider |
| | [`dns check`](#dns-check) | Public DNS checks only (no credentials); exit 1 on a problem |
| Vault and PKI | [`vault init`](#vault-init) | Initialise and unseal Vault, set up the enroll AppRole |
| | [`vault unseal`](#vault-unseal) | Unseal Vault and wait until it is active |
| | [`vault rotate-enroll-secret`](#vault-rotate-enroll-secret) | Issue a new enroll AppRole secret-id |
| | [`pki setup`](#pki-setup) | Create the internal certificate authority: YubiKey and browser certificate CAs (idempotent) |
| Identity | [`keycloak configure`](#keycloak-configure) | Import or patch the `portcullis` realm |
| | [`oidc register`](#oidc-register) | Create the core OIDC clients and push their secrets from `.env` |
| | [`invite`](#invite) | One-time setup link: register a passkey, signed in (no password) |
| | [`lldap-ui`](#lldap-ui) | Break-glass SSH tunnel to LLDAP's own web UI (server only) |
| | [`signin reset-core`](#signin-reset-core) | Locked out of the Hub: put the Hub and people pages back on Standard |
| YubiKey and browser certificates | [`cert enroll`](#cert-enroll) | New key and YubiKey certificate on a YubiKey |
| | [`cert renew`](#cert-renew) | New YubiKey certificate for the key already on the YubiKey |
| | [`cert revoke`](#cert-revoke) | Revoke a YubiKey or browser certificate (enforced by group-gate) |
| | [`cert list`](#cert-list) | List issued YubiKey and browser certificates |
| | [`cert sync`](#cert-sync) | Rewrite the revoked-serial list from Vault |

---

## Setup and lifecycle

### init

```
portcullis init [--domain DOMAIN] [--email EMAIL] [--dns-provider NAME]
                [--non-interactive] [--env-only] [--skip-dns] [--no-config-repo]
```

First-time setup. It creates `.env` (mode `0600`) with every secret randomly
generated: the Postgres password, the Keycloak admin password, the LLDAP admin
password and JWT secret, the forward-auth client and cookie secrets, the two
forward-auth session-store passwords (`FORWARD_AUTH_REDIS_PASSWORD`,
`FORWARD_AUTH_EXT_REDIS_PASSWORD`), `HUB_PROXY_SECRET`, and `BACKUP_PASSWORD`
for off-host backups. Then it runs these steps in order:

1. DNS records (`dns setup`)
2. Vault init, unseal and enroll AppRole (`vault init`)
3. CA bundle
4. `docker compose up`
5. Vault PKI, including a self-signed wildcard server cert for local use (`pki setup --with-server-cert`)
6. Keycloak realm (`keycloak configure`)
7. OIDC clients (`oidc register`)
8. `config/` repo (`config init`)

At its end it reads Traefik's ACME account and pins the main domain's CAA
to it, as [`up`](#up) does.

If `.env` already exists it is kept, and only empty or missing secrets are
generated. Every step is idempotent, so you can re-run `init` after a failure.

| Option | Meaning |
|--------|---------|
| `--domain DOMAIN` | Base domain (default: `$PORTCULLIS_DOMAIN`, otherwise a prompt) |
| `--email EMAIL` | Let's Encrypt account email (default: `admin@DOMAIN`) |
| `--dns-provider NAME` | `cloudflare`, `porkbun`, `route53`, `digitalocean`, `hetzner`, `hetzner-cloud`, `none`, or another lego provider name (default: `cloudflare`) |
| `--non-interactive` | Never prompt. DNS credentials must be in the environment (e.g. `CLOUDFLARE_API_TOKEN=...`) |
| `--env-only` | Only write or complete `.env`, then stop |
| `--skip-dns` | Do not create DNS records |
| `--no-config-repo` | Do not create the `config/` git repo |

DNS provider credentials are read from the environment or a hidden prompt,
never from the command line. See [Quick Start](../setup/quickstart.md).

### up

```
portcullis up
```

Starts or updates the core stack. It checks `.env` and the `portcullis-proxy`
network settings, creates the bind-mount sources, and rebuilds
`certs/ca-bundle.crt`. Then it runs `docker compose up -d --build` and waits
for vault, postgres, lldap and keycloak to be healthy. Vault unseals itself on
start.

Then it reads Traefik's ACME account URI (a helper container with the ACME
volume read-only and no network prints only the URI), writes it to
`secrets/domains/main-domain.env` (restarting `domains` when it changed), and,
with an automated provider and `DNS_CAA=true`, pins the main domain's CAA to
that account when the live pin differs. It waits up to 3 minutes for a first
registration. A failure only warns: `up` never fails because of it. See
[DNS Configuration → CAA](../setup/dns.md#caa).

Every `init`, `up`, `upgrade` and `restore` also writes the session store's
config, `secrets/sessions/valkey.conf` (its users and the SHA-256 of the two
`FORWARD_AUTH*_REDIS_PASSWORD`s, never the passwords; 0640, group 1000). When
it changed (a password was rotated) and the store is running, the store is
restarted before `docker compose up`: it keeps sessions in memory only, so
everyone signs in again once. See
[Security & Hardening](hardening.md#session-store-sessions).

After `docker compose up`, services are restarted if their bind-mounted config
files changed since the last start (e.g. after `git pull`). Affected files:
`oauth2-proxy/alpha.yaml` (forward-auth services), `group-gate/group-gate-map.conf`
(group-gate, enroll), `keycloak/themes/portcullis` (keycloak), monitoring
configs (prometheus, blackbox). Services that re-read their config automatically
(Traefik's dynamic file provider, group-gate's policy file) or apply config
through other commands (Keycloak's realm export via `keycloak configure`) are
not restarted.

### down

```
portcullis down
```

Stops and removes the core containers (`docker compose down`). Volumes and
`secrets/` are kept. Apps enabled in the Hub run as their own compose projects
and are not touched.

### upgrade

```
portcullis upgrade [--skip-backup]
```

Updates a running installation after `git pull`:

1. Generates any missing `HUB_PROXY_SECRET`, `FORWARD_AUTH_*` (incl. the session-store passwords `FORWARD_AUTH_REDIS_PASSWORD` / `FORWARD_AUTH_EXT_REDIS_PASSWORD`), `LLDAP_JWT_SECRET` or `BACKUP_PASSWORD`. Other secrets must already be in `.env`.
2. Creates a local backup (`portcullis backup`: Vault snapshot, `pg_dump`, volumes, `.env`, `certs/`, `secrets/`).
3. Pulls images.
4. Re-runs the idempotent setup steps: `vault init`, `pki setup` (both CAs, the `client-cert` and `browser-cert` roles incl. `CLIENT_CERT_TTL`, Keycloak truststore) and the CA bundle.
5. Runs `docker compose up -d --build` and waits for health.
6. Restarts services whose bind-mounted config files changed (see [`up`](#up) for the list).
7. Runs `keycloak configure` and `oidc register`.
8. Pins the main domain's CAA to Traefik's ACME account, as [`up`](#up) does.

| Option | Meaning |
|--------|---------|
| `--skip-backup` | Do not create a backup first |

See [Upgrading](upgrading.md).

### status

```
portcullis status [--json | --textfile]
```

Prints a health overview:

- compose services
- Vault: sealed/active, CA expiry (root, YubiKey certificate CA, browser certificate CA), issued certs (both mounts), and YubiKey and browser certificates expiring within `CERT_EXPIRY_WARN_DAYS` (default 7) days (each person's newest of each kind; renewed or replaced on the Sign-in page)
- Keycloak: realm, users, forward-auth client, and the passkey policy: the
  realm's passwordless WebAuthn policy must be attestation `direct`, any
  attachment, resident key and user verification required, with
  `webauthn-register-passwordless` enabled and the two-factor
  `webauthn-register` disabled. Anything else (or a realm or action that
  can't be read) is a failing line such as
  `✗ passkey policy: attestation none (wanted direct) — new passkeys can't be told apart; run ./portcullis keycloak configure`:
  with any other conveyance browsers send no attestation and every new
  passkey, a YubiKey included, counts as synced
- LLDAP and Traefik
- containers on `portcullis-proxy` answering to a core service name or an AI
  companion name they don't own ([hardening](hardening.md#ai-support-mcp-gate))
- mcp-gate refusing every AI request (`503`) and why, for example AI
  credentials it can't decrypt with `secrets/mcp-gate/age.key`
  ([AI support → Residuals](ai.md#residuals))
- **DNS**, for the main domain and every added domain, from the domains
  service's plans (`domains report`, over its loopback API): A/AAAA point at
  this server, the CAA as planned, the DNSSEC state, and records under the
  name that aren't Portcullis'. For the main domain it also compares the CAA
  pin with Traefik's current ACME account: when the CA wouldn't issue to it,
  or `main-domain.env` names another account, it fails with
  `CAA allows another ACME account than Traefik's — fix: ./portcullis dns setup`
  (a missing `main-domain.env` is only a warning). When the server's addresses
  couldn't be detected (and `.env` sets no `PORTCULLIS_PUBLIC_IPV4`), the main
  domain's A/AAAA are `unknown`: a warning line, not a failure.
  A DNSSEC state `bogus` or `ds_mismatch` fails too; `insecure` (signed
  under a parent zone that isn't validated) is a ✓ line. While the domains
  service isn't running the block is one line, "DNS checks unavailable".
  The main domain's plan is rebuilt for each `status` (public lookups only;
  at most once per 30 s, and `status` waits at most 20 s for it), so a CAA
  changed outside Portcullis — at the provider, or through the dns tool —
  shows at once, not after the hourly recheck. If the rebuild fails,
  `status` shows the cached plan with a warning that it may be stale ("the
  lines below are from <time>"), and each of that domain's ✓ lines says
  "(as of <time>, may be stale)"; `--json` has `dns.main.fresh` and
  `dns.main.checked_at`. A running domains image older than the CLI (it
  refuses the refresh) is named: "the domains image is older than this CLI
  (run ./portcullis up)", with the cached plan marked stale. `status --textfile` runs once after each scheduled
  backup, so this adds no steady lookups

Exits 1 if a core service is down or unhealthy, if Vault is not active, if
the passkey policy drifted, if such a container exists, if mcp-gate
refuses every AI request, or if a DNS check is a Problem.
Otherwise it exits 0.

| Option | Meaning |
|--------|---------|
| `--json` | Machine-readable output (same exit status). Expiring certs are in `vault.certs_expiring` (each with `kind`: `yubikey` / `browser`), name takeovers in `dns_shadows` (`container`, `name`), mcp-gate's refusal in `mcp_gate.refusing` (`null` while it serves), the passkey policy in `keycloak.passkey_policy` (`{ok, problems}`, `null` when Keycloak's admin API couldn't be used), the DNS block in `dns` (`{main, domains: {<name>: …}}`, each `{name, address_ok, address_unknown, caa_ok, would_issue, dnssec, foreign, problems, checks}` (`address_unknown`: the address set couldn't be judged — e.g. the server's IPv4 isn't known — a warning, never a problem), the main domain also `lost_account`; `null` while the DNS checks are unavailable) |
| `--textfile` | Write the same data as Prometheus metrics to `monitoring/textfile/status.prom` for the [monitoring profile](monitoring.md): service health, Vault active, the passkey policy (`portcullis_keycloak_passkey_policy_ok`, absent when not checked), CA expiry and per-person YubiKey / browser certificate expiry (label `kind`), the DNS checks (`portcullis_dns_check`, `portcullis_dnssec_state`). Run it after every scheduled backup (the systemd unit does) |

### version

```
portcullis version [--json]
```

Prints the core version and the Hub and Keycloak images in use:

- **Core version.** The `VERSION` file of a release tarball, else `git describe` of the checkout.
- **Hub image.** `HUB_IMAGE` from `.env` or the environment, else the default in `docker-compose.yml`, plus the image of the running Hub container if there is one.
- **Keycloak image.** `KEYCLOAK_IMAGE` from `.env` or the environment, else the default in `docker-compose.yml`, plus the image of the running Keycloak container if there is one.

`--json` prints `version`, `hub_image`, `hub_image_source` (`HUB_IMAGE` or `default`), `hub_running`, `keycloak_image`, `keycloak_image_source` (`KEYCLOAK_IMAGE` or `default`) and `keycloak_running` (`null` when the container isn't running).

| Option | Meaning |
|--------|---------|
| `--json` | Machine-readable output |

---

## Backups

See [Backups](backups.md) for the full picture.

### backup

```
portcullis backup [--offsite] [--list [--json]]
```

Creates a consistent backup in `backups/<timestamp>/` (mode `0700`) while
everything keeps running. It contains:

- a Vault raft snapshot
- a `pg_dump` of the Keycloak database
- the LLDAP, Hub and ACME volumes (SQLite via its online backup API)
- `.env`, `certs/`, `secrets/`, `config/` and the config files
- `MANIFEST.json` with the sha256 of every file

It keeps the newest `BACKUP_KEEP_LOCAL` (default 7) local backups.

!!! danger "The backup contains the Vault root token and unseal key"
    It can decrypt the CA and every secret. Protect it like the keys.

| Option | Meaning |
|--------|---------|
| `--offsite` | Also upload it to the restic repository `BACKUP_REPOSITORY`, encrypted with `BACKUP_PASSWORD`, then apply the retention `BACKUP_KEEP_DAILY/WEEKLY/MONTHLY` (7/4/6). Keep that password **offline**: without it the off-host copies are useless, with it they are the keys to everything |
| `--list` | List local backups. With `--offsite`, list the restic snapshots; `--json` prints restic's JSON |

### backup verify

```
portcullis backup verify [--snapshot ID]
portcullis backup verify --local [DIR]
```

**Off-host (default).** Runs `restic check`, reading
`BACKUP_VERIFY_READ_DATA` (default 10%) of the pack data. Then it restores the
latest snapshot (or `ID`) into a temporary directory and checks it.

**`--local`.** Checks a local backup instead: `DIR`, by default the newest in
`backups/`.

The checks:

- every file matches `MANIFEST.json`, and `.env` / `secrets/` are complete
- `vault.snap` is a raft snapshot (`meta.json`, `state.bin`, `SHA256SUMS` ok)
- `postgres.dump` restores into a throwaway Postgres container (no network) and contains the Keycloak realms
- the LLDAP database opens, passes `integrity_check` and has users
- every volume archive is readable

Exits non-zero if anything fails.

### backup schedule

```
portcullis backup schedule --systemd [--on-calendar SPEC] [--output DIR]
```

Prints, or writes to `DIR`, a systemd service and timer. They run
`portcullis backup --offsite` (just `backup` while `BACKUP_REPOSITORY` is
unset) as the current user, followed by `portcullis status --textfile`. The
user must be able to run docker.

| Option | Meaning |
|--------|---------|
| `--systemd` | Generate systemd units (the only scheduler supported) |
| `--on-calendar SPEC` | systemd `OnCalendar` (default `*-*-* 03:15:00`, plus up to 30 minutes random delay) |
| `--output DIR` | Write `portcullis-backup.service` / `.timer` into `DIR` and print the install commands |

### restore

```
portcullis restore [--yes] [--allow-empty-lldap] <backup-dir>
portcullis restore [--yes] [--allow-empty-lldap] --from-offsite [SNAPSHOT]
portcullis restore --list [--offsite]
```

Stops Portcullis and restores a backup made by `portcullis backup` or
`upgrade`:

- `.env`, `certs/`, `secrets/` and the config files
- the Vault data: the raft snapshot is restored into a fresh Vault, which then unseals with the backed-up key
- the Keycloak database: `pg_restore` into a fresh Postgres
- the LLDAP, Hub and ACME volumes

Then everything is started again — unless LLDAP has no users while the
restored Keycloak database has some: then it stops with Postgres and Vault up
(Keycloak would delete those users' copies and passkeys at their next lookup;
see [Backups](backups.md#restore)). The backup's checksums are verified first.
The current `.env`, `secrets/` and `certs/` are saved to
`backups/pre-restore-<timestamp>/`.

`--from-offsite` restores `SNAPSHOT` (default: latest) from
`BACKUP_REPOSITORY`. On a new host without `.env`, export `BACKUP_REPOSITORY`,
`BACKUP_PASSWORD` and the provider credentials first. The `.env` comes from
the backup.

| Option | Meaning |
|--------|---------|
| `-y`, `--yes` | Do not ask for confirmation |
| `--allow-empty-lldap` | Start even if LLDAP has no users (their Keycloak copies and passkeys are then removed) |
| `--from-offsite` | Restore from the restic repository |
| `--list` | List local backups (`--offsite`: restic snapshots) |

---

## Configuration

### config apply

```
portcullis config apply [--bundle-only]
```

Applies the ACME toggle in `.env` and rebuilds `certs/ca-bundle.crt`:

| Variable | Default | Effect |
|----------|---------|--------|
| `ACME_STAGING=true\|false` | `false` | Let's Encrypt staging vs production. Sets `ACME_CA_SERVER` in `.env`. On a flip where Portcullis manages the CAA (`DNS_CAA=true` and an automated provider with its credentials) it first rebuilds the domains image (so the dns tool matches the CLI), relaxes the main domain's CAA to CA-only **while Traefik keeps running** (CA-only lets its current account renew) and waits until no cache can still hold the old pin: the TTL caches got (the stored or the served one, whichever is longer) + 1 minute, at most 15 minutes per run (Porkbun: about 11). Only then it stops Traefik, clears its `acme.json`, writes the new CA server and starts Traefik again if it was running, so Traefik registers a new account. Interrupted after the stop, it starts Traefik again. The settle point is saved before the first write and moved to the tool's own point the moment the write is accepted (`secrets/domains/acme-relax.env`, 0600; read as the later of its NOT_BEFORE and WRITTEN_AT + OLD_TTL + 60 s; never backed up, and a `restore` keeps the live one: it describes DNS caches, not the host): a rerun waits for it, and never settles earlier because it only sees the CA-only records. A TTL that can't be read, or that the provider reports as 0 / 1 ("auto", the zone default) and no nameserver serves, refuses the relax before anything is written (exit 1, nothing changed): set an explicit CAA TTL at the provider. With a saved point that exists but can't be read, or with none saved while the CAA is already CA-only (or has none of Portcullis' entries), how long caches may hold the old pin can't be known: it assumes 24 h from now and says until when (so a first flip of a domain that was never pinned — Traefik never registered — waits a day; the message says so and when it can go ahead). When `main-domain.env` never held an account URI (Portcullis never pinned), there is no old pin to wait out and no 24 h point. Where Portcullis doesn't manage the CAA (`DNS_CAA=false`, `DNS_PROVIDER=none` or a manual provider, or no credentials) a flip does no relax, no settle and no wait. **Every flip**, managed or not, first runs a public, credential-free check — would the new CA let a *new* account order at every resolver? — and refuses before anything changes when it wouldn't (it names the live pin; for an unmanaged setup: remove that pin at the provider, or run `dns setup` with `DNS_CAA=false`, then run it again after its TTL), when the lookup fails, or when a saved settle point is still in the future. A Traefik with no container at all (after `down`) needs no stop. The saved point is deleted only once a flip has finished: ACME_STAGING reverted mid-flip keeps it, and a pin written again (`up`'s tighten, `dns setup`) only moves it later (now + the old pin's TTL + 1 min), since caches may still hold the original pin. A stale point can delay a later flip, never hurry it. Traefik that won't stop fails the flip before the clear. The CA bundle is built before Traefik stops; the sentinel (`certs/.acme-staging-last`) is written only once Traefik runs on the new CA server, so any failure or interrupt (INT, TERM, HUP) before that starts Traefik again and leaves the flip pending. If the relax fails, hasn't settled, or the clear fails, it stops fail safe (exit 1, the flip stays pending, Traefik runs on its old account) and says when to run it again; an old pin stored with a TTL above 15 minutes is named as the cause, with the time after which a rerun goes through (or lower the CAA TTL at the provider first) |

It also writes `ACME_DNS_PROVIDER` (Traefik's lego provider: `hetzner-cloud`
becomes lego's `hetzner`), and refuses `DNS_PROVIDER=hetzner` with
`HETZNER_API_TOKEN` set or `hetzner-cloud` with `HETZNER_API_KEY` set
([DNS Configuration → Hetzner](../setup/dns.md#hetzner-legacy-dns-and-hetzner-cloud)).

It never writes `traefik/dynamic/tls.yml`: that file is static, and which apps
ask for a YubiKey or browser certificate follows the sign-in methods and templates in the
Hub ([TLS tier](auth-policies.md#traefik-tls-tier)).

Run `portcullis up` afterwards. It restarts Traefik and, when the bundle
changed, the two forward-auth services, which read it only at start-up (the
sha256 they last started with is kept in `certs/.ca-bundle.loaded`). See
[Certificates](../setup/certificates.md).

| Option | Meaning |
|--------|---------|
| `--bundle-only` | Only rebuild `certs/ca-bundle.crt` (system CAs + internal PKI chain + the LE staging root if `ACME_STAGING=true`) |

### config init

```
portcullis config init [--remote URL | --from URL]
```

Creates `config/`, a separate git repo for this instance's settings. It moves
`.env`, `docker-compose.override.yml` and `traefik/dynamic/local/*.yml` into
it and symlinks them back, so a `git pull` of Portcullis never conflicts with
your settings. Re-running it only refreshes the symlinks.

| Option | Meaning |
|--------|---------|
| `--remote URL` | Set `config/`'s git remote. Push it to a **private** repo: `.env` holds secrets |
| `--from URL` | Clone an existing config repo into `config/` (new machine) |

### dns plan

`portcullis dns --help`:

```
Usage: portcullis dns plan|setup|check [options]

  plan      Show the main domain's DNS plan: wanted vs live records, CAA, DNSSEC
  setup     Show the plan, confirm, write the records through the provider API
  check     Public checks only (no credentials); exit 1 on any problem
```

```
portcullis dns plan [--json]
```

The DNS plan of `PORTCULLIS_DOMAIN`: every record Portcullis wants
(`address`: A/AAAA for `<domain>` and `*.<domain>`; `caa`: `issue` +
`issuewild` for the ACME CA, pinned to Traefik's ACME account, DNS-01 only;
`nomail` with `DNS_NOMAIL=true`), what the provider holds and the public
resolvers (1.1.1.1, 8.8.8.8) answer, records under the domain that aren't
Portcullis', whether the CA would issue, and the DNSSEC state with the steps
left. Changes nothing.

| Option | Meaning |
|--------|---------|
| `--json` | The plan object ([contract §12.2](../guides/integration-contracts.md#122-api)) |

The output is a table (set, name, type, wanted, live, status), the steps
left under it (`→ …`), then a `CAA:` line (issuer, account or "CA-only (no
Traefik account yet)", "would issue: yes / NO") and a `DNSSEC:` line (state,
zone, the DS values). With an automated provider the plan also reads the
provider's records; otherwise it uses the public resolvers only. If Traefik's
ACME account exists but can't be read, it warns and shows the CA-only pin.

### dns setup

```
portcullis dns setup [--yes] [--dnssec] [--only address|caa|nomail]
```

Shows the plan, asks to apply it (`--yes`: don't ask; required without a
terminal), writes the record sets through `DNS_PROVIDER`'s API with its
credentials from `.env`, waits until the public resolvers show the new
records **stably**, then runs [`dns check`](#dns-check). Each public
resolver is a pool of caches, so one clean answer isn't enough: the wait
ends when both resolvers showed the new records in 4 rounds in a row (10 s
apart, so at least 30 s) and every remaining TTL a resolver reported for an
old CAA answer has run out. It is bounded by the TTL the provider actually
stored (Porkbun raises 300 s to 600 s): up to that TTL + 1 minute, longer
while a resolver's answer shows it caches the old records longer, at most
15 minutes. When the bound is hit, the records **were written**: the
warning says "written; not yet stable at <resolver>", how long it may still
serve the old records and until when; `dns setup` then skips the check (a
stale cache would report Problems for records that are fine), says when to
run `dns check`, and exits 0. A failed write is a separate error (exit 1).
Right after the write it prints how long it will wait at most ("written;
waiting up to 11m0s for 1.1.1.1:53, 8.8.8.8:53 (TTL 600 s)"). When it
writes the caa set over a live Portcullis pin — removing it with
`DNS_CAA=false`, or replacing it — it saves a settle point
(`secrets/domains/acme-relax.env`: the write + the old pin's TTL + 1 min,
never earlier than a saved one) that every later `ACME_STAGING` flip waits
for. Only then does it read the caa set's TTL first (the other sets'
TTLs say nothing about a pin, and its message is shown); when it can't
(a pin made by hand with an "auto" or zone-default TTL, or the read
failed), it saves 24 hours from now instead, and says so. That point is
saved before the write: if the write then fails, the flip still waits
it out; when no pin was actually replaced (check with `./portcullis dns
plan`), you may delete `secrets/domains/acme-relax.env` by hand. The providers and their variables:

| Provider | Variables |
|----------|-----------|
| `cloudflare` | `CLOUDFLARE_API_TOKEN` |
| `porkbun` | `PORKBUN_API_KEY`, `PORKBUN_SECRET_API_KEY` |
| `route53` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_HOSTED_ZONE_ID` (optional) |
| `digitalocean` | `DO_AUTH_TOKEN` |
| `hetzner` | `HETZNER_API_KEY` (the legacy dns.hetzner.com API) |
| `hetzner-cloud` | `HETZNER_API_TOKEN` (DNS in the Hetzner Cloud API) |

Other providers (or `none`): it prints the records to create by hand and
exits 0. The credentials reach the domains image's dns tool on its stdin
only. A required variable that is empty fails before the tool starts, naming
the variable (never its value).

| Option | Meaning |
|--------|---------|
| `--yes` | Apply without asking |
| `--dnssec` | Also turn on DNSSEC signing (the whole zone; `cloudflare` only; others print the steps). Signing is never turned off |
| `--only SET` | Apply one record set: `address`, `caa` or `nomail` |

Without `--only` it applies `address` and `caa`, plus `nomail` with
`DNS_NOMAIL=true`. With `DNS_CAA=false` the `caa` step removes the CAA
entries Portcullis wrote. If Traefik's ACME account can't be read, the live
CAA is left alone (`--only caa` is refused). There is no `--check` option:
use `dns check`.

### dns check

```
portcullis dns check [--json]
```

The plan from the public resolvers only (no credentials needed): A/AAAA,
the CAA pin (would the CA issue for Traefik's account?) and DNSSEC. Exits
1 when an item or the DNSSEC state is a problem.

| Option | Meaning |
|--------|---------|
| `--json` | The plan object ([contract §12.2](../guides/integration-contracts.md#122-api)) |

See [DNS Configuration](../setup/dns.md) for the record sets, CAA and DNSSEC.

---

## Vault and PKI

### vault init

```
portcullis vault init
```

Idempotent. It is run by `portcullis init`, `upgrade` and `restore`.

1. Starts the vault container if it is not running.
2. If Vault is uninitialised, runs `vault operator init` with **one** key share. The output goes to `secrets/vault-init.json` (`0600`). The unseal key goes to `secrets/vault-unseal/unseal-key` (`0640`, group of the vault user). That file is mounted read-only into vault, which auto-unseals on every start.
3. Unseals Vault if it is sealed and waits until the raft node is active.
4. Enables AppRole and writes the `portcullis-enroll` policy (`vault/policies/enroll.hcl`) and role. The enroll role-id and secret-id go to `secrets/enroll/` (`0640`, group 10002 = the enroll user), which is mounted read-only into enroll.
5. Writes the `portcullis-metrics` policy (`vault/policies/metrics.hcl`: read `sys/metrics`) and keeps a token with only that policy in `secrets/monitoring/prometheus/vault-token` for Prometheus ([monitoring profile](monitoring.md)). The token is recreated when it has less than a year left.

!!! warning "Keep an offline copy of `secrets/vault-init.json`"
    Losing it together with the host means losing the CA.

### vault unseal

```
portcullis vault unseal
```

Unseals Vault with `secrets/vault-unseal/unseal-key` if it is sealed. Vault
normally does this itself on every container start. Then it waits until Vault
is the active raft node, and exits non-zero if that doesn't happen.

### vault rotate-enroll-secret

```
portcullis vault rotate-enroll-secret
```

Same as `portcullis vault init`, but it always issues a new enroll AppRole
secret-id (`secrets/enroll/secret-id`) and destroys every previous one. The
enroll service picks it up on its next login.

### pki setup

```
portcullis pki setup [--force] [--with-server-cert]
```

Creates the internal certificate authority in Vault
([Certificates](../setup/certificates.md#internal-certificate-authority)):

- the root CA (10 years, `pki`) and two intermediates signed by it, 5 years each: the YubiKey certificate CA (`pki_int`) and the browser certificate CA (`pki_file`, CN `<domain> Browser Certificate CA`)
- the `client-cert` role on `pki_int` and the `browser-cert` role on `pki_file`, both with lifetime `CLIENT_CERT_TTL` (default `720h` = 30 days). The CN is taken from the caller, never from the CSR

It writes `certs/root-ca.crt`, `intermediate-ca.crt`, `yubikey-ca.crt`,
`browser-ca.crt`, `ca-chain.crt` (root + both intermediates: Traefik's
`protected-any` and `authaware` options), `ca-chain-yubikey.crt` (the
YubiKey CA alone, no root: Traefik's `protected` option; Go trusts every CA
in it as an anchor, so a root would also admit browser certificates) and Keycloak's
truststore (`certs/truststore/portcullis-ca-chain.pem`,
`portcullis-yubikey-ca.pem`, `portcullis-browser-ca.pem`), and enables CRL
auto-rebuild and delta CRLs on both intermediates.

It is idempotent:

- An existing CA is never replaced.
- Both roles are rewritten, so a new `CLIENT_CERT_TTL` applies to certificates issued from then on.
- Missing pieces (the browser certificate CA, CA files, truststore, server cert) are recreated. When the browser certificate CA is created or either chain file on disk is out of date, it rewrites both chain files and the truststore, and the next `up` restarts Traefik and Keycloak.
- A partial earlier run is redone.
- It refuses (exit 1) when the two intermediates would have the same CN.

If Vault has no CA but `certs/ca-chain.crt` exists (Vault data lost), it
refuses to create a new CA. Restore a backup, or use `--force`.

| Option | Meaning |
|--------|---------|
| `--force` | **Destroy** both CAs and create new ones. Every YubiKey and browser certificate stops working |
| `--with-server-cert` | Also issue a self-signed `*.<domain>` server cert (`certs/server.crt`, `server.key` `0640` group 0) for local dev and CI |

Admin token: `VAULT_TOKEN` if set, else the root token in
`secrets/vault-init.json`.

---

## Identity

### keycloak configure

```
portcullis keycloak configure [--wipe-realm]
```

Idempotent configuration of the `portcullis` realm after start, through the
admin API on `127.0.0.1:8080` (override with `KEYCLOAK_URL`):

- imports `keycloak/realm-export.json` if the realm does not exist
- points the LDAP federation at LLDAP (`LLDAP_BASE_DN`, `LLDAP_ADMIN_PASSWORD`); users and groups deleted in LLDAP are removed from Keycloak (hourly sync, `removeInvalidUsersEnabled`, the group mapper drops missing groups)
- sets `sslRequired=external`, `browserFlow=portcullis-universal`, an empty `acr.loa.map` (sign-in is decided by [templates](auth-policies.md), not levels), brute-force protection (10 failures, then 60 s more per failure up to 15 min, never permanent) and the passkey policy (direct attestation, any attachment, resident key and user verification required), then reads the realm back and fails when the passkey policy still differs (Keycloak keeps the old policy, answering success, when an update lacks `webAuthnPolicyPasswordlessRpEntityName`)
- offline sessions at most 30 days idle / 90 days total (the Hub sets shorter values on its AI clients); refresh-token rotation off
- rebuilds every top-level flow of the file whose tree changed: the browser flow with the sign-in extension's methods and template check ([Sign-in flows](auth-policies.md#sign-in-flows-in-keycloak)), the invite identity provider's first-login and post-login flows
- keeps `webauthn-register-passwordless` enabled and the two-factor `webauthn-register` disabled
- the invite identity provider `portcullis-invite` (enroll; URLs and client secret from `secrets/enroll/invite-client-secret`) and the service-account client `portcullis-enroll` (view-users, manage-users)
- `lldap_admin` = realm-admin of the `portcullis` realm (realm console)
- pushes each certificate step's settings from the file onto its `portcullis-x509` execution, by alias: `x509-config` (YubiKey certificate, Vault's `pki_int` CRLs) and `x509-browser-config` (browser certificate, `pki_file` CRLs), with trust re-validation and the `clientAuth` EKU
- never touches the realm's events config (the Hub owns it: sign-in history)
- checks the sign-in executions' AMR reference values (max age 10 h), ensures the `amr` mapper and the sign-in extension's impersonation mapper (both on the `acr` scope; it fails unless exactly one `portcullis-impersonation` mapper is there) and the `groups` scope
- enables the `portcullis-impersonation-notice` required action (the person's notice after an administrator signed in as them); it fails when the realm lacks it (a fresh realm import has it) or it can't be enabled
- ensures the `email-unverified` scope (`email` claim, no `email_verified`) that Hub templates opt into with `keycloak_clients[].email_verified_claim: false`
- `portcullis-forward-auth`: the `acr`/`groups` scopes, no default acr, requires PKCE S256, the `auth.<domain>` callback (keeps the Hub's extra-domain callbacks), and the `portcullis-invite-client` scope (setup links work only through it; removed from every other client)
- creates a credential-less `testuser` and applies the `PORTAL_DISPLAY_NAME` branding
- never touches the Hub's AI clients (`portcullis.hub.template` = `portcullis-ai`) or its `mcp:*` client scopes

| Option | Meaning |
|--------|---------|
| `--wipe-realm` | Delete the realm first and re-import it from the file (users' passkeys are lost; clients must then be re-registered with `portcullis oidc register`). Flow changes don't need it: they are rebuilt on every run |

### oidc register

```
portcullis oidc register
```

Creates the `portcullis-forward-auth` client. It also creates `headscale`,
`headplane` and `netbird-dashboard` when their `*_OIDC_CLIENT_SECRET` is set in
`.env`. Each client's secret in Keycloak is set to the value in `.env`, so
oauth2-proxy and Keycloak always agree. Idempotent.

After changing `FORWARD_AUTH_CLIENT_SECRET`, run this, then `portcullis up`.

---

### invite

```
portcullis invite <user> [--ttl DURATION] [--to hub|portal|URL] [--replace-keys] [--json]
```

Prints a one-time setup link for an LLDAP user. Opening it lets the user
register a passkey or security key (YubiKey) and signs them in: no password,
no other step. The link is single use, expires after `--ttl` (default 72h,
max 168h) and replaces the user's previous links. Pending links do not
survive a restart of the enroll container.

This is also how the bootstrap `admin` gets (or recovers) its key: the Hub
refuses invites for `admin`; only the server can issue them.

| Option | Meaning |
|--------|---------|
| `--ttl DURATION` | Go duration, e.g. `30m`, `24h` |
| `--to` | Where to land afterwards: `hub` (`https://hub.<domain>/`), `portal` (`https://<domain>/`, default) or an https URL on the domain |
| `--replace-keys` | Lost or stolen key: first delete all of the user's passkeys and security keys in Keycloak (every passkey kind: synced, device-bound and security key) and sign them out everywhere. Without it the new key is added next to the old ones (a spare key) |
| `--json` | Print enroll's JSON (`{"url","expires_at"}`) |

---

### lldap-ui

```
portcullis lldap-ui
```

Break-glass access to LLDAP's own web UI. `directory.<domain>` redirects to
`people.<domain>` (LLDAP has no single sign-on), so LLDAP's UI is
reachable only from the server. The command prints the SSH tunnel to run on
your machine; then open `http://localhost:17170` and sign in as the LLDAP
admin (`LLDAP_ADMIN_PASSWORD` in `.env`). Use it for recovery only:
day-to-day, people and groups are managed in the Hub at `hub.<domain>` (admins) or `people.<domain>` (everyone, with per-request permission checks). Manual changes to rule-based groups in LLDAP are reverted by the Hub's evaluator and audited.

---

### signin reset-core

```
portcullis signin reset-core [--yes]
```

Recovery when no administrator can sign in to the Hub any more (a method
switched off, a template edited, or the Hub moved to a template nobody meets;
the Hub refuses such saves, but this covers the rest). It stops the Hub, runs
the Hub's own `hub signin reset-core` against its data in a one-off container
of the Hub's image, as the image's user (uid 10001, so nothing in the Hub's
data ends up owned by root), and starts the Hub again. The reset:

- puts the Hub and people.&lt;domain&gt; core pages on **Standard**;
- restores the built-in Standard rule (any passkey or any certificate) and
  enables it;
- switches Standard's methods back on (the passkey kinds and the YubiKey
  certificate);
- is audited `signin.reset_core` (actor `cli`) and prints what it changed.

Everything else (other templates, apps' picks, passwords) is kept. The
one-off container never becomes a Traefik target (`traefik.enable=false`). If
the reset fails, or the Hub can't be stopped, or you interrupt the command, the
CLI starts the Hub again; a failed reset then exits 1 with the Hub's exit
status, its own message and "the Hub was started again". Check its output and
the audit log for what, if anything, was saved.

Without `--yes` it asks you to type `reset`; with no terminal and no `--yes`
it refuses (exit 2). See
[Sign-in methods → Locked out of the Hub](auth-policies.md#locked-out-of-the-hub).

| Option | Meaning |
|--------|---------|
| `--yes` | Don't ask (for scripts and CI) |

---

## YubiKey and browser certificates

`cert revoke`, `cert list` and `cert sync` cover both kinds: YubiKey
certificates (the internal certificate authority's `pki_int`) and browser
certificates (`pki_file`). People create browser certificates themselves on
the [Sign-in page](auth-policies.md#browser-certificates); there is no CLI
command for them. `cert enroll` and `cert renew` need `ykman`, `openssl`,
`jq` and Vault access. Run them on the Portcullis host, or export
`VAULT_ADDR`/`VAULT_TOKEN`. The certificate CN is `<username>`.

| Environment | Meaning |
|-------------|---------|
| `PIV_PIN` | YubiKey PIV PIN. If unset, `ykman` prompts for it. Prompting is preferred, because a PIN given here appears on the `ykman` command line |
| `VAULT_TOKEN` | Admin token (default: root token from `secrets/vault-init.json`) |
| `VAULT_ADDR` | Default `http://127.0.0.1:8200` |

### cert enroll

```
portcullis cert enroll [--slot SLOT] [--ttl TTL] <username> [email]
```

Generates a new ECCP256 key pair on the YubiKey, overwriting the slot. It then
creates a CSR, has Vault sign it, and imports the YubiKey certificate into the
slot. It ends by naming the Sign-in page, `https://people.<domain>/signin`,
where the person renews it later.

| Option | Meaning |
|--------|---------|
| `--slot SLOT` | PIV slot (default: `$PIV_SLOT` or `9a`, Authentication) |
| `--ttl TTL` | Certificate lifetime (default: `$CLIENT_CERT_TTL` or `720h`). The Vault role caps it at `CLIENT_CERT_TTL` as of the last `pki setup` |

### cert renew

```
portcullis cert renew [--slot SLOT] [--ttl TTL] <username> [email]
```

Keeps the key already on the YubiKey and issues a fresh YubiKey certificate
for it. Same options as `cert enroll`. People can also renew their own on the
Sign-in page (see
[Certificates](../setup/certificates.md#lifetime-and-renewal)).

### cert revoke

```
portcullis cert revoke [--yes] <serial>
```

Revokes a YubiKey or browser certificate in Vault (it finds which CA issued
the serial), rotates that CA's CRL and rewrites the revoked-serial list that
group-gate checks on every request. Find serials with `portcullis cert list`,
on the person's Sign-in tab in the Hub, or on their Sign-in page. This is how
an administrator's certificate is revoked: the Hub refuses it.

| Option | Meaning |
|--------|---------|
| `-y`, `--yes` | Do not ask for confirmation |

### cert list

```
portcullis cert list [--all]
```

Lists issued YubiKey and browser certificates: serial, KIND (`YubiKey` or
`Browser`), CN, status and expiry. `expiring` means fewer than
`CERT_EXPIRY_WARN_DAYS` (default 7) days are left.

| Option | Meaning |
|--------|---------|
| `--all` | Include revoked certificates |

### cert sync

```
portcullis cert sync
```

Rewrites `certs/revocation/revoked-serials.txt` atomically from Vault's lists
of revoked serials of both CAs (`pki_int` and `pki_file`, the union). If
either cannot be queried (sealed, bad token, unreachable),
the file is left unchanged and the command fails. It never "un-revokes" by
writing an empty list.
