# 💬 Matrix (Synapse + Element)

> Self-hosted Matrix chat server (Synapse) with the Element web client

**Category:** communication  
**Tags:** `chat`, `matrix`, `synapse`, `element`, `messaging`, `e2ee`  
**Website:** <https://element-hq.github.io/synapse/>  
**Source:** <https://github.com/element-hq/synapse>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_matrix` |
| **Admin Group** | `admin_matrix` |
| **Admin Paths** | `/_synapse/admin` (require `admin_matrix` in addition to access) |
| **Subdomain** | `element`, `matrix` |

!!! info "Auth Notes"
    Two hosts per instance. The homeserver (matrix.<domain>, Synapse) does its own OIDC login against Keycloak and has no forward-auth, so Element, the Element mobile apps and other Matrix clients and bots reach the client API directly; Synapse only lets in users whose groups claim contains users_matrix (oidc attribute_requirements): outsiders get no account and no session. Element Web (element.<domain>) is a static client behind forward-auth + group-gate, so only members even get the page; it is fixed to this homeserver (no server picker) and redirects straight to SSO. Revoking access: Synapse checks the group only at the SSO login, so a user removed from users_matrix (or disabled in LLDAP) keeps the sessions they already have; every session expires after 7 days (session_lifetime) and must sign in again through the group-checked login. To cut a user off at once, deactivate them through the Admin API from inside the synapse container (POST /_synapse/admin/v1/deactivate/<user id> with an admin access token) or log out their devices (DELETE /_synapse/admin/v2/users/<user id>/devices/<device id>). Element Web is the one native-OIDC host router behind forward-auth (validate.py GATED_CLIENT_ROUTERS): it is a static client with no login of its own and no server data. Identity: accounts are keyed on the OIDC sub; the Matrix id is @<LLDAP username>:<homeserver host> (localpart_template preferred_username). allow_existing_users is false, so an SSO login is never attached to an existing account, and the email is not imported. No password login (password_config.enabled false), no open registration, no 3PID changes. A reused LLDAP username (new Keycloak sub) gets a new id with a numeric suffix, never the old account. server_name is the homeserver's hostname, so no .well-known on the apex is needed (Synapse serves /.well-known/matrix/client itself). It is permanent: every user and room id contains it. Synapse refuses to start if the instance's homeserver hostname changes after the first start; pick it when creating the instance (hosts.immutable: the Hub refuses to change it once the instance exists; the Element host can change any time). The default instance's homeserver host is matrix.<main domain>: changing Portcullis's main domain breaks it. A backup restores into the same instance only, never a new id. Admins: Synapse has no group-to-admin mapping, so admin_matrix grants nothing inside Synapse. Promote the first admin after their first SSO login with `UPDATE users SET admin = 1 WHERE name = '@alice:<homeserver host>';` in the matrix-db container (psql -U synapse -d synapse), then restart the synapse container; later admins via the Admin API (PUT /_synapse/admin/v2/users/<user id> {"admin": true}). The Admin API (/_synapse/admin, including shared-secret registration) is additionally behind forward-auth + group-gate and requires admin_matrix (auth.admin_paths), so call it from a browser session of an admin_matrix member or from inside the synapse container (curl http://localhost:8008/_synapse/admin/... with an admin access token, Element: Settings, Help & About). Federation is off: federation_domain_whitelist is [] and the listener serves no federation resource. To federate with specific servers, list their server names in the Federation peers setting: Synapse then serves the federation API and /.well-known/matrix/server on the homeserver host (port 443) and federates with those servers only. Open federation is not offered. Secrets (database, OIDC, registration shared secret, macaroon and form secrets) are generated per instance; the config is rendered at every start into a tmpfs; the server signing key is created once in the synapse-data volume (back it up with the volume: losing it breaks federation and other servers' trust). Synapse trusts X-Forwarded-For from any peer on portcullis-proxy (client IPs in logs and rate limits only). Upgrades: Synapse supports rolling upgrades between releases but read docs/upgrade.md for each step; keep matrix-db on PostgreSQL 16. Element Web is independent of the Synapse version.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `element` | `element.<domain>` | all | `authaware@file` | :white_check_mark: |
| `matrix` | `matrix.<domain>` | all | `authaware@file` | :x: |
| `matrix-admin` | `matrix.<domain>` | `/_synapse/admin` | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `element` | `vectorim/element-web:v1.12.33` | `sha256:b0aa4b5a4fc1…` |
| `matrix-db` | `postgres:16.15-alpine` | `sha256:0cefaabd882e…` |
| `synapse` | `ghcr.io/element-hq/synapse:v1.164.2` | `sha256:f0df87cff259…` |
| `synapse-init` | `ghcr.io/element-hq/synapse:v1.164.2` | `sha256:f0df87cff259…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Federation peers** | `list` of `string` | instance | `restart` | Matrix server names this homeserver may federate with (e.g. matrix.example.org). Empty = federation off (default). |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `MATRIX_DB_PASSWORD` | Synapse PostgreSQL password | `random` |
| `MATRIX_OIDC_SECRET` | Synapse OIDC client secret | `random` |
| `SYNAPSE_REGISTRATION_SECRET` | Synapse registration_shared_secret (Admin API break-glass registration) | `random` |
| `SYNAPSE_MACAROON_SECRET` | Synapse macaroon_secret_key (signs access and login tokens) | `random` |
| `SYNAPSE_FORM_SECRET` | Synapse form_secret (signs consent and SSO forms) | `random` |

## Keycloak Clients

**Matrix (Synapse)** (`matrix`)

Redirect URI: `https://{{HOST_MATRIX}}/_synapse/client/oidc/callback`

## Access URLs

- **Element**: `https://{{HOST_ELEMENT}}`
- **Homeserver**: `https://{{HOST_MATRIX}}`
