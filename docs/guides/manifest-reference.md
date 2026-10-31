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
| `group_access` | boolean | Yes | group-gate restricts the app's subdomains to `access_group` |
| `group_admin` | boolean | Yes | The app maps `admin_group` to its admin role |
| `access_group` | group | If `group_access: true` | LLDAP group required for access, by convention `users_<app>` |
| `admin_group` | group | If `group_admin: true` or `admin_paths` is non-empty | LLDAP group for admin privileges, by convention `admin_<app>` |
| `admin_paths` | list of path prefixes | No | Paths that additionally require `admin_group` (see below) |
| `notes` | string | No | Free-text notes about the auth integration. Shown on the app's docs page. Upgrade constraints go here too |

Constraints the schema enforces:

- `group_access: true` requires `access_group`.
- `group_admin: true` requires `admin_group`.
- A non-empty `admin_paths` requires `admin_group`.
- `method: public` requires `group_access: false` and an empty (or missing)
  `admin_paths`.

`access_group` is only *enforced* by group-gate when `group_access: true`.
Otherwise it is informational.

### Auth methods

| `method` | Meaning | Router middlewares |
|----------|---------|--------------------|
| `native-oidc` | The app talks OIDC to Keycloak itself. Needs `keycloak_clients` | **No** `portcullis-auth` on the host-wide router. Login or admin paths may use a separate `PathPrefix` router with forward-auth |
| `forward-auth` | oauth2-proxy + group-gate in front. The app has its own login, or none | `portcullis-auth@docker,portcullis-groups@docker` |
| `header-auth` | Forward-auth, and the app also trusts `X-Forwarded-User` from Traefik (and only from Traefik) | `portcullis-auth@docker,portcullis-groups@docker` |
| `mtls` | Client certificate at the TLS layer | `tls.options: protected@file`, no forward-auth |
| `custom` | App-specific account system, e.g. plex.tv | None |
| `public` | No authentication | None |

See [Choosing an auth method](https://github.com/porelli/portcullis-templates/blob/main/CONTRIBUTING.md#choosing-an-auth-method)
in the templates repo's contributing guide.

### SSO values

- `true`: the user authenticates once in Keycloak and is logged into the app automatically.
- `false`: the app has its own login form. Forward-auth only gates access, and the user logs in again.
- `"partial"`: the app auto-creates users from the identity, but needs extra setup, e.g. role assignment.

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
  group_access: false
  group_admin: false
  access_group: users_vaultwarden
  admin_group: admin_vaultwarden
  admin_paths: ["/admin"]
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

Redirect URIs must match `^[a-z][a-z0-9+.-]*://\S+$`, so custom schemes such
as `app.immich:///oauth-callback` work. `{{DOMAIN}}` is replaced.

The Hub tags each client with the template that owns it, and attaches the
`acr` and `groups` scopes (see [Hub → Keycloak clients](../operations/hub.md#keycloak-clients)).

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
- each `admin_paths` entry is served by a gated router

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
