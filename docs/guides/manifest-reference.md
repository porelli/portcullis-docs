# Manifest Reference

Every app template includes a `manifest.yaml` file that describes the app to the Hub. This page documents every field in the manifest schema.

## Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name shown in the Hub |
| `description` | string | Yes | One-line description of what the app does |
| `icon` | string | Yes | Unicode emoji for the app card (e.g., `"\U0001F4CA"`) |
| `category` | string | Yes | Category for grouping in the catalog |
| `tags` | list of strings | Yes | Searchable tags |

**Categories in use:** `monitoring`, `media`, `productivity`, `security`, `networking`, `ai`

Host-port collisions between apps are detected from the `ports:` section (see below); there is no manual conflict list.

## auth

Defines how the app authenticates users.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `method` | string | Yes | Auth method: `forward-auth`, `native-oidc`, `header-auth`, or `public` |
| `sso` | boolean or string | Yes | Whether single sign-on is supported. `true`, `false`, or `partial` |
| `group_access` | boolean | Yes | Whether access is restricted by LLDAP group membership |
| `group_admin` | boolean | Yes | Whether the app maps an LLDAP group to its admin role |
| `access_group` | string | Yes | LLDAP group name required for access (e.g., `users_grafana`) |
| `admin_group` | string | Yes | LLDAP group name for admin privileges (e.g., `admin_grafana`) |
| `notes` | string | No | Free-text notes about the auth integration |

### Auth Methods

**`forward-auth`** -- The app has no SSO support. oauth2-proxy handles authentication, and group-gate enforces group membership. The app itself sees no auth headers unless combined with header-auth patterns.

**`native-oidc`** -- The app has built-in OpenID Connect support and redirects to Keycloak directly. Requires a `keycloak_clients` entry.

**`header-auth`** -- The app accepts a trusted identity header (typically `X-Forwarded-User`) set by oauth2-proxy after forward authentication. This is a variant of forward-auth where the app also reads the authenticated user's identity.

**`public`** -- No authentication required. The app is accessible to anyone.

### SSO Values

- `true` -- Full SSO. User authenticates once in Keycloak and is automatically logged into the app.
- `false` -- No SSO. The app has its own login form. Forward auth just gates access; the user must log in separately.
- `partial` -- Partial SSO. The app auto-creates users from headers but may require additional setup (e.g., role assignment).

## settings

Optional list of user-configurable settings shown in the Hub. Settings are typically used for host paths (media libraries) or feature toggles.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | string | Yes | Environment variable name or unique identifier |
| `label` | string | Yes | Human-readable label shown in the Hub |
| `description` | string | Yes | Help text explaining what this setting controls |
| `type` | string | Yes | Input type (see below) |
| `required` | boolean | No | Whether the setting must be filled. Default: `false` |
| `default` | string | No | Default value |
| `options` | list of objects | No | For `select` type: `{value: "...", label: "..."}` |
| `target` | object | No | Where to mount a path setting (see below) |

### Setting Types

| Type | Description | Example |
|------|-------------|---------|
| `text` | Free-form text input | API keys, custom names |
| `path` | Single host directory path | `/mnt/media/movies` |
| `paths` | Multiple host directory paths | Multiple media folders |
| `boolean` | On/off toggle | Feature flags |
| `select` | Dropdown from predefined options | Theme selection |

### target (for path settings)

When `type` is `path` or `paths`, the `target` field specifies which container and mount point to bind the host path to:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service` | string | Yes | Docker Compose service name |
| `mount` | string | Yes | Container path to mount at |

Example:

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

When the user sets this to `/mnt/media/movies` in the Hub, the compose file gets an additional bind mount: `/mnt/media/movies:/data/movies`.

## ports

Declares host port bindings the app needs. The Hub:

1. Refuses to enable an app if any of its ports are already claimed by an enabled app.
2. Surfaces each port as an editable field in the Hub UI so users can rebind or disable it.
3. Writes the effective bindings into the per-app compose override at enable-time — so `compose.yml` itself should **not** contain a `ports:` block for anything declared here.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | string | Yes | Env var name used for the user-overridable host port |
| `label` | string | Yes | UI label (e.g., `DNS (TCP)`) |
| `description` | string | No | Help text shown under the label |
| `container` | int | Conditional | Container-side port. Required unless `range` is set. |
| `protocol` | string | Yes | `tcp` or `udp` |
| `default` | int | Conditional | Default host port. Required unless `range` is set. |
| `bind` | string | No | Default bind address (default: `0.0.0.0`) |
| `required` | boolean | No | If `false`, the user can clear the host port to disable the binding. Default: `false` |
| `service` | string | Yes | Compose service this port belongs to |
| `network_mode_host` | boolean | No | The service uses `network_mode: host`. Ports are claimed globally and can't be rebound via override. Default: `false` |
| `range` | string | No | Inclusive port range like `"49152-65535"`. Used for things like TURN media relays. Incompatible with user rebinding. |

Example — a DNS resolver with separate TCP/UDP bindings:

```yaml
ports:
  - key: ADGUARD_DNS_TCP_HOST
    label: DNS (TCP)
    description: Resolver port for TCP-based queries
    container: 53
    protocol: tcp
    default: 53
    required: true
    service: adguard
  - key: ADGUARD_DNS_UDP_HOST
    label: DNS (UDP)
    container: 53
    protocol: udp
    default: 53
    required: true
    service: adguard
