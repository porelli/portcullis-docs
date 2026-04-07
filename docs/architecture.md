# Architecture

Portcullis is a collection of services that work together to provide unified authentication for self-hosted applications. This page describes how the components connect and how authentication flows work.

## Component Overview

```mermaid
graph TB
    subgraph Internet
        User[User / Browser]
    end

    subgraph Portcullis
        Traefik[Traefik<br/>Reverse Proxy]

        subgraph Auth Layer
            OAuth2[oauth2-proxy<br/>Forward Auth]
            GroupGate[group-gate<br/>Access Control]
        end

        subgraph Identity
            Keycloak[Keycloak<br/>Identity Provider]
            LLDAP[LLDAP<br/>User Directory]
            Postgres[(PostgreSQL)]
        end

        subgraph PKI
            Vault[Vault PKI<br/>Certificate Authority]
        end

        subgraph Applications
            AppFA[Forward-Auth Apps<br/>Pi-hole, DokuWiki, ...]
            AppOIDC[Native OIDC Apps<br/>Jellyfin, Immich, ...]
            AppHeader[Header-Auth Apps<br/>Grafana, Kanboard, ...]
            AppPublic[Public Apps<br/>Plex, Docs, ...]
        end
    end

    User -->|HTTPS| Traefik
    User -.->|mTLS client cert| Traefik

    Traefik -->|forward-auth| OAuth2
    OAuth2 -->|OIDC| Keycloak
    Traefik -->|group check| GroupGate

    Traefik --> AppFA
    Traefik --> AppOIDC
    Traefik --> AppHeader
    Traefik --> AppPublic

    AppOIDC -->|OIDC| Keycloak

    Keycloak -->|LDAP federation| LLDAP
    Keycloak --> Postgres

    Vault -.->|issue client certs| User
```

### Component Roles

| Component | Role |
|-----------|------|
| **Traefik** | Reverse proxy. Terminates TLS, routes requests by subdomain, applies middleware chains, optionally requests client certificates. |
| **oauth2-proxy** | Forward authentication. Intercepts requests to protected apps, redirects unauthenticated users to Keycloak, and sets identity headers on success. |
| **group-gate** | Per-app access control. Checks the authenticated user's groups against the required group for each subdomain. Returns 403 if the user lacks access. |
| **Keycloak** | Identity provider. Handles WebAuthn (FIDO2) authentication, issues OIDC/SAML tokens, manages auth flows, and federates users from LLDAP. |
| **LLDAP** | Lightweight LDAP directory. Stores users and groups. Provides a web UI for user management. Keycloak syncs users and groups from LLDAP. |
| **PostgreSQL** | Database backend for Keycloak. |
| **Vault PKI** | Private certificate authority. Issues short-lived (24-hour) client certificates for mTLS authentication via the PIV slot on YubiKeys. |

## Repository Structure

Portcullis is organized as four separate repositories, each with a distinct responsibility:

