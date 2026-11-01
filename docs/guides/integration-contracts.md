# Integration Contracts

Portcullis is split across four repositories that meet at a few well-defined interfaces. This page is the **single source of truth** for those interfaces. Change it first, then change the repos on both sides.

| Repo | Role |
|------|------|
| `porelli/portcullis` (core) | Compose stack, `./portcullis` CLI, group-gate, enroll, socket proxies |
| `porelli/portcullis-hub` | Hub image (`ghcr.io/porelli/portcullis-hub`) |
| `porelli/portcullis-templates` | App templates (public; accepts outside contributions) |
| `porelli/portcullis-docs` | This site |

## 1. Versions and releases

- **Tags.** Every repo uses semver tags `vMAJOR.MINOR.PATCH`. A breaking change to any contract on this page bumps MAJOR in every repo it affects.
- **Hub image.** It is published as `X.Y.Z`, `X.Y`, `X` and `sha-<short>` for tags, and `edge` for `main`. Each release image is signed with cosign (keyless, GitHub OIDC) and carries SBOM and provenance attestations. There is **no `latest` tag**.
- **Core pins the Hub.** On core `main` the `HUB_IMAGE` default is `ghcr.io/porelli/portcullis-hub:edge`. A core **release** must pin a released Hub tag by digest, e.g. `ghcr.io/porelli/portcullis-hub:1.4.0@sha256:…`; `release.yml` refuses to publish otherwise (the tag must be a published Hub release that still resolves to that digest). Operators override it in `.env` and should pin tag + digest in production.
- **Core releases** carry a `CHANGELOG.md` section (Keep a Changelog) and a reproducible tarball with `VERSION` and its sha256; `portcullis version` reports the core version and the Hub image in use.
- **Core pins its own images.** Every image in core's `docker-compose.yml` is `tag@sha256:…`; core CI fails on an unpinned one.
- **Templates pin core.** The templates CI tests against the core ref in `.core-ref` in the templates repo: a tag, or `main` during development.
- **Templates pin their images.** Every template image is `tag@sha256:…` (enforced by `tests/validate.py`); Dependabot proposes updates.
- **Templates are versioned by tag.** The Hub tracks the source's default branch.
- **Current state.** No repository has a release tag yet: `HUB_IMAGE` defaults to `edge` and `.core-ref` is `main`.

## 2. Core environment variables available to templates

When a template's `compose.yml` references a variable, the Hub copies its value into the app's env from `/project/.env`. That file is **not** the core `.env`: core generates it as `secrets/hub/core.env` on every `./portcullis up`, with only the variables below, `PORTAL_DISPLAY_NAME`, the `HEADSCALE_*` / `HEADPLANE_*` / `NETBIRD_*` / `COTURN_*` variables, and any names the operator lists in `HUB_SHARED_ENV` (core secrets are refused). Templates may rely on:

| Variable | Meaning |
|----------|---------|
| `PORTCULLIS_DOMAIN` | Base domain; apps live at `<sub>.${PORTCULLIS_DOMAIN}` |
| `PORTCULLIS_PROXY_SUBNET` | Subnet of the `portcullis-proxy` network (default `172.31.250.0/24`) |
| `PORTCULLIS_PROXY_IP_RANGE` | Dynamic allocation range (default `172.31.250.128/25`) |
| `PORTCULLIS_TRAEFIK_IP` | Traefik's static IP on `portcullis-proxy` (default `172.31.250.2`). The **only** peer allowed to send identity headers |

Always use the default form, e.g. `${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}`. Any other required variable must be declared in the manifest's `env:` with `generate: random`. The Hub writes those into the per-app `.env`.

## 3. Template layout

- **Location.** One directory per app at the root of a template source repo: `<app-id>/manifest.yaml` and `<app-id>/compose.yml`. The `<app-id>` must match `^[a-z0-9][a-z0-9_-]{0,63}$`.
- **Manifest schema.** Manifests must validate against `schema/manifest.schema.json` in the templates repo (JSON Schema 2020-12). The Hub enforces the same rules and skips templates that fail.
- **Compose invocation.** The Hub runs `docker compose -p portcullis-<app-id> -f <template>/compose.yml [-f <data>/overrides/<app-id>.override.yml] [-f <data>/overrides/<app-id>.user.yml] --project-directory <core host path> --env-file <data>/env/<app-id>.env up -d --no-deps` (and `down --remove-orphans`; volumes are never removed). The template's `compose.yml` is read-only to the Hub. The second file is the Hub's override, regenerated from Settings before every `up`. The third is the operator's custom override (Hub Expert tab), stored outside the template clone; it is validated against the template and may not set `traefik.*` or `com.docker.compose.*` labels, `networks`, `network_mode`, `pid`/`ipc`/`uts`, `privileged`, `cap_add`, `devices`, `security_opt`, bind mounts outside `./templates/<app-id>/` and the bind roots (`HUB_OVERRIDE_BIND_ROOTS`, default `/srv:/mnt:/media`), unescaped `$` (compose interpolation) in any key or value, or YAML `!reset`/`!override` tags (full list in [Hub Management](../operations/hub.md#custom-override)). So everything this page derives from a template's labels (routes, subdomains, tiers, middlewares) comes from `compose.yml` and the Hub's override only.

