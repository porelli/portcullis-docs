# Quick Start

Get Portcullis running from zero to a working authentication gateway.

## Prerequisites

- **Docker** and **Docker Compose** (v2) -- [Install Docker](https://docs.docker.com/get-docker/)
- **A domain you control** with DNS hosted on a supported provider (Cloudflare, Porkbun, Route53, etc.)
- **A server** with ports 80 and 443 open (VPS, home server, or local machine)
- **A YubiKey** (optional for initial setup, required for WebAuthn authentication)

## Step 1: Clone the Core Repository

Clone only the core repo -- this contains everything needed to run the gateway:

```bash
git clone git@github.com:porelli/portcullis.git
cd portcullis
```

The Hub image is pulled automatically from `ghcr.io/porelli/portcullis-hub` (no build step needed), and the app templates are auto-cloned from `porelli/portcullis-templates` by the Hub on first startup.

## Step 2: Run Bootstrap

The bootstrap script handles all first-time setup:

```bash
./scripts/bootstrap.sh
```

The script will prompt you for:

- **Domain**: Your base domain (e.g., `portcullis.example.com`)
- **ACME email**: Email for Let's Encrypt certificate notifications
- **DNS provider**: Your DNS provider name (e.g., `cloudflare`, `porkbun`, `route53`)
- **DNS credentials**: API tokens or keys for your DNS provider

### What Bootstrap Does

1. **Generates secrets** -- Random passwords for Keycloak, PostgreSQL, LLDAP, oauth2-proxy, and other services
2. **Creates `.env`** -- Writes all configuration to a single environment file
3. **Starts core services** -- Brings up PostgreSQL, Vault, LLDAP, and Keycloak
4. **Initializes Vault PKI** -- Creates root and intermediate CAs for client certificate issuance
5. **Configures Keycloak** -- Imports the Portcullis realm with WebAuthn flows, X.509 authenticator, and LLDAP federation
6. **Registers OIDC clients** -- Creates the oauth2-proxy client in Keycloak
7. **Starts Traefik** -- Brings up the reverse proxy with ACME certificate request
8. **Starts auth services** -- Brings up oauth2-proxy, group-gate, and the Hub

## Step 3: Wait for Certificates

Traefik will request a wildcard certificate via ACME DNS-01 challenge. This typically takes 1-3 minutes. Check progress:

```bash
docker compose logs -f traefik 2>&1 | grep -i acme
```

You should see a message indicating the certificate was obtained for `*.portcullis.example.com`.

!!! note "Staging certificates"
    By default, `ACME_STAGING=true` uses Let's Encrypt staging certificates. These are not trusted by browsers but have no rate limits. See [TLS & mTLS](certificates.md) for details on switching to production.

## Step 4: Access the Hub

Open your browser and navigate to:

```
https://hub.<your-domain>
```

For example: `https://hub.portcullis.example.com`

If using staging certificates, you will need to accept the browser security warning or launch Chrome with `--ignore-certificate-errors`.

The Hub is Portcullis's web dashboard where you can enable apps, manage settings, and monitor services.

## Step 5: Enable Your First App

From the Hub:

1. Browse the **App Catalog**
2. Click on an app (e.g., Pi-hole, Grafana, or Jellyfin)
3. Click **Enable**
4. Configure any required settings (media paths, etc.)
5. The app will start and become accessible at its subdomain

## Step 6: Create Users in LLDAP

Open the LLDAP admin interface:

```
https://directory.<your-domain>
```

Log in with the LLDAP admin password (shown during bootstrap, stored in `.env` as `LLDAP_ADMIN_PASSWORD`).

1. Click **Create user**
2. Enter username, email, first name, last name
3. Set a temporary password (needed only for initial WebAuthn enrollment)
4. Add the user to app-specific groups (e.g., `users_grafana`, `users_pihole`)

## Step 7: First Login with WebAuthn

1. Open any protected app (e.g., `https://grafana.<your-domain>`)
2. You will be redirected to Keycloak
3. Enter the username and temporary password
4. Keycloak will prompt you to **register a security key**
5. Insert your YubiKey and tap it when prompted
6. You are now enrolled -- future logins require only a YubiKey tap

!!! tip "Passwordless after enrollment"
    After the initial WebAuthn enrollment, Keycloak's auth flow is: attempt X.509 (mTLS cert) first, then WebAuthn passwordless (YubiKey tap), then fall back to username + WebAuthn. Most users will simply tap their YubiKey.

## Next Steps

- [Configure DNS](dns.md) for your domain
- [Set up production TLS](certificates.md) when ready to go live
- [Understand the architecture](../architecture.md)
- [Add custom apps](../guides/adding-an-app.md)
- [Manage groups and access](../operations/groups.md)
