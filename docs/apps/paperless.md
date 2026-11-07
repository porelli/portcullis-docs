# 📄 Paperless-ngx

> Document management with OCR, full-text search and automatic tagging

**Category:** productivity  
**Tags:** `documents`, `ocr`, `scanning`, `archive`, `pdf`  
**Website:** <https://docs.paperless-ngx.com/>  
**Source:** <https://github.com/paperless-ngx/paperless-ngx>

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

!!! info "Auth Notes"
    OpenID Connect only, through Paperless' django-allauth provider (PAPERLESS_APPS openid_connect, provider id portcullis). The regular login form is off (PAPERLESS_DISABLE_REGULAR_LOGIN) and the login page goes straight to Portcullis (PAPERLESS_REDIRECT_LOGIN_TO_SSO). Who can sign in: allauth has no OIDC group restriction, so the SSO start and callback paths (/accounts/oidc/...) sit behind forward-auth + group-gate and only users_paperless members can sign in or get an account; allauth's headless provider-token endpoints (/api/auth/headless/{browser,app}/v1/auth/provider) are gated the same way, so no SSO login skips group-gate. The rest of the API (API tokens, mobile apps) is not gated. Removing a user from users_paperless (or admin_paperless) blocks new SSO logins and takes effect at their next login; browser sessions last 12 hours (PAPERLESS_SESSION_COOKIE_AGE, upstream default 3 weeks), so a removed admin keeps superuser rights for at most that long. API tokens keep working: deactivate the user in Paperless to cut them off at once. No password logins at all: DISABLE_REGULAR_LOGIN only hides the form, while HTTP Basic auth, POST /api/token/ and a password a user sets on their profile would still work, so the one-shot paperless-init job installs a database trigger that replaces every password hash with an unusable one (check_password never succeeds; a password typed on the profile page is discarded). Local accounts created in the Paperless UI therefore cannot sign in. The same job creates an inactive, passwordless placeholder account (paperless-bootstrap), because Paperless opens its signup page and makes the first account a superuser while the database has no user; Paperless only starts once the job succeeded (fail closed). There is no bootstrap superuser password: break-glass is on the server, e.g. docker exec -it <paperless container> python3 manage.py shell (or manage.py document_exporter for backups). Identity: accounts are keyed on the OIDC sub and named after preferred_username (the LLDAP username); allauth never links a login to an existing account by email (EMAIL_AUTHENTICATION off; LLDAP emails are user-editable). If the username is already taken, or the email claim equals another account's, allauth picks a different username or asks the user for one on its signup form; the account is still bound to that person's sub. Roles: groups come from the Keycloak groups claim at every login (PAPERLESS_SOCIAL_ACCOUNT_SYNC_GROUPS): a user's Paperless groups are exactly the Keycloak groups that also exist as Paperless groups. paperless-init creates the users_paperless Paperless group once with a regular-user role (documents, tags, correspondents, document types, storage paths, saved views, notes; read-only custom fields and tasks; own UI settings; no users, groups, mail, workflows, share links or settings), so a member can work with documents they own or that are shared with them (and unowned ones, e.g. from the consume folder). To grant more, create a Paperless group named like an LLDAP group and put users in that LLDAP group; groups assigned by hand in Paperless are replaced at the next login. admin_paperless members become superuser and staff, and lose it at their next login once removed. The Django admin (/admin) is additionally behind forward-auth + group-gate with admin_paperless. Consume folder: a volume (paperless-consume). To use a scanner folder on the host, bind it to /usr/src/paperless/consume in the app's custom override (Hub Expert tab, under /srv, /mnt or /media); it must be writable by uid 1000. Documents consumed from there have no owner, so every user with the regular role can see them; give them an owner with a Paperless workflow. Extra OCR languages beyond the image's eng, deu, fra, ita and spa can't be installed (the container runs rootless). Office documents (Tika / Gotenberg) are not included. Upgrades: paperless and paperless-init use the same image and move together; read the Paperless release notes before major upgrades (paperless-init runs upstream's compatibility check and the migrations with every volume mounted, as Paperless itself would). PostgreSQL stays on 18 and Redis on 8 (no major bumps without a data migration).

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `paperless` | `paperless.<domain>` | all | `authaware@file` | :x: |
| `paperless-admin` | `paperless.<domain>` | `/admin` | `authaware@file` | :white_check_mark: |
| `paperless-headless` | `paperless.<domain>` | `/api/auth/headless/browser/v1/auth/provider`, `/api/auth/headless/app/v1/auth/provider` | `authaware@file` | :white_check_mark: |
| `paperless-sso` | `paperless.<domain>` | `/accounts/oidc` | `authaware@file` | :white_check_mark: |

## AI support

**No AI support:** No official MCP server; community servers are small and not vetted by Portcullis.

An alternative **not vetted by Portcullis**, for an admin to evaluate on their own: nloui/paperless-mcp (<https://github.com/nloui/paperless-mcp>) — community, 248★, last change Nov 2025, API token. Portcullis never installs it.

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `paperless` | `ghcr.io/paperless-ngx/paperless-ngx:3.4.1` | `sha256:1a08d8dfc2b5…` |
| `paperless-db` | `postgres:18.6-alpine` | `sha256:10a5c69a8303…` |
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
