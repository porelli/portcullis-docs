# 📄 Docs Site

> Public documentation — no authentication

**Category:** public  
**Tags:** `docs`, `static`, `nginx`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `public` |
| **SSO** | :x: No |
| **Group Access** | :x: |
| **Group Admin** | :x: |
| **Subdomain** | `docs` |

!!! info "Auth Notes"
    Public documentation site — no authentication required.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `docs` | `docs.<domain>` | all | `public@file` | :x: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `docs` | `squidfunk/mkdocs-material:9.8.0` | `sha256:dc3b5de76c6e…` |

## Access URLs

- **Docs**: `https://docs.{{DOMAIN}}`
