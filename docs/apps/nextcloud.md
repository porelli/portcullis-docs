# ☁ Nextcloud

> Self-hosted productivity platform — files, calendar, contacts, office

**Category:** productivity  
**Tags:** `files`, `calendar`, `office`, `collaboration`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_nextcloud` |
| **Admin Group** | `admin_nextcloud` |
| **Subdomain** | `cloud` |

!!! info "Auth Notes"
    Access gated by forward-auth + group-gate; Nextcloud then shows its own login (admin account uses NEXTCLOUD_ADMIN_PASSWORD). No OIDC app is installed yet. Desktop/mobile sync clients and WebDAV cannot pass the forward-auth redirect. Nextcloud does not read the Portcullis identity headers (no user_oidc / header login), so the user-editable LLDAP email plays no part in which Nextcloud account is used. Public exceptions (Hub, off for every share until listed): only the listed share links and the static files their page needs bypass the gateway; logins (Basic auth, remember-me cookies) are not honoured there. The PDF viewer page (a PHP route) is not public, so PDFs on a share download instead of opening inline; Markdown renders only in mode all. Share-password brute force then faces the internet, limited by Nextcloud's own brute-force protection (it sees the client IP via TRUSTED_PROXIES = Traefik). Apps installed under /custom_apps that hook the share page are not covered. Upgrades: the image is pinned; Nextcloud only upgrades one major version at a time, so step through every major (e.g. 33 -> 34 -> 35) and never skip one.

## Public Exceptions

Public share links (/s/&lt;token&gt;) for people without a Portcullis account. Nextcloud's share password, expiry and download limits still apply; the gateway (forward-auth, group-gate, YubiKey) does not.

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
| `nextcloud` | `cloud.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `nextcloud` | `nextcloud:34.0.5-apache` | `sha256:515c072ea1cf…` |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `NEXTCLOUD_ADMIN_PASSWORD` | Nextcloud admin password | `random` |

## Access URLs

- **Nextcloud**: `https://cloud.{{DOMAIN}}`
