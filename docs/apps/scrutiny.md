# 💾 Scrutiny

> Hard drive S.M.A.R.T monitoring with web dashboard and alerts

**Category:** monitoring  
**Tags:** `disk`, `smart`, `health`, `monitoring`, `hardware`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_scrutiny` |
| **Admin Group** | `admin_scrutiny` |
| **Subdomain** | `disks` |

!!! info "Auth Notes"
    No SSO or user system. Access gated by group-gate middleware. All authenticated users have full access.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `scrutiny` | `disks.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `scrutiny` | `ghcr.io/analogj/scrutiny:v0.9.5-omnibus` | `sha256:6ee271ee5314…` |

## Access URLs

- **Dashboard**: `https://disks.{{DOMAIN}}`
