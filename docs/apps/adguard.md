# 🛡 AdGuard Home

> Network-wide ad and tracker blocking with DNS-over-HTTPS

**Category:** networking  
**Tags:** `dns`, `adblock`, `privacy`, `filtering`

!!! warning "Conflicts with: pihole"

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_adguard` |
| **Admin Group** | `admin_adguard` |

!!! info "Auth Notes"
    No SSO support. Has its own local admin password set during setup wizard. Access gated by group-gate middleware.

## Access URLs

- **Dashboard**: `https://adguard.{{DOMAIN}}`
