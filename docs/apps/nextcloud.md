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

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Native OIDC through Nextcloud's official <code>user_oidc</code> app: sign-in is one Portcullis login, and only members of <code>users_nextcloud</code> can sign in. Members of <code>admin_nextcloud</code> become Nextcloud admins (put them in both groups); there is no password login at all.</p>
<p><strong>The app:</strong> <code>user_oidc</code>, pinned v8.11.0, installed and configured by <code>setup.sh</code> at every start (upgrade it there). The login page redirects to Keycloak.</p>
<p><strong>Identity:</strong> accounts are created on the first SSO login and keyed on the LLDAP username (<code>preferred_username</code>, unique-uid off, so the Nextcloud user id is the username). Soft auto-provisioning is off, so an SSO login is never attached to an existing local account and nothing is matched by email (the user-editable email only fills the profile).</p>
<p><strong>Groups:</strong> sign-in is restricted to <code>access_group</code> in Keycloak (<code>keycloak_access_role</code>, contract §8 Access role): only <code>users_nextcloud</code> members can sign in, so a member of <code>admin_nextcloud</code> who is not also in <code>users_nextcloud</code> is denied — put Nextcloud's admins in both groups (<code>user_oidc</code>'s group whitelist + login restriction stay as a second check). Both groups are synced into Nextcloud at each login, and members of <code>admin_nextcloud</code> become Nextcloud admins within a minute (<code>nextcloud-cron</code> maps them into Nextcloud's <code>admin</code> group and removes SSO accounts that left it).</p>
<p><strong>No password login at all:</strong> Nextcloud can't switch its password form off server-side, so every local account (the <code>nc-breakglass</code> admin the image creates at install, the <code>admin</code> of installs made before this template version, accounts created in the Users page) is disabled at every start and within a minute by <code>nextcloud-cron</code>; the login form is hidden.</p>
<ul>
<li>Move a local account's files to its owner's SSO account with <code>occ files:transfer-ownership</code>.</li>
<li>An LLDAP user whose name is a local account (e.g. <code>admin</code> on older installs) gets &quot;User conflict&quot; until that account is deleted (<code>occ user:delete</code>).</li>
<li>Desktop/mobile clients use Login Flow v2 and get app passwords; WebDAV/OCS accept only app passwords or tokens (<code>token_auth_enforced</code>).</li>
<li>Break-glass is <code>occ</code> on the server, e.g. <code>docker compose -p portcullis-&lt;instance&gt; exec -u www-data nextcloud php occ group:adduser admin &lt;user&gt;</code> (or <code>user_oidc:provider</code>, <code>config:system:set</code>, <code>user:info</code>).</li>
</ul>
<p><strong>Revoking access:</strong> removing a user from the groups blocks new SSO logins and drops the groups at their next login, not sessions or app passwords already issued (<code>occ user:disable &lt;user&gt;</code> for that); single logout is off because the Keycloak client has no post-logout redirect URI.</p>
<p><strong>Hostname:</strong> <code>setup.sh</code> re-applies <code>trusted_domains</code>, <code>overwrite.cli.url</code>, <code>overwritehost</code> and <code>overwriteprotocol</code> from the instance's hostname at every start, so a hostname change only needs a restart.</p>
<p><strong>Public exceptions:</strong> the host is not behind forward-auth, so every share link already works without Portcullis sign-in, listed or not (Nextcloud's share token, password, expiry and brute-force protection apply; it sees the client IP via <code>TRUSTED_PROXIES</code> = Traefik).</p>
<ul>
<li>The Hub exception only changes hosts whose policy requires a client certificate: there, the listed share links (mode <code>all</code>: every share) and the static files their page needs are served without one, and logins (Basic auth, remember-me cookies) are refused on those paths.</li>
<li>The PDF viewer page (a PHP route) is not in the list, so on such hosts PDFs on a share download instead of opening inline; Markdown renders only in mode <code>all</code>.</li>
<li>Apps installed under <code>/custom_apps</code> that hook the share page are not covered.</li>
</ul>
<p><strong>Keycloak must be reachable at a public name and address:</strong> Nextcloud's HTTP client refuses hosts with a local TLD (<code>.local</code>, <code>.lan</code>, ...) or a private address (<code>allow_local_remote_servers</code> stays off; <code>user_oidc</code> has no switch scoped to the provider), so with split DNS or a LAN-only domain <code>user_oidc</code> answers &quot;Could not reach the OpenID Connect provider&quot;. Never set <code>user_oidc</code>'s <code>httpclient.allowselfsigned</code> (it turns TLS verification off).</p>
<p><strong>Upgrades:</strong> the image is pinned; Nextcloud only upgrades one major version at a time, so step through every major (e.g. 33 → 34 → 35) and never skip one. Keep <code>nextcloud</code> and <code>nextcloud-cron</code> on the same image.</p>
<p><strong>Database:</strong> chosen at setup (PostgreSQL on <code>nextcloud-postgres</code>, the default, MySQL / MariaDB on <code>nextcloud-mariadb</code>, each under its own compose profile, or SQLite in the data volume) and fixed after the first start. Switching means a new instance with the other choice and moving the data across (e.g. with Nextcloud's <code>occ db:convert-type</code>). Never bump the database servers' major versions in place.</p>
<p><strong>Settings:</strong> the default storage quota and the trash retention are applied live through <code>occ</code> by the <code>apply-settings</code> hook (<code>apply-settings.php</code>, run by the Hub as <code>www-data</code> in the nextcloud container at start and after every save; idempotent, exits non-zero on any <code>occ</code> failure). Quotas set per user in Nextcloud's Users page still win over the default.</p>
<p><strong>AI availability:</strong> while AI support is on, any container on <code>portcullis-proxy</code> can reach the companion and send wrong credentials; Nextcloud's brute-force protection counts them against the companion's address, which every AI request comes from, so such a container can slow everyone's AI requests down (sign-in itself still holds).</p>
<p><strong>Re-used usernames:</strong> accounts are keyed on the username, so a deleted person's username given to someone new gets the former person's Nextcloud account, on the web and through AI alike (the AI mint can't tell them apart: <code>user_oidc</code> stores no Keycloak id). Delete or rename the former person's Nextcloud account (<code>occ user:delete</code>) before re-using a username.</p>
</div>

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
