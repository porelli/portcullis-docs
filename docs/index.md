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

Traefik sits at the edge as a reverse proxy, terminating TLS and optionally requesting client certificates. Behind it, oauth2-proxy and group-gate enforce authentication and per-app access. Keycloak acts as the identity provider, federating users from LLDAP (a lightweight LDAP directory). Vault PKI issues short-lived client certificates for mTLS.

Apps choose their auth method: forward-auth for apps without SSO support, native OIDC for apps that speak OpenID Connect, header-auth for apps that trust upstream identity headers, or public for apps that need no authentication.

## Quick Links

- [Quick Start](setup/quickstart.md) -- Get Portcullis running in minutes
- [Architecture](architecture.md) -- Understand how the components fit together
- [App Catalog](apps/index.md) -- Browse available app templates
- [DNS Configuration](setup/dns.md) -- Set up your domain and wildcard DNS
- [TLS & mTLS](setup/certificates.md) -- Configure certificates and client auth
- [Adding an App](guides/adding-an-app.md) -- Create your own app template
- [Groups & Access Control](operations/groups.md) -- Manage who can access what
- [Hub Management](operations/hub.md) -- Use the web UI to manage everything
