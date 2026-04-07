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

!!! info "Auth Notes"
    No SSO support. Has its own internal ACL system. Access gated by group-gate middleware.

## Access URLs

- **Wiki**: `https://dokuwiki.{{DOMAIN}}`
