# Manifest Reference

Every app template has a `manifest.yaml` that describes the app to the Hub.
This page documents every field of the schema.

The authoritative definition is the JSON Schema (draft 2020-12)
[`schema/manifest.schema.json`](https://github.com/porelli/portcullis-templates/blob/main/schema/manifest.schema.json)
in the templates repo. The Hub enforces the same rules and skips templates that
fail them (see [Integration Contracts §3](integration-contracts.md#3-template-layout)).
Rules that need the compose file, the filesystem or several templates at once
are checked by `tests/validate.py` (see [Validation](#validation)).

For editor completion, start the manifest with:

```yaml
# yaml-language-server: $schema=../schema/manifest.schema.json
```

## Conventions

Several types recur throughout the schema:

| Type | Rule |
|------|------|
| *single line* | A string without control characters (U+0000–U+001F, U+007F) |
| *env key* | `^[A-Za-z_][A-Za-z0-9_]{0,127}$`. It becomes a key in the per-app `.env` |
| *group* | An LLDAP group name: `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` |
| *service* | A service name from the template's `compose.yml`: `^[a-zA-Z0-9][a-zA-Z0-9_.-]*$` |
| `{{DOMAIN}}` | In `urls` and redirect URIs, replaced with `PORTCULLIS_DOMAIN` |

**No other keys are allowed.** Every object in the schema sets
`additionalProperties: false`, so a typo is an error, not a silently ignored
field.

## Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | single line, 1–64 chars | Yes | Display name shown in the Hub |
| `description` | single line, 1–200 chars | Yes | One-line description of what the app does |
| `icon` | single line, 1–16 chars | Yes | Unicode emoji for the app card, e.g. `"\U0001F4CA"` |
| `category` | `^[a-z][a-z0-9-]{0,31}$` | Yes | Catalog category |
| `tags` | list of unique strings `^[a-z0-9][a-z0-9.+-]{0,31}$` | Yes | Searchable tags (lowercase) |
| `auth` | object | Yes | See [auth](#auth) |
| `settings` | list | No | See [settings](#settings) |
| `ports` | list | No | See [ports](#ports) |
| `env` | list | No | See [env](#env) |
| `keycloak_clients` | list | No; required (at least one) for `native-oidc` | See [keycloak_clients](#keycloak_clients) |
| `config_files` | list | No | See [config_files](#config_files) |
| `urls` | list | No | See [urls](#urls) |

**Categories in use:** `monitoring`, `media`, `productivity`, `security`,
`networking`, `ai`, `devops`, `finance`, `vpn`, `remote-access`, `public`.

## auth

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `method` | enum | Yes | `native-oidc`, `forward-auth`, `header-auth`, `mtls`, `custom` or `public` (see below) |
| `sso` | `true`, `false` or `"partial"` | Yes | Whether single sign-on is supported |
| `group_access` | boolean | Yes | group-gate restricts the app's subdomains to `access_group`. For `custom` apps only while Portcullis sign-in is in front of them (`native_login`) |
| `group_admin` | boolean | Yes | The app maps `admin_group` to its admin role |
| `access_group` | group | If `group_access: true` | LLDAP group required for access, by convention `users_<app>` |
| `admin_group` | group | If `group_admin: true` or `admin_paths` is non-empty | LLDAP group for admin privileges, by convention `admin_<app>` |
| `admin_paths` | list of path prefixes | No | Paths that additionally require `admin_group` (see below) |
| `public_access` | object | No | Public path exceptions: share-link paths the Hub can open without forward-auth (see [auth.public_access](#authpublic_access)) |
| `native_login` | object | No | The app has its own login and no SSO (`method: custom` only); enables the Hub's Sign-in setting (see [auth.native_login](#authnative_login)) |
| `identity_headers` | list of header names | If `method: header-auth` and `public_access` is set | Headers the app reads the user from (e.g. `X-Forwarded-User`); the Hub strips them on public paths |
| `notes` | string | No | Free-text notes about the auth integration. Shown on the app's docs page. Upgrade constraints go here too |

Constraints the schema enforces:

- `group_access: true` requires `access_group`.
- `group_admin: true` requires `admin_group`.
- A non-empty `admin_paths` requires `admin_group`.
- `method: public` requires `group_access: false` and an empty (or missing)
  `admin_paths`.
- `public_access` is only allowed with `method` `forward-auth`, `header-auth`
  or `native-oidc`; with `header-auth` it requires a non-empty
  `identity_headers` (each `^[A-Za-z][A-Za-z0-9-]{0,63}$`, unique).
- `native_login` requires `method: custom` and `sso: false`.

`access_group` is only *enforced* by group-gate when `group_access: true`.
Otherwise it is informational.

### Auth methods

| `method` | Meaning | Router middlewares |
|----------|---------|--------------------|
| `native-oidc` | The app talks OIDC to Keycloak itself. Needs `keycloak_clients` | **No** `portcullis-auth` on the host-wide router. Login or admin paths may use a separate `PathPrefix` router with forward-auth |
| `forward-auth` | oauth2-proxy + group-gate in front. The app has its own login, or none | `portcullis-auth@docker,portcullis-groups@docker` |
| `header-auth` | Forward-auth, and the app also trusts `X-Forwarded-User` from Traefik (and only from Traefik) | `portcullis-auth@docker,portcullis-groups@docker` |
| `mtls` | Client certificate at the TLS layer | `tls.options: protected@file`, no forward-auth |
| `custom` | The app handles its own sign-in (app-specific account system, e.g. plex.tv). With `native_login`, the Hub can put Portcullis sign-in in front of it | None: the Hub's override adds the gateway pair for Portcullis sign-in |
| `public` | No authentication | None |

See [Choosing an auth method](https://github.com/porelli/portcullis-templates/blob/main/CONTRIBUTING.md#choosing-an-auth-method)
in the templates repo's contributing guide.

### SSO values

- `true`: the user authenticates once in Keycloak and is logged into the app automatically.
- `false`: the app has its own login form. Forward-auth only gates access, and the user logs in again.
- `"partial"`: the app auto-creates users from the identity, but needs extra setup, e.g. role assignment.

### auth.native_login

For a `custom` app that has its own login and no SSO. The Hub then shows a
per-app **Sign-in** setting and implements it with compose-override labels;
the template itself never changes.

```yaml
auth:
  method: custom
  sso: false
  group_access: true          # enforced only behind Portcullis sign-in
  access_group: users_plex
  group_admin: false
  native_login:
    supported: true
    allow_without_gateway: true
    note: Plex signs users in with plex.tv accounts; its TV and mobile apps need "App's own login only".
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `supported` | `true` | Yes | The app's own login protects it on its own |
| `allow_without_gateway` | boolean | No (default `false`) | Admins may choose **App's own login only (no Portcullis)** |
| `note` | string (≤ 500) | No | Shown next to the Sign-in setting: what the app's login is, what breaks behind forward-auth |

The two modes ([Apps with their own login](../operations/auth-policies.md#apps-with-their-own-login)):

- **Portcullis sign-in, then the app's own login** (default): every router
  gets `portcullis-auth@docker,portcullis-groups@docker` in front of its own
  middlewares, the TLS tier from the policy, and group-gate requires
  `access_group` if `group_access: true`. The access policy applies as for
  `forward-auth`.
- **App's own login only** (only with `allow_without_gateway: true`): the
  template's middlewares without the gateway pair, `public@file`, no group.

Rules (schema and `tests/validate.py`; the Hub checks the first two too):

- only with `method: custom` and `sso: false`: an app with SSO is signed in
  through Portcullis and never gets a way around it;
- `supported` must be `true` (omit the block otherwise);
- a `custom` app with `group_access: true` needs `native_login` (group-gate
  only runs behind Portcullis sign-in);
- the compose file of a `custom` app never uses `portcullis-auth@docker` or
  `portcullis-groups@docker`: the Hub adds them.

### admin_paths

`admin_paths` lists path prefixes on the app's subdomains that need
`admin_group` **in addition** to the subdomain's group. The Hub publishes them
as group-gate `path_groups` (see [Groups → Path rules](../operations/groups.md#path-rules-path_groups-and-admin_paths)).

Each item must:

- match `^/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*$`, be at most 256 characters, and be unique in the list
- not contain `..` or `//`, and have no `.` segment (`/./`, a trailing `/.`)

Matching is a segment-boundary prefix match: `/admin` matches `/admin` and
`/admin/x`, but not `/administrator`.

Path rules only take effect on routers that use `portcullis-groups@docker`.
`validate.py` therefore fails if no router with
`portcullis-auth@docker,portcullis-groups@docker` serves each listed path.

```yaml
auth:
  method: native-oidc
  sso: true
  group_access: true
  group_admin: false
  access_group: users_vaultwarden
  admin_group: admin_vaultwarden
  admin_paths: ["/admin"]
```

### auth.public_access

Public path exceptions let anonymous visitors use an app's share links
(Nextcloud `/s/<token>`, Grafana shared dashboards) while the rest of the
host stays behind Portcullis. The template only **declares** the paths. When
an admin turns the exception on in the [Hub](../operations/hub.md#public-exceptions),
the Hub adds one Traefik router for them **without** forward-auth and
group-gate (contracts §3). A template must never ship such a router in
`compose.yml`. The app's own auth (share token, share password, expiry) is
all that protects these paths; see
[Auth policies → Public exceptions](../operations/auth-policies.md#public-exceptions).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled_by_default` | boolean | No (default `false`) | State of the Hub toggle until an admin chooses |
| `description` | string, one line, ≤ 500 | No | Shown in the Hub above the warning |
| `default_mode` | `listed` or `all` | No | `listed`: only shares an admin lists in the Hub; `all`: every share. Default `listed` if a path has `{token}`, else `all`. `listed` needs a `{token}` path |
| `token_pattern` | anchored regex `^...$`, ≤ 200 | If a path has `{token}` (and only then) | Every listed share token must match it |
| `credential_headers` | list of header names | No | Headers besides `Authorization` / `Proxy-Authorization` (always refused) the app logs a user in with, e.g. Immich `x-api-key` |
| `credential_cookies` | list of cookie names | No | Cookies the app logs a user in with (session, remember-me, render keys) |
| `credential_query` | list of parameter names | No | Query parameters the app logs a user in with (e.g. Immich `apiKey`, Grafana `auth_token`) |
| `static_extensions` | list of `[a-z0-9]{1,8}` | No | Extra file extensions supporting paths may serve (default: `avif css eot gif ico jpeg jpg js map mjs otf png svg ttf webp woff woff2`). Script extensions (`php`, `phtml`, `cgi`, `py`, `jsp`, …) are refused |
| `service` | compose service | No | Service the public router targets. Default: the only service with HTTP routers |
| `paths` | list, 1–20 | Yes | See below |

Each `paths` item:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prefix` | path | Yes | Segment-boundary prefix: `/s` matches `/s` and `/s/...`, not `/sx`. Letters, digits and `. _ ~ -` per segment, optional trailing `/`; one whole segment may be `{token}`. Not `/` itself; no wildcards, `..`, `//`, `%`, `?`, `#`, `$`, quotes or backticks |
| `description` | string, one line, ≤ 200 | Yes | What the path is for (shown in the Hub and on the app page) |
| `supporting` | boolean | No | Token-free path the share page needs. Opened in both modes, and **only for static files** below it unless `exact`. Can't have `{token}` |
| `exact` | boolean | No | Opens only this path itself (`Path`, no subpaths): a single app route or file the page needs. Requires `justification`; can't have `{token}`. A path on the broad list (an exact `/index.php` is still the whole front controller) also needs `broad: true` |
| `broad` | boolean | No | Acknowledges a prefix on the broad list; requires `justification` |
| `justification` | string | If `broad: true` or `exact: true` | Why the broad prefix / exact route is needed |

What each mode opens:

| Path kind | Mode `listed` | Mode `all` |
|-----------|---------------|------------|
| `{token}` path, e.g. `/s/{token}` | `/s/<t>` for each listed token `<t>` | `/s` (up to the segment before `{token}`) |
| `supporting: true` | static files under the prefix (see below) | same |
| `supporting: true` + `exact: true` | the exact path | same |
| other token-free paths | no | segment-boundary prefix (or the exact path with `exact: true`) |

Static files means Traefik's `PathRegexp` of the prefix, dot-free directory
segments and a file name ending in a static extension, e.g.
`/dist/core-common.js` or `/core/img/actions/a.svg`, but not `/dist/`,
`/dist/a`, `/dist/a.php` or `/dist/x.php/a.js`. An app route that only
accepts extension-less paths is therefore never reached through a
supporting path.

Logins never ride the public router: core's public guard (contracts §5)
answers 403 to requests carrying `Authorization`, `Proxy-Authorization`,
a `credential_headers` header, a `credential_cookies` cookie or a
`credential_query` parameter. Cookie and query names are compared
case-insensitively after PHP's name mangling (leading spaces dropped, ` `
and `.` become `_`, `name[…]` is `name`), raw and percent-decoded. List
**every** way the app authenticates a request at the pinned version.

In mode `listed` with no listed share, nothing is opened and no router is
generated.

Rules (schema, `tests/validate.py` and the Hub):

- **Broad prefixes** need `broad: true` and a `justification`: `/api`, `/apps`,
  `/index.php`, `/ocs`, `/ocs/v1.php`, `/ocs/v2.php`, `/remote.php`,
  `/remote.php/dav`, `/remote.php/webdav`, `/public.php`, `/dav`, `/webdav`,
  `/graphql`, `/rest`, `/v1`, `/v2`, `/v3`, `/auth`, `/login`, `/user`,
  `/users`, `/account`, `/settings`, `/identity`, `/sso`, `/oidc`, and any
  bare `/<name>.php`. A `{token}` path is checked on its mode-`all` extent
  (`/api/{token}` is broad).
- **Never public**: anything overlapping `/oauth2`, `/admin` or
  `/.well-known`, or the app's `admin_paths`.
- **No overlap with other routers**: a prefix (mode-`all` extent) may not
  overlap a `Path`/`PathPrefix` of another router on the app's hosts (login
  gates, admin routers, API splits). Traefik's `PathPrefix` is a plain string
  prefix, so `PathPrefix(`/login`)` overlaps `/logins`.
- **Analysable routing only**: routers on the app's hosts may use only
  `Host`, `Path`, `PathPrefix`, `Method`, `Header`, `HeaderRegexp`, `Query`,
  `QueryRegexp` and `ClientIP`, without negation. `PathRegexp`, negated
  matchers or unknown matchers make the Hub refuse the template's public
  plan (it can't prove there is no overlap).
- **`token_pattern`** must be anchored and compile, and must reject `""`,
  `.`, `..`, `a/b`, `/`, backticks, spaces, `%2F`, `${X}`, `)` and newlines.
  The Hub additionally requires tokens of `[A-Za-z0-9._~-]{1,128}`.
- **Routing names**: routers and middlewares named `portcullis-public-*` are
  reserved for the Hub.
- **Service**: with several routed services, set `service`. If it defines
  several Traefik services, exactly one host-wide router on it must name one.

- **Supporting prefixes are directories**: a supporting prefix whose last
  segment looks like a file (`/custom.css`) must be `exact`.

Set `enabled_by_default: true` only when turning the exception on opens
nothing by itself (mode `listed`) and can't weaken the host. Example
(Nextcloud, abridged):

```yaml
auth:
  method: forward-auth
  public_access:
    enabled_by_default: true
    default_mode: listed
    description: Public share links for people without a Portcullis account.
    token_pattern: '^[A-Za-z0-9-]{1,32}$'
    credential_cookies: [nc_username, nc_token, nc_session_id]
    paths:
      - prefix: "/s/{token}"          # quote: { } in flow style is YAML syntax
        description: Share page, password form, download and direct preview
      - prefix: "/public.php/dav/files/{token}"
        description: Public WebDAV of the share
      - prefix: /dist
        description: Compiled JS/CSS
        supporting: true                # static files only
      - prefix: /core/mimeicon
        description: File-type icon for files without a preview
        supporting: true
        exact: true
        justification: "#[PublicPage] route that only redirects to a static icon"
      - prefix: /apps/text/public
        description: Markdown viewer sessions (token in the body, so only in mode all)
```

## settings

User-configurable settings shown in the Hub. Each `key` becomes a key in the
per-app `.env`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | env key | Yes | Variable name |
| `label` | single line, non-empty | Yes | Label shown in the Hub |
| `type` | enum | Yes | `text`, `path`, `paths`, `boolean` or `select` |
| `description` | string | No | Help text |
| `required` | boolean | No | The setting must be filled in |
| `default` | string without control chars | No | Default value |
| `options` | list of strings without control chars | Required (at least one) for `select` | The choices of a `select` |
| `target` | object | No | Bind-mount target for `path` / `paths` (see below) |

### Setting types

| Type | Input | Example |
|------|-------|---------|
| `text` | Free-form text | API keys, custom names |
| `path` | One host directory | `/mnt/media/movies` |
| `paths` | Several host directories | Several media folders |
| `boolean` | On/off toggle | Feature flags |
| `select` | Dropdown of `options` | Log level |

`options` is a **list of plain strings**. Each string is both the stored value
and the label:

```yaml
settings:
  - key: MYAPP_LOG_LEVEL
    label: Log level
    type: select
    options: [info, debug, warn]
    default: info
```

### target

For `path` and `paths`, `target` says where the host path is mounted:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service` | service | Yes | Compose service to mount into |
| `mount` | `^/[^:]*$` (absolute, no `:`, no control chars) | Yes | Container path |

```yaml
settings:
  - key: JELLYFIN_MOVIES_PATH
    label: Movies folder
    description: Host path to your movies library
    type: path
    target:
      service: jellyfin
      mount: /data/movies
```

When the user sets it to `/mnt/media/movies`, the Hub's per-app override gets
the bind mount `"/mnt/media/movies:/data/movies"`.

## ports

Host port bindings the app needs (for non-HTTP protocols such as DNS or TURN;
HTTP always goes through Traefik). The Hub:

1. Refuses to enable the app if one of its ports is already claimed by another enabled app.
2. Shows each port as an editable field, so users can rebind it or (if not `required`) disable it.
3. Writes the effective bindings into the per-app compose override. `compose.yml` must **not** publish these ports itself.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | env key | Yes | Variable holding the user-overridable host port |
| `label` | single line, non-empty | Yes | UI label, e.g. `DNS (TCP)` |
| `protocol` | `tcp` or `udp` | Yes | |
| `service` | service | Yes | Compose service the port belongs to |
| `container` | integer 1–65535 | Yes, unless `range` is set | Container-side port |
| `default` | integer 1–65535 | Yes, unless `range` is set | Default host port |
| `range` | `"low-high"` | No | Inclusive port range, e.g. `"49152-65535"`. Mutually exclusive with `container` and `default`; can't be rebound |
| `bind` | IPv4 or IPv6 address | No | Default bind address (default `0.0.0.0`) |
| `required` | boolean | No | If not `true`, the user can clear the host port to disable the binding |
| `description` | string | No | Help text |
| `network_mode_host` | boolean | No | The service uses `network_mode: host`. Ports are claimed globally and can't be rebound |

```yaml
ports:
  - key: ADGUARD_DNS_TCP_HOST
    label: DNS (TCP)
    container: 53
    protocol: tcp
    default: 53
    required: true
    service: adguard
  - key: COTURN_MEDIA_RANGE
    label: TURN media relays
    protocol: udp
    range: "49152-65535"
    required: true
    service: coturn
    network_mode_host: true
```

## env

Per-app environment variables.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | env key | Yes | Variable name |
| `description` | non-empty string | Yes | What it is for |
| `generate` | `random`, `none` or `""` | No | `random`: the Hub generates 32 hex characters on first enable and writes them to the per-app `.env` |
| `required` | boolean | No | The variable must have a value |

Secrets (passwords, OIDC client secrets, app keys) must be `generate: random`
entries. Never hard-code a secret in `compose.yml`. A variable that
`compose.yml` references as required (`${VAR:?...}`) must be an `env` entry with
`generate: random`, because that is all the Hub writes.

```yaml
env:
  - key: VAULTWARDEN_ADMIN_TOKEN
    description: Vaultwarden admin panel token
    generate: random
  - key: VAULTWARDEN_OIDC_SECRET
    description: Vaultwarden OIDC client secret
    generate: random
```

## keycloak_clients

OIDC clients the Hub registers in Keycloak when the app is enabled. Required
(at least one) for `native-oidc`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` | Yes | Keycloak client ID. Core clients such as `portcullis-forward-auth` are reserved |
| `secret_env` | env key | Yes | The `env` entry (with `generate: random`) holding the client secret |
| `name` | single line, non-empty | Yes | Display name in Keycloak |
| `redirect_uri` | URI | Exactly one of the two | A single redirect URI |
| `redirect_uris` | list of URIs (at least one) | Exactly one of the two | Several redirect URIs |
| `email_verified_claim` | boolean | No (default `true`) | `false`: the client gets the `email-unverified` scope instead of `email`, so tokens carry `email` but no `email_verified` claim. For apps that refuse `email_verified=false` but accept the claim being absent (Vaultwarden). The app must then not request the `email` scope |

Redirect URIs must match `^[a-z][a-z0-9+.-]*://\S+$`, so custom schemes such
as `app.immich:///oauth-callback` work. `{{DOMAIN}}` is replaced.

The Hub tags each client with the template that owns it, and attaches the
`acr` and `groups` scopes (see [Hub → Keycloak clients](../operations/hub.md#keycloak-clients)).

**`email_verified_claim`.** Keycloak never trusts the LLDAP email (users can
edit it), so the built-in `email` scope always sends `email_verified: false`.
Some apps refuse that value. With `email_verified_claim: false` the Hub
attaches core's `email-unverified` scope instead (the `email` claim only) and
removes `email` from the client. Keycloak rejects a request for a scope the
client doesn't have (`invalid_scope`), so drop `email` from the scopes the app
requests; `tests/validate.py` checks `*SCOPE*` environment variables. The
email is still unverified: identity stays `sub` / `preferred_username`, and
the app must never link accounts by email
([contract §8](integration-contracts.md#8-keycloak-clients-core-hub-templates)).

```yaml
keycloak_clients:
  - client_id: vaultwarden
    secret_env: VAULTWARDEN_OIDC_SECRET
    redirect_uri: "https://passwords.{{DOMAIN}}/identity/connect/oidc-signin"
    name: Vaultwarden
    email_verified_claim: false
```

```yaml
keycloak_clients:
  - client_id: immich
    secret_env: IMMICH_OIDC_SECRET
    redirect_uris:
      - "https://photos.{{DOMAIN}}/auth/login"
      - "https://photos.{{DOMAIN}}/user-settings"
      - "app.immich:///oauth-callback"
    name: Immich
```

## config_files

Files the Hub copies from the template directory into the core checkout when
the app is enabled.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `src` | relative path, no `..` segment, no whitespace | Yes | Path relative to the template directory. Must exist (`validate.py`) |
| `dest` | non-empty, no `..` segment | Yes | Destination relative to the core checkout. Must stay inside it and not at its top level |

The Hub already copies the whole template directory to
`<core>/templates/<app-id>/` before every `compose up`. Mounting
`./templates/<app-id>/<file>` is usually all you need, and every built-in
template uses `config_files: []`.

## urls

Links shown in the Hub.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `label` | single line, non-empty | Yes | Link text |
| `url` | `^https?://\S+$` | Yes | URL, with `{{DOMAIN}}` replaced |

```yaml
urls:
  - label: Vault
    url: "https://passwords.{{DOMAIN}}"
```

## Validation

Run the validator from the templates repo:

```bash
python3 -m venv .venv && .venv/bin/pip install -r tests/requirements.txt
.venv/bin/python tests/validate.py            # all templates
.venv/bin/python tests/validate.py my-app     # one template (cross-template checks still run)
.venv/bin/python tests/validate.py --strict   # warnings fail too
```

It prints one line per problem with a hint. Exit codes: `0` OK, `1` rule
violations, `2` usage or setup error. Besides the schema, it checks:

**Layout**

- the directory name is a valid app ID (`^[a-z0-9][a-z0-9_-]{0,63}$`)
- the files are named exactly `manifest.yaml` and `compose.yml`
- `tests/apps/<app-id>.sh` exists
- the directory is listed in `.github/dependabot.yml`
- `.core-ref` holds exactly one ref

**Manifest**

- no key is declared twice across `env`, `settings` and `ports`, and none shadows a core variable
- every `secret_env` is an `env` entry with `generate: random`
- port `bind` values are IPs and `range` values are valid
- `config_files` sources exist
- `auth.native_login` only with `method: custom` and `sso: false`, and a `custom` app with `group_access: true` declares it

**Networks and volumes**

- Traefik-routed services use `networks: [default, portcullis-proxy]`, and internal services stay off `portcullis-proxy`
- `portcullis-proxy` is declared `external: true`, and no other networks are used
- volumes declare `name: portcullis_<volume>`, unique across templates and never external

**Variables**

- core variables use their default form, e.g. `${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}`
- every other variable is declared in the manifest
- required `${VAR:?}` variables are `generate: random` env entries

**Services**

- no `ports:`, `build:`, `container_name:` or `env_file:`
- every image is pinned `tag@sha256:digest`, and floating tags (`latest`, `16-alpine`, ...) are rejected

**Bind mounts**

- only `./templates/<app-id>/<file>` (the file must exist) and `./certs/ca-bundle.crt:<path>:ro`
- never `./scripts/` or another template's files

**Routers**

- every router has a rule of the form `` Host(`<sub>.${PORTCULLIS_DOMAIN:-portcullis.local}`) ``, and no core subdomain
- `entrypoints: websecure`, and `tls.options` one of `authaware@file`, `public@file`, `protected@file` (`mtls` apps need `protected@file`)
- `security-headers@file` is in the middlewares
- `portcullis-auth@docker` and `portcullis-groups@docker` always appear together, in that order
- forward-auth and header-auth routers use them; native-OIDC host-wide routers don't
- `public`, `custom` and `mtls` routers use neither (for `custom` apps the Hub adds them, see [auth.native_login](#authnative_login))
- each `admin_paths` entry is served by a gated router

**Public exceptions** (`auth.public_access`)

- only for `forward-auth`, `header-auth` and `native-oidc`; header-auth apps list `identity_headers`, and every identity-like `X-…`/`Remote-…` header in `compose.yml` must be among them
- the prefix, broad, never-public, overlap, matcher and `token_pattern` rules of [auth.public_access](#authpublic_access)
- `exact` paths have a `justification` and no `{token}`; supporting prefixes don't name a file
- no router or middleware named `portcullis-public-*`

**Header trust**

- header-auth apps restrict identity headers to Traefik's IP
- nothing trusts `**`, `0.0.0.0/0`, `::/0` or the proxy subnet

**Cross-template**

- no subdomain or volume name is used by two templates

---

## Complete example

A native-OIDC app with path settings, generated secrets and a Keycloak client:

```yaml
# yaml-language-server: $schema=../schema/manifest.schema.json
name: Jellyfin
description: Free and open-source media server -- movies, TV, music, live TV
icon: "\U0001F4FA"
category: media
tags: [media, movies, tv, music, streaming, opensource]

auth:
  method: native-oidc
  sso: true
  group_access: true
  group_admin: true
  access_group: users_jellyfin
  admin_group: admin_jellyfin
  notes: >
    SSO-Auth plugin with group enforcement. Users must be in access_group
    to log in. Members of admin_group get Jellyfin admin.

settings:
  - key: JELLYFIN_MOVIES_PATH
    label: Movies folder
    description: Host path to your movies library
    type: path
    target:
      service: jellyfin
      mount: /data/movies

env:
  - key: JELLYFIN_ADMIN_PASSWORD
    description: Jellyfin admin password
    generate: random
  - key: JELLYFIN_OIDC_SECRET
    description: Jellyfin OIDC client secret
    generate: random

keycloak_clients:
  - client_id: jellyfin
    secret_env: JELLYFIN_OIDC_SECRET
    redirect_uris:
      - "https://media.{{DOMAIN}}/sso/OID/redirect/keycloak"
    name: Jellyfin

config_files: []

urls:
  - label: Jellyfin
    url: "https://media.{{DOMAIN}}"
```

A forward-auth app with host ports:

```yaml
name: Pi-hole
description: Network-wide ad blocking via DNS sinkhole
icon: "\U0001F6AB"
category: networking
tags: [dns, adblock, privacy, filtering]

auth:
  method: forward-auth
  sso: false
  group_access: true
  group_admin: false
  access_group: users_pihole
  admin_group: admin_pihole
  notes: No SSO support. Has its own web password. Access gated by group-gate middleware.

ports:
  - key: PIHOLE_DNS_TCP_HOST
    label: DNS (TCP)
    container: 53
    protocol: tcp
    default: 53
    required: true
    service: pihole
  - key: PIHOLE_DNS_UDP_HOST
    label: DNS (UDP)
    container: 53
    protocol: udp
    default: 53
    required: true
    service: pihole

env:
  - key: PIHOLE_WEBPASSWORD
    description: Pi-hole web interface password
    generate: random

keycloak_clients: []
config_files: []

urls:
  - label: Dashboard
    url: "https://pihole.{{DOMAIN}}/admin"
```

The real manifests of every built-in template are rendered in the [App Catalog](../apps/index.md).
