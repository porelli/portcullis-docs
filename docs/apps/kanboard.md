# 📋 Kanboard

> Minimalist Kanban project management with header-based auth

**Category:** productivity  
**Tags:** `kanban`, `projects`, `tasks`, `boards`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `header-auth` |
| **SSO** | :warning: Partial |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_kanboard` |
| **Admin Group** | `admin_kanboard` |
| **Subdomain** | `kanboard` |

!!! info "Auth Notes"
    Reverse proxy auth with X-Forwarded-User header, honoured only from Traefik (TRUSTED_PROXY_NETWORKS = PORTCULLIS_TRAEFIK_IP). Auto-creates users on first login. Admin role set manually in Kanboard UI. Access gated by group-gate.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `kanboard` | `kanboard.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `kanboard` | `kanboard/kanboard:v1.2.57` | `sha256:637989624e53…` |

## Access URLs

- **Kanboard**: `https://kanboard.{{DOMAIN}}`
