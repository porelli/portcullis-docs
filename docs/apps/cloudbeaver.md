# 🗃 CloudBeaver

> Web-based database manager — PostgreSQL, MySQL, SQLite and more

**Category:** devops  
**Tags:** `database`, `sql`, `admin`, `postgresql`, `mysql`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `header-auth` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_cloudbeaver` |
| **Admin Group** | `admin_cloudbeaver` |

!!! info "Auth Notes"
    Access gated by forward-auth + group-gate. CloudBeaver's reverseProxy auth provider logs users in from X-Forwarded-User and trusts team/role headers from any peer with no allowlist, so CloudBeaver is kept off portcullis-proxy behind a small nginx gate (cloudbeaver-gate) that rejects (403) X-Forwarded-User from anything but Traefik (PORTCULLIS_TRAEFIK_IP) and strips the X-User/X-Team/X-Role/X-Role-TE/name headers. Roles and connections are managed in CloudBeaver.

## Access URLs

- **Database Manager**: `https://db.{{DOMAIN}}`
