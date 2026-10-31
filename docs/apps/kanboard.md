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
| **Subdomain** | `kanboard` |

!!! info "Auth Notes"
    No public exceptions: Kanboard's router reads ?controller=&action= before the path (app/Core/Http/Router.php), so any public prefix would reach every APP_PUBLIC action, local password login included. Reverse proxy auth: users are matched on X-Forwarded-User, the immutable LLDAP username, honoured only from Traefik (TRUSTED_PROXY_NETWORKS = PORTCULLIS_TRAEFIK_IP). X-Forwarded-Email (user-editable) only fills the profile email and is ignored from other peers too. Auto-creates users on first login. The LLDAP user named in "Kanboard admin username" (KANBOARD_ADMIN_USER, default admin = LLDAP's built-in admin) gets the Kanboard admin role; other roles are set in the Kanboard UI. Access gated by group-gate. Accounts created when the header carried the email are named after it; rename them to the LLDAP username in Kanboard.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `kanboard` | `kanboard.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `kanboard` | `kanboard/kanboard:v1.2.57` | `sha256:637989624e53…` |

## Settings

User-configurable options available in the Hub UI:

| Setting | Type | Description |
|---------|------|-------------|
| **Kanboard admin username** | `text` | LLDAP username (not email) that Kanboard makes an administrator when it signs in. Default: admin (LLDAP's built-in admin account).  (default `admin`) |

## Access URLs

- **Kanboard**: `https://kanboard.{{DOMAIN}}`
