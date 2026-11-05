# 📷 Immich

> Self-hosted photo and video backup with AI-powered search

**Category:** media  
**Tags:** `photos`, `videos`, `backup`, `ai`, `gallery`  
**Website:** <https://immich.app/>  
**Source:** <https://github.com/immich-app/immich>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_immich` |
| **Admin Group** | `admin_immich` |
| **Subdomain** | `photos` |

!!! info "Auth Notes"
    Full OIDC with auto-register and auto-launch; password login is disabled while OIDC is configured. Storage quota and role come from the instance settings as the token claims immich_quota (GiB, -1 = unlimited) and immich_role: members of the admin group are Immich administrators (privileged setting), and Immich re-reads both at every sign-in. Trash days and machine learning are rendered into config.json at every start. Identity: OAuth users are keyed on the OIDC sub. Immich also links a login to an existing user with the same email and cannot be told not to, while LLDAP emails are user-editable; so on every start a one-shot job (immich-lock-local-users) gives local, unlinked users (such as the initial admin@portcullis.local) a placeholder OAuth id, and Immich then refuses the email link. Do not create local users in the Immich UI (they are only locked at the next restart); let users sign in with SSO instead. A user who unlinks OAuth in their settings is locked out of SSO until an admin clears the placeholder. Public exceptions (Hub, off by default): shared links still work for signed-in users; turning them on only matters when the policy requires a client certificate at the TLS handshake, which it then no longer does for any path of photos.<domain> (mTLS stays enforced at login via the Keycloak acr). Upgrades: immich-server and immich-machine-learning are pinned to the same release and must always move together; read the upstream release notes for breaking changes and keep immich-db on the image upstream specifies. Shared folders: immich-server runs as root (no compose user:), so External photo library declares runs_as uid 0 / gid 0, read-only; on a shared folder it joins the folder's group through group_add.

## Public Exceptions

Shared links (/share/&lt;key&gt;, /s/&lt;slug&gt;) for visitors without a client certificate. Immich's shared-link key, password and expiry still apply.

The app signs users in itself (native OIDC), so these paths are reachable without Portcullis sign-in anyway. When an admin turns them on in the Hub, they are also served without a client certificate on hosts whose policy requires one (see [Public exceptions](../operations/auth-policies.md#public-exceptions)).

**Default:** off, mode `all`  
**Refused by the public guard (login credentials):** header `Authorization`, header `Proxy-Authorization`, header `x-api-key`, header `x-immich-user-token`, header `x-immich-session-token`, cookie `immich_access_token`, cookie `immich_maintenance_token`, query `apiKey`, query `sessionKey`  

| Prefix | Opened | Description |
|--------|--------|-------------|
| `/share` | mode `all` only | Shared-link page by key (server-rendered OpenGraph, SPA) |
| `/s` | mode `all` only | Shared-link page by custom slug |
| `/_app` | always (supporting); static files only | SvelteKit JS, CSS and fonts |
| `/custom.css` | always (supporting); this exact path only: Single public route serving the admin's custom CSS (server/src/app.common.ts) | Admin custom CSS loaded by every page |
| `/favicon.ico` | always (supporting); this exact path only: Single static file | Favicon |
| `/api/server/config` | always (supporting); this exact path only: Public route (no auth) with the login/branding config the web app needs to start | Server config fetched at web app boot |
| `/api/server/features` | always (supporting); this exact path only: Public route (no auth) with the feature flags the web app needs to start | Feature flags fetched at web app boot |
| `/api/server/media-types` | always (supporting); this exact path only: Public route (no auth), list of accepted file types | Accepted media types (upload into a shared album) |
| `/api/shared-links/me` | mode `all` only; this exact path only: Shared-link route (sharedLink auth) | Resolves the shared link of the key / slug |
| `/api/shared-links/login` | mode `all` only; this exact path only: Shared-link route (sharedLink auth) | Password check of protected shared links |
| `/api/assets` | mode `all` only | Asset info, thumbnails, originals, video playback and upload (Immich checks the shared-link key) |
| `/api/albums` | mode `all` only | Shared album and its map markers |
| `/api/timeline` | mode `all` only | Album timeline buckets |
| `/api/download/info` | mode `all` only; this exact path only: Shared-link route (sharedLink auth) | Download size / archive plan |
| `/api/download/archive` | mode `all` only; this exact path only: Shared-link route (sharedLink auth) | Zip download |

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `immich` | `photos.<domain>` | all | `authaware@file` | :x: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `immich-db` | `ghcr.io/immich-app/postgres:16-vectorchord0.4.3-pgvectors0.2.0` | `sha256:1a078b237c1d…` |
| `immich-init` | `alpine:3.24.3` | `sha256:be2656061b53…` |
| `immich-lock-local-users` | `ghcr.io/immich-app/postgres:16-vectorchord0.4.3-pgvectors0.2.0` | `sha256:1a078b237c1d…` |
| `immich-machine-learning` | `ghcr.io/immich-app/immich-machine-learning:v3.3.5` | `sha256:5b28c9352c83…` |
| `immich-redis` | `redis:7.4.12-alpine` | `sha256:8da19c7399dc…` |
| `immich-server` | `ghcr.io/immich-app/immich-server:v3.3.5` | `sha256:485d546a2e31…` |
| `immich-setup` | `alpine:3.24.3` | `sha256:be2656061b53…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Storage quota** | `size` | per person | `next_sign_in` | How much each person may upload. Set per group; a person in several groups gets the largest. Immich applies it at the person's next sign-in. Default: `100GiB`. |
| **Role** | `enum` | per person | `next_sign_in` | Immich administrators. The instance's admin group is an administrator by default; Immich applies the role at the person's next sign-in. Choices: `user`, `admin`. Default: `user`. Preset for the admin group: `admin`. Privileged: per-group values only from [groups delegates can't steer](../operations/groups.md#guarding-groups). |
| **Keep deleted items for** | `int` (days) | instance | `restart` | Days a deleted photo or video stays in the trash before Immich removes it. Default: `30`. |
| **Machine learning** | `bool` | instance | `restart` | Smart search, face recognition and duplicate detection (the immich-machine-learning service). Off = Immich never calls it. Default: `true`. |
| **External photo library** | `path` | instance | `restart` | Host path to existing photos to import (mounted read-only). Mounted at `/usr/src/app/external` (ro). Folder mount: reads (read-only) as runs as root. |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `IMMICH_DB_PASSWORD` | Immich database password | `random` |
| `IMMICH_OIDC_SECRET` | Immich OIDC client secret | `random` |
| `IMMICH_ADMIN_PASSWORD` | Password for the initial Immich admin (admin@portcullis.local) | `random` |

## Keycloak Clients

**Immich** (`immich`)

Redirect URIs:
- `https://{{HOST_IMMICH}}/auth/login`
- `https://{{HOST_IMMICH}}/user-settings`
- `app.immich:///oauth-callback`

## Access URLs

- **Photos**: `https://{{HOST_IMMICH}}`
