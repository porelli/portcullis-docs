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
| `PORTCULLIS_DOMAIN` | Main (base) domain. Core hosts live at `<sub>.${PORTCULLIS_DOMAIN}` (e.g. Keycloak at `auth.${PORTCULLIS_DOMAIN}`). A contract v2 template uses it only for core hosts, never for its own hostnames (§3.1) |
| `PORTCULLIS_PROXY_SUBNET` | Subnet of the `portcullis-proxy` network (default `172.31.250.0/24`) |
| `PORTCULLIS_PROXY_IP_RANGE` | Dynamic allocation range (default `172.31.250.128/25`) |
| `PORTCULLIS_TRAEFIK_IP` | Traefik's static IP on `portcullis-proxy` (default `172.31.250.2`). The **only** peer allowed to send identity headers |

Always use the default form, e.g. `${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}`. Any other required variable must be declared in the manifest's `env:` with `generate: random`. The Hub writes those into the per-app `.env`.

**NEW (contract v2):** the Hub also writes instance-scoped variables into every instance's `.env`: `PORTCULLIS_INSTANCE`, `PORTCULLIS_HOST_<ROUTER>`, `PORTCULLIS_OIDC_CLIENT_ID`, `PORTCULLIS_OIDC_CLIENT_ID_<KEY>`, `PORTCULLIS_ACCESS_GROUP` and `PORTCULLIS_ADMIN_GROUP` (§3.1). They don't come from `core.env` and templates don't declare them in the manifest.

## 3. Template layout

