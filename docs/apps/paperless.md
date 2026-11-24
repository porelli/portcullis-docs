# 📄 Paperless-ngx

![Paperless-ngx logo](logos/paperless.svg){ width="64" height="64" }

<p class="app-logo-credit"><small>Logo: © 2026 The paperless-ngx contributors, <code>GPL-3.0-only</code>, <a href="https://github.com/paperless-ngx/paperless-ngx/blob/fbadc2e1b8c34f80b48be0766cae7168e0e8ec24/docs/assets/logo_leaf.svg" target="_blank" rel="noopener noreferrer nofollow">source</a>. Shown only to identify the app; any trademark stays its owner's.</small></p>

> Document management with OCR, full-text search and automatic tagging

**Category:** productivity  
**Tags:** `documents`, `ocr`, `scanning`, `archive`, `pdf`  
**Website:** <https://docs.paperless-ngx.com/>  
**Source:** <https://github.com/paperless-ngx/paperless-ngx>

## About

<div class="app-long-description">
<p>Paperless-ngx turns paper and PDF documents into a searchable archive. It runs OCR on scans, indexes the text for full-text search, and assigns tags, correspondents and document types automatically from what it learns.</p>
<p>Portcullis signs people in through OpenID Connect, with no password login, limited to the access group. Members of the admin group are Paperless superusers.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :white_check_mark: |
| **Access Group** | `users_paperless` |
| **Admin Group** | `admin_paperless` |
| **Admin Paths** | `/admin` (require `admin_paperless` in addition to access) |
| **Subdomain** | `paperless` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>OpenID Connect only, through Paperless' django-allauth provider: the login page goes straight to Portcullis, and only members of <code>users_paperless</code> can sign in or get an account. There are no password logins at all.</p>
<p><strong>The provider:</strong> <code>PAPERLESS_APPS</code> <code>openid_connect</code>, provider id <code>portcullis</code>. The regular login form is off (<code>PAPERLESS_DISABLE_REGULAR_LOGIN</code>) and the login page goes straight to Portcullis (<code>PAPERLESS_REDIRECT_LOGIN_TO_SSO</code>).</p>
<p><strong>Who can sign in:</strong> allauth has no OIDC group restriction, so the SSO start and callback paths (<code>/accounts/oidc/...</code>) sit behind forward-auth + group-gate and only <code>users_paperless</code> members can sign in or get an account. allauth's headless provider-token endpoints (<code>/api/auth/headless/{browser,app}/v1/auth/provider</code>) are gated the same way, so no SSO login skips group-gate. The rest of the API (API tokens, mobile apps) is not gated.</p>
<p><strong>Revoking access:</strong> removing a user from <code>users_paperless</code> (or <code>admin_paperless</code>) blocks new SSO logins and takes effect at their next login. Browser sessions last 12 hours (<code>PAPERLESS_SESSION_COOKIE_AGE</code>, upstream default 3 weeks), so a removed admin keeps superuser rights for at most that long. API tokens keep working: deactivate the user in Paperless to cut them off at once.</p>
<p><strong>Trusted proxies:</strong> <code>PAPERLESS_TRUSTED_PROXIES</code> never decides who signs in (no <code>REMOTE_USER</code> or header auth): it feeds only the client address of a failed-login log line (python-ipware 3, which matches proxies as string prefixes against the <code>X-Forwarded-For</code> entries themselves) and allauth's proxy count (1). The entrypoint passes the narrowest prefix of <code>PORTCULLIS_TRAEFIK_SOURCE</code> (its address for a /32, which also prefixes .20-.29 and .200-.255; the exact octets for a /8, /16 or /24) and refuses any other range, so a container that reaches Paperless directly can at most falsify that log line or its own rate-limit address, never an identity.</p>
<p><strong>No password logins at all:</strong> <code>DISABLE_REGULAR_LOGIN</code> only hides the form, while HTTP Basic auth, <code>POST /api/token/</code> and a password a user sets on their profile would still work. So the one-shot <code>paperless-init</code> job installs a database trigger that replaces every password hash with an unusable one (<code>check_password</code> never succeeds; a password typed on the profile page is discarded). Local accounts created in the Paperless UI therefore cannot sign in.</p>
<ul>
<li>The same job creates an inactive, passwordless placeholder account (<code>paperless-bootstrap</code>), because Paperless opens its signup page and makes the first account a superuser while the database has no user; Paperless only starts once the job succeeded (fail closed).</li>
<li>There is no bootstrap superuser password: break-glass is on the server, e.g. <code>docker exec -it &lt;paperless container&gt; python3 manage.py shell</code> (or <code>manage.py document_exporter</code> for backups).</li>
</ul>
<p><strong>Identity:</strong> accounts are keyed on the OIDC <code>sub</code> and named after <code>preferred_username</code> (the LLDAP username); allauth never links a login to an existing account by email (<code>EMAIL_AUTHENTICATION</code> off; LLDAP emails are user-editable). If the username is already taken, or the email claim equals another account's, allauth picks a different username or asks the user for one on its signup form; the account is still bound to that person's <code>sub</code>.</p>
<p><strong>Roles:</strong> groups come from the Keycloak <code>groups</code> claim at every login (<code>PAPERLESS_SOCIAL_ACCOUNT_SYNC_GROUPS</code>): a user's Paperless groups are exactly the Keycloak groups that also exist as Paperless groups.</p>
<ul>
<li><code>paperless-init</code> creates the <code>users_paperless</code> Paperless group once with a regular-user role (documents, tags, correspondents, document types, storage paths, saved views, notes; read-only custom fields and tasks; own UI settings; no users, groups, mail, workflows, share links or settings), so a member can work with documents they own or that are shared with them (and unowned ones, e.g. from the consume folder).</li>
<li>To grant more, create a Paperless group named like an LLDAP group and put users in that LLDAP group; groups assigned by hand in Paperless are replaced at the next login.</li>
<li><code>admin_paperless</code> members become superuser and staff, and lose it at their next login once removed.</li>
<li>The Django admin (<code>/admin</code>) is additionally behind forward-auth + group-gate with <code>admin_paperless</code>.</li>
</ul>
<p><strong>Consume folder:</strong> a volume (<code>paperless-consume</code>). To use a scanner folder on the host, bind it to <code>/usr/src/paperless/consume</code> in the app's custom override (Hub <strong>Expert</strong> tab, under <code>/srv</code>, <code>/mnt</code> or <code>/media</code>); it must be writable by uid 1000. Documents consumed from there have no owner, so every user with the regular role can see them; give them an owner with a Paperless workflow.</p>
<p><strong>Limits:</strong> extra OCR languages beyond the image's eng, deu, fra, ita and spa can't be installed (the container runs rootless). Office documents (Tika / Gotenberg) are not included.</p>
<p><strong>Upgrades:</strong> <code>paperless</code> and <code>paperless-init</code> use the same image and move together; read the Paperless release notes before major upgrades (<code>paperless-init</code> runs upstream's compatibility check and the migrations with every volume mounted, as Paperless itself would). PostgreSQL stays on 18 and Redis on 8 (no major bumps without a data migration).</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `paperless` | `paperless.<domain>` | all | `default` | :x: |
| `paperless-admin` | `paperless.<domain>` | `/admin` | `default` | :white_check_mark: |
| `paperless-headless` | `paperless.<domain>` | `/api/auth/headless/browser/v1/auth/provider`, `/api/auth/headless/app/v1/auth/provider` | `default` | :white_check_mark: |
| `paperless-sso` | `paperless.<domain>` | `/accounts/oidc` | `default` | :white_check_mark: |

## AI support

**No AI support:** No official MCP server; community servers are small and not vetted by Portcullis.

An alternative **not vetted by Portcullis**, for an admin to evaluate on their own: nloui/paperless-mcp (<https://github.com/nloui/paperless-mcp>) — community, 247★, last change Nov 2025, no licence file, API token (surveyed 2026-11-06). Portcullis never installs it.

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `paperless` | `ghcr.io/paperless-ngx/paperless-ngx:3.4.1` | `sha256:1a08d8dfc2b5…` |
| `paperless-db` | `postgres:18.6-alpine` | `sha256:123b17998cca…` |
| `paperless-init` | `ghcr.io/paperless-ngx/paperless-ngx:3.4.1` | `sha256:1a08d8dfc2b5…` |
| `paperless-redis` | `redis:8.10.3-alpine` | `sha256:21090af93f83…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **OCR languages** | `multi_enum` | instance | `restart` | Tesseract language(s) of your documents (installed: English, German, French, Italian, Spanish). Several are passed joined with "+". Choices: `eng`, `deu`, `fra`, `ita`, `spa`. Default: `eng`. |
| **Time zone** | `string` | instance | `restart` | IANA time zone for dates, e.g. Europe/Berlin. Default: `UTC`. |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `PAPERLESS_SECRET_KEY` | Django secret key (sessions, tokens) | `random` |
| `PAPERLESS_DB_PASSWORD` | Paperless database password | `random` |
| `PAPERLESS_OIDC_SECRET` | Paperless OIDC client secret | `random` |

## Keycloak Clients

**Paperless-ngx** (`paperless`)

Redirect URI: `https://{{HOST_PAPERLESS}}/accounts/oidc/portcullis/login/callback/`

## Access URLs

- **Documents**: `https://{{HOST_PAPERLESS}}`
