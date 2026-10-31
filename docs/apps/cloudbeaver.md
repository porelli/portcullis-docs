# 🗃 CloudBeaver

> Web-based database manager — PostgreSQL, MySQL, SQLite and more

**Category:** devops  
**Tags:** `database`, `sql`, `admin`, `postgresql`, `mysql`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `header-auth` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_cloudbeaver` |
| **Admin Group** | `admin_cloudbeaver` |
| **Subdomain** | `db` |

!!! info "Auth Notes"
    Access gated by forward-auth + group-gate. CloudBeaver's reverseProxy auth provider logs users in from X-Forwarded-User (the immutable LLDAP username; the provider has no email header) and trusts team/role headers from any peer with no allowlist, so CloudBeaver is kept off portcullis-proxy behind a small nginx gate (cloudbeaver-gate) that rejects (403) X-Forwarded-User or X-Forwarded-Email from anything but Traefik (PORTCULLIS_TRAEFIK_IP) and strips the X-User/X-Team/X-Role/X-Role-TE/name and X-Forwarded-Email headers. Accounts created when the header carried the email are named after it; rename them to the LLDAP username in CloudBeaver's admin UI. Roles and connections are managed in CloudBeaver.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `cloudbeaver` | `db.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `cloudbeaver` | `dbeaver/cloudbeaver:26.2.3` | `sha256:0c875296f85f…` |
| `cloudbeaver-gate` | `nginx:1.31.8-alpine` | `sha256:785835ea65db…` |

## Access URLs

- **Database Manager**: `https://db.{{DOMAIN}}`
