# ☁ Nextcloud

> Self-hosted productivity platform — files, calendar, contacts, office

**Category:** productivity  
**Tags:** `files`, `calendar`, `office`, `collaboration`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :white_check_mark: |
| **Access Group** | `users_nextcloud` |
| **Admin Group** | `admin_nextcloud` |
| **Subdomain** | `cloud` |

!!! info "Auth Notes"
    Native OIDC through Nextcloud's official user_oidc app (pinned v8.11.0, installed and configured by setup.sh at every start; upgrade it there). Sign-in is one Portcullis login: the login page redirects to Keycloak. Accounts are created on the first SSO login and keyed on the LLDAP username (preferred_username, unique-uid off, so the Nextcloud user id is the username); soft auto-provisioning is off, so an SSO login is never attached to an existing local account and nothing is matched by email (the user-editable email only fills the profile). A local account with the same name as an LLDAP user (e.g. the break-glass "admin") makes that user's SSO login fail with "User conflict" until it is renamed or removed (occ files:transfer-ownership moves its files). Only members of users_nextcloud or admin_nextcloud may sign in (user_oidc group whitelist + login restriction); both groups are synced into Nextcloud at each login, and members of admin_nextcloud become Nextcloud admins within a minute (nextcloud-cron maps them into Nextcloud's "admin" group and removes SSO accounts that left it; local accounts are never touched). Desktop/mobile clients use Login Flow v2 and get app passwords; WebDAV/OCS accept only app passwords or tokens (token_auth_enforced), never an account password. Break-glass: the local "admin" account (NEXTCLOUD_ADMIN_PASSWORD) signs in at /login?direct=1; /login sits behind forward-auth + group-gate (users_nextcloud), so its password form never faces the internet. Last resort: occ inside the container. Removing a user from the groups blocks new SSO logins and drops the groups at their next login, not sessions or app passwords already issued (disable the user in Nextcloud for that); single logout is off because the Keycloak client has no post-logout redirect URI. Hostname: setup.sh re-applies trusted_domains, overwrite.cli.url, overwritehost and overwriteprotocol from the instance's hostname at every start, so a hostname change only needs a restart. Existing installs: the first start installs user_oidc; local accounts created by hand keep working with their passwords only through /login?direct=1 (behind the gateway) and app passwords. Public exceptions: with native OIDC the host is not behind forward-auth, so share links work like on any Nextcloud (share token, password, expiry and Nextcloud's brute-force protection, which sees the client IP via TRUSTED_PROXIES = Traefik). The Hub exception matters when the host's policy requires a client certificate: then only the listed share links (or all, in mode all) and the static files their page needs skip it, and logins (Basic auth, remember-me cookies) are refused there. The PDF viewer page (a PHP route) is not in the list, so on such hosts PDFs on a share download instead of opening inline; Markdown renders only in mode all. Apps installed under /custom_apps that hook the share page are not covered. Upgrades: the image is pinned; Nextcloud only upgrades one major version at a time, so step through every major (e.g. 33 -> 34 -> 35) and never skip one. Keep nextcloud and nextcloud-cron on the same image.

## Public Exceptions

Public share links (/s/&lt;token&gt;) for visitors without a client certificate. Nextcloud's share password, expiry and download limits still apply.

When an admin turns them on in the Hub, these paths skip forward-auth and group-gate (see [Public exceptions](../operations/auth-policies.md#public-exceptions)).

**Default:** on, mode `listed`  
**Share token:** `^[A-Za-z0-9-]{1,32}$`  
**Refused by the public guard (login credentials):** header `Authorization`, header `Proxy-Authorization`, cookie `nc_username`, cookie `nc_token`, cookie `nc_session_id`  

| Prefix | Opened | Description |
|--------|--------|-------------|
| `/s/{token}` | per listed share; mode `all`: every share | Share page, password form, download and direct preview |
| `/index.php/s/{token}` | per listed share; mode `all`: every share | Same share routes for links created without pretty URLs |
| `/public.php/dav/files/{token}` | per listed share; mode `all`: every share | Public WebDAV of the share (listing, downloads, zip, uploads to editable shares) |
| `/public.php/dav/uploads/{token}` | per listed share; mode `all`: every share | Chunked uploads to file-drop / editable shares |
| `/apps/files_sharing/publicpreview/{token}` | per listed share; mode `all`: every share | Thumbnails of the shared files |
| `/dist` | always (supporting); static files only | Compiled JS/CSS of core, files, files_sharing and systemtags |
| `/core/css` | always (supporting); static files only | Core stylesheets |
| `/core/img` | always (supporting); static files only | Core images |
| `/core/js` | always (supporting); static files only | mimetypelist.js (and the oc.js config fallback, same data the page inlines) |
| `/core/l10n` | always (supporting); static files only | Core translations |
| `/core/mimeicon` | always (supporting); this exact path only: #[PublicPage] PreviewController::getMimeIconUrl, only redirects to a static icon (core/Controller/PreviewController.php) | File-type icon for files without a preview |
| `/apps/theming` | always (supporting); static files only | Theme stylesheets and icons (*.css / *.svg / *.png; its admin routes have no file extension) |
| `/apps/viewer` | always (supporting); static files only | In-browser image/video/audio viewer (static app, no routes) |
| `/apps/files/l10n` | always (supporting); static files only | Files UI translations |
| `/apps/systemtags/l10n` | always (supporting); static files only | System tags translations |
| `/apps/files_sharing/css` | always (supporting); static files only | Share page styles |
| `/apps/files_sharing/img` | always (supporting); static files only | Share page images |
| `/apps/files_sharing/l10n` | always (supporting); static files only | Share page translations |
| `/apps/text/js` | always (supporting); static files only | Markdown / README viewer scripts |
| `/apps/text/public` | mode `all` only | Markdown / README viewer public sessions (token in the request body, so only in mode all) |

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `nextcloud` | `cloud.<domain>` | all | `authaware@file` | :x: |
| `nextcloud-login` | `cloud.<domain>` | `/login (exact)`, `/index.php/login (exact)` | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `nextcloud` | `nextcloud:34.0.5-apache` | `sha256:515c072ea1cf…` |
| `nextcloud-cron` | `nextcloud:34.0.5-apache` | `sha256:515c072ea1cf…` |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `NEXTCLOUD_ADMIN_PASSWORD` | Password of the break-glass local Nextcloud admin (sign in at /login?direct=1) | `random` |
| `NEXTCLOUD_OIDC_SECRET` | Nextcloud OIDC client secret | `random` |

## Keycloak Clients

**Nextcloud** (`nextcloud`)

Redirect URIs:
- `https://{{HOST_NEXTCLOUD}}/apps/user_oidc/code`
- `https://{{HOST_NEXTCLOUD}}/index.php/apps/user_oidc/code`

## Access URLs

- **Nextcloud**: `https://{{HOST_NEXTCLOUD}}`