- **Support files.** Files that ship with a template are bind-mounted as `./templates/<app-id>/<file>`. Compose resolves relative paths against the core checkout on the host. Before every `compose up`, the Hub copies the template directory to `<core>/templates/<app-id>/`; core mounts `./templates` read-write into the Hub at `/project/templates`.
- **Networks.** Frontends join the external network `portcullis-proxy`; internal services join only `default`. Volumes declare `name: portcullis_<name>`.
- **Middlewares.** Forward-auth and header-auth routers use `portcullis-auth@docker,portcullis-groups@docker`. Native-OIDC host-wide routers must not, nor may `mtls`, `custom` or `public` routers. For a `custom` template with `auth.native_login` the Hub's override sets every router's `middlewares` label: `portcullis-auth@docker,portcullis-groups@docker,<the template's own>` (Portcullis sign-in, the default) or the template's own without the pair ("own login only", only with `allow_without_gateway: true`; TLS tier `public@file`, no `groups` entry). The template is never edited.
- **Public exceptions.** A template may declare share-link paths in `auth.public_access` (`enabled_by_default`, `default_mode` `listed|all`, `token_pattern`, `credential_headers`, `credential_cookies`, `credential_query`, `static_extensions`, `service`, `paths[]` with `prefix` (optionally one whole `{token}` segment), `description`, `supporting`, `exact`, `broad` + `justification`); header-auth templates with it also declare `auth.identity_headers`. Fields and rules: [Manifest reference](manifest-reference.md#authpublic_access). The template never ships the public router: the Hub generates it (§5). Router and middleware names starting with `portcullis-public-` are reserved for the Hub.

## 4. Policy file (Hub → group-gate)

The Hub writes `group-gate-policy.json` atomically (temp file + rename) to the `hub_data` volume. group-gate mounts that volume read-only and re-reads the file on every request.

```json
{
  "version": 4,
  "default":  {"factors": ["mtls", "webauthn"], "op": "any"},
  "policies": {"<subdomain>": {"factors": ["mtls", "webauthn"], "op": "any|all"}},
  "groups":   {"<subdomain>": "<required LLDAP group>"},
  "path_groups": {
    "<subdomain>": [{"prefix": "/admin", "group": "<LLDAP group>"}]
  },
  "public_paths": {
    "<subdomain>": {
      "paths": [{"path": "/s/{token}", "match": "prefix"}, {"path": "/dist", "match": "static"}],
      "token_pattern": "^[A-Za-z0-9-]{1,32}$",
      "static_extensions": ["css", "js", "..."],
      "credential_headers": ["Authorization", "Proxy-Authorization"],
      "credential_cookies": ["nc_token"],
      "credential_query": []
    }
  },
  "expiring": [
    {"user": "jsmith", "group": "contractors", "at": "2027-03-31T23:59:59Z"}
  ]
}
```

- **`factors`** is a subset of `mtls` and `webauthn`; the Hub never writes anything else. There is no `password` factor (no password sign-in exists): group-gate treats it as an unknown factor and **denies** (fail closed). The Hub rewrites stored policies naming it on load, never into a weaker one (`all`: dropped; alternative or alone: `any of [mtls, webauthn]`). `op` is `any` or `all`, and is ignored when there is at most one factor. An empty factor list means public.
- **Unknown values fail closed.** An unknown factor, op or key shape, a file that exists but can't be parsed, or a `version` newer than group-gate supports (currently 4) makes group-gate deny the request.
- **Version 4** (**NEW**; the Hub always writes 4) adds the `expiring` array. group-gate serves **only** version 4. A group-gate that knows only version 3 denies every request on a version-4 file, so **the Hub and core must be upgraded together**.
    - **`expiring`**: an array of `{"user": "<lowercase username>", "group": "<LLDAP group>", "at": "<RFC 3339 UTC timestamp>"}` entries for temporary group memberships. group-gate treats the membership as **absent** once `now >= at`, regardless of what the user's token says. Usernames are lowercase; timestamps are RFC 3339 in UTC (e.g., `2027-03-31T23:59:59Z`).
    - The Hub writes every pending expiry into this array so that expiry enforcement is strict even while the Hub is down. On removal (whether by expiry, rule change, or explicit action), the Hub also revokes the user's Keycloak sessions so OIDC apps lose access at their next token refresh.
- **Keys are subdomains only.** group-gate looks everything up by the request's subdomain, so `policies`, `groups` and `path_groups` are keyed by the lowercase subdomains that **enabled** templates route — never by template ID, which could equal another app's subdomain.
- **Routing must be fully visible.** The Hub parses every `traefik.http.routers.*.rule` label in a template's compose file and only accepts literal `Host(\`<sub>.${PORTCULLIS_DOMAIN…}\`)` hosts. It rejects any template with `HostRegexp`/`HostHeader`/`HostSNI`, other domains, variables in the label, routers without a rule, TCP routers, or a rule branch that is not restricted by `Host()`. A host the Hub can't see would get no policy and no group (fail open).
- **`policies`** has an entry for each subdomain of an enabled template that has a per-app policy. Templates that inherit the default publish nothing; group-gate falls back to `default`. An override only names factors the app's auth method can enforce (the Hub refuses others with `400`: `mtls` apps only `mtls`, `custom`/`public` apps without Portcullis sign-in none); every app that runs group-gate can enforce both, so for those the default applies unchanged.
- **One owner per subdomain.** The Hub refuses to enable a template that routes a subdomain another enabled template already routes. If a collision still reaches the writer, it publishes the stricter policy (higher LoA, then `all` over `any`), merges path groups, keeps the group of the lowest template ID, and logs the collision.
- **`groups`** comes from enabled templates with `auth.group_access: true`: subdomain maps to `auth.access_group`. Not for a `custom` app switched to its own login only (its routers have no group-gate); the fail-closed snapshot records that (`native_login_only`).
- **Fail closed when a template goes missing.** At enable time the Hub stores each app's published config (subdomains, groups, admin paths, policy override) in its state. If an enabled app's template later stops loading, the Hub keeps publishing that last known config and reports it as drift. If there is no stored config, every subdomain the app's running containers route (or a running app project that isn't enabled) gets `groups[sub] = "__portcullis_deny__"`. group-gate matches groups exactly and nobody is in that group, so all requests are denied. Never create an LLDAP group with that name.
- **`path_groups`** comes from enabled templates that declare `auth.admin_paths` (a list of path prefixes). Each prefix requires `auth.admin_group`, **in addition** to the subdomain's group.
    - Matching uses group-gate's normalized `X-Forwarded-Uri` path: percent-decoded once, `//` collapsed, dot-segments resolved.
    - It is a prefix match on segment boundaries (`/admin` matches `/admin` and `/admin/x`, not `/administrator`). The longest matching prefix wins.
