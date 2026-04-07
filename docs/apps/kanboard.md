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

!!! info "Auth Notes"
    Reverse proxy auth with X-Forwarded-User header. Auto-creates users on first login. Admin role set manually in Kanboard UI. Access gated by group-gate.

## Access URLs

- **Kanboard**: `https://kanboard.{{DOMAIN}}`
