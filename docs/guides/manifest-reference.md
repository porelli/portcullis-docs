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
| `{{DOMAIN}}` | In `urls` and redirect URIs, replaced with `PORTCULLIS_DOMAIN` (the main domain) |
| `{{HOST_<ROUTER>}}` | **NEW (contract v2).** In `urls` and redirect URIs, replaced with the instance's full hostname for host router `<router>` (`<ROUTER>` as in [instances](#instances)) |

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
| `links` | object | Yes | The app's own website and source repository. See [links](#links) |
| `auth` | object | Yes | See [auth](#auth) |
| `settings` | object `{sections, options}` | No | Options set in the Hub (template contract v3). See [settings](#settings) |
| `files` | list | No | Data files for file deliveries. See [files](#files) |
| `hooks` | list | No | Commands the Hub runs with the settings on stdin. See [hooks](#hooks) |
| `reload` | object | No | The app's reload action. See [reload](#reload) |
| `ports` | list | No | See [ports](#ports) |
| `env` | list | No | See [env](#env) |
| `keycloak_clients` | list | No; required (at least one) for `native-oidc` | See [keycloak_clients](#keycloak_clients) |
| `config_files` | list | No | See [config_files](#config_files) |
| `urls` | list | No | See [urls](#urls) |
| `tests` | object | Yes, for templates in the default catalog (`tests.signin`; validate.py) | CI only, the Hub ignores it. See [tests.signin](#testssignin) |
| `instances` | `multi` or `single` | No (default `single`) | **NEW (contract v2).** Whether the Hub may run more than the default instance. See [instances](#instances) |
| `hosts` | object | No | Per-host properties by host router name; today only `immutable`. See [hosts.immutable](#hostsimmutable) |

**Categories in use:** `monitoring`, `media`, `productivity`, `security`,
`networking`, `ai`, `devops`, `finance`, `vpn`, `remote-access`, `public`.

## links

Where the app itself comes from. The docs site shows both on the app's page.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `website` | `https://` URL (≤ 512 chars, no credentials or placeholders) | Yes | The project's own homepage (not a mirror, store page or Docker Hub). If it has none, its repository or documentation site |
| `source` | `https://` URL or `null` | Yes | The canonical upstream code repository (GitHub, GitLab, Codeberg, Gitea, SourceHut, …), or the repository the template's image is built from when that differs (name the upstream in `auth.notes`). `null` only for closed-source apps |
| `source_note` | single line, 10–200 chars | Only with `source: null` | Why there is no source repository, e.g. "Plex Media Server is proprietary" |

`tests/validate.py` refuses registry and package pages, this templates
repository, and non-repository URLs on known code hosts.

```yaml
links:
  website: https://jellyfin.org/
  source: https://github.com/jellyfin/jellyfin
```

## auth

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `method` | enum | Yes | `native-oidc`, `forward-auth`, `header-auth`, `mtls`, `custom` or `public` (see below) |
| `sso` | `true`, `false` or `"partial"` | Yes | Whether single sign-on is supported |
| `group_access` | boolean | Yes | group-gate restricts the instance's hostnames to its access group (`access_group` for the default instance). For `custom` apps only while Portcullis sign-in is in front of them (`native_login`) |
| `group_admin` | boolean | Yes | The app maps `admin_group` to its admin role |
| `access_group` | group | If `group_access: true` | LLDAP group required for access, by convention `users_<app>`. It is the **default instance's** group; every other instance uses `users_<instance-id>` ([instances](#instances)) |
| `admin_group` | group | If `group_admin: true` or `admin_paths` is non-empty | LLDAP group for admin privileges, by convention `admin_<app>`. The default instance's; other instances use `admin_<instance-id>` |
| `admin_paths` | list of path prefixes | No | Paths that additionally require `admin_group` (see below) |
| `public_access` | object | No | Public path exceptions: share-link paths the Hub can open without forward-auth (see [auth.public_access](#authpublic_access)) |
| `native_login` | object | No | The app has its own login and no SSO (`method: custom` only); enables the Hub's Sign-in setting (see [auth.native_login](#authnative_login)) |
| `keycloak_access_role` | boolean | No | `native-oidc` only, needs `access_group`. Keycloak itself refuses sign-in to anyone outside the instance's access group (see below) |
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
- `keycloak_access_role: true` requires `method: native-oidc` and
  `access_group`; so does `method: native-oidc` with `group_access: false`.

`access_group` is only *enforced* by group-gate when `group_access: true`.
Otherwise it is informational, unless the Keycloak access role applies.

**`keycloak_access_role`.** The Hub restricts sign-in to the instance's access
group in Keycloak ([contract §8](integration-contracts.md#8-keycloak-clients-core-hub-templates),
"Access role"): every client of the instance gets a client role `access`, the
access group gets that role, and the client's browser flow denies sign-in
without it (also when the user already has a Keycloak session). The Hub does
the same for every `native-oidc` template with `group_access: false`. Set it
for apps that can't restrict sign-in to a group themselves or that let
outsiders create accounts without rights (Immich, Headscale, NetBird,
DokuWiki, Wiki.js, Actual), and as defence in depth on apps whose login paths
are gated by group-gate or that check groups themselves (Paperless,
Vaultwarden, GitLab, Nextcloud). It fails closed: without the group or the
role nobody signs in. Only access-group members sign in — admin-group members
too only if they are also in the access group. Every client of such an app has
direct access grants, implicit flow, service accounts, device and CIBA grants
and standard token exchange switched off (only the browser flow signs in):
don't use it for an app whose client needs one of them. CI has no Hub, so the
sign-in test runs without the access role (see
[tests.signin](#testssignin) `expected_fail`).

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

`admin_paths` lists path prefixes on the app's hostnames that need
the admin group **in addition** to the hostname's group. The Hub publishes them
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

Options an admin (or each person) sets in the Hub: template contract v3,
[Integration Contracts §13](integration-contracts.md#13-settings). Each option
has a type, a scope, constraints and one or more deliveries (how the value
reaches the app). The Hub validates, stores, resolves and delivers the values;
the template only declares them. Decoding is strict: an unknown key anywhere
under `settings`, `files`, `hooks` or `reload` is refused.

```yaml
settings:
  sections: [Storage, Accounts, Library]   # panel sections, in order
  options: [...]                           # the options below
```

| Field | Type | Description |
|-------|------|-------------|
| `sections` | list of `^[A-Za-z0-9][A-Za-z0-9 ]{0,31}$`, unique | Panel sections, in display order |
| `options` | list of options | The options, in display order |

A list directly under `settings:` (contract v2) is refused.

**Immich example (abridged):**

```yaml
settings:
  sections: [Storage, Accounts, Library]
  options:
    - key: trash_days
      label: Keep deleted items for
      type: int
      unit: days
      min: 0
      max: 3650
      default: 30
      section: Library
      applies: restart
      delivery: [{env: IMMICH_TRASH_DAYS}]
    - key: storage_quota
      label: Storage quota
      type: size
      step: 1GiB
      allow_unlimited: true
      scope: person
      default: 100GiB
      resolve: max
      resolve_choices: [max, min, priority]
      section: Storage
      applies: next_sign_in
      delivery:
        - claim: {client: immich, name: immich_quota, json_type: int,
                  render: {unit: GiB, unlimited: "-1"}}
    - key: role
      label: Role
      type: enum
      options: [{value: user, label: User}, {value: admin, label: Administrator}]
      scope: person
      privileged: true
      default: user
      group_values: {"{{ADMIN_GROUP}}": admin}
      resolve: max
      section: Accounts
      applies: next_sign_in
      delivery: [{claim: {client: immich, name: immich_role, json_type: string}}]
    - key: external_library
      label: External photo library
      type: path
      mode: ro
      needs: read
      writes_as: {uid: 0, gid: 0}
      target: {service: immich-server, mount: /usr/src/app/external}
      applies: restart
```

### Option fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | `^[a-z][a-z0-9_]{0,39}$`, unique | Yes | Identifier (not an env name) |
| `label` | single line, 1–64 chars | Yes | Panel label |
| `description` | text, ≤ 500 chars, no control characters | No | Help text in the panel and on My apps |
| `section` | one of `settings.sections` | No | Panel section |
| `type` | see [Types](#types) | Yes | |
| `scope` | `instance`, `person`, `group`, `person_entered` | No (default `instance`) | See [Scopes](#scopes) |
| `required` | boolean | No | The value must be non-empty. A set secret counts as non-empty. On `person` scope the default must be non-empty; not for `group` scope |
| `default` | a value of the option's type | `person`: yes; refused for `group`, `person_entered` and secrets | The template's default (for `person`: everyone else with access) |
| `applies` | `live`, `reload`, `next_request`, `next_sign_in`, `restart`, `account_creation` | No | When a change takes effect. Default: `next_sign_in` with a claim delivery, `next_request` with a header delivery, otherwise `restart`. See [Applies](#applies) |
| `requires` | list of option keys | No | Instance options only: other instance options that must be non-empty when this one is (not itself) |
| `delivery` | list of [deliveries](#deliveries) | See [Deliveries](#deliveries) | How the value reaches the app |
| `resolve` | `max`, `min`, `priority`, `union`, `intersection`, `any`, `all` | `person` only, and required there | How one value is picked for a person in several groups. See [Scopes](#scopes) |
| `resolve_choices` | list of the above | `person` only | Other rules the admin may switch to; each must fit the type |
| `group_values` | map `{{ACCESS_GROUP}}` / `{{ADMIN_GROUP}}` → value | `person` only | Preset rows for the instance's own groups (the manifest needs `access_group` / `admin_group`). Other group names are refused: the admin picks them |
| `privileged` | boolean | `person` only | The option grants a privilege. Only `enum` and `bool`; the default must be the lowest value (the first `options` entry, or `false`); no `{{ACCESS_GROUP}}` preset |
| `self_visible` | boolean (default `true`) | `person` only | `false` hides the person's value from My apps |
| `unique` | boolean | `list`, or `person_entered` `string` / `int` | No two items (list) or no two people (person-entered) hold the same value |
| `admin_override` | boolean | `person_entered` only | Admins may enter a value for someone (they can always clear one) |

Type constraints (`pattern`, `min`, `options`, …) are in [Types](#types). A
constraint the type doesn't take (`min` on an `enum`) is refused.

### Types

Values are stored canonically: sizes in bytes, durations in seconds. Write
sizes with binary units only (`10GiB`, `512MiB`; `10GB` and `10G` are
refused) and durations with a unit (`30d`, `90m`, `60s`). `default`, `min` /
`max` / `step` and `group_values` must be valid values of the option.

| Type | Holds | Constraints |
|------|-------|-------------|
| `string` | Text (one line) | `pattern` (anchored `^…$`, Go RE2 syntax: no lookarounds or backreferences, matches the whole value), `min_len` / `max_len` (0–65535), `format`: `hostname`, `ip`, `cidr` (no host bits), `url` (http/https), `email`, `iana_tz`, `locale`, `cron`, `semver`, `hex` |
| `int` | 64-bit integer | `min`, `max`, `step` (values are `min + k × step`), `unit` (a label, e.g. `days`) |
| `size` | Bytes | `min`, `max`, `step` (values are `k × step`), `allow_unlimited` (the value `unlimited`; every delivery must then set `render.unlimited`) |
| `duration` | Seconds | `min`, `max` |
| `bool` | `true` / `false` | — |
| `enum` | One choice | `options: [{value, label}]` (at least one; value ≤ 128 chars, label one line ≤ 64). The order is the rank for `max` / `min` |
| `multi_enum` | A set of choices | `options` as for `enum`, `min_items` / `max_items`; stored in option order |
| `list` | Ordered items | `items: {type, …}` (`string`, `int`, `bool` or `enum`, with that type's constraints), `min_items` / `max_items` (0–1000), `unique` |
| `table` | Records | `min_items` / `max_items`, `columns: [{name, label, type, required, …}]` (name `^[a-z][a-z0-9_]{0,31}$`, unique; type `string`, `int`, `bool` or `enum` with its constraints), `key_column` (that column's values are unique; records are delivered keyed by it) |
| `path` | A host directory, bind-mounted | `target: {service, mount}` (an absolute, clean container path), `mode` (`ro` / `rw`), `needs` (`read` / `write`; `write` with `ro` is refused), `writes_as: {uid, gid}` (numbers, or keys of instance `int` / `string` options; shown in the panel), or instead of those three a `folder` block, and `checks` ([Shared folders](#shared-folders-folder-checks-lan_only)). Instance scope only, no `delivery`: the target is the delivery. The value is a host path or `folder:<id>[/<subpath>]` |
| `secret` | A write-only value | `min_len` / `max_len`, `generate: {length, charset}` (length 8–128; charset `hex`, `alphanumeric` or `ascii_printable`: printable ASCII without space, `'` and `\`). No `default`. Values can't contain `'` or control characters |
| `group` / `groups` | One / a set of LLDAP groups | `groups`: `min_items` / `max_items` |
| `user` / `users` | One / a set of LLDAP usernames (lowercased; never an email) | `users`: `min_items` / `max_items` |

**Refused:** the contract v2 types `text`, `boolean`, `select` and `paths`
(use `string`, `bool`, `enum` with `options: [{value, label}]`, and one `path`
per directory), and the reserved types `folder`, `person_secret`,
`person_id`, option fields `hash`, `length`, `revoke_on_leave`,
`on_restore`, `pool`, `username`, `mount` and `runs_as.uid_from` /
`gid_from` (later features). `env[].generate: none` is gone: a value the admin enters is a
setting.

### Shared folders (`folder`, `checks`, `lan_only`)

[Integration Contracts §13.15](integration-contracts.md#1315-shared-folders-checks-and-lan-only-ports)
and [§14](integration-contracts.md#14-shared-folders-and-the-doctor).

**`folder`** (a `path` option; replaces `mode`, `needs` and `writes_as`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `access` | `read` / `write` | Yes | `read` always mounts read-only |
| `runs_as` | `{uid, gid}` numbers, or `{uid_env, gid_env}` env names of instance `int` options; one source per id (`uid_from` / `gid_from`: reserved, project 3) | Yes | The uid and gid the app uses on this mount; numbers must match the service's compose `user:` when the service sets one |
| `joins_group` | `group_add` / `gid_env` / `template` | No (default `group_add`) | How the app joins the folder's group; `gid_env` needs `runs_as.gid_env` |
| `must_own` | boolean | No | The Hub also sets the owner to the app's uid. Writers only |

**`checks`** (option level, next to `folder`): a list of `{kind, reason, …}`;
`reason` is required (one line, ≤ 200 characters).

| `kind` | On | Parameters |
|--------|----|------------|
| `filesystem` | a `path` option with `folder` | `needs`: from `[xattr, acl]`; `not`: from `[nfs, cifs, fuse]` |
| `exclusive` | a `path` option with `folder.access: write` | — |
| `free_space` | a `path` option | `min`: a size in binary units (`500GiB`) |
| `requires_group_value` | a `scope: person` option | — |

**`ports[].lan_only`**: see [ports](#ports).

**Choosing `runs_as` and `joins_group`.** Give the ids the app's process
really has on the mount:

- the image runs as root and the compose service sets no `user:` (Jellyfin,
  Immich): `runs_as: {uid: 0, gid: 0}` with the default `group_add`;
- the service sets `user: "1000:1000"`: the same numbers;
- the service sets `user: "${PUID:-1000}:${PGID:-1000}"`: `runs_as:
  {uid_env: PUID, gid_env: PGID}`, both instance `int` options;
- the image drops supplementary groups before starting the app (s6
  `s6-setuidgid`, `su -g`, many PUID/PGID images): a `group_add` gid never
  reaches the process. Use `joins_group: gid_env` so the Hub writes the
  folder's gid into the app's primary group variable instead (Plex:
  `PLEX_GID`), or, for a root process that keeps its own rights, say so in
  the notes (motionEye).

**One primary group per process.** With `joins_group: gid_env` every
folder option of the service shares that one variable, so they must all
use the **same shared folder** (subfolders are fine) or all use host paths;
the Hub refuses an assignment that would need two gids ("point both
settings at the same shared folder"). Plex's three libraries follow this
rule; say it in the template's notes so admins know. The variable may not
be read by another service's `user:` or `group_add`.

**Hardware transcoding next to a folder block.** Next to a `folder` block,
every `group_add` entry of the target service must be a number or exactly
one `${NAME}` of an instance `int` option; group names (`video`,
`render`) are refused. The render group's gid differs from host to host,
so declare an `int` option (for example `render_gid`, env `RENDER_GID`,
default `109`) and write `group_add: ["${RENDER_GID:-109}"]`. A variable
that isn't a declared `int` option is refused on every service.

**Jellyfin example:**

```yaml
settings:
  sections: [Libraries]
  options:
    - key: movies_path
      label: Movies folder
      description: Host path to your movies library
      section: Libraries
      type: path
      target: {service: jellyfin, mount: /data/movies}
      folder:
        access: read
        runs_as: {uid: 0, gid: 0}
        joins_group: group_add
      applies: restart
```

### Scopes

| Scope | Values | Rules |
|-------|--------|-------|
| `instance` | One value for the instance | Without `delivery`: `env: <UPPER(key)>` |
| `person` | A `default` plus per-group rows the admin adds; resolved to one value per person with access | Needs `default` and a per-person delivery (claim, header, file or hook); env is refused |
| `group` | One record per group the admin adds; not resolved per person | No `default`. Env needs `render.format: json`. Records are delivered only for groups that still exist with the same LLDAP id |
| `person_entered` | Each person enters their own value on My apps | See [Person-entered options](#person-entered-options) |

**`resolve`** picks one value for a person in several groups with a row:

| Rule | Types |
|------|-------|
| `max`, `min` | `int`, `size`, `duration`, `enum` (by option order); `unlimited` beats any number under `max` and loses under `min` |
| `priority` | Any: the first row (in the admin's order) the person is in |
| `union`, `intersection` | `list`, `multi_enum`, `groups` |
| `any`, `all` | `bool` |

The default is a fallback for people in none of the rows' groups and never
takes part in `max` / `union`. Nobody outside the population (the access
group's members, minus expired memberships) gets a value.

**Group values must only grant.** A group-scope record, and a group row, is
left out when its group was deleted or re-created, and records aren't
delivered at all while Users & Groups is unavailable. The app must treat a
missing record as "nothing granted", never as "no restriction".

### Person-entered options

`scope: person_entered`: each person with access enters their own value
(Firefox Sync's Mozilla account ID). See
[Adding an App](adding-an-app.md#values-each-person-enters) for the full
example.

- Types `string`, `int`, `bool` or `enum` only (not `secret`). A `string`
  needs `max_len` (at most 256), a `pattern` or a `format`.
- `unique: true` (string / int): no two people of one instance hold the same
  value. `admin_override: true`: admins may enter one for someone.
- Refused: `default`, `required`, `resolve`, `resolve_choices`,
  `group_values`, `privileged`, `requires` (in either direction),
  `self_visible: false`, `applies: account_creation`.
- `applies` must match the delivery:
    - `file`: the file's `on_membership_change` (`restart` → `restart`,
      `reload` → `reload`, `hook` → `live`; a file without one is refused);
    - `hook`: `live`, and the hook's `when` lists `membership_change`;
    - `claim`: `next_sign_in`; `header`: `next_request`;
    - `env`: `restart`, and `render.join` or `render.format: json` (the
      variable is the list of everyone's values).
- A template whose routes can run without Portcullis identity (method
  `public` or `custom`, or `native_login.allow_without_gateway`) needs
  `auth.access_group`: its members may enter a value.

### Deliveries

Each entry of `delivery` is exactly one of:

| Delivery | Form | For |
|----------|------|-----|
| env | `{env: NAME}` | `instance`, `group` (`render.format: json`), `person_entered` (the list). The name must match the env-key rule, not be `PORTCULLIS_*`, not be used by another option, `env:`, `ports:` or a client's `secret_env`, and be interpolated in `compose.yml` as `${NAME…}` (not hard-coded in a service's `environment`) |
| indexed env | `{env: NAME_{n}}` | An `instance` `list` with `max_items` (at most 64): writes `NAME_1` … `NAME_<max_items>`, one item each, unused ones empty. Every `NAME_<n>` compose references must be within `max_items` |
| claim | `{claim: {client, name, json_type, render}}` | `person`, `person_entered` on `native-oidc` templates. `client` is a `keycloak_clients[]` `client_id`; `name` matches `^[a-z][a-z0-9_]{0,63}$` and isn't a standard OIDC / JWT, Keycloak, `attr_*` or `portcullis_*` claim; one option per claim and client |
| header | `{header: {name, render}}` | `person`, `person_entered`. `name` matches `^X-Forwarded-Attr-[A-Za-z0-9]+(-[A-Za-z0-9]+){0,30}$`; one option per header. See the header rules below |
| file | `{file: {name, field, render}}` | Any scope. `name` is a `files[]` entry. `field` (`person`, `person_entered` only; default the option key, `^[a-z][a-z0-9_]{0,39}$`) names the value in the file's `people` / `entries`; one option per field |
| hook | `{hook: <name>, render}` | Any scope. `name` is a `hooks[]` entry |

`render` goes inside the claim, header or file; on an env or hook delivery
it is the entry's own `render` key.

**`json_type`** (claims): `string`, `int`, `bool` or `json`. `int` is a
32-bit integer (Keycloak's conversion): a size must be rendered in a unit
(`render.unit: GiB`) and `render.unlimited` must be a 32-bit integer
(`"-1"`). `bool` needs a `bool` option whose `render.true` / `render.false`
are exactly `true` / `false`. `json` takes `render.format: json`, a table, or
numbers. Statically visible mismatches are refused; a value that doesn't fit
at delivery time is not delivered (the person's claim is cleared).

**Headers** are per-person values group-gate adds on the instance's hosts.
They need routers with `portcullis-groups@docker`, and every router that
reaches the delivering backend (its network namespace, `network_mode:
service:` followed) must run Portcullis forward-auth, so no client can send
the header itself. Refused: method `public` or `custom` without Portcullis
sign-in, `native_login.allow_without_gateway`, and Traefik-labelled services
on `network_mode: host`. The Hub's public-exception router strips every
declared header name (and its `_` spelling).

### Render

| Field | For | Meaning |
|-------|-----|---------|
| `unit` | `size`: `B`, `KiB`, `MiB`, `GiB`, `TiB` (binary) or `KB`, `MB`, `GB`, `TB` (decimal, strictly 10ⁿ); `duration`: `s`, `m`, `h`, `d`; `int`: its own `unit` | The value divided by the unit |
| `integer` | `size`, `duration` | Refuse values that aren't whole in the unit (the save names the app and the unit) |
| `unlimited` | `size` with `allow_unlimited` (required there) | What `unlimited` renders as for this app, e.g. `"-1"`, `"0"`, `"none"`. Stored values are never numbers for unlimited |
| `true` / `false` | `bool` | The strings for true and false (default `true` / `false`) |
| `join` | lists, sets, person-entered env lists | Separator (default `,`) |
| `format` | structured values | `json`, `yaml` or `csv` |

Env, header and claim values are one line; headers are at most 1 KiB and
claims 4 KiB. Env values are single-quoted, so a value with `'`, `\` or a
newline is refused at save.

### Applies

| `applies` | Effect of a change |
|-----------|--------------------|
| `live` | A hook applied it; no restart. Needs a hook delivery (or a file with `on_membership_change: hook`) |
| `reload` | The template's `reload` action. Needs `reload` |
| `next_request` | Headers: each request reads the attributes file |
| `next_sign_in` | Claims: Keycloak reads them at sign-in |
| `restart` | The Hub restarts the instance |
| `account_creation` | Only new accounts get it; the panel warns "existing accounts keep their value" |

A save does the strongest effect of the changed options once (restart over
reload over nothing).

## files

Data files the Hub writes for file deliveries
([contracts §13.7](integration-contracts.md#137-data-files)).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `^[a-z][a-z0-9_-]{0,31}$`, unique | Yes | The file is `<mount>/<name>.json` (and `<name>.secrets.json` when it holds a secret option) |
| `service` | service | Yes | The compose service that reads it |
| `mount` | absolute, clean container directory (no `:`) | Yes | The Hub bind-mounts the file's directory here read-only (a directory, not a file: atomic renames give a new inode). It may not collide with another file's or a path option's target on the same service |
| `on_membership_change` | `restart`, `reload`, `hook`, `none` (default) | No | What happens when people joining or leaving change the file. `reload` needs `reload`; `hook` a hook with `membership_change` |

The data file is mode 0640 and the secrets file 0600, both owned by the
Hub's uid 10001: the reading service runs as root, or with
`group_add: ["10001"]` for the data file and `user: "10001"` for a secrets
file.

## hooks

Commands the Hub runs in the app's running containers with the desired
settings on standard input
([contracts §13.8](integration-contracts.md#138-hooks-and-reload)).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `^[a-z][a-z0-9_-]{0,31}$`, unique | Yes | Referenced by `{hook: <name>}` |
| `service` | service | Yes | Where it runs (a running container of this instance) |
| `command` | non-empty list of non-empty strings, no control characters | Yes | argv, run directly (never through `sh -c`) |
| `user` | string | No | User to run as (default: the container's) |
| `when` | list of `start`, `settings_change`, `membership_change` (at least one) | Yes | `start`: after every successful start; `settings_change`: after a save that changed its input; `membership_change`: after people joining or leaving changed its input. A hook whose last run failed runs again at its next trigger |
| `timeout` | Go duration, e.g. `60s` | No (default `30s`) | At most `10m` |

## reload

The template's reload action, at most one: `{service, signal}` (signal `HUP`,
`USR1` or `USR2`, sent to the service's running containers; applied when the
container still runs, and isn't unhealthy, 10 s later) or `{hook: <name>}` (a
declared hook). Not both. `applies: reload` and
`on_membership_change: reload` need it.

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
| `lan_only` | boolean | No | The port should be reachable only from the local networks; the Hub's doctor warns when it is bound to all interfaces or a public address ([§14.7](integration-contracts.md#147-local-networks-and-exposure)) |

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

Per-app environment variables. **Contract v3:** `env` entries with `generate: none` are refused. An admin-entered variable is a `settings` option (see above).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | env key | Yes | Variable name |
| `description` | non-empty string | Yes | What it is for |
| `generate` | `random` or `""` | No | `random`: the Hub generates 32 hex characters on first enable and writes them to the per-app `.env` |
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
| `client_id` | `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` | Yes | Keycloak client ID of the default instance. Other instances get `<instance-id>` (first entry) and `<instance-id>-<client_id>` (further entries); compose reads the id from `PORTCULLIS_OIDC_CLIENT_ID` / `PORTCULLIS_OIDC_CLIENT_ID_<KEY>`. Core clients such as `portcullis-forward-auth` are reserved |
| `secret_env` | env key | Yes | The `env` entry (with `generate: random`) holding the client secret |
| `name` | single line, non-empty | Yes | Display name in Keycloak |
| `redirect_uri` | URI | Exactly one of the two | A single redirect URI |
| `redirect_uris` | list of URIs (at least one) | Exactly one of the two | Several redirect URIs |
| `backchannel_logout_url` | `https://{{HOST_<ROUTER>}}/<path>` | No | The app's OIDC back-channel logout endpoint on one of its own hosts (`single` templates may use `https://<sub>.{{DOMAIN}}/<path>`). The Hub sets it as the client's back-channel logout URL with "session required" (logout tokens carry `sid`), so a Keycloak sign-out — the Hub signs users out when they leave a group — ends the app's session too. It follows hostname changes. The path must be routed without forward-auth (Keycloak posts to it server-to-server). Nextcloud uses it |
| `email_verified_claim` | boolean | No (default `true`) | `false`: the client gets the `email-unverified` scope instead of `email`, so tokens carry `email` but no `email_verified` claim. For apps that refuse `email_verified=false` but accept the claim being absent (Vaultwarden). The app must then not request the `email` scope |

Redirect URIs must match `^[a-z][a-z0-9+.-]*://\S+$`, so custom schemes such
as `app.immich:///oauth-callback` work. `{{DOMAIN}}` and `{{HOST_<ROUTER>}}`
are replaced; a `multi` template names its own hosts only as
`{{HOST_<ROUTER>}}` (e.g. `https://{{HOST_IMMICH}}/auth/login`).

The Hub tags each client with the **instance id** that owns it (the template
id for the default instance), and attaches the
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
    redirect_uri: "https://{{HOST_VAULTWARDEN}}/identity/connect/oidc-signin"
    name: Vaultwarden
    email_verified_claim: false
```

```yaml
keycloak_clients:
  - client_id: immich
    secret_env: IMMICH_OIDC_SECRET
    redirect_uris:
      - "https://{{HOST_IMMICH}}/auth/login"
      - "https://{{HOST_IMMICH}}/user-settings"
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
| `url` | `^https?://\S+$` | Yes | URL, with `{{DOMAIN}}` and `{{HOST_<ROUTER>}}` replaced. A `multi` template uses `{{HOST_<ROUTER>}}` for its own hosts |

```yaml
urls:
  - label: Vault
    url: "https://passwords.{{DOMAIN}}"
```

## tests.signin

How CI signs real users in to the app (`tests/e2e/app_signin.py` in the
templates repo, run by `test-apps.yml` after the app's shell test). The Hub
ignores `tests`. The test creates `e2eadmin` (access + admin group),
`e2emember` (access group) and `e2eoutsider` (no group), registers the
template's Keycloak clients and writes the group-gate policy as the Hub would,
and signs
each in through a setup link with a virtual security key. It passes when the
member is signed in (and not admin), the admin has admin rights and the
outsider is refused; a visible password field fails it unless `password`
explains it. CI runs **without the Hub**: the clients are plain Keycloak
clients, so the Hub's Keycloak access role
([`keycloak_access_role`](#auth)) is not applied there.

| Field | Type | Description |
|-------|------|-------------|
| `skip` | string | Why the app can't be signed into in CI. Only for `public`, `custom` and `mtls` apps; then nothing else is set |
| `path` | `^/` | Required otherwise. Page opened on the host; the setup link lands there |
| `host` | `{{HOST_<ROUTER>}}` | Host to sign in on (default: the host of the first `urls` entry) |
| `login` | list of Playwright selectors | The app's own SSO buttons, clicked when visible |
| `fill` | list of `{selector, value}` | Inputs filled before clicking |
| `signed_in` | check | Required otherwise. How to recognise the signed-in user |
| `admin` | check | Required when `auth.group_admin` is true. How to recognise admin rights |
| `password` | string | Why a password field on the app's pages is expected (a documented own login or break-glass) |
| `setup` | list of `{service, command, save_env, user}` or `{restart: true}` | Post-start steps an admin would do: run `command` in `service` (as `user`); with `save_env`, save the last output line as that env/setting and restart the app; `restart: true` restarts the app (a documented restart after the first start) |
| `expected_fail` | `{member, admin, outsider}: {reason, match, not_match}` | Known failures: reported, not fatal, only if the failure matches `match` and not `not_match` (regexes, case-insensitive), searched in that check's own evidence only: its detail, the pages its flow saw, and the app's container logs / `log_files` since its flow started. A flow the test broke (password field, Keycloak/enroll or browser error, never on the app) or an exception always fails; a marked check that passes fails the run. A `native-oidc` app that can't restrict sign-in by group itself (`group_access: false`, or `keycloak_access_role: true`) and lets outsiders in marks `outsider`: with the Hub its access role refuses them at Keycloak, but CI has no Hub and doesn't apply the role. `forward-auth` / `header-auth` apps never may. Never widen an app's access (e.g. auto-provisioning) to make a check pass: mark it |
| `refused_users` | list of usernames | Extra users in `access_group` and `admin_group` that must be refused with HTTP 403 (names the app reserves, e.g. CloudBeaver's `cbadmin-*`) |
| `log_files` | list of `{service, path}` | Files inside the app's containers, searched by `expected_fail.match` and kept as artifacts |
| `pause_between_users` | seconds | Wait between the users' sign-ins, for apps whose per-client rate limits CI's single client address would trip (Actual: 500 requests a minute) |
| `max_clicks` | integer | How often each `login` selector may be clicked per user (default 5; lower for apps that rate-limit logins, e.g. Actual) |
| `boot_timeout`, `timeout`, `refused_after` | seconds | Container readiness (600), per-user sign-in (240), how long the outsider is watched once on the app (45) |

A **check** is one of:

| Form | Passes when |
|------|-------------|
| `text: "{username}"` (+ `url: /path`) | the visible text contains it (case-insensitive) |
| `html: "{username}"` | the page source contains it |
| `json: {url, field, equals, contains, headers}` | `GET url` with the session's cookies answers JSON whose dotted `field` equals `equals` (default `{username}`) or is a list containing `contains` |
| `js: "<expression>"` (+ `equals`, `url`) | the expression, evaluated in the app's page (after opening `url`, if set; may return a promise), equals `equals` (default `{username}`) |
| `reach: /path` (+ `text`) | the path answers 2xx on the app host (and shows `text`) |

Plus `wait` (seconds to poll, default 10), `url_contains` and `absent` (text
that must not be on the page: the app's own denial, e.g. DokuWiki's
"Permission Denied" for a session without rights). Strings may use
`{username}`, `{email}`, `{access_group}` and `{admin_group}`.

```yaml
tests:
  signin:
    path: /
    signed_in:
      json: {url: /api/user, field: login}     # Grafana (group_admin: false: no admin check)
```

With admin rights mapped from `admin_group` (DokuWiki):

```yaml
tests:
  signin:
    path: /doku.php?do=login
    login: ["a:has-text('Portcullis')"]
    signed_in: {text: "{username}", absent: "Permission Denied"}
    admin: {reach: /doku.php?do=admin, text: "Access Control List"}
```

A known failure (Immich: native OIDC with no group restriction of its own;
with the Hub its Keycloak access role keeps outsiders out, but CI runs without
the Hub, so every test user gets in there):

```yaml
tests:
  signin:
    path: /auth/login
    signed_in:
      json: {url: /api/users/me, field: storageLabel}
    expected_fail:
      outsider:
        reason: "Immich has no OIDC group restriction of its own: only the Hub's Keycloak access role (keycloak_access_role) keeps outsiders out, and CI runs without the Hub (app_signin.py registers plain clients)"
        match: "e2eoutsider signed in"
```

## instances

**NEW (contract v2).** `instances: multi` lets the Hub run several fully
separate instances of the template, each with its own project, volumes,
settings, secrets, Keycloak clients, groups and hostnames
([Integration Contracts §3.1](integration-contracts.md#31-template-contract-v2-instances-and-hostname-variables-new-contract-v2)
and [§11](integration-contracts.md#11-app-instances-hub-new-instances)).
`single` (the default) means only the default instance, whose id is the
template id. Keep a template `single` only when it needs host-level uniqueness
(e.g. fixed host devices), and say why in `auth.notes`. Host ports are no
reason: they are per-instance settings.

```yaml
instances: multi
```

**Hostname variables.** Each hostname the template serves has one *host
router* (a rule with `Host()` alone; path-scoped routers on the same host reuse
its variable). The Hub sets `PORTCULLIS_HOST_<ROUTER>` to the instance's full
hostname for it; `<ROUTER>` is the template's original router name
upper-cased, with `-` and `.` turned into `_`. The default subdomain `<sub>` is
one DNS label (`^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`), and a template uses one
rule form for all its routers. Router rules use it with the default subdomain:

```yaml
traefik.http.routers.grafana.rule: Host(`${PORTCULLIS_HOST_GRAFANA:-grafana.portcullis.local}`)
traefik.http.routers.vaultwarden-admin.rule: Host(`${PORTCULLIS_HOST_VAULTWARDEN:-passwords.portcullis.local}`) && PathPrefix(`/admin`)
```

**Instance variables** the Hub sets for every instance (never declare them in
`env`, `settings` or `ports`; always use the default form with the default
instance's value):

| Variable | Value |
|----------|-------|
| `PORTCULLIS_INSTANCE` | Instance id (the template id for the default instance) |
| `PORTCULLIS_HOST_<ROUTER>` | Full hostname for host router `<router>` |
| `PORTCULLIS_OIDC_CLIENT_ID` | Keycloak client id of the first `keycloak_clients` entry |
| `PORTCULLIS_OIDC_CLIENT_ID_<KEY>` | Keycloak client id of each entry; `<KEY>` = its `client_id` upper-cased, `-`/`.` → `_` (two entries mapping to the same `<KEY>` are an error) |
| `PORTCULLIS_ACCESS_GROUP` | The instance's access group (`access_group` for the default instance, else `users_<id>`) |
| `PORTCULLIS_ADMIN_GROUP` | The instance's admin group (`admin_group` for the default instance, else `admin_<id>`) |

A `multi` template has no `${PORTCULLIS_DOMAIN}` in router rules (it may still
use it for core hosts such as `auth.${PORTCULLIS_DOMAIN:-portcullis.local}`),
no volume `name:` (the Hub sets `portcullis_<key>` for the default instance and
`portcullis_<instance-id>-<key>` for the others), and no hard-coded Keycloak
client id or group name in `compose.yml`. Routers that may serve
extra-domain hostnames list `portcullis-auth@docker` on the router itself,
never inside a chain middleware (the Hub swaps it for the extra-domain sign-in
there, and refuses extra-domain hostnames for a router whose own chain reaches
it).

### hosts.immutable

Host routers whose hostname is fixed once the instance exists, for apps that
bind their data to their own hostname (Synapse's `server_name` is part of
every user and room id):

```yaml
hosts:
  immutable: [matrix]   # host router names
```

The admin chooses the hostname when creating the instance; the Hub refuses
every later change (`409`), the default instance's too, and moving it means a
new instance. The default instance's immutable hosts start as
`<sub>.<main domain>` and are pinned on its first enable: a later main-domain
change never moves them (the instance shows as error until the old domain is
enrolled as an extra domain). A restore into a new id keeps the archive's
hostname for such routers
([contract §11.3, §11.6](integration-contracts.md#11-app-instances-hub-new-instances)).
`tests/validate.py` requires the list where it knows the app needs it
(`IMMUTABLE_HOSTS`: matrix).

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

- no variable is written twice across `env`, `ports` and the settings' env deliveries, and none shadows a core variable
- `links` (see [links](#links))
- every `secret_env` is an `env` entry with `generate: random`
- port `bind` values are IPs and `range` values are valid
- `config_files` sources exist
- `auth.native_login` only with `method: custom` and `sso: false`, and a `custom` app with `group_access: true` declares it

**Networks and volumes**

- Traefik-routed services use `networks: [default, portcullis-proxy]`, and internal services stay off `portcullis-proxy`
- `portcullis-proxy` is declared `external: true`, and no other networks are used
- volumes of `single` templates declare `name: portcullis_<volume>`, unique across templates and never external; volumes of `multi` templates declare no `name:` (**NEW**, contract v2)

**Variables**

- core variables use their default form, e.g. `${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}`
- instance variables (`PORTCULLIS_INSTANCE`, `PORTCULLIS_HOST_*`, `PORTCULLIS_OIDC_CLIENT_ID*`, `PORTCULLIS_ACCESS_GROUP`, `PORTCULLIS_ADMIN_GROUP`) use their default form with the default instance's value, the same default at every use, and are never declared in the manifest (**NEW**, contract v2)
- every other variable is declared in the manifest
- required `${VAR:?}` variables are `generate: random` env entries

**Services**

- no `ports:`, `build:`, `container_name:` or `env_file:`
- every image is pinned `tag@sha256:digest`, and floating tags (`latest`, `16-alpine`, ...) are rejected

**Bind mounts**

- only `./templates/<app-id>/<file>` (the file must exist) and `./certs/ca-bundle.crt:<path>:ro`
- never `./scripts/` or another template's files

**Routers**

- every router has a rule of the form `` Host(`${PORTCULLIS_HOST_<ROUTER>:-<sub>.portcullis.local}`) `` (**NEW**, contract v2), optionally `&& <path matchers>`, where `<ROUTER>` is the host router of that hostname; `single` templates may still use `` Host(`<sub>.${PORTCULLIS_DOMAIN:-portcullis.local}`) ``. No core subdomain
- each hostname has exactly one host router, no two host routers map to the same variable, and the template doesn't mix the two rule forms
- no router, service or middleware name contains `_` (**NEW**, contract v2)
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

**Instances** (**NEW**, contract v2; `instances: multi`)

- no `${PORTCULLIS_DOMAIN}` in any router rule
- every env value, `hostname:` or label that names one of the template's own hosts uses its `PORTCULLIS_HOST_<ROUTER>` variable (no `https://<sub>.${PORTCULLIS_DOMAIN…}` for its own subdomains)
- `urls` and redirect URIs name the template's own hosts only as `{{HOST_<ROUTER>}}`
- no hard-coded Keycloak client id or group name in `compose.yml` (use `PORTCULLIS_OIDC_CLIENT_ID*`, `PORTCULLIS_ACCESS_GROUP`, `PORTCULLIS_ADMIN_GROUP`)
- no router, service or middleware name starting with `portcullis-`, and no own paths under `/oauth2/`
- bind mounts of support files are read-only (`:ro`)

**Cross-template**

- no default subdomain or volume name is used by two templates

### Settings, files, hooks and reload

`check_settings` in `tests/validate.py` refuses what the Hub refuses when it
discovers the template, with the same messages (`setting <key>: …`). A
green Lint means the Hub lists the template. Besides the field rules above:

- **Options:** keys unique; `section` listed in `sections`; `label`,
  `description`, `scope` and `applies` valid; the type known (contract v2 and
  reserved types and fields refused); only the constraints the type takes;
  `default`, bounds, `step` and `group_values` valid values of the option.
- **Scope fields:** `privileged`, `self_visible`, `resolve`,
  `resolve_choices` and `group_values` only with `scope: person`, which needs
  a `default`; `admin_override` only with `person_entered`; no `default` for
  `group`; `unique` only for lists and person-entered `string` / `int`;
  `generate` only for secrets; `writes_as` only for paths; paths instance
  only.
- **Privileged:** `enum` or `bool` only, the default its lowest value, no
  `{{ACCESS_GROUP}}` preset.
- **`resolve`** fits the type; `group_values` keys are only
  `{{ACCESS_GROUP}}` / `{{ADMIN_GROUP}}` and the manifest declares that group.
- **`requires`:** instance options only, naming existing instance options,
  not itself.
- **Deliveries:** each one exactly one kind; at least one for every scope
  but instance; a per-person delivery for `person`; no per-person env;
  group env with `render.format: json`; `applies: live` with a hook (or a
  file with `on_membership_change: hook`); `applies: reload` and
  `on_membership_change: reload` with `reload`.
- **Env:** the name rules of [Deliveries](#deliveries); compose interpolates
  it and doesn't hard-code it; indexed env only for instance lists with
  `max_items` (≤ 64), covering every index compose references.
- **Claims:** `native-oidc`, a declared client, a name that isn't reserved,
  a `json_type` that fits the render, one option per claim and client.
- **Headers:** the name form, gated routers, every router to the backend's
  network namespace behind forward-auth, no identity-less method, no
  Traefik-labelled `network_mode: host` service, one option per header.
- **Files:** declared, `field` only for per-person scopes, one option per
  field; names unique, services in `compose.yml`, mounts absolute and clean,
  not colliding with another file or a path target on the same service.
- **Hooks:** names unique, services in `compose.yml`, a non-empty argv
  without control characters, valid `when`, `timeout` ≤ 10m.
- **Reload:** `{service, signal}` or `{hook}`, not both; the service or hook
  declared; signal `HUP`, `USR1` or `USR2`.
- **Person-entered:** the rules of [Person-entered options](#person-entered-options).
- **Render:** units, `integer`, `unlimited` (required with
  `allow_unlimited`), `true` / `false`, `join` and `format` fit the type;
  `yaml` / `csv` only on file and hook deliveries (never for a
  `person_entered` scalar); on an env delivery `true`, `false`,
  `unlimited` and `join` without `'` or `\`; a numeric `unlimited` no size
  within `min` / `max` renders as.
- **Values:** the `default` and every `group_values` value render through
  every delivery (the implicit `UPPER(key)` env included), and an env value
  holds no `'`, `\` or line break (JSON text: no `\"` escapes either).
- **Secrets:** `scope: instance` only; `generate.length` within `min_len` /
  `max_len`.
- **Shared folders, checks and gids:** the rules and every refusal are
  listed in
  [contracts §13.15](integration-contracts.md#1315-shared-folders-checks-and-lan-only-ports).
  In short: `folder` only on instance `path` options and never with `mode`,
  `needs` or `writes_as`; `runs_as` matches the service's compose `user:`;
  gids 60000–60999 (the folder groups) are refused wherever a gid comes
  from; on **every** service, the compose `user:` uid is a whole number, a
  user name or one reference, its gid a whole number or one reference, and
  each `group_add` entry a whole number, a group name or one reference,
  where a reference is exactly `$NAME`, `${NAME}`, `${NAME:-n}` or
  `${NAME-n}` naming an instance `int` option (no mixed text, nesting or
  `+` forms); YAML `!!binary` is refused anywhere.

The validator also warns when a service reads a secrets file but runs
neither as root nor as `user: "10001"`.

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
links:
  website: https://jellyfin.org/
  source: https://github.com/jellyfin/jellyfin

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
  sections: [Libraries]
  options:
    - key: movies_path
      label: Movies folder
      description: Host path to your movies library
      section: Libraries
      type: path
      mode: ro
      needs: read
      writes_as: {uid: 0, gid: 0}
      target:
        service: jellyfin
        mount: /data/movies
      applies: restart

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
links:
  website: https://pi-hole.net/
  source: https://github.com/pi-hole/pi-hole

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
