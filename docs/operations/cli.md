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
| | [`dns setup`](#dns-setup) | Create A/AAAA records for the domain and its wildcard |
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
password and JWT secret, the forward-auth client and cookie secrets, and
`HUB_PROXY_SECRET`, and `BACKUP_PASSWORD` for off-host backups. Then it runs these steps in order:

1. DNS records (`dns setup`)
2. Vault init, unseal and enroll AppRole (`vault init`)
3. CA bundle
4. `docker compose up`
5. Vault PKI, including a self-signed wildcard server cert for local use (`pki setup --with-server-cert`)
6. Keycloak realm (`keycloak configure`)
7. OIDC clients (`oidc register`)
8. `config/` repo (`config init`)

If `.env` already exists it is kept, and only empty or missing secrets are
generated. Every step is idempotent, so you can re-run `init` after a failure.

| Option | Meaning |
|--------|---------|
| `--domain DOMAIN` | Base domain (default: `$PORTCULLIS_DOMAIN`, otherwise a prompt) |
| `--email EMAIL` | Let's Encrypt account email (default: `admin@DOMAIN`) |
| `--dns-provider NAME` | `cloudflare`, `porkbun`, `route53`, `digitalocean`, `hetzner`, `none`, or another lego provider name (default: `cloudflare`) |
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

1. Generates any missing `HUB_PROXY_SECRET`, `FORWARD_AUTH_*`, `LLDAP_JWT_SECRET` or `BACKUP_PASSWORD`. Other secrets must already be in `.env`.
2. Creates a local backup (`portcullis backup`: Vault snapshot, `pg_dump`, volumes, `.env`, `certs/`, `secrets/`).
3. Pulls images.
4. Re-runs the idempotent setup steps: `vault init`, `pki setup` (both CAs, the `client-cert` and `browser-cert` roles incl. `CLIENT_CERT_TTL`, Keycloak truststore) and the CA bundle.
5. Runs `docker compose up -d --build` and waits for health.
6. Restarts services whose bind-mounted config files changed (see [`up`](#up) for the list).
7. Runs `keycloak configure` and `oidc register`.

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
- Keycloak: realm, users, forward-auth client
- LLDAP and Traefik
- containers on `portcullis-proxy` answering to a core service name or an AI
  companion name they don't own ([hardening](hardening.md#ai-support-mcp-gate))
- mcp-gate refusing every AI request (`503`) and why, for example AI
  credentials it can't decrypt with `secrets/mcp-gate/age.key`
  ([AI support → Residuals](ai.md#residuals))

Exits 1 if a core service is down or unhealthy, if Vault is not active, if
such a container exists, or if mcp-gate refuses every AI request.
Otherwise it exits 0.

| Option | Meaning |
|--------|---------|
| `--json` | Machine-readable output (same exit status). Expiring certs are in `vault.certs_expiring` (each with `kind`: `yubikey` / `browser`), name takeovers in `dns_shadows` (`container`, `name`), mcp-gate's refusal in `mcp_gate.refusing` (`null` while it serves) |
| `--textfile` | Write the same data as Prometheus metrics to `monitoring/textfile/status.prom` for the [monitoring profile](monitoring.md): service health, Vault active, CA expiry and per-person YubiKey / browser certificate expiry (label `kind`). Run it after every scheduled backup (the systemd unit does) |

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
| `ACME_STAGING=true\|false` | `false` | Let's Encrypt staging vs production. Sets `ACME_CA_SERVER` in `.env`. On a flip it clears Traefik's `acme.json` so Traefik registers again |

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

### dns setup

```
portcullis dns setup [--check]
```

Creates or updates the A records (and AAAA, if the host has public IPv6) for
`PORTCULLIS_DOMAIN` and `*.PORTCULLIS_DOMAIN`. They point at this host's public
IP. It uses `DNS_PROVIDER` and the provider's credentials from `.env`:

| Provider | Variables |
|----------|-----------|
| `cloudflare` | `CLOUDFLARE_API_TOKEN` |
| `porkbun` | `PORKBUN_API_KEY`, `PORKBUN_SECRET_API_KEY` |
| `digitalocean` | `DO_AUTH_TOKEN` |
| `hetzner` | `HETZNER_API_KEY` |
| `route53` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_HOSTED_ZONE_ID` (needs the `aws` CLI) |

For other providers, or `none`, it prints the records to create by hand.

| Option | Meaning |
|--------|---------|
| `--check` | Only compare what resolves (via 1.1.1.1) with the public IP. Exits non-zero if the records are not correct yet |

See [DNS Configuration](../setup/dns.md).

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
`protected-any` and `authaware` options), `ca-chain-yubikey.crt` (root + the
YubiKey CA only: Traefik's `protected` option) and Keycloak's
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
- sets `sslRequired=external`, `browserFlow=portcullis-universal`, an empty `acr.loa.map` (sign-in is decided by [templates](auth-policies.md), not levels), brute-force protection (10 failures, then 60 s more per failure up to 15 min, never permanent) and the passkey policy (direct attestation, any attachment, resident key and user verification required)
- offline sessions at most 30 days idle / 90 days total (the Hub sets shorter values on its AI clients); refresh-token rotation off
- rebuilds every top-level flow of the file whose tree changed: the browser flow with the sign-in extension's methods and template check ([Sign-in flows](auth-policies.md#sign-in-flows-in-keycloak)), the invite identity provider's first-login and post-login flows
- keeps `webauthn-register-passwordless` enabled and the two-factor `webauthn-register` disabled
- the invite identity provider `portcullis-invite` (enroll; URLs and client secret from `secrets/enroll/invite-client-secret`) and the service-account client `portcullis-enroll` (view-users, manage-users)
- `lldap_admin` = realm-admin of the `portcullis` realm (realm console)
- pushes each certificate step's settings from the file onto its `portcullis-x509` execution, by alias: `x509-config` (YubiKey certificate, Vault's `pki_int` CRLs) and `x509-browser-config` (browser certificate, `pki_file` CRLs), with trust re-validation and the `clientAuth` EKU
- never touches the realm's events config (the Hub owns it: sign-in history)
- checks the sign-in executions' AMR reference values (max age 10 h), and ensures the `amr` mapper and the `groups` scope
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
