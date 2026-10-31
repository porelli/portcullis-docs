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
| | [`version`](#version) | Core version and the Hub image in use |
| Backups | [`backup`](#backup) | Consistent backup to `backups/` (`--offsite`: also restic, encrypted) |
| | [`backup verify`](#backup-verify) | `restic check` + restore + sanity checks (or `--local`) |
| | [`backup schedule`](#backup-schedule) | systemd timer for daily backups |
| | [`restore`](#restore) | Restore a local or off-host (`--from-offsite`) backup |
| Configuration | [`config apply`](#config-apply) | Apply `ACME_STAGING` / `MTLS_ENABLED`, rebuild the CA bundle |
| | [`config init`](#config-init) | Keep your settings in `config/`, a separate git repo |
| | [`dns setup`](#dns-setup) | Create A/AAAA records for the domain and its wildcard |
| Vault and PKI | [`vault init`](#vault-init) | Initialise and unseal Vault, set up the enroll AppRole |
| | [`vault unseal`](#vault-unseal) | Unseal Vault and wait until it is active |
| | [`vault rotate-enroll-secret`](#vault-rotate-enroll-secret) | Issue a new enroll AppRole secret-id |
| | [`pki setup`](#pki-setup) | Create the client-certificate CA (idempotent) |
| Identity | [`keycloak configure`](#keycloak-configure) | Import or patch the `portcullis` realm |
| | [`oidc register`](#oidc-register) | Create the core OIDC clients and push their secrets from `.env` |
| Client certificates (YubiKey PIV) | [`cert enroll`](#cert-enroll) | New key and certificate on a YubiKey |
| | [`cert renew`](#cert-renew) | New certificate for the key already on the YubiKey |
| | [`cert revoke`](#cert-revoke) | Revoke a certificate (enforced by group-gate) |
| | [`cert list`](#cert-list) | List issued certificates |
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
4. Re-runs the idempotent setup steps: `vault init`, `pki setup` (client role incl. `CLIENT_CERT_TTL`, Keycloak truststore) and the CA bundle.
5. Runs `docker compose up -d --build` and waits for health.
6. Runs `keycloak configure` and `oidc register`.

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
- Vault: sealed/active, CA expiry, issued certs, and client certs expiring within `CERT_EXPIRY_WARN_DAYS` (default 7) days
- Keycloak: realm, users, forward-auth client
- LLDAP and Traefik

Exits 1 if a core service is down or unhealthy, or if Vault is not active.
Otherwise it exits 0.

| Option | Meaning |
|--------|---------|
| `--json` | Machine-readable output (same exit status). Expiring certs are in `vault.certs_expiring` |
| `--textfile` | Write the same data as Prometheus metrics to `monitoring/textfile/status.prom` for the [monitoring profile](monitoring.md): service health, Vault active, CA and per-user client-cert expiry. Run it after every scheduled backup (the systemd unit does) |

### version

```
portcullis version [--json]
```

Prints the core version and the Hub image in use:

- **Core version.** The `VERSION` file of a release tarball, else `git describe` of the checkout.
- **Hub image.** `HUB_IMAGE` from `.env` or the environment, else the default pinned in `docker-compose.yml`, plus the image of the running Hub container if there is one.

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
portcullis restore [--yes] <backup-dir>
portcullis restore [--yes] --from-offsite [SNAPSHOT]
portcullis restore --list [--offsite]
```

Stops Portcullis and restores a backup made by `portcullis backup` or
`upgrade`:

- `.env`, `certs/`, `secrets/` and the config files
- the Vault data: the raft snapshot is restored into a fresh Vault, which then unseals with the backed-up key
- the Keycloak database: `pg_restore` into a fresh Postgres
- the LLDAP, Hub and ACME volumes

Then everything is started again. The backup's checksums are verified first.
The current `.env`, `secrets/` and `certs/` are saved to
`backups/pre-restore-<timestamp>/`.

`--from-offsite` restores `SNAPSHOT` (default: latest) from
`BACKUP_REPOSITORY`. On a new host without `.env`, export `BACKUP_REPOSITORY`,
`BACKUP_PASSWORD` and the provider credentials first. The `.env` comes from
the backup.

| Option | Meaning |
|--------|---------|
| `-y`, `--yes` | Do not ask for confirmation |
| `--from-offsite` | Restore from the restic repository |
| `--list` | List local backups (`--offsite`: restic snapshots) |

---

## Configuration

### config apply

```
portcullis config apply [--bundle-only]
```

Applies the TLS toggles in `.env` and rebuilds `certs/ca-bundle.crt`:

| Variable | Default | Effect |
|----------|---------|--------|
| `ACME_STAGING=true\|false` | `false` | Let's Encrypt staging vs production. Sets `ACME_CA_SERVER` in `.env`. On a flip it clears Traefik's `acme.json` so Traefik registers again |
| `MTLS_ENABLED=true\|false` | `true` | Rewrites `traefik/dynamic/tls.yml`. With `false` no tier requests client certs, and routers that rely only on the protected tier become unauthenticated |

Run `portcullis up` afterwards to restart Traefik. See
[TLS & mTLS](../setup/certificates.md).

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

Creates the client-certificate CA in Vault:

- root CA (10 years) and intermediate CA (5 years)
- the `client-cert` role, with lifetime `CLIENT_CERT_TTL` (default `720h` = 30 days). The CN is taken from the caller, never from the CSR

It writes `certs/root-ca.crt`, `intermediate-ca.crt`, `ca-chain.crt` and
Keycloak's truststore (`certs/truststore/portcullis-ca-chain.pem`), and
enables CRL auto-rebuild on `pki_int`.

It is idempotent:

- An existing CA is never replaced.
- The `client-cert` role is rewritten, so a new `CLIENT_CERT_TTL` applies to certs issued from then on.
- Missing pieces (CA files, truststore, server cert) are recreated.
- A partial earlier run is redone.

If Vault has no CA but `certs/ca-chain.crt` exists (Vault data lost), it
refuses to create a new CA. Restore a backup, or use `--force`.

| Option | Meaning |
|--------|---------|
| `--force` | **Destroy** the existing CA and create a new one. Every enrolled client certificate stops working |
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
- points the LDAP federation at LLDAP (`LLDAP_BASE_DN`, `LLDAP_ADMIN_PASSWORD`)
- sets the ACR→LoA map and `browserFlow=portcullis-universal`
- pushes the X.509 authenticator settings from the file to the realm: CRL check against Vault's `pki_int` CRL, trust re-validation, `clientAuth` EKU
- checks the AMR reference values, and ensures the `amr` mapper and the `groups` scope
- ensures the `email-unverified` scope (`email` claim, no `email_verified`) that Hub templates opt into with `keycloak_clients[].email_verified_claim: false`
- sets the `acr`/`groups` scopes and the redirect URI on `portcullis-forward-auth`
- creates a credential-less `testuser` and applies the `PORTAL_DISPLAY_NAME` branding

| Option | Meaning |
|--------|---------|
| `--wipe-realm` | Delete the realm first and re-import it from the file. Needed to apply auth-flow changes; clients must then be re-registered with `portcullis oidc register` |

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

## Client certificates (YubiKey PIV)

`cert enroll` and `cert renew` need `ykman`, `openssl`, `jq` and Vault access.
Run them on the Portcullis host, or export `VAULT_ADDR`/`VAULT_TOKEN`. The cert
CN is `<username>`.

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
creates a CSR, has Vault sign it, and imports the certificate into the slot.

| Option | Meaning |
|--------|---------|
| `--slot SLOT` | PIV slot (default: `$PIV_SLOT` or `9a`, Authentication) |
| `--ttl TTL` | Certificate lifetime (default: `$CLIENT_CERT_TTL` or `720h`). The Vault role caps it at `CLIENT_CERT_TTL` as of the last `pki setup` |

### cert renew

```
portcullis cert renew [--slot SLOT] [--ttl TTL] <username> [email]
```

Keeps the key already on the YubiKey and issues a fresh certificate for it.
Same options as `cert enroll`. Users can also renew their own certificate at
`https://enroll.<domain>/self` (see
[TLS & mTLS](../setup/certificates.md#lifetime-and-renewal)).

### cert revoke

```
portcullis cert revoke [--yes] <serial>
```

Revokes a client certificate in Vault and rewrites the revoked-serial list that
group-gate checks on every request. Find serials with `portcullis cert list` or
in the enrollment UI (`/certs`).

| Option | Meaning |
|--------|---------|
| `-y`, `--yes` | Do not ask for confirmation |

### cert list

```
portcullis cert list [--all]
```

Lists issued client certificates: serial, CN, status and expiry. `expiring`
means fewer than `CERT_EXPIRY_WARN_DAYS` (default 7) days are left.

| Option | Meaning |
|--------|---------|
| `--all` | Include revoked certificates |

### cert sync

```
portcullis cert sync
```

Rewrites `certs/revocation/revoked-serials.txt` atomically from Vault's list of
revoked serials. If Vault cannot be queried (sealed, bad token, unreachable),
the file is left unchanged and the command fails. It never "un-revokes" by
writing an empty list.
