# Portcullis

**Self-hosted YubiKey authentication gateway for your entire homelab.**

Portcullis puts a unified authentication layer in front of all your self-hosted applications. Tap your YubiKey to log in -- one identity, one set of credentials, every app.

## Key Features

- **WebAuthn (FIDO2)** -- Passwordless browser authentication with YubiKey tap
- **mTLS (PIV certificates)** -- Client certificate auth for APIs, CLI tools, and service-to-service communication
- **22+ app templates** -- Enable apps like Jellyfin, Nextcloud, Grafana, Immich, and more with one click
- **Hub UI** -- Web dashboard to manage apps, view logs, configure settings, and control access
- **Per-app access control** -- LLDAP groups determine who can access which apps
- **Single sign-on** -- Keycloak-powered OIDC/SAML for apps with native SSO support
- **Forward auth** -- Transparent authentication for apps without SSO via oauth2-proxy + group-gate
- **Wildcard TLS** -- One wildcard certificate covers all subdomains, with automatic renewal via ACME DNS-01
- **Privacy by design** -- Individual subdomain names never appear in Certificate Transparency logs
- **Fully self-hosted** -- No external auth providers, no cloud dependencies

## How It Works

Traefik sits at the edge as a reverse proxy, terminating TLS and optionally requesting client certificates. Behind it, oauth2-proxy and group-gate enforce authentication and per-app access. Keycloak acts as the identity provider, federating users from LLDAP (a lightweight LDAP directory). Vault PKI issues client certificates (30 days, self-service renewal) for mTLS, and revocation is checked on every request.

Apps choose their auth method: forward-auth for apps without SSO support, native OIDC for apps that speak OpenID Connect, header-auth for apps that trust upstream identity headers, or public for apps that need no authentication.

## Repositories

Portcullis is split across four repositories:

| Repository | Purpose | Link |
|-----------|---------|------|
| **portcullis** | Core stack: Traefik, Keycloak, LLDAP, Vault, oauth2-proxy, group-gate, enrollment UI and the `./portcullis` admin CLI | [porelli/portcullis](https://github.com/porelli/portcullis) |
| **portcullis-hub** | Management UI for enabling apps, viewing logs, and configuring settings. Published as `ghcr.io/porelli/portcullis-hub`. | [porelli/portcullis-hub](https://github.com/porelli/portcullis-hub) |
| **portcullis-templates** | 22 app templates (manifest + compose) that serve as the default Hub marketplace | [porelli/portcullis-templates](https://github.com/porelli/portcullis-templates) |
| **portcullis-docs** | This documentation site | [porelli/portcullis-docs](https://github.com/porelli/portcullis-docs) |

## Quick Links

- [Quick Start](setup/quickstart.md) -- Get Portcullis running in minutes
- [Architecture](architecture.md) -- Understand how the components fit together
- [App Catalog](apps/index.md) -- Browse available app templates
- [DNS Configuration](setup/dns.md) -- Set up your domain and wildcard DNS
- [TLS & mTLS](setup/certificates.md) -- Configure certificates and client auth
- [Adding an App](guides/adding-an-app.md) -- Create your own app template
- [Groups & Access Control](operations/groups.md) -- Manage who can access what
- [Hub Management](operations/hub.md) -- Use the web UI to manage everything
- [CLI Reference](operations/cli.md) -- Every `./portcullis` command
- [Security & Hardening](operations/hardening.md) -- Socket proxies, networks, header trust, threat model
