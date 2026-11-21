# 🛡 AdGuard Home

> Network-wide ad and tracker blocking with DNS-over-HTTPS

**Category:** networking  
**Tags:** `dns`, `adblock`, `privacy`, `filtering`  
**Website:** <https://adguard.com/en/adguard-home/overview.html>  
**Source:** <https://github.com/AdguardTeam/AdGuardHome>

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

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>No SSO in AdGuard Home (local accounts only). Access is gated by forward-auth + group-gate, and AdGuard's own admin password (set in its setup wizard) stays on purpose.</p>
<p>Why the password stays: upstream can only disable it by leaving <code>users</code> empty, which turns authentication off for every peer (<a target="_blank" rel="noopener noreferrer nofollow" href="https://github.com/AdguardTeam/AdGuardHome/wiki/Configuration">https://github.com/AdguardTeam/AdGuardHome/wiki/Configuration</a>, <code>users</code>), and its web server has no client allowlist, so every other container on <code>portcullis-proxy</code> would get the full admin API unauthenticated.</p>
<p>The same web server also answers DNS-over-HTTPS (<code>/dns-query</code>); through Portcullis it is behind forward-auth, so DoH clients can't use it.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `adguard` | `adguard.<domain>` | all | `authaware@file` | :white_check_mark: |

## AI support

**No AI support:** No MCP server known, and every member of the access group is a full administrator of the app (no per-person rights to act with).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `adguard` | `adguard/adguardhome:v0.107.80` | `sha256:e2e1b48c832f…` |

## Host Ports

Ports this app binds on the host. Collisions with other enabled apps block enable; each binding can be rebound or disabled from the Hub UI.

| Port | Protocol | Default | Container | Required | Notes |
|------|----------|---------|-----------|----------|-------|
| **DNS (TCP)** | `tcp` | `53` | `53` | :white_check_mark: | — |
| **DNS (UDP)** | `udp` | `53` | `53` | :white_check_mark: | — |

## Access URLs

- **Dashboard**: `https://{{HOST_ADGUARD}}`