- **Core repo** ([porelli/portcullis](https://github.com/porelli/portcullis)) -- Contains the `docker-compose.yml` for all core services (Traefik, Keycloak, LLDAP, Vault, oauth2-proxy, group-gate), bootstrap and helper scripts (`scripts/`), Traefik static and dynamic configuration (`traefik/`), Keycloak realm export, and the enrollment UI (`enroll/`). This is the only repo you need to clone to deploy Portcullis.

- **Hub repo** ([porelli/portcullis-hub](https://github.com/porelli/portcullis-hub)) -- The management web UI. Built and published as a container image at `ghcr.io/porelli/portcullis-hub`. The core `docker-compose.yml` pulls this image automatically -- no manual build step is required.

- **Templates repo** ([porelli/portcullis-templates](https://github.com/porelli/portcullis-templates)) -- Houses the 22 app templates (each with a `manifest.yaml` and `compose.yml`). The Hub automatically clones this repo on first startup as the default marketplace source. New templates are contributed here and synced to running instances via the Hub UI.

- **Docs repo** ([porelli/portcullis-docs](https://github.com/porelli/portcullis-docs)) -- This documentation site, built with MkDocs Material. App catalog pages are auto-generated from the template manifests.

## Authentication Flows

Portcullis supports four authentication methods. Each app declares its method in its `manifest.yaml`.

### Forward Auth (oauth2-proxy + group-gate)

Used by apps that have no native SSO support (Pi-hole, DokuWiki, Scrutiny, etc.). Traefik delegates authentication to oauth2-proxy before the request reaches the app.

```mermaid
sequenceDiagram
    participant U as User
    participant T as Traefik
    participant O as oauth2-proxy
    participant G as group-gate
    participant K as Keycloak
    participant A as App

    U->>T: GET https://pihole.example.com
    T->>O: Forward auth check
    O-->>T: 401 (no session)
    T-->>U: 302 Redirect to oauth2-proxy /sign_in
    U->>O: Follow redirect
    O-->>U: 302 Redirect to Keycloak
    U->>K: Keycloak login (WebAuthn / YubiKey tap)
    K-->>U: 302 Redirect to oauth2-proxy /callback
    U->>O: Callback with auth code
    O->>K: Exchange code for tokens
    K-->>O: ID token + access token (includes groups)
    O-->>U: Set session cookie, redirect to app
    U->>T: GET https://pihole.example.com (with cookie)
    T->>O: Forward auth check
    O-->>T: 200 OK (headers: X-Forwarded-User, X-Forwarded-Groups)
    T->>G: Group check (subdomain=pihole, groups from header)
    G-->>T: 200 OK (user is in users_pihole)
    T->>A: Forward request
    A-->>U: App response
```

### Native OIDC

Used by apps with built-in OpenID Connect support (Jellyfin, Immich, Vaultwarden, Nextcloud, etc.). The app redirects to Keycloak directly, without oauth2-proxy.

```mermaid
sequenceDiagram
    participant U as User
    participant T as Traefik
    participant A as App
    participant K as Keycloak

    U->>T: GET https://photos.example.com
    T->>A: Forward request
    A-->>U: 302 Redirect to Keycloak authorize endpoint
    U->>K: Keycloak login (WebAuthn / YubiKey tap)
    K-->>U: 302 Redirect to app callback
    U->>T: GET https://photos.example.com/callback?code=...
    T->>A: Forward request
    A->>K: Exchange code for tokens
    K-->>A: ID token + access token
    A-->>U: Set session, app response
```

### Header Auth

Used by apps that accept a trusted identity header from the reverse proxy (Grafana, Kanboard, Firefly III). The user authenticates via forward auth, and the app reads the `X-Forwarded-User` header.

```mermaid
sequenceDiagram
    participant U as User
    participant T as Traefik
    participant O as oauth2-proxy
    participant G as group-gate
    participant A as App

    U->>T: GET https://grafana.example.com
    Note over T,O: Forward auth (same as above)
    T->>O: Forward auth check
    O-->>T: 200 OK (X-Forwarded-User: alice)
    T->>G: Group check
    G-->>T: 200 OK
    T->>A: Forward request with X-Forwarded-User: alice
    A-->>U: App logs in user "alice" automatically
```

### mTLS (Client Certificate)

When mTLS is enabled, Traefik can authenticate users via X.509 client certificates stored in the PIV slot of their YubiKey. This happens at the TLS layer, before any HTTP processing.

```mermaid
sequenceDiagram
    participant U as User + YubiKey
    participant T as Traefik
    participant K as Keycloak
    participant A as App

    U->>T: TLS handshake (presents client cert)
    T->>T: Verify cert against Vault CA chain
    Note over T: Extract CN from cert
    T->>A: Forward request with X-Forwarded-Tls-Client-Cert-Info
    A-->>U: App response (user authenticated by cert)
```

If the app also uses Keycloak, the X.509 authenticator in Keycloak's browser flow can map the certificate CN to a user identity, skipping the WebAuthn prompt entirely.

## TLS Tiers

Traefik is configured with three TLS option sets. Each app chooses its tier based on its security requirements.

| Tier | Traefik TLS Option | Client Cert Behavior | Use Case |
|------|-------------------|---------------------|----------|
| **protected** | `RequireAndVerifyClientCert` | Required -- TLS handshake fails without a valid cert | Highest security apps (Vault UI) |
| **authaware** | `VerifyClientCertIfGiven` | Optional -- verified if present, WebAuthn fallback if not | Most apps (default for forward-auth and OIDC apps) |
| **public** | `NoClientCert` | Not requested | Public-facing apps, apps that manage their own auth |

When `MTLS_ENABLED=false` in `.env`, all three tiers behave like `public` -- no client certificates are requested for any app.

## Network Topology

Portcullis uses a two-network architecture to isolate apps from core services. Traefik bridges between the networks and is the only service exposed to the internet (ports 80 and 443).

- **`portcullis` network** -- Core services only (Keycloak, LLDAP, Vault, PostgreSQL, oauth2-proxy, group-gate, Hub). Apps cannot reach these services directly.
- **`portcullis-proxy` network** -- Traefik and app frontend services. This is how Traefik discovers and routes to app containers.
- **Per-app internal networks** -- Each app's compose project creates its own default network. Internal services (databases, caches, workers) live here, isolated from all other apps.

Each app runs as its own Docker Compose project (`portcullis-<app-id>`). Frontend services join both `default` (for internal communication) and `portcullis-proxy` (for Traefik routing). Internal services only join `default`.

```mermaid
graph TB
    Internet -->|:80/:443| T

    subgraph "Network: portcullis (core)"
        T[Traefik :80/:443]
        KC[Keycloak :8080]
        LL[LLDAP :3890/:17170]
        V[Vault :8200]
        PG[PostgreSQL :5432]
        O2[oauth2-proxy :4180]
        GG[group-gate :8080]
        Hub[Hub :3000]
    end

    subgraph "Network: portcullis-proxy (routing)"
        T
        AppA_FE[App A Frontend]
        AppB_FE[App B Frontend]
        AppC_FE[App C Frontend]
    end

    subgraph "portcullis-appA (isolated)"
        AppA_FE
        AppA_DB[(App A Database)]
    end

    subgraph "portcullis-appB (isolated)"
        AppB_FE
        AppB_DB[(App B Database)]
    end

    subgraph "portcullis-appC (isolated)"
        AppC_FE
    end

    T --- O2
    T --- GG
    T --- AppA_FE
    T --- AppB_FE
    T --- AppC_FE
    AppA_FE --- AppA_DB
    AppB_FE --- AppB_DB
    KC --- LL
    KC --- PG
    O2 --- KC
```

Traefik is connected to both the `portcullis` network (for forward-auth checks via oauth2-proxy and group-gate) and the `portcullis-proxy` network (for routing to app frontends). Native OIDC apps that need to reach Keycloak do so over HTTPS via the public URL, not via the internal network.

DNS is configured as a wildcard record (`*.portcullis.example.com`), so all subdomains resolve to the same server IP. Traefik routes each subdomain to the correct container based on Docker labels.
