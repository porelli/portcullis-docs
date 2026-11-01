# Quick Start

Get Portcullis running from zero to a working authentication gateway with one
command: `./portcullis init`.

## Prerequisites

- **Docker** with the **compose plugin** (v2) -- [Install Docker](https://docs.docker.com/get-docker/)
- `openssl`, `jq` and `curl` on the host (the CLI checks for them)
- **A domain you control**, with DNS hosted at a provider Traefik's ACME client (lego) supports: Cloudflare, Porkbun, Route53, DigitalOcean, Hetzner, ... (see [DNS Configuration](dns.md))
- **A server** with ports 80 and 443 reachable (VPS, home server, or local machine)
- **A YubiKey** (or another FIDO2 key) for WebAuthn. `ykman` is only needed for PIV/mTLS certificates

## Step 1: Clone the core repository

```bash
git clone git@github.com:porelli/portcullis.git
cd portcullis
```

That is all you need to clone. The Hub image is pulled from
`ghcr.io/porelli/portcullis-hub` (no build step), and the Hub clones the app
templates from `porelli/portcullis-templates` on first start.

## Step 2: Run `portcullis init`

```bash
./portcullis init
```

It prompts for:

- **Domain**: your base domain, e.g. `portcullis.example.com`. Apps live at `<name>.<domain>`
- **Email** for Let's Encrypt notices (default `admin@<domain>`)
- **DNS provider** (default `cloudflare`) and its API credentials, read with a hidden prompt

Unattended:

```bash
CLOUDFLARE_API_TOKEN=... ./portcullis init --non-interactive \
  --domain portcullis.example.com --dns-provider cloudflare
```

All options are in the [CLI Reference](../operations/cli.md#init).

### What `init` does

1. **Writes `.env`** (mode `0600`) with every secret randomly generated:
   `POSTGRES_PASSWORD`, `KEYCLOAK_ADMIN_PASSWORD`, `LLDAP_ADMIN_PASSWORD`,
   `LLDAP_JWT_SECRET`, `FORWARD_AUTH_CLIENT_SECRET`,
   `FORWARD_AUTH_COOKIE_SECRET`, `HUB_PROXY_SECRET`, and `BACKUP_PASSWORD`
   (encrypts off-host backups). Docker compose refuses
   to start if any of them is missing, so there are no default passwords. An
   existing `.env` is kept; only empty or missing secrets are filled in.
2. **Creates DNS records** for `<domain>` and `*.<domain>` pointing at this
   host's public IP (`dns setup`; skipped with `--skip-dns` or
   `--dns-provider none`). The wildcard covers all app and core subdomains: `auth`, `traefik`, `hub`, `directory`, `enroll`, `people`, `metrics`, and each enabled app.
3. **Initialises Vault** in server mode with persistent raft storage. The root
   token and unseal key go to `secrets/` (see the warning below), and the
   enrollment service gets a least-privilege AppRole. Vault unseals itself on
   every start from then on.
4. **Starts the core stack** (`docker compose up -d --build`) and waits for
   Vault, PostgreSQL, LLDAP and Keycloak to be healthy.
5. **Creates the Vault PKI**: root and intermediate CA for YubiKey client
   certificates, Keycloak's truststore, and a self-signed wildcard server cert
   for local use.
6. **Configures Keycloak**: imports the `portcullis` realm (WebAuthn, X.509,
   LLDAP federation, step-up flows) and registers the forward-auth OIDC client
   with the secret from `.env`.
7. **Creates `config/`**, a separate git repo holding your `.env` and
   overrides (skip with `--no-config-repo`; see
   [CLI Reference](../operations/cli.md#config-init)).
8. **Prints the URLs** of the enrollment UI, directory, identity provider, Hub
   and Traefik dashboard.

Every step is idempotent: if something fails (DNS not propagated yet, a slow
image pull), fix it and run `./portcullis init` again.

!!! danger "Back up `secrets/` now, offline"
    `secrets/vault-init.json` holds the Vault root token and the unseal key.
    Losing it together with the host means losing the CA, and every client
    certificate with it. Anyone who has it can unseal Vault. Keep an offline
    copy, and treat backups made by `./portcullis backup` the same way: they
    contain `secrets/` and `.env`. Store `BACKUP_PASSWORD` offline too:
    without it, off-host backups can't be restored after losing the host
    (see [Backups](../operations/backups.md)).

### Settings in `.env` worth knowing

`init` writes sensible defaults. The full reference with comments is
`.env.example` in the core repo.

| Variable | Default | Notes |
|----------|---------|-------|
| `ACME_STAGING` | `false` | `true` uses Let's Encrypt staging (untrusted certs, no rate limits). Apply with `./portcullis config apply && ./portcullis up` |
| `MTLS_ENABLED` | `true` | Request YubiKey client certificates. See [TLS & mTLS](certificates.md) |
| `CLIENT_CERT_TTL` | `720h` | Client certificate lifetime (30 days) |
| `HUB_PROXY_SECRET` | generated | Shared secret Traefik adds to every request to the Hub. The Hub refuses to start without it (at least 32 characters) |
| `HUB_IMAGE` | `ghcr.io/porelli/portcullis-hub:edge` on core `main` | Hub image. `edge` is the latest build of the Hub's `main`; a core release pins a released tag by digest. If you override it, use a released tag with its digest, e.g. `ghcr.io/porelli/portcullis-hub:1.2.3@sha256:…` (see [Upgrading & Releases](../operations/upgrading.md#hub-image)) |
| `BACKUP_PASSWORD` | generated | restic repository password for `./portcullis backup --offsite`. Keep an offline copy; never rotate it |
| `BACKUP_REPOSITORY` | unset | restic repository for off-host backups (`s3:`, `b2:`, `rest:`, …). See [Backups](../operations/backups.md) |
| `COMPOSE_PROFILES` | unset | `monitoring` enables Prometheus, Alertmanager and Grafana at `metrics.<domain>`. See [Monitoring](../operations/monitoring.md) |
| `HUB_SHARED_ENV` | empty | Extra variable names the Hub may pass to templates. Core secrets are refused |
| `HUB_OVERRIDE_BIND_ROOTS` | `/srv:/mnt:/media` | Host directories an app's custom compose override (Hub → Expert) may bind-mount. System paths and `/` are refused |
| `PORTCULLIS_PROXY_SUBNET` | `172.31.250.0/24` | Fixed subnet of the shared `portcullis-proxy` network |
| `PORTCULLIS_PROXY_IP_RANGE` | `172.31.250.128/25` | Dynamic addresses for app containers. Must be inside the subnet and must not contain Traefik's IP |
| `PORTCULLIS_TRAEFIK_IP` | `172.31.250.2` | Traefik's static IP on `portcullis-proxy`. Header-auth apps trust identity headers only from this address |
| `PORTCULLIS_AUTH_SUBNET` | `172.31.251.0/28` | Internal Traefik ↔ Keycloak network `portcullis-auth`. Must not overlap the proxy subnet |
| `PORTCULLIS_AUTH_IP_RANGE` | `172.31.251.8/29` | Dynamic range on `portcullis-auth` |
| `PORTCULLIS_AUTH_TRAEFIK_IP` | `172.31.251.2` | The only address Keycloak accepts proxy headers (incl. the forwarded client cert) from |
| `HUB_PEOPLE_ADDR` | `:8889` | Hub's people listener port (set by core, not operator config). Accessible to any signed-in user at `people.<domain>` |

!!! warning "Change the network ranges before `init`, not after"
    Only change the `PORTCULLIS_*_SUBNET` / `_IP_RANGE` / `_TRAEFIK_IP`
    values if they collide with a host, LAN or VPN network, and do it
    **before** the first `init` (`./portcullis init --env-only` writes `.env`
    and stops, so you can edit it). Docker cannot change an existing network.
    For `portcullis-proxy` you would have to disable the apps in the Hub, run
    `./portcullis down`, `docker network rm portcullis-proxy`,
    `./portcullis up`, and re-enable the apps. `./portcullis up` detects the
    mismatch and prints these steps. See [Security & Hardening](../operations/hardening.md#networks).

## Step 3: Wait for the certificate

Traefik requests the wildcard certificate with an ACME DNS-01 challenge. This
usually takes 1-3 minutes:

```bash
docker compose logs -f traefik 2>&1 | grep -i acme
./portcullis status        # overall health; exits 1 if something is down
```

## Step 4: First sign-in (setup link)

Sign-in is **passkey-only**: there is no password anywhere in the browser
flow. `./portcullis init` ends with a one-time **setup link** for the LLDAP
`admin`:

1. Open the link, click **Register my key** and touch your YubiKey (set or
   enter its PIN).
2. You are signed in and land in the Hub. No LLDAP or Keycloak login.
3. Every later sign-in is **Sign in with Passkey** and one touch.

The link works once and expires after 72 h. A new one only from the server:
`./portcullis invite admin --to hub` adds another key (a spare);
`./portcullis invite admin --to hub --replace-keys` is for a lost or stolen
key (removes the old keys first). The Hub never issues links for
administrators.

## Step 5: Create users

In the Hub, **Users & Groups** (or LLDAP at `https://directory.<your-domain>`,
which keeps its own `admin` / `LLDAP_ADMIN_PASSWORD` login):

1. Create the user. The **username** is the user's identity everywhere (it
   can't be changed later). The email is only profile data: users can edit it
   themselves, so it is never used to identify or link accounts.
2. Add the user to the groups of the apps they need, e.g. `users_grafana`.
   Members of `lldap_admin` can reach the core admin UIs (Hub, enrollment,
   directory, Traefik dashboard, Keycloak's realm console).
3. Send the user their setup link (the Hub shows it once; on the server:
   `./portcullis invite <user>`). It lands them on `https://<your-domain>/`,
   the portal with the apps they may use.

Keycloak reads users and groups from LLDAP through its LDAP federation.

## Step 6: Enable your first app

In the Hub:

1. Browse the **App Catalog** and open an app (e.g. Grafana).
2. Fill in any required settings (media paths, etc.).
3. Click **Enable**. The Hub starts the app as its own compose project,
   registers its Keycloak client if it has one, and publishes its group and
   policy to group-gate.

The app is reachable at its subdomain. Users need the app's `users_<app>`
group if the app enforces group access.

## Step 7 (optional): YubiKey client certificates

For mTLS (PIV certificates), an admin enrolls a user's YubiKey at
`https://enroll.<your-domain>`, or on the host:

```bash
./portcullis cert enroll alice alice@example.com
```

Certificates last 30 days. Users renew their own at
`https://enroll.<your-domain>/self`. See [TLS & mTLS](certificates.md).

## Day-to-day

```bash
./portcullis status                # health
./portcullis up / down             # start / stop the core stack
git pull && ./portcullis upgrade   # update (backs up first)
./portcullis backup --offsite      # backup, also to restic (schedule it: backup schedule --systemd)
./portcullis version               # core version + Hub image
```

## Next steps

- [CLI Reference](../operations/cli.md)
- [Backups](../operations/backups.md): set up off-host backups and the systemd timer
- [Monitoring](../operations/monitoring.md)
- [DNS Configuration](dns.md)
- [TLS & mTLS](certificates.md)
- [Architecture](../architecture.md) and [Security & Hardening](../operations/hardening.md)
- [Groups & Access Control](../operations/groups.md)
- [Adding an App](../guides/adding-an-app.md)
