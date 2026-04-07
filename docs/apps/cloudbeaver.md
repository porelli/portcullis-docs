# 🗃 CloudBeaver

> Web-based database manager — PostgreSQL, MySQL, SQLite and more

**Category:** devops  
**Tags:** `database`, `sql`, `admin`, `postgresql`, `mysql`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_cloudbeaver` |
| **Admin Group** | `admin_cloudbeaver` |

!!! info "Auth Notes"
    No SSO support. Uses its own internal user/role system. Access gated by group-gate middleware.

## Access URLs

- **Database Manager**: `https://db.{{DOMAIN}}`
