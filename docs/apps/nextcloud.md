# ☁️ Nextcloud

> Self-hosted productivity platform — files, calendar, contacts, office

**Category:** productivity  
**Tags:** `files`, `calendar`, `office`, `collaboration`  
**Website:** <https://nextcloud.com/>  
**Source:** <https://github.com/nextcloud/server>

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
    Native OIDC through Nextcloud's official user_oidc app (pinned v8.11.0, installed and configured by setup.sh at every start; upgrade it there). Sign-in is one Portcullis login: the login page redirects to Keycloak. Accounts are created on the first SSO login and keyed on the LLDAP username (preferred_username, unique-uid off, so the Nextcloud user id is the username); soft auto-provisioning is off, so an SSO login is never attached to an existing local account and nothing is matched by email (the user-editable email only fills the profile). Sign-in is restricted to access_group in Keycloak (keycloak_access_role, contract §8 Access role): only users_nextcloud members can sign in, so a member of admin_nextcloud who is not also in users_nextcloud is denied — put Nextcloud's admins in both groups (user_oidc's group whitelist + login restriction stay as a second check); both groups are synced into Nextcloud at each login, and members of admin_nextcloud become Nextcloud admins within a minute (nextcloud-cron maps them into Nextcloud's "admin" group and removes SSO accounts that left it). No password login at all: Nextcloud can't switch its password form off server-side, so every local account (the nc-breakglass admin the image creates at install, the "admin" of installs made before this template version, accounts created in the Users page) is disabled at every start and within a minute by nextcloud-cron; the login form is hidden. Move a local account's files to its owner's SSO account with occ files:transfer-ownership. An LLDAP user whose name is a local account (e.g. "admin" on older installs) gets "User conflict" until that account is deleted (occ user:delete). Desktop/mobile clients use Login Flow v2 and get app passwords; WebDAV/OCS accept only app passwords or tokens (token_auth_enforced). Break-glass is occ on the server, e.g. docker compose -p portcullis-<instance> exec -u www-data nextcloud php occ group:adduser admin <user> (or user_oidc:provider, config:system:set, user:info). Removing a user from the groups blocks new SSO logins and drops the groups at their next login, not sessions or app passwords already issued (occ user:disable <user> for that); single logout is off because the Keycloak client has no post-logout redirect URI. Hostname: setup.sh re-applies trusted_domains, overwrite.cli.url, overwritehost and overwriteprotocol from the instance's hostname at every start, so a hostname change only needs a restart. Public exceptions: the host is not behind forward-auth, so every share link already works without Portcullis sign-in, listed or not (Nextcloud's share token, password, expiry and brute-force protection apply; it sees the client IP via TRUSTED_PROXIES = Traefik). The Hub exception only changes hosts whose policy requires a client certificate: there, the listed share links (mode all: every share) and the static files their page needs are served without one, and logins (Basic auth, remember-me cookies) are refused on those paths. The PDF viewer page (a PHP route) is not in the list, so on such hosts PDFs on a share download instead of opening inline; Markdown renders only in mode all. Apps installed under /custom_apps that hook the share page are not covered. Keycloak must be reachable at a public name and address: Nextcloud's HTTP client refuses hosts with a local TLD (.local, .lan, ...) or a private address (allow_local_remote_servers stays off; user_oidc has no switch scoped to the provider), so with split DNS or a LAN-only domain user_oidc answers "Could not reach the OpenID Connect provider". Never set user_oidc's httpclient.allowselfsigned (it turns TLS verification off). Upgrades: the image is pinned; Nextcloud only upgrades one major version at a time, so step through every major (e.g. 33 -> 34 -> 35) and never skip one. Keep nextcloud and nextcloud-cron on the same image. Database: chosen at setup (PostgreSQL on nextcloud-postgres, the default, MySQL / MariaDB on nextcloud-mariadb, each under its own compose profile, or SQLite in the data volume) and fixed after the first start. Switching means a new instance with the other choice and moving the data across (e.g. with Nextcloud's occ db:convert-type). Never bump the database servers' major versions in place. Settings: the default storage quota and the trash retention are applied live through occ by the apply-settings hook (apply-settings.php, run by the Hub as www-data in the nextcloud container at start and after every save; idempotent, exits non-zero on any occ failure). Quotas set per user in Nextcloud's Users page still win over the default. AI availability: while AI support is on, any container on portcullis-proxy can reach the companion and send wrong credentials; Nextcloud's brute-force protection counts them against the companion's address, which every AI request comes from, so such a container can slow everyone's AI requests down (sign-in itself still holds). Re-used usernames: accounts are keyed on the username, so a deleted person's username given to someone new gets the former person's Nextcloud account, on the web and through AI alike (the AI mint can't tell them apart: user_oidc stores no Keycloak id). Delete or rename the former person's Nextcloud account (occ user:delete) before re-using a username.