- **Location.** One directory per app at the root of a template source repo: `<app-id>/manifest.yaml` and `<app-id>/compose.yml`. The `<app-id>` must match `^[a-z0-9][a-z0-9_-]{0,63}$`.
- **Manifest schema.** Manifests must validate against `schema/manifest.schema.json` in the templates repo (JSON Schema 2020-12). The Hub enforces the same rules and skips templates that fail.
- **Compose invocation.** The Hub runs one compose project per **instance** (§11): `docker compose -p portcullis-<instance-id> -f <template>/compose.yml [-f <data>/overrides/<instance-id>.override.yml] [-f <data>/overrides/<instance-id>.user.yml] --project-directory <core host path> --env-file <data>/env/<instance-id>.env up -d --no-deps` (and `down --remove-orphans`; volumes are removed only by a guarded delete, §11.4). The default instance's id is the template id, so for it this is exactly `portcullis-<app-id>`, `<app-id>.override.yml` and `<app-id>.env`. The template's `compose.yml` is read-only to the Hub. The second file is the Hub's override, regenerated from Settings before every `up`. The third is the operator's custom override (Hub Expert tab), stored outside the template clone; it is validated against the template and may not set `traefik.*` or `com.docker.compose.*` labels, `networks`, `network_mode`, `pid`/`ipc`/`uts`, `privileged`, `cap_add`, `devices`, `security_opt`, bind mounts outside `./templates/<app-id>/` and the bind roots (`HUB_OVERRIDE_BIND_ROOTS`, default `/srv:/mnt:/media`), unescaped `$` (compose interpolation) in any key or value, or YAML `!reset`/`!override` tags (full list in [Hub Management](../operations/hub.md#custom-override)). So everything this page derives from a template's labels (routes, hostnames, tiers, middlewares) comes from `compose.yml` and the Hub's override only.

- **Support files.** Files that ship with a template are bind-mounted as `./templates/<app-id>/<file>`. Compose resolves relative paths against the core checkout on the host. Before every `compose up`, the Hub copies the template directory to `<core>/templates/<app-id>/`; core mounts `./templates` read-write into the Hub at `/project/templates`. All instances of a template share this copy, so support files are mounted read-only (`:ro`).
- **Networks.** Frontends join the external network `portcullis-proxy`; internal services join only `default`. A service name on `portcullis-proxy` is ambiguous once a template has two instances, so services address each other only over `default` (Traefik reaches containers by IP, not by name).
- **Volumes.** A `single` template declares `name: portcullis_<volume key>`. A `multi` template (§3.1) declares **no** `name:`; the Hub's override sets it (§11.2).
- **Middlewares.** Forward-auth and header-auth routers use `portcullis-auth@docker,portcullis-groups@docker` (on extra-domain hosts the Hub's override renders `portcullis-auth-ext@docker` instead, §5; templates always write `portcullis-auth@docker`). Native-OIDC host-wide routers must not, nor may `mtls`, `custom` or `public` routers. For a `custom` template with `auth.native_login` the Hub's override sets every router's `middlewares` label: `portcullis-auth@docker,portcullis-groups@docker,<the template's own>` (Portcullis sign-in, the default) or the template's own without the pair ("own login only", only with `allow_without_gateway: true`; TLS tier `public@file`, no `groups` entry). The template is never edited.
- **Public exceptions.** A template may declare share-link paths in `auth.public_access` (`enabled_by_default`, `default_mode` `listed|all`, `token_pattern`, `credential_headers`, `credential_cookies`, `credential_query`, `static_extensions`, `service`, `paths[]` with `prefix` (optionally one whole `{token}` segment), `description`, `supporting`, `exact`, `broad` + `justification`); header-auth templates with it also declare `auth.identity_headers`. Fields and rules: [Manifest reference](manifest-reference.md#authpublic_access). The template never ships the public router: the Hub generates it (§5). Router and middleware names starting with `portcullis-public-` are reserved for the Hub.

### 3.1 Template contract v2: instances and hostname variables — NEW (contract v2)

Contract v2 lets a template run as several independent instances (§11) whose hostnames the admin chooses, on the main domain or on an enrolled domain (§12). The templates repo's schema, `tests/validate.py` and the Hub implement exactly what this section says.

- **`instances`** (manifest, top level): `multi` or `single`; default `single`. The Hub creates instances other than the default one (§11) only for `multi` templates; for a `single` template it refuses with `409` and the reason. A template stays `single` only when it needs host-level uniqueness (e.g. fixed host devices), justified in `auth.notes`. Host ports are no reason: they are per-instance settings with the existing port collision check, so a second instance must pick free ports (or disable them) before it can start.
- **Host routers.** Each hostname a template serves has exactly one **host router**: the router whose rule is a `Host()` alone, with no path matcher. Path-scoped routers on the same hostname (`Host(...) && <path matchers>`, e.g. `vaultwarden-admin`) reuse the host router's variable. A v2 template may not have a hostname without a host router.
- **Hostname variables.** Each host router `<router>` gets the variable **`PORTCULLIS_HOST_<ROUTER>`**: `<ROUTER>` is the template's **original** router name (never the per-instance name of the Traefik-names bullet below) upper-cased, with `-` and `.` turned into `_` (`grafana` → `PORTCULLIS_HOST_GRAFANA`, `litellm-ui` → `PORTCULLIS_HOST_LITELLM_UI`). Two host routers that map to the same variable are an error. The value is the **full hostname**: lowercase, no scheme, port or trailing dot (e.g. `grafana.team-b.example.org`). The Hub writes one variable per host router into every instance's `.env`, the default instance included. The same original router name keys `{{HOST_<ROUTER>}}`, the `hosts` maps of the Hub API (§11.7) and the sign-in router's name (§5).
- **Rule form.** Every router rule of a v2 template is exactly `` Host(`${PORTCULLIS_HOST_<ROUTER>:-<sub>.portcullis.local}`) ``, optionally followed by ` && <path matchers>` (`PathPrefix`, `Path`, or a parenthesised `||` of them, as today). The default value names the template's **default subdomain** `<sub>`, a single DNS label (`^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`): the default instance's hostname is `<sub>.<main domain>`, and a new instance's pre-filled hostname is derived from it (§11.3). Each variable is written with the same default everywhere it appears. A template uses one rule form for all its routers: it may not mix this form with the `${PORTCULLIS_DOMAIN}` form of the conversion period.
- **Own hostnames everywhere.** Wherever a v2 template names one of its own hosts (env URLs, `hostname:`, middleware values such as a `redirectregex` replacement), it uses the variable in the same default form, e.g. `APP_URL: https://${PORTCULLIS_HOST_FIREFLY:-finance.portcullis.local}`. Core hosts keep `${PORTCULLIS_DOMAIN}`: `https://auth.${PORTCULLIS_DOMAIN:-portcullis.local}/realms/portcullis`.
- **Manifest placeholders.** `{{HOST_<ROUTER>}}` in `urls[].url` and `keycloak_clients[].redirect_uri` / `redirect_uris` is replaced with the instance's hostname for that host router; `{{DOMAIN}}` stays the main domain. A `multi` template writes its own hosts only as `{{HOST_<ROUTER>}}`. In a `multi` template, `{{DOMAIN}}` in those fields may only form a core host: the URL's host is exactly `<core subdomain>.{{DOMAIN}}` for a core subdomain (§4, e.g. `https://auth.{{DOMAIN}}/realms/portcullis`); the apex `{{DOMAIN}}` alone, any other `<label>.{{DOMAIN}}` (its own hosts included) and anything under a core host are refused at discovery.
- **Instance variables.** The Hub writes these into every instance's `.env` too. Templates use them instead of hard-coding the values, always in the default form with the **default instance's** value (e.g. `${PORTCULLIS_ACCESS_GROUP:-users_grafana}`):

    | Variable | Value |
    |----------|-------|
    | `PORTCULLIS_INSTANCE` | The instance id (§11.1); the template id for the default instance |
    | `PORTCULLIS_HOST_<ROUTER>` | The instance's full hostname for that host router |
    | `PORTCULLIS_OIDC_CLIENT_ID` | Keycloak client id of the first `keycloak_clients` entry for this instance (§11.2); empty without clients |
    | `PORTCULLIS_OIDC_CLIENT_ID_<KEY>` | The same for **every** entry; `<KEY>` is the entry's manifest `client_id` upper-cased with `-` and `.` turned into `_` (headscale: `PORTCULLIS_OIDC_CLIENT_ID_HEADSCALE`, `PORTCULLIS_OIDC_CLIENT_ID_HEADPLANE`). Two entries whose `client_id`s map to the same `<KEY>` are an error |
    | `PORTCULLIS_ACCESS_GROUP` | The instance's access group (§11.2); empty if the manifest has no `access_group` |
    | `PORTCULLIS_ADMIN_GROUP` | The instance's admin group (§11.2); empty if the manifest has no `admin_group` |

    These names are reserved: a manifest may not declare them in `env`, `settings` or `ports`.
- **`multi` templates also** have no `${PORTCULLIS_DOMAIN}` in any router rule, no volume `name:` (the Hub sets it, §11.2), and no hard-coded Keycloak client id or group name in `compose.yml` (they use the variables above). Router, service and middleware names a template defines may not start with `portcullis-` (reserved for core and the Hub) and may not contain `_` (every v2 template, so the per-instance prefix below can't be ambiguous).
- **Traefik names per instance.** Traefik's Docker provider merges same-named routers and services across containers, so two instances must never define the same name. For every instance **except the default one**, the Hub's override renames each router, service and middleware the template's labels define from `<name>` to `<instance-id>_<name>`. It also rewrites the references to them in `routers.*.service` and `routers.*.middlewares` (`<name>@docker`). Names the template doesn't define (`portcullis-auth@docker`, `security-headers@file`, …) are kept. The override replaces each labelled service's `labels` with compose's `!override` tag, so no original name survives. Neither instance ids nor v2 template names contain `_`, so the prefix can't be ambiguous. The default instance keeps the template's names unchanged.
- **Conversion period.** Until every template is converted, the Hub sets `PORTCULLIS_HOST_*` for every instance (default included). An `instances: single` template may still use `` Host(`<sub>.${PORTCULLIS_DOMAIN:-portcullis.local}`) `` rules. Such a template runs only as its default instance, its hostnames are fixed at `<sub>.<main domain>`, and the Hub refuses hostname changes for it (`409`). Its host keys are still its host routers' names. It uses that form for all its routers (no mixing).

Example (`grafana`, contract v2):

```yaml
# manifest.yaml (excerpt)
instances: multi
auth:
  method: header-auth
  group_access: true
  access_group: users_grafana     # the default instance's group
urls:
  - label: Dashboards
    url: "https://{{HOST_GRAFANA}}"
```

```yaml
# compose.yml (excerpt)
services:
  grafana:
    environment:
      GF_SERVER_ROOT_URL: https://${PORTCULLIS_HOST_GRAFANA:-grafana.portcullis.local}
    volumes:
      - grafana-data:/var/lib/grafana
    labels:
      traefik.enable: "true"
      traefik.http.routers.grafana.rule: Host(`${PORTCULLIS_HOST_GRAFANA:-grafana.portcullis.local}`)
      traefik.http.routers.grafana.entrypoints: websecure
      traefik.http.routers.grafana.tls.options: public@file
      traefik.http.routers.grafana.middlewares: portcullis-auth@docker,portcullis-groups@docker,security-headers@file
      traefik.http.services.grafana.loadbalancer.server.port: "3000"
volumes:
  grafana-data: {}                # no name: the Hub sets it per instance
```

For the instance `grafana-team-b` on `grafana.team-b.example.org`, the Hub writes `PORTCULLIS_INSTANCE=grafana-team-b`, `PORTCULLIS_HOST_GRAFANA=grafana.team-b.example.org`, `PORTCULLIS_ACCESS_GROUP=users_grafana-team-b`, `PORTCULLIS_ADMIN_GROUP=admin_grafana-team-b` and `PORTCULLIS_OIDC_CLIENT_ID=` (no clients) into `<data>/env/grafana-team-b.env`. Its override renames the router and the service to `grafana-team-b_grafana`, renders the router's middlewares as `portcullis-auth-ext@docker,portcullis-groups@docker,security-headers@file` (an extra-domain host, §5), adds the sign-in router `portcullis-oauth2-grafana-team-b_grafana`, and names the volume `portcullis_grafana-team-b-grafana-data`.

## 4. Policy file (Hub → group-gate)

The Hub writes `group-gate-policy.json` atomically (temp file + rename) to the `hub_data` volume. group-gate mounts that volume read-only and re-reads the file on every request.

**NEW (policy v5):** the file is `version: 5` and every per-app map is keyed by **full hostname** instead of subdomain, so instances on the main domain and on enrolled domains (§11, §12) each get their own policy. Format:

```json
{
  "version": 5,
  "default":  {"factors": ["mtls", "webauthn"], "op": "any"},
  "extra_domains": ["<enrolled domain>"],
  "policies": {"<hostname>": {"factors": ["mtls", "webauthn"], "op": "any|all"}},
  "groups":   {"<hostname>": "<required LLDAP group>"},
  "path_groups": {
    "<hostname>": [{"prefix": "/admin", "group": "<LLDAP group>"}]
  },
  "public_paths": {
    "<hostname>": {
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

Example: main domain `portcullis.example.com`, two Grafana instances (`grafana-team-a` on the main domain, `grafana-team-b` on the enrolled domain `team-b.example.org`, its hostname edited to `grafana.team-b.example.org`) and the default instance of Vaultwarden. Core hosts (`portcullis.example.com`, `auth.portcullis.example.com`, `hub.portcullis.example.com`, `people.portcullis.example.com`, …) are **not** in the file: they come from `group-gate-map.conf`.

```json
{
  "version": 5,
  "default": {"factors": ["mtls", "webauthn"], "op": "any"},
  "extra_domains": ["team-b.example.org"],
  "policies": {
    "grafana-team-a.portcullis.example.com": {"factors": ["webauthn"], "op": "any"},
    "grafana.team-b.example.org": {"factors": ["mtls", "webauthn"], "op": "all"}
  },
  "groups": {
    "grafana-team-a.portcullis.example.com": "users_grafana-team-a",
    "grafana.team-b.example.org": "users_grafana-team-b",
    "passwords.portcullis.example.com": "users_vaultwarden"
  },
  "path_groups": {
    "passwords.portcullis.example.com": [{"prefix": "/admin", "group": "admin_vaultwarden"}]
  },
  "public_paths": {
    "grafana-team-a.portcullis.example.com": {
      "paths": [
        {"path": "/public-dashboards/{token}", "match": "prefix"},
        {"path": "/api/public/dashboards/{token}", "match": "prefix"},
        {"path": "/public/build", "match": "static"}
      ],
      "token_pattern": "^[0-9a-f]{32}$",
      "static_extensions": ["css", "js", "svg", "woff2"],
      "credential_headers": ["Authorization", "Proxy-Authorization", "X-Access-Token", "X-Grafana-Id"],
      "credential_cookies": ["grafana_session", "renderKey"],
      "credential_query": ["auth_token"]
    }
  },
  "expiring": []
}
```

- **`factors`** is a subset of `mtls` and `webauthn`; the Hub never writes anything else. There is no `password` factor (no password sign-in exists): group-gate treats it as an unknown factor and **denies** (fail closed). The Hub rewrites stored policies naming it on load, never into a weaker one (`all`: dropped; alternative or alone: `any of [mtls, webauthn]`). `op` is `any` or `all`, and is ignored when there is at most one factor. An empty factor list means public.
- **Unknown values fail closed.** An unknown factor, op or key shape, a file that exists but can't be parsed, or a `version` other than the one group-gate supports (currently 5) makes group-gate deny the request.
- **Version 5** (**NEW**; the Hub always writes 5). group-gate serves **only** version 5 and denies every request on a version-4 (or older) file; a group-gate that knows only version 4 denies every request on a version-5 file. **The Hub and core must be upgraded together.**
- **`expiring`** is unchanged from version 4:
    - an array of `{"user": "<lowercase username>", "group": "<LLDAP group>", "at": "<RFC 3339 UTC timestamp>"}` entries for temporary group memberships. group-gate treats the membership as **absent** once `now >= at`, regardless of what the user's token says. Usernames are lowercase; timestamps are RFC 3339 in UTC (e.g., `2027-03-31T23:59:59Z`).
    - The Hub writes **at most one entry** per `(user, group)` pair: the **earliest** `at` when multiple expiries exist for the same membership.
    - The Hub writes every pending expiry into this array so that expiry enforcement is strict even while the Hub is down. The Hub keeps publishing an expired entry until the membership is actually removed from LLDAP, plus a 10-minute grace period afterwards (cleared on regrant). One exception: the end of an "added" exception of a rule group is not written while the user is a current member, the group's rule matches them and the evaluator keeps them (they stay by rule after the end). Manual expiries and grace entries are always written.
    - **Which removals revoke Keycloak sessions.** The Hub signs the user out of Keycloak (`POST …/users/{id}/logout`) after: every membership the evaluator removes (rule, exception or expiry), an admin's member removal, a group deletion (every former member), and a password change; a user deletion removes the Keycloak copy. OIDC apps then lose access at their next token refresh, forward-auth sessions within about a minute (oauth2-proxy cookie refresh). Core runs Keycloak's LDAP federation with `cachePolicy: NO_CACHE`, so that refresh reads the user's current groups and attributes from LLDAP instead of a cached copy.
    - When group-gate strips an expired membership for a request, it also withholds `Authorization` and `X-Forwarded-Access-Token`. The `portcullis-groups` middleware lists both in `authResponseHeaders` and echoes them to the backend only when the request is allowed.
- **Keys are full hostnames** (**NEW**, policy v5). `policies`, `groups`, `path_groups` and `public_paths` are keyed by the lowercase hostnames that **enabled** instances route, e.g. `grafana.team-b.example.org` — never by template or instance id. A key is a **valid hostname**: at most 253 characters and matching `^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$` (lowercase, at least two labels, no port, no trailing dot, no wildcard). This page uses "valid hostname" in exactly this sense. Any other key shape makes group-gate deny.
- **`extra_domains`** (**NEW**, policy v5): every enrolled domain (§12) the Hub knows, sorted, each a valid hostname. A host equal to or under one of them is an **extra-domain host** (§5); group-gate uses this to build the step-up URL. The Hub writes it from its last known list of enrolled domains (§12.3), so it is never empty just because the domains service is down. A malformed entry makes group-gate deny.
- **Host matching** (**NEW**, policy v5). group-gate takes the request host from `X-Forwarded-Host` (first value), lowercases it, strips a `:<port>` and trailing dots, and looks it up **exactly** (`Grafana-A.Team-A.com.:443` → `grafana-a.team-a.com`). It never falls back to a subdomain-only or parent-domain match: a host with no entry gets `default` and no group, as an unlisted subdomain did before. A host that is not a valid hostname after normalisation is denied.
- **Routing must be fully visible.** The Hub parses every `traefik.http.routers.*.rule` label in a template's compose file and only accepts the contract v2 form `` Host(`${PORTCULLIS_HOST_<ROUTER>:-<sub>.portcullis.local}`) `` (§3.1), or, for `single` templates during the conversion period, the literal form `` Host(`<sub>.${PORTCULLIS_DOMAIN…}`) ``, each optionally `&& <path matchers>`. It rejects any template with `HostRegexp`/`HostHeader`/`HostSNI`, other domains, other variables in the label, routers without a rule, TCP routers, or a rule branch that is not restricted by `Host()`. The Hub resolves each rule to the instance's hostname. A host the Hub can't see would get no policy and no group (fail open).
- **`policies`** has an entry for each hostname of an enabled instance that has a per-instance policy. Instances that inherit the default publish nothing; group-gate falls back to `default`. An override only names factors the app's auth method can enforce (the Hub refuses others with `400`: `mtls` apps only `mtls`, `custom`/`public` apps without Portcullis sign-in none); every app that runs group-gate can enforce both, so for those the default applies unchanged.
- **One owner per hostname.** The Hub refuses to enable an instance, or to set a hostname (§11.3), that another instance or a core host already uses. If a collision still reaches the writer, it publishes the stricter policy (higher LoA, then `all` over `any`), merges path groups, keeps the group of the lowest instance id, and logs the collision.
- **`groups`** comes from enabled instances of templates with `auth.group_access: true`: each hostname maps to the instance's access group (§11.2). Not for a `custom` app switched to its own login only (its routers have no group-gate); the fail-closed snapshot records that (`native_login_only`).
- **Fail closed when a template goes missing.** At enable time the Hub stores each instance's published config (hostnames, groups, admin paths, policy override) in its state. If an enabled instance's template later stops loading, the Hub keeps publishing that last known config and reports it as drift. If there is no stored config, every hostname the instance's running containers route (or a running `portcullis-*` app project that isn't an enabled instance) gets `groups[host] = "__portcullis_deny__"`. group-gate matches groups exactly and nobody is in that group, so all requests are denied. Never create an LLDAP group with that name.
- **`path_groups`** comes from enabled instances of templates that declare `auth.admin_paths` (a list of path prefixes). Each prefix requires the instance's admin group, **in addition** to the hostname's group.
    - Matching uses group-gate's normalized `X-Forwarded-Uri` path: percent-decoded once, `//` collapsed, dot-segments resolved.
    - It is a prefix match on segment boundaries (`/admin` matches `/admin` and `/admin/x`, not `/administrator`). The longest matching prefix wins.
- **Core hosts** are never taken from this file. `group-gate-map.conf` in core owns them; it keeps `<sub>=<group>` entries, and group-gate expands each `<sub>` to `<sub>.<main domain>` (**NEW**, policy v5; `PORTCULLIS_DOMAIN` is required). The core hosts are `<main domain>` itself (the portal) and `<sub>.<main domain>` for the core subdomains `auth`, `traefik`, `hub`, `directory`, `enroll`, `people`, `metrics`. A policy-file entry for a core host is ignored, as before. The map file's app entries (e.g. `grafana=users_grafana`) expand the same way and, as before, policy-file entries add to or override them.
    - `people` is accessible to any signed-in user (§5.1); `metrics` (Grafana of core's optional [monitoring](../operations/monitoring.md) profile) is a core subdomain too. All appear in group-gate, the Hub (`policy.CoreHosts(mainDomain)`) and the templates validator.
    - **Extra domains never route core services**: no core host is on an enrolled domain, and the Hub never assigns a core host to an instance.
- **`public_paths`** is, per hostname, the configuration of core's public guard (§5) for an enabled instance whose public router exists:
    - `paths`: `{path, match}` patterns. `match` is `prefix` (segment boundary), `exact` or `static` (files below `path`: dot-free directories, a file name with one of `static_extensions`). One whole segment may be `{token}`, which matches one segment that `token_pattern` (anchored) accepts. Listed share tokens are published as `{token}`: tokens are secrets and stay in the Hub's `state.yaml`; Traefik's rule routes only the listed ones.
    - `credential_headers` (always including `Authorization` and `Proxy-Authorization`), `credential_cookies`, `credential_query`: credentials the guard refuses.
    - Any unknown key, malformed pattern or bad regex makes the guard deny. Missing-template snapshots keep publishing the entry (the containers keep their public router).
- **Older files.** A policy file **without** a `version` key, or with `version` 4 or lower, is **denied** by group-gate (only version 5 is served). A missing file (the Hub has never written one, or the volume is gone) is treated as an empty policy with no groups or path groups.

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

- **`fields`**: maps each custom field name to its header name. The header name has each underscore-separated word capitalized (e.g., `cost_center` → `Cost-Center`). Only fields with the **ShareWithApps** flag are included. Field names match `^[a-z][a-z0-9]*(_[a-z0-9]+)*$` and are at most 31 characters (no leading, trailing or doubled `_`), so the underscore-to-hyphen-plus-capitalize mapping is **injective** (no collisions possible) and always gives a valid header name. group-gate **skips** (and logs) a field whose name or header name is invalid; the other fields still produce headers. Only an unreadable or malformed file (or two fields on one header) means no attribute headers at all.
- **`users`**: maps each lowercase username to their field values. Each field is an array of strings (even for single-valued fields). Users with no shared field values are omitted.
- **Written atomically** with mode `0644`, using temp file + rename, at the same time as the policy file.
- **Encoding:** Each attribute value is percent-encoded before being joined: `%` becomes `%25` and `,` becomes `%2C`. After encoding, values are joined with `, ` (comma-space). Apps must percent-decode each value after splitting on `, `. The **1 KB limit** per value is measured **before** percent-encoding; a value over 1 KB (before encoding) is dropped and logged.
- **Security:** group-gate returns these headers only on **allow** (after auth factors are satisfied). Client copies of `X-Forwarded-Attr-*` headers are stripped by `authResponseHeadersRegex: ^X-Forwarded-Attr-` on **every** forwardAuth middleware in Traefik (Traefik cannot delete headers by prefix in a headers middleware, so each middleware's regex is the mechanism). Routers **without** a forwardAuth middleware in their chain (such as `keycloak`, `vault-ui`, `enroll-invite`, `headscale`, `netbird`, and `docs`) do not strip these headers, so backends on those routes **must not trust** `X-Forwarded-Attr-*` headers.
- **Logging:** A corrupt `user-attributes.json` file is logged by group-gate; no attribute headers are sent (never a deny).

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
- **Attribute headers (NEW).** When custom user fields are defined (§9.6) and the **ShareWithApps** flag is enabled on a field, group-gate returns additional headers on **every request it allows** through `portcullis-groups`:
    - **`X-Forwarded-Attr-<Header-Name>`**, where `<Header-Name>` is the field's name with each underscore-separated word capitalized (e.g., `cost_center` → `Cost-Center`).
    - **Values** are percent-encoded (`%` → `%25`, `,` → `%2C`), then joined with `, ` (comma-space). Control characters (ASCII 0x00–0x1F and 0x7F) are stripped from each value before encoding. Each individual value is limited to **1 KB** (measured **before** percent-encoding); longer values are **dropped** (not truncated) and logged by group-gate. Apps must percent-decode each value after splitting on `, `.
    - group-gate reads field values from `user-attributes.json` (§4.1). A missing or corrupt file results in no attribute headers (never a deny). Users absent from the file get no attribute headers.
    - **Scope:** attribute headers are returned for **all requests** that pass through `portcullis-groups`, including every instance hostname (main or enrolled domain) and the core hosts (`auth`, `traefik`, `hub`, `directory`, `enroll`, `people`, `metrics`). They are **not** returned on public routers (which have no `portcullis-auth` or `portcullis-groups` middlewares).
    - **Forwarding:** Client copies of `X-Forwarded-Attr-*` headers are stripped by `authResponseHeadersRegex: ^X-Forwarded-Attr-` on **every** forwardAuth middleware. Traefik cannot delete headers by prefix in a headers middleware, so the regex on every forwardAuth middleware is the stripping mechanism. Routers **without** forwardAuth in their chain (such as `keycloak`, `vault-ui`, `enroll-invite`, `headscale`, `netbird`, and `docs`) do not strip these headers, so backends on those routes **must not trust** `X-Forwarded-Attr-*` headers.
- **Email is never an identity or linking key.** No repo may authorise, create, match or link accounts by email. Native-OIDC templates key accounts on `sub` / `preferred_username`.
- **Order.** On the Hub router, `hub-proxy-secret@docker` comes **after** `portcullis-auth@docker,portcullis-groups@docker`, so the secret is never sent to oauth2-proxy or group-gate.
- **TLS tier per host.** Traefik selects TLS options per SNI host, so every router of a host must carry the same `tls.options`; on a mismatch Traefik uses its default options and answers `421 Misdirected Request`. The Hub writes one tier for all routers of an app: `public@file`, `authaware@file` or `protected@file` from the app's **effective** policy (its override or the default, intersected with what its method can enforce: an `mtls` app always gets `protected@file`, an app that handles its own sign-in `public@file`), except that `protected@file` becomes `authaware@file` for **all** of the app's routers while its public router exists (`policy.HostTier`).
- **Public router.** When an app's public exceptions are on and open at least one path, the Hub's override adds, on the `public_access.service` (default: the only routed service):
    - `traefik.http.routers.portcullis-public-<instance-id>`: rule `` Host(`<host>`) && (<entries>) `` over the app's hosts on that service. Entries: `` Path(`p`) || PathPrefix(`p/`) `` for prefixes (and each listed `{token}` expansion), `` Path(`p`) `` for `exact` paths, and for other supporting paths `` PathRegexp(`^p(/[A-Za-z0-9_~@+-]+)*/[A-Za-z0-9_~@+-][A-Za-z0-9._~@+-]*\.(<static extensions>)$`) `` (written with compose's `$$`). Then `entrypoints: websecure`, the host's tier, a priority above every router of the app (explicit priorities, and rule length plus 253 per `${…}` for implicit ones), the service's single Traefik service;
    - middlewares `portcullis-public-guard@docker,portcullis-public-strip-<instance-id>@docker,rate-limit@file,security-headers@file` (`rate-limit` and `security-headers` come from core's `traefik/dynamic/middlewares.yml`). No `portcullis-auth`, no `portcullis-groups`;
    - `traefik.http.middlewares.portcullis-public-strip-<instance-id>.headers.customrequestheaders.<H>: ""` for each core identity header (`X-Forwarded-User`, `X-Forwarded-Email`, `X-Forwarded-Groups`, `X-Forwarded-Preferred-Username`, `X-Forwarded-Access-Token`, `X-Auth-Request-User`, `-Email`, `-Groups`, `-Preferred-Username`, `-Access-Token`, `Remote-User`, `-Email`, `-Groups`, `-Name`), `Authorization`, `Proxy-Authorization`, each `auth.identity_headers` and `public_access.credential_headers` entry, each also with `_` for `-`. Without forward-auth nothing else deletes client copies; core's entrypoints also drop alias headers (`aliasHeadersStrategy=delete`).
- **Public guard (core).** `portcullis-public-guard@docker` is a forwardAuth middleware defined on group-gate (`http://group-gate:8080/public-guard`, no `authResponseHeaders`). It runs first, so it sees the request before the strip middleware. It answers 403 (no redirect) unless:
    - the policy file is version 5 and has a `public_paths` entry for the request's normalised hostname (§4; never a core host);
    - `X-Forwarded-Uri` has no `#`, no encoded `/`, `\`, NUL or `#` in the path, and every normalised form of the path (decoded once, `//` collapsed, dot-segments resolved; as for `path_groups`) is inside a published pattern;
    - no request header is a credential header (case-insensitive, `_` read as `-`);
    - no cookie (every `Cookie` header, split on `;` and `,`) and no query key (everything after the first `?`, split on `&` and `;`) names a credential. Names are compared case-insensitively after PHP's mangling (php-src `main/php_variables.c`, `php_register_variable_ex`: leading spaces dropped, ` ` and `.` become `_`, `name[…]` is `name`, an unclosed `[` becomes `_`, NUL ends the name), both raw and percent- / `+`-decoded; a name that isn't valid UTF-8 after decoding (overlong forms) or has control characters is refused.

    On allow it returns 200 without identity headers. Its logs mask token-like path segments and show query parameter names only.
- **Exposure drift.** The Hub compares every exposure label of each running container (each router's `tls.options`, all `portcullis-public-<instance-id>` and `portcullis-oauth2-<instance-id>_<router>` router labels and the strip middleware, every router's `middlewares` of `native_login` apps and of routers on extra-domain hosts) with what it would render now, `PORTCULLIS_DOMAIN` and the instance's `PORTCULLIS_HOST_*` expanded; any difference is `public_access_mismatch` drift.
- **Extra-domain hosts — NEW (contract v2 / domains).** An instance hostname equal to or under an enrolled domain (§12; listed in the policy file's `extra_domains`, §4) is an **extra-domain host**. That includes enrolled subdomains of the main domain: with `team-a.portcullis.example.com` enrolled, both `team-a.portcullis.example.com` and `x.team-a.portcullis.example.com` are extra-domain hosts. Every other instance hostname is a **main-domain host** (`<label>.<main domain>`). On extra-domain hosts:
    - **Same protection.** Routers carry the same middleware chain, `tls.options` tier, public router and group-gate checks they would carry on the main domain, with one substitution: the Hub's override renders `portcullis-auth-ext@docker` in place of `portcullis-auth@docker` (in the template's middlewares and in the `native_login` prepend alike). `portcullis-groups@docker` is unchanged. Nothing else about an instance's protection depends on its domain.
    - **Second oauth2-proxy (core).** Core runs a second oauth2-proxy service, **`forward-auth-ext`**, that serves extra-domain hosts only. It uses the same Keycloak client (`portcullis-forward-auth`) and the same cookie secret source (`FORWARD_AUTH_COOKIE_SECRET`) as `forward-auth`, a **relative** redirect URL `/oauth2/callback` (resolved against the request host) and a **host-only** cookie named **`_portcullis_ext`**. The distinct name keeps it apart from the main domain's `.<main domain>` cookie, which a host under an enrolled subdomain of the main domain also receives. Core defines its forwardAuth middleware **`portcullis-auth-ext`** (`http://forward-auth-ext:4180`) with the same `trustForwardHeader`, `authResponseHeaders` and `authResponseHeadersRegex` as `portcullis-auth`. `forward-auth`, `portcullis-auth`, the `auth.<main domain>` callback and the `.<main domain>` cookie stay exactly as they are.
    - **Certificates.** Traefik serves the enrolled domain's wildcard certificate from its file provider (`certs.yml`, §12.4), picked by SNI. The Hub assigns a host on an enrolled domain only while that domain is assignable (§12.3).
    - **Sign-in router.** For every extra-domain host on which any of the instance's routers, as rendered (including the `native_login` prepend), uses `portcullis-auth-ext@docker`, the Hub's override adds a router to `forward-auth-ext`. The labels go on the instance's first service, in `compose.yml` order, that has `traefik.enable: "true"`. Example host `grafana.team-b.example.org`, instance `grafana-team-b`, host router `grafana`:

        ```yaml
        traefik.http.routers.portcullis-oauth2-grafana-team-b_grafana.rule: Host(`grafana.team-b.example.org`) && PathPrefix(`/oauth2/`)
        traefik.http.routers.portcullis-oauth2-grafana-team-b_grafana.entrypoints: websecure
        traefik.http.routers.portcullis-oauth2-grafana-team-b_grafana.tls.options: authaware@file   # the host's tier
        traefik.http.routers.portcullis-oauth2-grafana-team-b_grafana.priority: "<above the public router and every router of the instance>"
        traefik.http.routers.portcullis-oauth2-grafana-team-b_grafana.service: forward-auth-ext@docker
        ```

        It is named `portcullis-oauth2-<instance-id>_<host router>` (the original router name, §3.1), carries no middlewares (like core's `oauth2-callback` router on `auth.<main domain>`), and is Host-scoped, so it gets the host's TLS options and core CI's "no host-less router" rule still holds. On extra-domain hosts the path prefix `/oauth2/` belongs to Portcullis: a `multi` template must not serve its own paths there. Router names starting with `portcullis-oauth2-` are reserved for the Hub.
    - **Callback and cookie.** On an extra-domain host the callback is `https://<host>/oauth2/callback` (served by `forward-auth-ext` through the sign-in router) and the session cookie is the host-only `_portcullis_ext`. On main-domain hosts nothing changes: `forward-auth`, callback `https://auth.<main domain>/oauth2/callback`, cookie for `.<main domain>`. The user's Keycloak session at `auth.<main domain>` makes the extra-domain sign-in a silent redirect (no key touch) unless the instance's policy needs a stronger factor than the session has.
    - **Callback redirect URIs.** The Hub keeps `https://<host>/oauth2/callback` for every extra-domain host with a sign-in router in the redirect URIs of core's Keycloak client `portcullis-forward-auth` (shared by both oauth2-proxy services). It adds and removes only such entries (Keycloak has no wildcard host matching), on instance create, hostname change, disable and delete. Core's `./portcullis keycloak configure` keeps redirect URIs of that form that it didn't set itself.
    - **Step-up URL.** group-gate builds the step-up URL from the request host: `https://auth.<main domain>/oauth2/start?acr_values=<acr>&rd=https://<host>/` for main-domain hosts (unchanged), and `https://<host>/oauth2/start?acr_values=<acr>&rd=/` for extra-domain hosts (`extra_domains`, §4; served by `forward-auth-ext`; same host, so `rd` needs no whitelist entry).
    - **Never core.** Extra domains never route core services: no core router has a host on an enrolled domain, and the portal, Hub, people, auth, enroll, directory, traefik and metrics pages exist only on the main domain.

### 5.1 People subdomain (NEW)

- **`people.<domain>`** is a new core subdomain that routes to the Hub's directory UI/API. It is accessible to **any signed-in user** (not just administrators).
- **Hub listener.** The Hub serves a second HTTP listener on port **8889** (configurable via `HUB_PEOPLE_ADDR`, default `:8889`). This listener serves only the directory UI and API (Users, Groups, Org chart, Import), with per-request permission checks. App, policy, drift, compose and Docker endpoints are **not** registered on this listener.
- **Core routing.** Core routes `people.<domain>` to `http://hub:8889` with the middleware chain: `rate-limit@file`, `client-headers@file`, `portcullis-auth@docker`, `portcullis-groups@docker`, `hub-proxy-secret@docker`, `security-headers@file`. The same `X-Portcullis-Proxy-Secret` header is required.
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

    On create and on every reconcile (enable, ACR push), the Hub attaches the wanted one first, then detaches the other one from the client's default **and** optional scopes. It does this only for clients it may reconcile (owner tag, or an untagged client that points only at the instance's hosts; see [Hub → Keycloak clients](../operations/hub.md#keycloak-clients)). If the realm has no `email-unverified` scope, the Hub reports an error and leaves the client's `email` scope attached.
- **What the template must do.** An app with `email_verified_claim: false` must not request the `email` scope: Keycloak answers `invalid_scope` to a requested scope the client doesn't have. `email-unverified` is a default scope, so the email claim arrives without being requested. `tests/validate.py` rejects `*SCOPE*` environment values that contain `email` for such templates.
- **Use it only for apps that refuse `email_verified=false` but accept it absent** (Vaultwarden SSO signups). The email is exactly as unverified as before: identity stays `sub` / `preferred_username` (§5), and the app must still never link accounts by email.
- **Clients per instance (NEW, contract v2).** Each instance has its own Keycloak clients, one per `keycloak_clients[]` entry, with ids from §11.2 and redirect URIs with `{{HOST_<ROUTER>}}` expanded to the instance's hostnames. A hostname change rewrites those redirect URIs (and web origins) in place (§11.3); a guarded delete removes the clients (§11.4). The Hub also maintains the extra-domain callback URIs on `portcullis-forward-auth` (§5). Core's two oauth2-proxy services, `forward-auth` (main domain) and `forward-auth-ext` (extra-domain hosts), both use that client.

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
- **No other changes.** The Hub doesn't touch the federation's settings or its built-in mappers (it adds only its own `portcullis-attr-<field>` mappers, §9.6). Core sets the federation's `cachePolicy` to `NO_CACHE` (realm export and `./portcullis keycloak configure`), so LLDAP group and attribute changes reach the next token.

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
- **Reconciliation.** The Hub writes computed membership into the real LLDAP groups. group-gate, Keycloak and apps treat rule-based groups exactly like manual groups. Re-evaluation happens on every detail change, rule change, import, exception change, and **periodically at most every 60 seconds** (binding). group-gate enforces `expiring` entries exactly regardless of the Hub's reconcile cadence.
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
    - A rule of such a group must also **not match a person with no field values** (every new account): refused with 409.
    - The evaluator **never adds** an account still marked `created_by` (a delegate created it, no admin has acted on it since) to such a group; it reports it instead.
    - Built-in groups (`lldap_admin`, `lldap_password_manager`, `INVITE_PROTECTED_GROUPS`, core-subdomain groups) can never be rule-based.
- **Deleting a group** deletes it in LLDAP first, then removes its rule, exceptions, expiries, grace entries and permission grants from `directory.yaml`; creating a group purges any leftovers for that name first. A re-created group inherits nothing.

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

- **Native-OIDC apps:** The Hub creates a Keycloak client scope `portcullis-attributes` with LDAP attribute mappers and protocol mappers for each shared field. Each field becomes a claim `attr_<field>` (e.g., `attr_department`) in **access tokens, ID tokens and userinfo**. The scope is a **default client scope** on Hub-registered clients (always included).
- **Forward-auth and header-auth apps:** The Hub writes `user-attributes.json` (§4.1); group-gate returns `X-Forwarded-Attr-<Header-Name>` headers (§5); the `portcullis-groups` middleware forwards them.

## 10. Landing portal app list (Hub → core)

- **File.** The Hub writes `portal-apps.json` atomically into `hub_data` (`/data`, next to `group-gate-policy.json`, mode 0644) whenever it writes the policy file (enable, disable, template sync, settings). A core landing portal reads it like group-gate reads the policy file: mount `hub_data` read-only.
- **Endpoint.** `GET /api/portal/apps` returns the same document, behind the proxy secret like every other Hub route.
- **Format, version 1.**

    ```json
    {
      "version": 1,
      "domains": ["team-b.example.org"],
      "apps": [
        {
          "id": "grafana-team-b",
          "template": "grafana",
          "name": "Grafana (grafana-team-b)",
          "description": "…",
          "icon": "📊",
          "category": "monitoring",
          "urls": [{"label": "Dashboards", "url": "https://grafana.team-b.example.org"}],
          "auth_method": "header-auth",
          "access_group": "users_grafana-team-b",
          "admin_group": "admin_grafana-team-b"
        },
        {
          "id": "immich",
          "template": "immich",
          "name": "Immich",
          "description": "…",
          "icon": "📷",
          "category": "media",
          "urls": [{"label": "Photos", "url": "https://photos.portcullis.example.com"}],
          "auth_method": "native-oidc",
          "access_group": "users_immich",
          "admin_group": "admin_immich"
        }
      ]
    }
    ```

    - Only enabled apps whose template is present are listed, sorted by `id`.
    - **NEW (instances):** one entry per enabled instance (§11). `id` is the instance id and `template` the template id; for the default instance both are the template id. `name` is the template's name, followed by ` (<instance-id>)` for other instances.
    - `{{DOMAIN}}` and `{{HOST_<ROUTER>}}` in URLs are already expanded (the instance's hostnames).
    - **NEW (domains):** `domains` lists, sorted, every enrolled domain (§12) on which at least one listed instance has a hostname.
    - `access_group` is the group group-gate requires (`auth.group_access`); `""` means any signed-in user.
    - `admin_group` is informational.
- **Rendering.** The portal filters by the signed-in user's groups (`X-Auth-Request-Groups`) and must escape every field. An unknown `version` means: show nothing.
- **Core's portal** is group-gate's `/portal` at `https://<domain>/` (router `portal`: forward-auth, then `replacePath`). It reads `/hub-data/portal-apps.json`, shows only `https` URLs whose host is on the main domain or on a domain in `domains`, and adds the Hub, the Keycloak realm console, enrollment, LLDAP and Traefik for `lldap_admin`, plus every user's passkeys (account console) and certificate (`enroll.<domain>/self`).

## 11. App instances (Hub) — NEW (instances)

A template can run as several fully separate **instances**. Each instance has its own compose project, containers, volumes, settings, env and generated secrets, Keycloak clients, groups, auth policy, public exceptions, sign-in mode, drift tracking and last-operation record. Instances share nothing; only the read-only template files under `<core>/templates/<app-id>/` (§3) are common. Every instance operation is admin-only and audited (§11.7).

### 11.1 Instance ids and the default instance

- **Default instance.** Every enabled template has a default instance whose id **is the template id**, so it follows the template-id pattern `^[a-z0-9][a-z0-9_-]{0,63}$` (§3), not the instance-id one. Its project, files, hostnames, groups, Keycloak clients, volumes and policy keys are exactly what a single deployment of the template uses, so existing state is the default instance as-is.
- **Other instances.** Their ids match `^[a-z][a-z0-9-]{0,30}$` (a DNS label). The Hub suggests `<template>-<suffix>` (e.g. `grafana-team-a`). An id must not start with `portcullis`, and must not equal any template id of any source (those are the default instances' ids) or another instance's id.
- **Collisions are refused** (`409`) before anything is created: a compose project, volume name, Keycloak client id or group name (case-insensitive) derived from the id (§11.2) that already exists and doesn't belong to this instance, or that equals a name the **default instance of any template of any source** would use (its volumes `portcullis_<key>`, manifest `client_id`s, `access_group` and `admin_group`), enabled or not.
- **`instances: single`** templates have only the default instance (§3.1).

### 11.2 Derived names

| What | Default instance (id = template id) | Other instance `<id>` |
|------|-------------------------------------|-----------------------|
| Compose project | `portcullis-<template>` | `portcullis-<id>` |
| Hub files | `<data>/env/<template>.env`, `<data>/overrides/<template>.override.yml`, `<template>.user.yml`, `<data>/ops/<template>.json` | the same with `<id>` |
| Volume `<key>` | `portcullis_<key>` (today's names) | `portcullis_<id>-<key>` |
| Traefik routers, services, middlewares the template defines | the template's names | `<id>_<name>` (§3.1) |
| Public router / strip middleware | `portcullis-public-<template>`, `portcullis-public-strip-<template>` | `portcullis-public-<id>`, `portcullis-public-strip-<id>` |
| Keycloak clients | the manifest's `client_id`s | first `keycloak_clients` entry: `<id>`; each further entry: `<id>-<manifest client_id>` |
| Access group | manifest `access_group` | `users_<id>` |
| Admin group | manifest `admin_group` | `admin_<id>` |
| `PORTCULLIS_INSTANCE` | `<template>` | `<id>` |

- The Hub's override sets every volume's `name:` from this table, for `multi` templates (which declare none) and for the default instance alike.
- Creating an instance generates fresh values for every `generate: random` env entry, and creates `users_<id>` (if the manifest has `access_group`) and `admin_<id>` (if it has `admin_group`) in LLDAP as empty manual groups. The Hub tags each Keycloak client with the **instance id** that owns it and reconciles only clients with its own tag.
- Settings, auth policies, public exceptions and share tokens, sign-in mode, the fail-closed `published` snapshot, ops records and drift are keyed by instance id.
- **Instance states.** `created` (exists, never started: `POST /api/instances` creates without enabling), `enabled` (the project is up), `disabled` (stopped, everything kept), `deleting` (a guarded delete started and hasn't finished, §11.4), `error` (the last lifecycle operation failed; its ops record says why).

### 11.3 Hostnames

- **Pre-filled.** For a new instance on domain `<domain>`, each host router with default subdomain `<sub>` (§3.1) gets `<sub>-<suffix>.<domain>`, where `<suffix>` is the instance id without a leading `<template>-` (the whole id if it has no such prefix). If the label `<sub>-<suffix>` would be longer than 63 characters, the suffix is truncated to fit (a trailing `-` dropped); if the hostname is then still not a valid hostname (§4), creation is refused with an error that names the host router and asks for an explicit hostname. `grafana-team-a` on `portcullis.example.com` → `grafana-team-a.portcullis.example.com`; an instance `litellm-lab` → `llm-lab.<domain>`. The default instance's hostnames are `<sub>.<main domain>`. Every hostname is individually editable.
- **Valid hostnames.** A hostname is a valid hostname (§4) and either lies on an **assignable** enrolled domain `<d>` (§12.3) — `<d>` itself or `<label>.<d>`; enrolled domains never nest (§12.3), so at most one matches — or, if it is at or under no enrolled domain, is a main-domain host `<label>.<main domain>`. `<label>` matches `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`. Deeper names are refused: the wildcard certificates cover one label. An enrolled subdomain of the main domain (e.g. `team-a.<main domain>`) is assignable as its own apex only as an extra-domain host, on that enrolled domain.
- **Refused before anything changes** (`400` invalid, `409` collision): a hostname that is invalid, on a domain that isn't enrolled or isn't assignable, a core host (§4), used by any other instance (enabled or not), or used twice within the instance. Templates still using `${PORTCULLIS_DOMAIN}` rules (§3.1) can't change hostnames at all (`409`).
- **A change applies immediately.** In order: the Hub records the new hostnames in its state, regenerates the instance's env and override, updates its Keycloak clients' redirect URIs and web origins, updates the `portcullis-forward-auth` callback URIs (§5), rewrites the policy file and `portal-apps.json` (the old hostnames vanish from them at once), and restarts the instance (`compose up`). Public share links keep their tokens and move to the new host. **There are no redirects:** the old hostnames stop routing. A step that fails after validation is reported like any lifecycle operation (`OpError`) and the instance is reconciled by retrying the change.
- Audited as `instance.update` with the old and new hostnames.

### 11.4 Guarded delete

Deleting an instance is permanent and needs the instance id typed: `{"confirm": "<instance-id>"}` (missing or different: `400`). The Hub:

1. **Takes a backup** (§11.5, reason `delete`). If it fails, the delete stops and nothing is removed.
2. Records `deleting` (and the backup path) in its state. From here on the instance is listed as **partially deleted** until the delete completes, and the only action offered is Delete (retry).
3. Stops and removes the project (`down --remove-orphans`), then removes its volumes (§11.2).
4. Deletes its Keycloak clients (only clients tagged with this instance) and its callback URIs on `portcullis-forward-auth`.
5. Deletes its access and admin groups through the Users & Groups guardrails (`DeleteGroup`, which also signs former members out). A protected or permission group is kept, with a warning.
6. Removes its env file, overrides, ops record, generated secrets, share tokens and state entry, and rewrites the policy file and `portal-apps.json`.

Every step is idempotent. A retry skips step 1 (the first backup is kept) and continues where the last attempt failed. Backups are not removed with the instance: they stay listed (`GET /api/backups`) and can be restored into a new instance (§11.6). Audited as `instance.delete` with the backup path. Disabling an instance (stop, keep everything) is unchanged.

The **default instance** can be deleted the same way. That removes the manifest's `access_group` and `admin_group` (by convention `users_<template>` / `admin_<template>`) through the same guardrails; the template stays in the catalog and enabling it again creates a fresh default instance.

### 11.5 Backups

- **When.** On demand (`instance.backup`), before every delete and before every restore.
- **Path.** `<data>/backups/<instance-id>/<UTC timestamp>.tar`, the timestamp as `YYYYMMDDTHHMMSSZ` (e.g. `<data>/backups/grafana-team-a/20261102T153000Z.tar`). Written to a temporary name and renamed when complete; files `0600`, directories `0700`, owned by the Hub (uid 10001). Never pruned automatically.
- **Consistency.** A running instance is stopped while its volumes are copied, then started again, so databases are copied at rest. Volume I/O runs in a helper container (image pinned by digest) through the Hub's socket proxy (§6).
- **Layout** (an uncompressed tar):

    ```text
    MANIFEST.json
    config/instance.yaml       # the instance's state entry: template, hostnames, settings, auth policy,
                               # public exceptions and share tokens, sign-in mode, published snapshot
    config/env                 # <data>/env/<instance-id>.env (generated secrets included)
    config/override.yml        # the Hub override as last applied
    config/user.yml            # the custom override, only if there is one
    volumes/<volume key>.tar   # one inner tar per volume; numeric uid/gid, modes and mtimes preserved
    ```

    `MANIFEST.json` is the first tar member; the other members follow sorted by path (byte order). It lists the sha256 (lowercase hex, 64 characters) of every other member:

    ```json
    {
      "version": 1,
      "instance": "grafana-team-a",
      "template": "grafana",
      "template_commit": "170866c0f2…",
      "created_at": "2026-11-02T15:30:00Z",
      "reason": "manual",
      "volumes": {"grafana-data": "portcullis_grafana-team-a-grafana-data"},
      "files": {
        "config/env": "60303ae22b998861bce3b28f33eec1be758a213c86c93c076dbe9f558c11c752",
        "config/instance.yaml": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "config/override.yml": "fd61a03af4f77d870fc21e05e7e80678095c92d808cfb3b5c279ee04c74aca13",
        "volumes/grafana-data.tar": "a3f5c2a4d1e6b7c8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2"
      }
    }
    ```

    `reason` is `manual`, `delete` or `restore`; `volumes` maps each volume key to the volume name it was copied from.
- **Offsite.** Core's `./portcullis backup` archives the `hub_data` volume, so `<data>/backups/` is included (and shipped with `--offsite`).
- The archive contains the instance's generated secrets in clear; it is protected like the rest of `hub_data`.

### 11.6 Restore

A backup restores into the **same** instance (replacing its data) or into a **new** instance id. Audited as `instance.restore` with the archive and the target.

- **Checks first, nothing changes on failure:** `MANIFEST.json` `version` is 1; every listed file is present with a matching sha256 and there are no unlisted files (mismatch: `409`, refused); the template exists. For a new id: the id rules and collisions of §11.1, and the template must be `multi`.
- **Same instance** (`POST /api/instances/{id}/restore`). The Hub takes a backup (reason `restore`) and stops the instance. It replaces every volume's contents, the env (`config/env`), the custom override (`config/user.yml`, removed if the archive has none) and the instance's state from `config/instance.yaml`, **except its hostnames: the current hostnames are kept**. The Hub override is **regenerated**, not restored (`config/override.yml` is informational). Then the Hub re-applies the Keycloak clients' redirect URIs and web origins, the forward-auth callback URIs, the policy file and `portal-apps.json`, and starts the instance. If any step fails, it puts the pre-restore backup back and reports the failure: the instance's previous data is kept.
- **New id** (`POST /api/instances/restore`), from any listed archive, including one of a deleted instance; the deleted instance's id may be reused. The Hub creates the instance from the archive's config with: hostnames reset to the new id's defaults on the main domain (§11.3), new Keycloak clients and new empty groups (§11.2), new volumes filled from the archive, and the archive's settings, policy, public exceptions and generated secrets, except each Keycloak client's `secret_env`, which is regenerated.

### 11.7 Hub API and audit

Instance and domain operations live on the Hub listener only (never on the people listener, §5.1), are **admin-only** (`lldap_admin`; delegates get `403`) and pass the proxy-secret and CSRF guards. Each one is appended to `audit.jsonl` (§9.5) as one of `instance.create`, `instance.update`, `instance.delete`, `instance.backup`, `instance.restore`, `domain.enroll`, `domain.token`, `domain.delete`, with `result` `ok`, `refused` or `error`. DNS credentials never appear in audit entries, logs, errors or responses.

| Route | Body | Does |
|-------|------|------|
| `GET /api/instances` | — | Every instance (shape below) |
| `POST /api/instances` | `{"template": "grafana", "id": "grafana-team-a", "hosts": {"grafana": "grafana-team-a.portcullis.example.com"}}` | Create without enabling (state `created`; §11.1–11.3); `hosts` omitted = the defaults on the main domain; `201` with the instance |
| `PUT /api/instances/{id}/hosts` | `{"hosts": {"<host router>": "<hostname>"}}` | Change hostnames (§11.3) |
| `DELETE /api/instances/{id}` | `{"confirm": "<id>"}` | Guarded delete (§11.4) |
| `GET /api/backups` | — | Every archive under `<data>/backups/`, deleted instances' included (shape below) |
| `GET /api/instances/{id}/backups` | — | The same, for one instance id |
| `POST /api/instances/{id}/backups` | — | Back up now (§11.5); `201` with the backup entry |
| `POST /api/instances/{id}/restore` | `{"archive": "grafana-team-a/20261102T153000Z.tar"}` | Restore into the same instance (§11.6); the archive must belong to `{id}` |
| `POST /api/instances/restore` | `{"archive": "grafana-team-a/20261102T153000Z.tar", "id": "grafana-team-c"}` | Restore into a new instance (§11.6); default hostnames |
| `GET /api/domains` | — | The domains service's list (§12.2), passed through |
| `POST /api/domains` | `{"name": "team-b.example.org", "provider": "cloudflare", "credentials": {"api_token": "…"}}` | Enroll (§12.3) |
| `POST /api/domains/{name}/token` | `{"provider": "cloudflare", "credentials": {…}}` | Replace the credentials |
| `DELETE /api/domains/{name}` | — | Remove; `409` while any instance uses the domain |

`archive` is always `<instance-id>/<timestamp>.tar`, relative to `<data>/backups/`; anything else is `400`.

`GET /api/instances` returns, sorted by `id`:

```json
[
  {
    "id": "grafana-team-b",
    "template": "grafana",
    "default": false,
    "state": "enabled",
    "hosts": {"grafana": "grafana.team-b.example.org"},
    "access_group": "users_grafana-team-b",
    "admin_group": "admin_grafana-team-b",
    "keycloak_clients": [],
    "project": "portcullis-grafana-team-b"
  }
]
```

`state` is one of `created`, `enabled`, `disabled`, `deleting`, `error` (§11.2); `hosts` is keyed by the original host-router name (§3.1).

`GET /api/backups` (and `GET /api/instances/{id}/backups`) returns, newest first:

```json
[
  {
    "archive": "grafana-team-a/20261102T153000Z.tar",
    "instance": "grafana-team-a",
    "template": "grafana",
    "created_at": "2026-11-02T15:30:00Z",
    "reason": "delete",
    "size": 73400320,
    "instance_exists": false
  }
]
```

The fields come from the archive's `MANIFEST.json`; `size` is in bytes; `instance_exists` says whether an instance with that id exists now.

**Existing per-app routes take the instance id.** Their paths are unchanged; the `{id}` path segment or the `"id"` body field is now an **instance** id (the template id still names the default instance): `POST /api/templates/enable` and `POST /api/templates/disable` (`{"id": "<instance-id>"}`), `/api/templates/settings/{id}`, `/api/templates/status/{id}`, `/api/templates/logs/{id}`, `/api/templates/compose/{id}`, `/api/templates/env/{id}`, `/api/templates/exec/{id}`, `/api/templates/restart/{id}`, `/api/templates/lastop/{id}` and `POST /api/drift/resolve` (`{"id": "<instance-id>", …}`); `GET /api/drift` reports drift per instance id. `GET /api/templates` stays the template catalog, keyed by template id, with each template's instance ids.

## 12. Domains service (core ⇄ Hub ⇄ Traefik) — NEW (domains API)

Extra domains and subdomains (e.g. `team-b.example.org`, `team-a.portcullis.example.com`) are enrolled by Hub admins. A new core service, **`domains`**, owns their DNS credentials, creates their records, and obtains and renews a wildcard certificate per domain. The main domain is not handled by it: it keeps Traefik's built-in resolver and `./portcullis dns setup`.

### 12.1 Service, network and secrets (core)

- **Service.** `domains` (Go: `github.com/go-acme/lego/v4` as a library for ACME DNS-01, `github.com/libdns/<provider>` for records, `filippo.io/age` for encryption at rest). It listens on `:8080` on the internal network `portcullis-domains`, whose only members are `domains` and the Hub; it reaches ACME and the DNS providers over a separate network with internet access. Traefik never routes it.
- **Volumes.** `domains_data` (domains only, read-write): encrypted credentials, ACME account, per-domain state. `domains_certs` (read-write in `domains`, **read-only** in Traefik at `/etc/traefik/dynamic/domains`): certificates and `certs.yml` (§12.4).
- **API secret.** `secrets/domains/api-secret` (≥ 32 characters, generated by `./portcullis init` / `up`), mounted read-only into `domains` and into the Hub, group 10001, mode 0640. Never an env var.
- **Encryption key.** `secrets/domains/age.key` (an age X25519 identity, generated by `init` / `up`), mounted read-only into `domains` only.
- **Configuration.** `PORTCULLIS_DOMAIN` (the main domain), `ACME_EMAIL` and `ACME_CA_SERVER` (as for Traefik's resolver), and the server's public IPv4 and, when present, IPv6, which `./portcullis up` detects as `dns setup` does.
- **Hub configuration.**

    | Env var (Hub) | Default | Meaning |
    |---|---|---|
    | `HUB_DOMAINS_API_URL` | `http://domains:8080` | Base URL of the domains API |
    | `HUB_DOMAINS_SECRET_FILE` | `/run/portcullis/domains/api-secret` | The API secret |

    Without a readable secret file the Hub's Domains section is disabled and says why; instances can then use only main-domain hosts.

### 12.2 API

Every request carries `Authorization: Bearer <api-secret>` (compared in constant time; otherwise `401`). Bodies are JSON. Errors are non-2xx with `{"error": "<message>"}`; messages never contain credentials. The Hub is the only caller and the service trusts it: it doesn't check instance assignments (§12.3).

`{name}` is a valid hostname (§4), not the main domain, not a parent of it, and not at or under a core subdomain host `<sub>.<main domain>` (`auth`, `hub`, …; `400` otherwise).

| Request | Success | Errors |
|---------|---------|--------|
| `PUT /domains/{name}` `{"provider": "<p>", "credentials": {…}}` | `202` with the domain object (`state: pending`); work starts in the background | `400` bad name, provider or credential keys; `409` already enrolled |
| `GET /domains` | `200` with an array of domain objects, sorted by `name` | — |
| `POST /domains/{name}/token` `{"provider": "<p>", "credentials": {…}}` | `202` with the domain object; replaces the stored credentials (the provider may change) and re-runs records and, if needed, issuance | `400`; `404` not enrolled |
| `DELETE /domains/{name}` | `204`; or `200` with `{"warning": "<message>"}` if some DNS records couldn't be removed | `404` not enrolled |

**Credentials per provider** (exactly these keys; non-empty strings; unknown keys are `400`):

| `provider` | `credentials` keys |
|------------|--------------------|
| `cloudflare` | `api_token` |
| `porkbun` | `api_key`, `secret_api_key` |
| `route53` | `access_key_id`, `secret_access_key`, `hosted_zone_id` (optional) |
| `digitalocean` | `auth_token` |
| `hetzner` | `api_token` |

**Domain object:**

```json
{
  "name": "team-b.example.org",
  "provider": "cloudflare",
  "records_ok": true,
  "cert_not_after": "2027-01-31T08:14:02Z",
  "last_error": "",
  "state": "ready"
}
```

- `records_ok`: the last check found `<name>` and the probe name `portcullis-probe.<name>` (answered by the `*.<name>` record) resolving to exactly the server's addresses (A, and AAAA when the server has IPv6) at **both** public resolvers `1.1.1.1:53` and `8.8.8.8:53`.
- `cert_not_after`: RFC 3339 UTC expiry of the certificate currently served, or `null` if there is none.
- `last_error`: the last failure, `""` after a success.
- `state`:

    | `state` | Meaning |
    |---------|---------|
    | `pending` | Enrolled or credentials replaced; work not started yet |
    | `records` | Creating and verifying the A/AAAA records |
    | `issuing` | ACME DNS-01 order for `<name>` and `*.<name>` in progress |
    | `ready` | Records OK; a valid certificate is in `certs.yml` |
    | `renewing` | Less than 30 days left; renewal in progress, the current certificate stays served |
    | `error` | The last step failed (`last_error`); retried with backoff. A still-valid certificate stays served |

Example: `PUT /domains/team-b.example.org` with `{"provider": "porkbun", "credentials": {"api_key": "pk1_…", "secret_api_key": "sk1_…"}}` → `202` `{"name": "team-b.example.org", "provider": "porkbun", "records_ok": false, "cert_not_after": null, "last_error": "", "state": "pending"}`.

### 12.3 What the Hub does

- **Enroll.** The Hub refuses (`409`) a name equal to, below or above an already enrolled domain (enrolled domains never nest), a name at or below any core subdomain host `<sub>.<main domain>` (e.g. `auth.<main domain>`, `x.hub.<main domain>`), and a hostname an instance uses. Other names under the main domain are allowed, deeper ones included (`team-a.<main domain>`, `lab.team-a.<main domain>`). It forwards the credentials once (`PUT`) and forgets them: they are never stored in its state, ops records, logs, audit or errors, and its API never returns them (the token field is write-only in the UI). Replacing them is `POST /domains/{name}/token`.
- **Assignable.** A domain may receive instance hostnames (create, hostname change, restore) only while `records_ok` is `true` and `cert_not_after` is in the future. A domain that stops being assignable keeps its existing hostnames; the Hub shows a warning.
- **Known domains (fail closed).** The Hub keeps the enrolled domain names (with their provider and last known status, **never credentials**) in `state.yaml`. When the domains service is unreachable, new assignments (create, hostname change, restore onto an enrolled domain) and domain operations get `503`, and the last known list keeps feeding `extra_domains` in the policy file and `domains` in `portal-apps.json`.
- **The Hub is the authority on assignments.** It refuses `DELETE /api/domains/{name}` with `409` while any instance (enabled or not) has a hostname on the domain. The domains service doesn't check assignments.
- **Status.** The Domains section shows, per domain: records OK, certificate valid until, last error, state.

### 12.4 Records and certificates

- **Records.** `<name>` and `*.<name>`: A to the server's IPv4 and, when it has one, AAAA to its IPv6; TTL 300; existing A/AAAA records at those two names are replaced. The zone is found with a SOA lookup (lego's `dns01.FindZoneByFqdn`), so a subdomain of a zone works with that zone's credentials; for `route53`, `hosted_zone_id` skips the lookup. `DELETE` removes the records the service created.
- **Certificates.** One certificate per domain with SANs `<name>` and `*.<name>`, from `ACME_CA_SERVER` by DNS-01 with the domain's own credentials (so two accounts at one provider can coexist). Renewed when less than 30 days remain. Failures back off.
- **`domains_certs` layout.** Each pair is written under a new name (never over the served pair), then `certs.yml` is rewritten atomically (temp file + rename), then the old pair is removed:

    ```text
    certs.yml
    team-b.example.org/<serial>.crt    # full chain
    team-b.example.org/<serial>.key
    ```

    ```yaml
    # Written by the domains service; do not edit.
    tls:
      certificates:
        - certFile: /etc/traefik/dynamic/domains/team-b.example.org/04c1e2….crt
          keyFile: /etc/traefik/dynamic/domains/team-b.example.org/04c1e2….key
    ```

    With no certificates the file is `tls: {certificates: []}`. Paths are Traefik-side. Traefik's file provider picks up changes without a restart; `DELETE` drops the domain from `certs.yml` first, then removes its files.
- **Secrets at rest.** Credentials exist only in `domains_data`, encrypted with the age key; the volume is in `./portcullis backup` only in that encrypted form. The same backup also contains `secrets/` (age key included), so it must be protected like the keys themselves, as for Vault's. Credentials are never logged, never returned by the API and never put in `last_error`.
