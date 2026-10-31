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

!!! info "Auth Notes"
    mTLS only (protected TLS tier). Requires PIV client certificate. No SSO or group integration — access controlled at the TLS layer.

## Access URLs

- **Vault UI**: `https://vault.{{DOMAIN}}`
