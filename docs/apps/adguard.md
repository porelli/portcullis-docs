# 🛡 AdGuard Home

> Network-wide ad and tracker blocking with DNS-over-HTTPS

**Category:** networking  
**Tags:** `dns`, `adblock`, `privacy`, `filtering`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_adguard` |
| **Admin Group** | `admin_adguard` |
| **Subdomain** | `adguard` |

!!! info "Auth Notes"
    No SSO support. Has its own local admin password set during setup wizard. Access gated by group-gate middleware.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `adguard` | `adguard.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `adguard` | `adguard/adguardhome:v0.107.79` | `sha256:aba9e3bf0613…` |

## Host Ports

Ports this app binds on the host. Collisions with other enabled apps block enable; each binding can be rebound or disabled from the Hub UI.

| Port | Protocol | Default | Container | Required | Notes |
|------|----------|---------|-----------|----------|-------|
| **DNS (TCP)** | `tcp` | `53` | `53` | :white_check_mark: | — |
| **DNS (UDP)** | `udp` | `53` | `53` | :white_check_mark: | — |

## Access URLs

- **Dashboard**: `https://adguard.{{DOMAIN}}`