- **Core subdomains** (`auth`, `traefik`, `hub`, `directory`, `enroll`, `metrics`) are never taken from this file. `group-gate-map.conf` in core owns them.
    - `metrics` (Grafana of core's optional [monitoring](../operations/monitoring.md) profile) is a core subdomain too, in group-gate, the Hub (`policy.CoreSubdomains`) and the templates validator.
- **`public_paths`** is, per subdomain, the configuration of core's public guard (§5) for an enabled app whose public router exists:
    - `paths`: `{path, match}` patterns. `match` is `prefix` (segment boundary), `exact` or `static` (files below `path`: dot-free directories, a file name with one of `static_extensions`). One whole segment may be `{token}`, which matches one segment that `token_pattern` (anchored) accepts. Listed share tokens are published as `{token}`: tokens are secrets and stay in the Hub's `state.yaml`; Traefik's rule routes only the listed ones.
    - `credential_headers` (always including `Authorization` and `Proxy-Authorization`), `credential_cookies`, `credential_query`: credentials the guard refuses.
    - Any unknown key, malformed pattern or bad regex makes the guard deny. Missing-template snapshots keep publishing the entry (the containers keep their public router).
- **Older files.** A file without `version`, `groups`, `path_groups`, `public_paths` or `expiring` is valid and is treated as empty for the missing keys.

### 4.1 User attributes file (Hub → group-gate) — NEW

The Hub writes `user-attributes.json` atomically to the same directory as the policy file (`hub_data` volume). group-gate reads it on every request to populate attribute headers for apps. A missing or corrupt file results in no attribute headers being sent (never a deny).

**File format (version 1):**

```json
{
  "version": 1,
  "fields": {
    "department": "Department",
    "cost_center": "Cost-Center",
    "office_location": "Office-Location"
  },
  "users": {
    "jsmith": {
      "department": ["Engineering"],
      "cost_center": ["CC-1234"],
      "office_location": ["Milan"]
    },
    "alee": {
      "department": ["HR", "Operations"],
      "office_location": ["Berlin"]
    }
  }
}
```

- **`fields`**: maps each custom field name to its header name. The header name has each underscore-separated word capitalized (e.g., `cost_center` → `Cost-Center`). Only fields with the **ShareWithApps** flag are included.
- **`users`**: maps each lowercase username to their field values. Each field is an array of strings (even for single-valued fields). Users with no shared field values are omitted.
- **Written atomically** with mode `0644`, using temp file + rename, at the same time as the policy file.
- **Security:** group-gate returns these headers only on **allow** (after auth factors are satisfied). The `portcullis-groups` middleware forwards them downstream with `authResponseHeadersRegex: ^X-Forwarded-Attr-`. The `client-headers` middleware (on every core entrypoint) strips any `X-Forwarded-Attr-*` headers sent by the client, so clients can never forge attribute values.

## 5. Hub ⇄ Traefik

- **Proxy secret.** Traefik adds the header `X-Portcullis-Proxy-Secret: ${HUB_PROXY_SECRET}` to every request it routes to the Hub, using a `headers.customRequestHeaders` middleware on the Hub router.
    - The Hub rejects any request without a matching header, compared in constant time.
    - The only exception is `GET /healthz`.
    - `HUB_PROXY_SECRET` is generated by `portcullis init`, and the Hub refuses to start without it.
- **Identity headers.** Behind `portcullis-auth@docker,portcullis-groups@docker`, every backend (the Hub, enroll, header-auth apps) receives:
    - `X-Forwarded-User` and `X-Auth-Request-User`: the **immutable LLDAP username** (`preferred_username`; oauth2-proxy `userIDClaim`)
    - `X-Forwarded-Email` and `X-Auth-Request-Email`: the **user-editable** email (LLDAP lets users change it; Keycloak `trustEmail=false`)
    - `X-Auth-Request-Groups`: comma-separated groups

    Traefik guarantees these because each one is listed in the forward-auth middlewares' `authResponseHeaders`, so client copies are deleted. The Hub shows `X-Forwarded-User` as-is and never looks the signed-in user up in LDAP to identify them. Its LLDAP service account (§9) is used only for user and group management.
- **Attribute headers (NEW).** When custom user fields are defined (§9.6) and the **ShareWithApps** flag is enabled on a field, group-gate returns additional headers on **allow**:
    - **`X-Forwarded-Attr-<Header-Name>`**, where `<Header-Name>` is the field's name with each underscore-separated word capitalized (e.g., `cost_center` → `Cost-Center`).
    - **Values** are joined with `, ` (comma-space). Control characters (ASCII 0x00–0x1F and 0x7F) are stripped from each value. Each individual value is limited to **1 KB**; longer values are truncated.
    - group-gate reads field values from `user-attributes.json` (§4.1). A missing or corrupt file results in no attribute headers (never a deny).
    - The `portcullis-groups` middleware forwards these headers with `authResponseHeadersRegex: ^X-Forwarded-Attr-`.
    - The `client-headers` middleware strips any `X-Forwarded-Attr-*` headers sent by the client, preventing forgery.
- **Email is never an identity or linking key.** No repo may authorise, create, match or link accounts by email. Native-OIDC templates key accounts on `sub` / `preferred_username`.
- **Order.** On the Hub router, `hub-proxy-secret@docker` comes **after** `portcullis-auth@docker,portcullis-groups@docker`, so the secret is never sent to oauth2-proxy or group-gate.
- **TLS tier per host.** Traefik selects TLS options per SNI host, so every router of a host must carry the same `tls.options`; on a mismatch Traefik uses its default options and answers `421 Misdirected Request`. The Hub writes one tier for all routers of an app: `public@file`, `authaware@file` or `protected@file` from the app's **effective** policy (its override or the default, intersected with what its method can enforce: an `mtls` app always gets `protected@file`, an app that handles its own sign-in `public@file`), except that `protected@file` becomes `authaware@file` for **all** of the app's routers while its public router exists (`policy.HostTier`).
- **Public router.** When an app's public exceptions are on and open at least one path, the Hub's override adds, on the `public_access.service` (default: the only routed service):
    - `traefik.http.routers.portcullis-public-<app>`: rule `` Host(`<host>`) && (<entries>) `` over the app's hosts on that service. Entries: `` Path(`p`) || PathPrefix(`p/`) `` for prefixes (and each listed `{token}` expansion), `` Path(`p`) `` for `exact` paths, and for other supporting paths `` PathRegexp(`^p(/[A-Za-z0-9_~@+-]+)*/[A-Za-z0-9_~@+-][A-Za-z0-9._~@+-]*\.(<static extensions>)$`) `` (written with compose's `$$`). Then `entrypoints: websecure`, the host's tier, a priority above every router of the app (explicit priorities, and rule length plus 253 per `${…}` for implicit ones), the service's single Traefik service;
    - middlewares `portcullis-public-guard@docker,portcullis-public-strip-<app>@docker,rate-limit@file,security-headers@file` (`rate-limit` and `security-headers` come from core's `traefik/dynamic/middlewares.yml`). No `portcullis-auth`, no `portcullis-groups`;
    - `traefik.http.middlewares.portcullis-public-strip-<app>.headers.customrequestheaders.<H>: ""` for each core identity header (`X-Forwarded-User`, `X-Forwarded-Email`, `X-Forwarded-Groups`, `X-Forwarded-Preferred-Username`, `X-Forwarded-Access-Token`, `X-Auth-Request-User`, `-Email`, `-Groups`, `-Preferred-Username`, `-Access-Token`, `Remote-User`, `-Email`, `-Groups`, `-Name`), `Authorization`, `Proxy-Authorization`, each `auth.identity_headers` and `public_access.credential_headers` entry, each also with `_` for `-`. Without forward-auth nothing else deletes client copies; core's entrypoints also drop alias headers (`aliasHeadersStrategy=delete`).
- **Public guard (core).** `portcullis-public-guard@docker` is a forwardAuth middleware defined on group-gate (`http://group-gate:8080/public-guard`, no `authResponseHeaders`). It runs first, so it sees the request before the strip middleware. It answers 403 (no redirect) unless:
    - the policy file is version 3 and has a `public_paths` entry for the request's subdomain (never a core subdomain);
    - `X-Forwarded-Uri` has no `#`, no encoded `/`, `\`, NUL or `#` in the path, and every normalised form of the path (decoded once, `//` collapsed, dot-segments resolved; as for `path_groups`) is inside a published pattern;
    - no request header is a credential header (case-insensitive, `_` read as `-`);
    - no cookie (every `Cookie` header, split on `;` and `,`) and no query key (everything after the first `?`, split on `&` and `;`) names a credential. Names are compared case-insensitively after PHP's mangling (php-src `main/php_variables.c`, `php_register_variable_ex`: leading spaces dropped, ` ` and `.` become `_`, `name[…]` is `name`, an unclosed `[` becomes `_`, NUL ends the name), both raw and percent- / `+`-decoded; a name that isn't valid UTF-8 after decoding (overlong forms) or has control characters is refused.

    On allow it returns 200 without identity headers. Its logs mask token-like path segments and show query parameter names only.
- **Exposure drift.** The Hub compares every exposure label of each running container (each router's `tls.options`, all `portcullis-public-<app>` router labels and the strip middleware, and every router's `middlewares` of `native_login` apps) with what it would render now, `PORTCULLIS_DOMAIN` expanded; any difference is `public_access_mismatch` drift.

### 5.1 People subdomain (NEW)

- **`people.<domain>`** is a new core subdomain that routes to the Hub's directory UI/API. It is accessible to **any signed-in user** (not just administrators).
- **Hub listener.** The Hub serves a second HTTP listener on port **8889** (configurable via `HUB_PEOPLE_ADDR`, default `:8889`). This listener serves only the directory UI and API (Users, Groups, Org chart, Import), with per-request permission checks. App, policy, drift, compose and Docker endpoints are **not** registered on this listener.
- **Core routing.** Core routes `people.<domain>` to `http://hub:8889` with the same middlewares as the admin Hub: `client-headers`, `portcullis-auth`, `portcullis-groups`, `hub-proxy-secret`, `security-headers`. The same `X-Portcullis-Proxy-Secret` header is required.
- **group-gate-map.conf.** The map file uses the special value **`*`** (asterisk) for the `people` subdomain, meaning "any signed-in user". This value is valid **only** in `group-gate-map.conf`, never in the policy file.
- **Redirect.** The existing `directory.<domain>` subdomain redirects to `https://people.<domain>/` (previously it redirected to `https://hub.<domain>/#users`).

## 6. Docker access

Neither Traefik nor the Hub mounts `/var/run/docker.sock` directly. Each gets its own socket proxy, on its own internal network:

| Client | Proxy endpoint | Allowed |
|--------|----------------|---------|
| Traefik | `tcp://socket-proxy-traefik:2375` | read-only (`POST=0`): containers, networks, events, version, ping |
| Hub | `tcp://socket-proxy-hub:2375` | containers, images, networks, volumes, exec, events, info, version, ping, logs, plus POST/PUT/DELETE. No build, commit, swarm, nodes, services, tasks, plugins, secrets, configs, system (df/prune), auth, distribution or session |

The Hub reads `DOCKER_HOST` for both the `docker compose` CLI (only `up`/`down`) and its own Engine API calls (status, logs, exec, events). Core CI checks that only the two proxies mount the socket and that each proxy network has exactly its two members. See [Security & Hardening](../operations/hardening.md#docker-socket-proxies).

## 7. Docs ⇄ templates

- **Generator.** `scripts/generate-app-docs.py` in the docs repo reads every `<app-id>/manifest.yaml` and writes `docs/apps/*.md` plus `docs/apps/.nav.yml`.
- **Triggers.**
    - On push to `main`, the templates repo sends a `repository_dispatch` event (`templates-updated`) to the docs repo, which rebuilds the site. This needs the `DOCS_DISPATCH_TOKEN` secret in the templates repo.
    - The docs repo also rebuilds daily as a fallback.

## 8. Keycloak clients (core ⇄ Hub ⇄ templates)

- **Client scopes core provides.** `./portcullis keycloak configure` keeps these realm client scopes in place (idempotent):
    - `acr` (with an `amr` mapper) and `groups` (claim `groups`, plain group names).
    - `email-unverified`: protocol `openid-connect`, included in the token `scope`, with exactly **one** mapper, `email` (user property `email` → claim `email` in the ID token, access token, userinfo and introspection). It has **no** `email_verified` mapper; any other mapper on the scope is deleted on the next run.
- **What the Hub attaches.** A client the Hub creates for a template's `keycloak_clients[]` entry gets the default client scopes `profile`, `acr`, `groups` and exactly one of the two email scopes; on reconcile the Hub re-attaches `acr`, `groups` and that email scope if they are missing:
    - `email` (the default): tokens carry `email` and `email_verified: false`, because LLDAP email is user-editable and the LDAP federation has `trustEmail=false`.
    - `email-unverified`, when the entry sets `email_verified_claim: false`: tokens carry `email` and no `email_verified` claim.

    On create and on every reconcile (enable, ACR push), the Hub attaches the wanted one first, then detaches the other one from the client's default **and** optional scopes. It does this only for clients it may reconcile (owner tag, or an untagged client that points only at the template's hosts; see [Hub → Keycloak clients](../operations/hub.md#keycloak-clients)). If the realm has no `email-unverified` scope, the Hub reports an error and leaves the client's `email` scope attached.
- **What the template must do.** An app with `email_verified_claim: false` must not request the `email` scope: Keycloak answers `invalid_scope` to a requested scope the client doesn't have. `email-unverified` is a default scope, so the email claim arrives without being requested. `tests/validate.py` rejects `*SCOPE*` environment values that contain `email` for such templates.
- **Use it only for apps that refuse `email_verified=false` but accept it absent** (Vaultwarden SSO signups). The email is exactly as unverified as before: identity stays `sub` / `preferred_username` (§5), and the app must still never link accounts by email.

## 9. Hub ⇄ LLDAP (users & groups)

Day-to-day user administration happens in the Hub's **Users & Groups** tab. The Hub is already behind forward-auth, `lldap_admin` and WebAuthn step-up; LLDAP's own web UI (0.6.3) has a separate login and no SSO or header auth. It stays available as a fallback.

### 9.1 Service account (core provides)

- **Account.** Core creates an LLDAP user `portcullis-hub`, makes it a member of `lldap_admin`, and gives it a random password (≥ 32 characters). It keeps the account in place idempotently on every `./portcullis up`: create it if missing, re-add it to `lldap_admin`, and reset the password if the files and LLDAP disagree.
- **Credentials are files, never env vars.** Core mounts them read-only into the Hub as `/run/portcullis/lldap/username` and `/run/portcullis/lldap/password`, owned by group 10001 with mode 0640 (directory 0750). The Hub reads them on every LLDAP login, so a rotated password needs no restart. One trailing newline is ignored.
- **Hub configuration.**

    | Env var (Hub) | Default | Meaning |
    |---|---|---|
    | `HUB_LLDAP_CREDENTIALS_DIR` | `/run/portcullis/lldap` | directory with `username` and `password` |
    | `LLDAP_HTTP_URL` | `http://lldap:17170` | LLDAP HTTP API |
    | `LLDAP_LDAP_URL` | `ldap://lldap:3890` | LLDAP LDAP, used **only** to set passwords (`ldaps://` also accepted) |
    | `LLDAP_BASE_DN` | `dc=portcullis,dc=local` | must equal LLDAP's `LLDAP_LDAP_BASE_DN` (core: `${LLDAP_BASE_DN}`) |

- **Not configured.** If the files are missing, empty, or the username isn't a valid username, the Users & Groups tab shows "user management is disabled" and why. Every `/api/directory` mutation answers 503, and the rest of the Hub works as before.
- **Network.** The Hub reaches `lldap:17170` and `lldap:3890` on the `portcullis` network, the same way Keycloak's LDAP federation and enroll do.
- **Why `lldap_admin`.** LLDAP 0.6.3's narrower `lldap_password_manager` can only change passwords of non-admins: `createUser`, `createGroup`, `addUserToGroup`, `deleteUser` and the other GraphQL mutations go through `get_admin_handler`, which requires `Permission::Admin` (`crates/graphql-server/src/mutation/mod.rs`, `crates/access-control/src/lib.rs`).
- **Contained.** The account can never sign in through the gateway: Keycloak's LDAP federation has the user filter `(!(uid=portcullis-hub))`, so it is never imported (`keycloak configure` also deletes a copy imported earlier), and group-gate denies the username `portcullis-hub` on every endpoint (`GATE_DENY_USERS`).
- **Why this is acceptable.** `lldap_admin` can put anyone into `lldap_admin`. The Hub could already start arbitrary containers through its socket proxy (§6), so it is host-root-equivalent anyway. Every change it makes is attributed to the signed-in admin and audited (§9.5).

### 9.2 What the Hub calls

- **Login.** `POST /auth/simple/login` `{"username","password"}` returns `{token, refreshToken}`. The JWT is cached until one minute before its `exp`. On expiry or on a `401`, the Hub tries `GET /auth/refresh` with the `Refresh-Token` header first, then logs in again.
- **GraphQL** (`POST /api/graphql`, `Authorization: Bearer <jwt>`). The Hub uses only these operations: `users { id email displayName creationDate groups { id displayName } }`, `groups { id displayName creationDate users { id } }`, `createUser`, `updateUser` (email, displayName), `deleteUser`, `createGroup`, `deleteGroup`, `addUserToGroup`, `removeUserFromGroup`.
- **Passwords: LDAP Password Modify (RFC 3062), not HTTP.** LLDAP stores passwords with OPAQUE. Its HTTP endpoints (`/auth/opaque/register/start|finish`) expect the *client* half of the OPAQUE registration (ristretto255 + argon2), which the Go standard library can't do. LLDAP 0.6.3 has no GraphQL password mutation. Its LDAP server, however, implements the Password Modify extended operation (`1.3.6.1.4.1.4203.1.11.1`) and runs the OPAQUE registration server-side (`crates/ldap/src/password.rs`; `lldap_admin` may change any password). So the Hub:
    1. simple-binds as `uid=portcullis-hub,ou=people,<base DN>`;
    2. sends `userIdentity = uid=<user>,ou=people,<base DN>` and `newPasswd`;
    3. unbinds.

    The password crosses the internal `portcullis` network in clear text, like Keycloak's and enroll's LDAP binds today. Core may switch to LDAPS by setting `LLDAP_LDAP_URL=ldaps://…`.

### 9.3 Keycloak side

- LDAP users are imported into Keycloak lazily. The Hub uses its existing Keycloak admin credentials (`KEYCLOAK_ADMIN`, `KEYCLOAK_ADMIN_PASSWORD`) and imports a user explicitly with `GET /admin/realms/portcullis/users?username=<u>&exact=true`, which makes the LDAP federation import the user.
- **Status shown.** The Hub shows whether a user is imported, their WebAuthn credential count (`webauthn` + `webauthn-passwordless`) and their pending required actions. It doesn't show client certificates: they live in Vault/enroll, not in Keycloak.
- **Status lookups.** The Hub lists users (`GET …/users?max=1000&briefRepresentation=false`) and the realm's LDAP provider (`GET …/components?type=org.keycloak.storage.UserStorageProvider`, `providerId` `ldap`), then reads `GET …/users/{id}/credentials` per user. A failed credentials lookup marks only that user.
- **Stale records.** A Keycloak user whose `federationLink` is the LDAP provider but whose username isn't in LLDAP is listed as stale. The Hub deletes such a copy by id only on an explicit, confirmed request. Never for `admin`, the service account, users LLDAP has, or Keycloak-local users.
- **Remove passkeys.** Deletes every WebAuthn credential, signs the user out (`POST …/users/{id}/logout`), then either requests a new invite (§9.4) or, for password users, adds `webauthn-register-passwordless`.
- **Password reset.** Signs the user out of Keycloak.
- **Delete.** The Hub deletes the user in LLDAP, then deletes the Keycloak copy by id. The federation is `READ_ONLY`, so this never writes to LDAP.
- **No other changes.** The Hub doesn't touch the federation's settings or mappers.

### 9.4 One-time invites (core provides)

New users are onboarded **without a password**. The admin creates the user in the Hub and gets a one-time link. The user opens it, registers their security key, and is signed in. There are no other manual steps.

- **Endpoint.** Core (enroll) serves `POST /internal/invites` on a listener that Traefik does **not** route: `http://enroll:8444`, the `portcullis` network only.
    - Hub configuration: `HUB_INVITE_API_URL` (default `http://enroll:8444/internal/invites`).
    - Shared secret: a file of ≥ 32 characters, mounted read-only into both containers. In the Hub it is at `HUB_INVITE_SECRET_FILE` (default `/run/portcullis/invite/secret`, group 10001, 0640). Never an env var. Core keeps it in `secrets/enroll/invite-api-secret` (enroll) and `secrets/hub/invite/secret` (Hub), generated by `./portcullis up`.
- **Request.** `Authorization: Bearer <secret>`, `Content-Type: application/json`, body `{"username": "<lldap user id>"}`.
- **Response.** `201` with `{"url": "https://enroll.<domain>/invite/<token>", "expires_at": "<RFC 3339>"}`. The Hub accepts only `https` URLs with a host and no userinfo, and requires `expires_at`.
- **Errors.** Non-2xx with an optional `{"error": "<message>"}`, which the Hub shows to the admin (truncated to 200 characters). Suggested codes:
    - `401`/`403`: wrong secret;
    - `404`: no such LLDAP user;
    - `409`: refused, e.g. a protected account.
- **Semantics (core).**
    - The token is random (256 bit), stored only as a hash, single-use and expires after 72 h. Invites live in enroll's memory: restarting enroll invalidates pending ones (issue a new invite).
    - Creating an invite revokes the user's earlier unredeemed invites. A user who already has keys gets one more (core's login theme gives every new passkey a unique label); to replace lost keys, delete them first (the Hub's "Reset passkeys", or `./portcullis invite <user> --replace-keys`).
    - Opening the link (`GET`) does not use it; the page's same-origin `POST` does. Redeeming adds `webauthn-register-passwordless` to the Keycloak user (enroll's service account `portcullis-enroll`), signs the user in through the hidden Keycloak identity provider `portcullis-invite` (first login links the existing LLDAP user, never creates one), requires the passkey registration, and lands on `https://<domain>/` (the portal). The session has `acr=hwk`, `amr=[hwk]`.
    - Core's API refuses (`409`) `portcullis-hub`, `admin` and **every member** of `lldap_admin`, `lldap_password_manager`, the groups of the core subdomains in `group-gate-map.conf` and `INVITE_PROTECTED_GROUPS`: an invite hands the account to whoever holds the link, so the API secret must not be a way to take over an administrator. It looks the groups up in LLDAP and fails closed (`503`) when it can't. For invites made through this API the check is repeated when the link is redeemed and again in the identity-provider steps (authorization code, token): a user added to a protected group after the invite was created gets a "no longer usable" page, and their pending API invites are cancelled. Administrators are invited / recovered only from the server (`./portcullis invite <user>`, a loopback listener reached through `docker exec`), never through the Hub.
    - Sign-in has no password: the browser flow is passkey / client cert only. A password set through the Hub's fallback works for LLDAP's own UI and LDAP-binding apps, not for Keycloak.
- **What the Hub does.**
    - **New user (invite mode, the default).** LLDAP `createUser` with no password, group memberships, pre-import into Keycloak, then `POST /internal/invites`. The Hub sets **no** required action: the invite registers the key. If the invite secret is missing, the Hub refuses invite-mode creation before creating anything.
    - **"Send new invite"** on any user except `portcullis-hub`, `admin` and administrators.
    - **"Reset passkeys".** Removes the passkeys (§9.3), then sends a new invite (administrators: none, see below).
    - **Administrators.** The Hub computes the same administrator set as core: `lldap_admin`, `lldap_password_manager`, `INVITE_PROTECTED_GROUPS` (Hub env, same value as enroll's), and the groups of the core subdomains in `group-gate-map.conf` (Hub: `HUB_GATE_MAP_FILE`, default `$PROJECT_DIR/group-gate/group-gate-map.conf`, re-read on use).
        - It never sends invite requests for administrators. "Reset passkeys" for them skips the invite and checks this before removing anything.
        - A new user created into an administrator group is created without an invite. The Hub shows `./portcullis invite <user>` instead.
        - A `409` from core is shown as "administrators are recovered from the server: `./portcullis invite <user>`", prefixed with core's `error` text if any.
    - **Never stored.** The link is shown to the admin once (copy button). The Hub doesn't store it, log it or put it in the audit log.
- **Password fallback.** Off by default, under "Advanced". The Hub generates a 26-character random password, shown once, or the admin types one (12 to 256 characters). Optionally it adds `webauthn-register-passwordless`. The same fallback exists as "Password…" on existing users.

### 9.5 Guardrails and audit (Hub)

- **Protected accounts.** `portcullis-hub` (the account named in the `username` file) and `admin` (core's `LLDAP_LDAP_USER_DN`; Keycloak's federation and enroll bind as it with `LLDAP_ADMIN_PASSWORD`) can't be changed through the Hub at all: no delete, edit, password, invite, passkey action or group change. An invite or passkey reset for `admin` would hand the root account to whoever gets the link, so the bootstrap admin is recovered from the server only (`./portcullis invite admin`). The Hub's tests check that every user-targeting operation refuses both accounts.
- **Another administrator.** An invite, a passkey reset or a password for **another** `lldap_admin` member hands the acting admin that account. Core refuses invites for administrators (§9.4): the Hub doesn't offer them and shows "administrators are recovered from the server: `./portcullis invite <user>`". A passkey reset or a password for another administrator is allowed only with the target's username typed again (`{"confirm": "<username>"}`; without it the Hub answers `400`), and the audit entry carries `target_is_lldap_admin=true`.
- **Reserved names.** `admin` and `portcullis-hub` can't be created. Usernames must match `^[a-z0-9][a-z0-9._-]{0,63}$`, stricter than LLDAP, because they end up in DNs and URLs. Group names must match `^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`, must not start with `lldap_`, and must not duplicate an existing group (case-insensitive). LLDAP's built-in groups can't be deleted.
- **Self-protection.** You can't delete yourself (`X-Forwarded-User`) or remove yourself from `lldap_admin`.
- **Last admin.** The last remaining human `lldap_admin` member (every member except `portcullis-hub`) can't be deleted or removed from `lldap_admin`.
- **Confirmation.** Deleting a user or a group and removing passkeys require the name typed again (`{"confirm": "<name>"}`).
- **Request guards.** Mutations are POST/PUT/DELETE under `/api/directory/`, behind the proxy secret (§5) and the CSRF guard (same origin, JSON body). Mutations without `X-Forwarded-User` are refused (403). Checks and changes are serialised.
- **Audit.** Every mutation, including refused and failed ones, is appended to `$HUB_DATA_DIR/audit.jsonl` (mode 0600) as one JSON object per line:

    ```json
    {"time","actor","action","target","detail","result","error"}
    ```

    `result` is `ok`, `refused` or `error`. The log never contains passwords, tokens or invite links. `GET /api/directory/audit` and the UI show the last 100 entries.

### 9.6 Custom fields and delegated permissions (NEW)

Portcullis now supports **custom user fields** (e.g., department, manager, cost center), **rule-based groups** (membership computed from field values), and **delegated permissions** (allowing non-admins to manage people).

#### Custom fields

- **Storage.** Custom fields are LLDAP user attributes created by the Hub using LLDAP's schema API (`addUserAttribute`). Each field has:
    - **Type:** `STRING` (LLDAP 0.6.3 limitation)
    - **Flags:** `visible=true`, `editable=false` (users cannot edit their own fields through LLDAP's UI)
- **Field types** (Hub-managed):
    - **Free text:** arbitrary string values
    - **List:** predefined values the admin maintains
    - **Person:** references another user by username (e.g., manager field for org charts)
- **Field flags** (per field):
    - **ShareWithApps** (default **on**): field values are sent to apps as OIDC claims and identity headers (§4.1, §5)
    - **Admin-only:** only administrators may edit this field (security rule: see below)
- **Visibility.** Everyone signed in can see everyone's field values and the org chart.

**Example field definitions in directory.yaml:**

```yaml
fields:
  - name: department
    type: list
    share_with_apps: true
    admin_only: false
    list_values:
      - Engineering
      - HR
      - Operations
  - name: manager
    type: person
    share_with_apps: true
    admin_only: false
  - name: security_clearance
    type: list
    share_with_apps: false
    admin_only: true
    list_values:
      - Public
      - Confidential
      - Secret
```

#### Rule-based groups

- **Group types.** A group is either **manual** (membership managed by hand) or **rule-based** (membership computed from field values by the Hub).
- **Rules.** A rule combines conditions with all/any blocks (nestable). Conditions: `is`, `is not`, `is one of`, `is empty`, and for person fields, `reports to (directly or indirectly)`.
- **Exceptions.** On a rule-based group, a person can be **added** (although they don't match) or **kept out** (although they match). Every exception requires a written **reason**, which is stored and shown.
- **Expiry.** Any membership (exceptions, and members of manual groups too) can have an **expiry date/time**. When a membership expires, the person is removed automatically, and the Hub writes the expiry into the policy file's `expiring` array (§4) so group-gate enforces it strictly.
- **Reconciliation.** The Hub writes computed membership into the real LLDAP groups. group-gate, Keycloak and apps treat rule-based groups exactly like manual groups. Re-evaluation happens on every detail change, rule change, import, exception change, and periodically (at least every minute) for expiries.
- **Audit.** Every membership change from rules, expiry or import is audited with its cause.

**Example rule (conceptual; stored in directory.yaml):**

```yaml
groups:
  - name: nextcloud_milan
    type: rule
    rule:
      all:
        - field: office_location
          op: is
          value: Milan
        - field: department
          op: is_one_of
          values: [Engineering, Operations]
    exceptions:
      - user: jsmith
        mode: added
        reason: "Contractor working with Milan team"
        added_by: admin
        added_at: "2026-11-01T10:00:00Z"
```

#### Hub-private state: directory.yaml

The Hub stores field definitions, rules, exceptions, expiries and permission grants in `directory.yaml` under `$HUB_DATA_DIR`. This file is:

- **Atomic** (like `state.yaml`): corrupt file = refuse to start.
- **Never exposed** to clients or other repos.
- **LLDAP holds only:** user attribute schemas (name, type, flags) and current values; group membership (reconciled by the Hub for rule-based groups).

#### Delegated permissions

Three permissions can be granted to groups (manual or rule-based):

1. **`edit_details`**: edit user fields, bulk import (CSV review + apply)
2. **`invite`**: create new users via invite link (with no group memberships)
3. **`remove`**: delete users

- **Grants.** Each permission is granted to an LLDAP group the admin picks. Members of that group (non-admins) get the permission. Admins always have all permissions.
- **Scope.** Delegation is global for now (all users, subject to the constraints below). Scoped delegation (e.g., "HR Milan edits only Milan people") is a non-goal for this release.
- **Protected targets.** Delegates may **never** target:
    - Themselves (`X-Forwarded-User`)
    - The service account (`portcullis-hub`)
    - The bootstrap `admin`
    - Any member of `lldap_admin`, `lldap_password_manager`, `INVITE_PROTECTED_GROUPS`, or the core-subdomain groups in `group-gate-map.conf`
    - Any member of a permission group
- **Delegate invite constraints:**
    - A delegate's invite creates a user with **no groups** and **no password**. The new account is marked `created_by: <delegate username>`.
    - With `edit_details`, delegates can fill in fields, making the person match rules. This is visible: the audit records the inviter, and rule memberships show "via rule, account created by X".
    - Delegates can **re-invite** (send a new invite link) only accounts they created (`created_by` matches) that still have **zero Keycloak credentials** (no passkeys, no password). An admin taking over an account (setting a password, resetting passkeys, or sending an invite) clears `created_by`, so delegates can no longer re-invite it.
- **Manual groups, exceptions, expiries.** Delegates may not modify membership of manual groups, add exceptions, or set expiries. These are admin-only.
- **Security rules:**
    - Rules of **protected groups** (`lldap_admin`, `lldap_password_manager`, `INVITE_PROTECTED_GROUPS`, core-subdomain groups), **permission groups**, and **app admin groups** (`admin_group`, `path_groups` admin access) may only reference **admin-only** fields. A field used by such a rule cannot lose its admin-only flag.
    - Built-in groups (`lldap_admin`, `lldap_password_manager`, `INVITE_PROTECTED_GROUPS`, core-subdomain groups) can never be rule-based.

**Example permissions in directory.yaml:**

```yaml
permissions:
  edit_details:
    granted_to: hr_team
  invite:
    granted_to: hr_team
  remove:
    granted_to: hr_managers
```

#### Fields reach apps

- **Native-OIDC apps:** The Hub creates a Keycloak client scope `portcullis-attributes` with LDAP attribute mappers and protocol mappers for each shared field. Each field becomes a claim `attr_<field>` (e.g., `attr_department`). The scope is optionally a default scope on Hub-registered clients.
- **Forward-auth and header-auth apps:** The Hub writes `user-attributes.json` (§4.1); group-gate returns `X-Forwarded-Attr-<Header-Name>` headers (§5); the `portcullis-groups` middleware forwards them.

## 10. Landing portal app list (Hub → core)

- **File.** The Hub writes `portal-apps.json` atomically into `hub_data` (`/data`, next to `group-gate-policy.json`, mode 0644) whenever it writes the policy file (enable, disable, template sync, settings). A core landing portal reads it like group-gate reads the policy file: mount `hub_data` read-only.
- **Endpoint.** `GET /api/portal/apps` returns the same document, behind the proxy secret like every other Hub route.
- **Format, version 1.**

    ```json
    {
      "version": 1,
      "apps": [
        {
          "id": "immich",
          "name": "Immich",
          "description": "…",
          "icon": "📷",
          "category": "media",
          "urls": [{"label": "Photos", "url": "https://photos.example.org"}],
          "auth_method": "native-oidc",
          "access_group": "users_immich",
          "admin_group": "admin_immich"
        }
      ]
    }
    ```

    - Only enabled apps whose template is present are listed, sorted by `id`.
    - `{{DOMAIN}}` in URLs is already expanded.
    - `access_group` is the group group-gate requires (`auth.group_access`); `""` means any signed-in user.
    - `admin_group` is informational.
- **Rendering.** The portal filters by the signed-in user's groups (`X-Auth-Request-Groups`) and must escape every field. An unknown `version` means: show nothing.
- **Core's portal** is group-gate's `/portal` at `https://<domain>/` (router `portal`: forward-auth, then `replacePath`). It reads `/hub-data/portal-apps.json`, shows only `https` URLs on the domain, and adds the Hub, the Keycloak realm console, enrollment, LLDAP and Traefik for `lldap_admin`, plus every user's passkeys (account console) and certificate (`enroll.<domain>/self`).