```

Example — a TURN relay using host networking plus a UDP media range:

```yaml
ports:
  - key: COTURN_STUN_PORT
    label: STUN/TURN
    container: 3478
    protocol: udp
    default: 3478
    required: true
    service: coturn
    network_mode_host: true
  - key: COTURN_MEDIA_RANGE
    label: TURN media relays
    protocol: udp
    range: "49152-65535"
    required: true
    service: coturn
    network_mode_host: true
```

## env

List of environment variables the app needs. The Hub generates random values for variables with `generate: random` during initial setup.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | string | Yes | Environment variable name |
| `description` | string | Yes | What this variable is for |
| `generate` | string | No | `random` to auto-generate, `none` or omit for manual. Default: `none` |
| `required` | boolean | No | Whether the variable must have a value. Default: `false` |

Example:

```yaml
env:
  - key: JELLYFIN_ADMIN_PASSWORD
    description: Jellyfin admin password
    generate: random
  - key: JELLYFIN_OIDC_SECRET
    description: Jellyfin OIDC client secret
    generate: random
```

## keycloak_clients

List of OIDC clients to register in Keycloak when the app is enabled. Required for `native-oidc` apps.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | string | Yes | Keycloak client identifier |
| `secret_env` | string | Yes | Name of the env var holding the client secret |
| `redirect_uri` | string | Conditional | Single redirect URI (use this or `redirect_uris`) |
| `redirect_uris` | list of strings | Conditional | Multiple redirect URIs |
| `name` | string | Yes | Display name in Keycloak |

The `{{DOMAIN}}` placeholder in redirect URIs is replaced with the value of `PORTCULLIS_DOMAIN`.

Example with a single redirect URI:

```yaml
keycloak_clients:
  - client_id: vaultwarden
    secret_env: VAULTWARDEN_OIDC_SECRET
    redirect_uri: "https://passwords.{{DOMAIN}}/identity/connect/oidc-signin"
    name: Vaultwarden
```

Example with multiple redirect URIs (e.g., web + mobile app):

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

List of configuration files to copy into the app container or volume.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `src` | string | Yes | Source path relative to the template directory |
| `dest` | string | Yes | Destination path in the container |

Example:

```yaml
config_files:
  - src: config/settings.json
    dest: /app/config/settings.json
```

## urls

Links displayed in the Hub for quick access to the app.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `label` | string | Yes | Link text |
| `url` | string | Yes | URL template (supports `{{DOMAIN}}` placeholder) |

Example:

```yaml
urls:
  - label: Dashboard
    url: "https://grafana.{{DOMAIN}}"
  - label: Admin Panel
    url: "https://grafana.{{DOMAIN}}/admin"
```

---

## Complete Example

Here is a complete manifest for a native OIDC app with settings, environment variables, and a Keycloak client:

```yaml
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
    to log in. Members of admin_group get Jellyfin admin. Configured
    automatically by setup sidecar.

settings:
  - key: JELLYFIN_MOVIES_PATH
    label: Movies folder
    description: Host path to your movies library
    type: path
    target:
      service: jellyfin
      mount: /data/movies
  - key: JELLYFIN_TV_PATH
    label: TV Shows folder
    description: Host path to your TV shows library
    type: path
    target:
      service: jellyfin
      mount: /data/tv
  - key: JELLYFIN_MUSIC_PATH
    label: Music folder
    description: Host path to your music library
    type: path
    target:
      service: jellyfin
      mount: /data/music

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
      - "http://media.{{DOMAIN}}/sso/OID/redirect/keycloak"
    name: Jellyfin

config_files: []

urls:
  - label: Jellyfin
    url: "https://media.{{DOMAIN}}"
```

And a simpler manifest for a forward-auth app with no OIDC:

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
