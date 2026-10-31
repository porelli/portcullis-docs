# 📝 DokuWiki

> Simple, file-based wiki — no database required, easy backups

**Category:** productivity  
**Tags:** `wiki`, `docs`, `knowledge-base`, `file-based`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_dokuwiki` |
| **Admin Group** | `admin_dokuwiki` |
| **Subdomain** | `dokuwiki` |

!!! info "Auth Notes"
    No SSO support. Has its own internal ACL system. Access gated by group-gate middleware.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `dokuwiki` | `dokuwiki.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `dokuwiki` | `linuxserver/dokuwiki:2026-07-14c-ls332` | `sha256:fac142ae9f7d…` |

## Access URLs

- **Wiki**: `https://dokuwiki.{{DOMAIN}}`