## Public Exceptions

Public share links (/s/&lt;token&gt;) for visitors without a client certificate. Nextcloud's share password, expiry and download limits still apply.

The app signs users in itself (native OIDC), so these paths are reachable without Portcullis sign-in anyway. When an admin turns them on in the Hub, they are also served without a client certificate on hosts whose policy requires one (see [Public exceptions](../operations/auth-policies.md#public-exceptions)).

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

## AI support

People's AI assistants can use this app as themselves through these MCP servers, once an admin switches AI support on in the app's **AI support** tab (see [AI support](../operations/ai.md)).

**Nextcloud** (`nextcloud`)

| Property | Value |
|----------|-------|
| **Endpoint** | `https://cloud.<domain>/mcp` |
| **Server** | a companion container (`nextcloud-mcp`), scaled to 0 while AI support is off |
| **Upstream** | community companion, vetted by the template's reviewers |
| **Source** | <https://github.com/cbcoutinho/nextcloud-mcp-server> |
| **Identity mode** | per-person app credential (`app_token`): the Hub mints one for each person in the app; mcp-gate sends it with every call |
| **Modes** | read only, read and write (default read and write) |
| **In "All my apps"** | :white_check_mark: |
| **MCP versions** | `2025-11-25`, `2025-06-18` |
| **Needs the person's confirmation** | `*delete*`, `nc_calendar_bulk_operations`, `nc_calendar_manage_calendar`, `nc_calendar_create_event`, `nc_calendar_create_meeting`, `nc_calendar_update_event`, `nc_calendar_create_todo`, `nc_calendar_update_todo` |
| **Never offered** | `nc_share_create`, `nc_share_create_public_link`, `nc_share_update`, `nc_share_list`, `nc_share_get` |
| **Hidden in read-only mode** | `*_write_*`, `*_edit_*`, `*_create*`, `*_delete*`, `*_move_*`, `*_copy_*`, `*_restore_*`, `*_tag_file`, `*_untag_file`, `*_update*`, `*_complete_*`, `*_bulk_*`, `*_manage_*` |

Why this choice, and what to know: [AI support → Nextcloud](../operations/ai.md#ai-nextcloud).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `nextcloud` | `nextcloud:34.0.5-apache` | `sha256:515c072ea1cf…` |
| `nextcloud-cron` | `nextcloud:34.0.5-apache` | `sha256:515c072ea1cf…` |
| `nextcloud-mariadb` | `mariadb:11.8.9` | `sha256:c4124d1afa87…` |
| `nextcloud-mcp` | `ghcr.io/cbcoutinho/nextcloud-mcp-server:0.205.3` | `sha256:c8b613f9f1c6…` |
| `nextcloud-postgres` | `postgres:17.11-alpine` | `sha256:266d3c257594…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Database** | `enum` | instance | `restart` | Where Nextcloud keeps its data other than files. PostgreSQL or MySQL / MariaDB run as a database server next to Nextcloud; SQLite needs none but suits only a few people. Fixed after the first start. Choices: `sqlite`, `mysql`, `postgres`. Default: `postgres`. |
| **Default storage quota** | `size` | instance | `live` | Storage each Nextcloud account gets unless a quota is set for it in Nextcloud's Users page. Default: `10GiB`. |
| **Delete trash after** | `duration` | instance | `live` | Deleted files are removed from the trash after this long (earlier only when an account runs out of space). Default: `30d`. |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `NEXTCLOUD_ADMIN_PASSWORD` | Install-time password of the local admin nc-breakglass (disabled after install; no password login) | `random` |
| `NEXTCLOUD_OIDC_SECRET` | Nextcloud OIDC client secret | `random` |
| `NEXTCLOUD_DB_PASSWORD` | Password of the nextcloud account on the MySQL / MariaDB or PostgreSQL server (setting database) | `random` |

## Keycloak Clients

**Nextcloud** (`nextcloud`)

Redirect URIs:

- `https://{{HOST_NEXTCLOUD}}/apps/user_oidc/code`
- `https://{{HOST_NEXTCLOUD}}/index.php/apps/user_oidc/code`

## Access URLs

- **Nextcloud**: `https://{{HOST_NEXTCLOUD}}`
