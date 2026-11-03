# 📋 Kanboard

> Minimalist Kanban project management with header-based auth

**Category:** productivity  
**Tags:** `kanban`, `projects`, `tasks`, `boards`  
**Website:** <https://kanboard.org/>  
**Source:** <https://github.com/kanboard/kanboard>

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
    No public exceptions: Kanboard's router reads ?controller=&action= before the path (app/Core/Http/Router.php), so any public prefix would reach every APP_PUBLIC action, local password login included. Reverse proxy auth: users are matched on X-Forwarded-User, the immutable LLDAP username, honoured only from Traefik (TRUSTED_PROXY_NETWORKS = PORTCULLIS_TRAEFIK_IP). X-Forwarded-Email (user-editable) only fills the profile email and is ignored from other peers too. Auto-creates users on first login. The LLDAP user picked in "Kanboard administrator" (default admin = LLDAP's built-in admin) gets the Kanboard admin role; other roles are set in the Kanboard UI. Access gated by group-gate. Accounts created when the header carried the email are named after it; rename them to the LLDAP username in Kanboard.

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

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Kanboard administrator** | `user` | instance | `restart` | The LLDAP user (username, not email) that Kanboard makes an administrator when it signs in. Default: admin (LLDAP's built-in admin account). Default: `admin`. |

## Access URLs

- **Kanboard**: `https://{{HOST_KANBOARD}}`
