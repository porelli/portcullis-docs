# 🔒 Vault UI

> PLACEHOLDER / EXPERIMENTAL: mTLS-only (protected tier) demo route; currently runs SFTPGo, not a Vault UI

**Category:** security  
**Tags:** `vault`, `secrets`, `pki`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `mtls` |
| **SSO** | :x: No |
| **Group Access** | :x: |
| **Group Admin** | :x: |
| **Subdomain** | `vault` |

!!! info "Auth Notes"
    mTLS only (protected TLS tier). Requires PIV client certificate. No SSO or group integration — access controlled at the TLS layer.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `vault-ui` | `vault.<domain>` | all | `protected@file` | :x: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `vault-ui` | `drakkan/sftpgo:v2.7.6` | `sha256:1edd28d80de2…` |

## Access URLs

- **Vault UI**: `https://vault.{{DOMAIN}}`
