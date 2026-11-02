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
- **Compose invocation.** The Hub runs one compose project per **instance** (§11): `docker compose -p portcullis-<instance-id> -f <template>/compose.yml [-f <data>/overrides/<instance-id>.override.yml] [-f <data>/overrides/<instance-id>.user.yml] --project-directory <core host path> --env-file <data>/env/<instance-id>.env up --no-start --no-deps` (create, pulling images; the image-label check below runs on the created containers), then the same with `up -d --no-deps --pull never` (start exactly the images that were checked), and `down --remove-orphans`; volumes are removed only by a guarded delete, §11.4. The default instance's id is the template id, so for it this is exactly `portcullis-<app-id>`, `<app-id>.override.yml` and `<app-id>.env`. The template's `compose.yml` is read-only to the Hub. The second file is the Hub's override, regenerated from Settings before every `up`. The third is the operator's custom override (Hub Expert tab), stored outside the template clone; it is validated against the template and may not set `traefik.*` or `com.docker.compose.*` labels, `networks`, `network_mode`, `pid`/`ipc`/`uts`, `privileged`, `cap_add`, `devices`, `security_opt`, bind mounts outside `./templates/<app-id>/` and the bind roots (`HUB_OVERRIDE_BIND_ROOTS`, default `/srv:/mnt:/media`), unescaped `$` (compose interpolation) in any key or value, or YAML `!reset`/`!override` tags (full list in [Hub Management](../operations/hub.md#custom-override)). So everything this page derives from a template's labels (routes, hostnames, tiers, middlewares) comes from `compose.yml` and the Hub's override only.

- **Support files.** Files that ship with a template are bind-mounted as `./templates/<app-id>/<file>`. Compose resolves relative paths against the core checkout on the host. Before every `compose up`, the Hub copies the template directory to `<core>/templates/<app-id>/`; core mounts `./templates` read-write into the Hub at `/project/templates`. All instances of a template share this copy, so support files are mounted read-only (`:ro`).
- **Networks.** Frontends join the external network `portcullis-proxy`; internal services join only `default`. A service name on `portcullis-proxy` is ambiguous once a template has two instances, so services address each other only over `default` (Traefik reaches containers by IP, not by name).
- **Volumes.** A `single` template may name a (non-external) volume only inside its own namespace: `name: portcullis_<template-id>`, or a name starting with `portcullis_<template-id>-` or `portcullis_<template-id>_` (without `name:` compose calls it `portcullis-<template-id>_<key>`); any other name — another app's, core's, a bare `portcullis_<key>`, a name outside `portcullis_` — is refused. A `multi` template (§3.1) declares **no** `name:`; the Hub's override sets it (§11.2). A name two templates' default instances (or an instance and a default instance, §11.1) would share — template `a`'s `portcullis_a-b-data` and template `a-b`'s, a `multi` default instance's `portcullis_<key>` — is a name collision: the Hub loads only the first template (enabled ones first, then source order) and refuses such an instance. Core's volume keys (`postgres_data`, `vault_data`, `lldap_data`, `hub_data`, `traefik_acme`, `domains_data`, `prometheus_data`, `alertmanager_data`, `grafana_data`: Docker names `portcullis_<key>`) are refused as volume keys and as volume names, and an external volume may not be named `portcullis*` (an external volume without `name:` is named by its key): that is core's or another instance's data. Volume names must be literals.
- **Middlewares.** Forward-auth and header-auth routers use `portcullis-auth@docker,portcullis-groups@docker` (on extra-domain hosts the Hub's override renders `portcullis-auth-ext@docker` instead, §5; templates always write `portcullis-auth@docker`). Native-OIDC host-wide routers must not, nor may `mtls`, `custom` or `public` routers. For a `custom` template with `auth.native_login` the Hub's override sets every router's `middlewares` label: `portcullis-auth@docker,portcullis-groups@docker,<the template's own>` (Portcullis sign-in, the default) or the template's own without the pair ("own login only", only with `allow_without_gateway: true`; TLS tier `public@file`, no `groups` entry). The template is never edited.
- **Public exceptions.** A template may declare share-link paths in `auth.public_access` (`enabled_by_default`, `default_mode` `listed|all`, `token_pattern`, `credential_headers`, `credential_cookies`, `credential_query`, `static_extensions`, `service`, `paths[]` with `prefix` (optionally one whole `{token}` segment), `description`, `supporting`, `exact`, `broad` + `justification`); header-auth templates with it also declare `auth.identity_headers`. Fields and rules: [Manifest reference](manifest-reference.md#authpublic_access). The template never ships the public router: the Hub generates it (§5). Router and middleware names starting with `portcullis-public-` are reserved for the Hub.
- **Core names are off limits (NEW, domains).** The Hub rejects a template whose `compose.yml` mentions `forward-auth-ext`, `portcullis-auth-ext` or `portcullis-oauth2-` anywhere (the extra-domain sign-in is rendered by the Hub only, §5), joins a core network (`portcullis`, `portcullis-auth`, `portcullis-certs`, `portcullis-domains`, `domains-egress`, `socket-proxy-traefik`, `socket-proxy-hub`, `monitoring`, `alerting`, by external name or `name:`, with or without the `portcullis_` project prefix; a template's own project-scoped networks may use any key), sets `network_mode` to anything but exactly `none`, `host` or `service:<another service of the same template>` (any other value is a network name — `network_mode: portcullis` would put the service on core's internal network, `portcullis-proxy` or another project's network likewise; Docker matches the keywords exactly, so `Host` or ` none` are refused as network names; `container:…` is refused in any case or spacing; `network_mode` together with `networks` is refused), sets `name:` or `external:` on the top-level `networks.default` (any value, even `external: false`: the default network stays the project's own, never `portcullis-proxy` or another instance's), answers to a name ending in `-internal` — a gate's upstream (gated backends sit on the default network only, behind the template's gate) — on any network other than the project's own `default` (service name, `container_name` and `hostname` count on every network the service joins, an alias on its network; case-insensitive, trailing dot ignored; a service under `network_mode` has no DNS name of its own), or answers to a core DNS name (service name, `container_name`, `hostname` or a network alias; also as the first label of a dotted name, case-insensitively): every service name of core's `docker-compose.yml` (`traefik`, `socket-proxy-traefik`, `socket-proxy-hub`, `postgres`, `vault`, `lldap`, `keycloak`, `forward-auth`, `forward-auth-ext`, `group-gate`, `hub`, `enroll`, `domains`, `prometheus`, `alertmanager`, `blackbox`, `textfile-exporter`, `grafana`) and compose's container names for them (`portcullis-<service>-<n>`). Core's monitoring `grafana` is included (the Grafana template's compose service is `dashboards`). Network names, external names, `container_name`, `hostname`, `network_mode` and aliases must be literals (no `${…}` / `$VAR`; `$$` is a literal dollar), except that `hostname` may be exactly `${PORTCULLIS_HOST_<ROUTER>:-<sub>.portcullis.local}` (the §3.1 form) for a hostname variable of the template's own host routers, with a default that isn't reserved; compose `include` and service `extends` are refused. The checks run on the decoded YAML (anchors, merge keys, quoting and escapes resolved), and a present value of an unexpected shape (services, networks or a network's configuration that isn't a mapping with string keys) is refused. Also refused: more than one YAML document in `compose.yml` or `manifest.yaml` (any second document, even an empty one: compose merges documents, the checks read one); `container:` in `pid`, `ipc` or `volumes_from`; `ipv4_address` / `ipv6_address` / `link_local_ips` on a shared (external or named) network such as `portcullis-proxy`; interpolation in any label key or in any `traefik.*` value other than an HTTP router `rule` (the template's own host variables excepted); Traefik label keys with surrounding whitespace or upper case in `traefik.<proto>.<kind>.<name>` (router keys: anywhere); reserved names split by a variable or written with characters that case-fold to them; label keys with non-ASCII characters (Traefik's label decoder compares with Unicode case folding, so `routerſ`, `middlewareſ` or `tlſ` would be read as `routers`, `middlewares`, `tls`); `traefik.*` keys other than `traefik.enable`, `traefik.docker.network` and `traefik.http.<routers|services|middlewares>.<name>.<attribute>`, every part compared case-folded like Traefik's decoder: router attributes `rule`, `entrypoints`, `middlewares`, `service`, `priority`, `tls`, `tls.options`, `observability.*` (no `tls.certresolver` or `tls.domains`: certificates are core's); service attributes only `loadbalancer.server.port`, `loadbalancer.server.scheme`, `loadbalancer.passhostheader`, `loadbalancer.responseforwarding.flushinterval` and `loadbalancer.sticky.cookie[.*]` — a service balances over the labelled container itself, never `server.url` / `servers[n].url` (Traefik would proxy to any address it reaches: the socket proxies, the Hub, Keycloak from the trusted Traefik address), a `serverstransport`, a `weighted` / `mirroring` / `failover` service, or a `healthcheck` (Traefik's own requests, sent from the address core's header-auth services trust, with the template's method and headers, following redirects); middleware types only `addprefix`, `stripprefix`, `stripprefixregex`, `replacepath`, `replacepathregex`, `redirectregex`, `redirectscheme`, `headers`, `compress`, `contenttype`, `chain`, `ratelimit`, `inflightreq` (no `redis.*`), `ipallowlist`, `buffering`, `retry`, `circuitbreaker`, `grpcweb`, each with its own attributes — never `forwardauth`, `errors`, `plugin`, `basicauth`, `digestauth`, `passtlsclientcert`; no `serverstransports`; explicit YAML tags other than the core `!!` ones (compose's `!reset` / `!override`); any `traefik.*` key segment outside `[A-Za-z0-9_-]` with an optional `[n]` (a stray `]` or `[`, or an empty segment, crashes Traefik's label decoder and stops its docker provider) and any name segment outside `^[a-z0-9][a-z0-9_-]*$`; TCP and UDP routing (`traefik.tcp.*`, `traefik.udp.*`); defining a router, service or middleware with a name core uses (core's `@docker` names: `hub`, `keycloak`, `portcullis-auth`, `hub-proxy-secret`, …); a router `service` that isn't a service the template defines itself (`<name>` or `<name>@docker`; never core's, another app's, `@file` or `@internal`), router / chain `middlewares` other than the template's own, `portcullis-auth@docker`, `portcullis-groups@docker` and core's five `@file` middlewares from `traefik/dynamic/middlewares.yml` — `client-headers@file`, `client-cert-pem@file`, `rate-limit@file`, `rate-limit-auth@file`, `security-headers@file` (never an administrator's own objects under `traefik/dynamic/local/`); a reference — router `service`, router `middlewares`, chain `middlewares` — whose key or value isn't lowercase (Traefik reads them case-insensitively, the Hub renames them per instance: both must read the same names); a service name whose container in the template's project (`portcullis-<id>-<service>-<n>`, also `portcullis_<id>_<service>_<n>`) is a core service's (`forward` + `auth` = `portcullis-forward-auth-1`) — for the default instance the template is skipped, for another instance the id is refused; compose keys outside an allowlist (top level: `services`, `volumes`, `networks`, `name`, `x-*`; per service the usual runtime keys — never `label_file`, `deploy`, `annotations`, `env_file`, `build`, `configs`, `secrets`, `profiles`, `links`, …). Templates join core only through `portcullis-proxy`.
- **Image labels.** Docker merges an image's `LABEL`s into its containers' labels. The Hub first runs `compose up --no-start` (containers created, none started) and compares each created container's `traefik.*` label keys (folded like Traefik's decoder) with the keys compose was given (the template's and the Hub override's); any other key takes the project down (volumes kept) and fails the operation (`409`, naming the labels) before anything starts; the same check runs again after the real `up`. Reconcile reports such running containers as exposure drift.
- **Trust model.** A template source is code the admin chose to install: `privileged`, `cap_add`, devices and host networking stay allowed in templates (their own containers). The Hub's checks protect core: routing it can see, no core networks, names or sign-in plumbing, no namespace or volume sharing with other containers. Bind mounts of host paths outside `./templates/<app-id>/` are host-level access, like `privileged`: the Hub doesn't confine them in templates (a template that bind-mounts Docker's volume directory reads core's data), so installing a template source means trusting it with the host. Custom overrides (Expert) are stricter (§5, the allowlist).

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
- **Traefik names per instance.** Traefik's Docker provider merges same-named routers and services across containers, so two instances must never define the same name. For every instance **except the default one**, the Hub's override renames each router, service and middleware the template's labels define from `<name>` to `<instance-id>_<name>`. It also rewrites the references to them in `routers.*.service` and `routers.*.middlewares` (`<name>@docker`). Names the template doesn't define (`portcullis-auth@docker`, `security-headers@file`, …) are kept. The override replaces each labelled service's `labels` with compose's `!override` tag, so no original name survives. Neither instance ids nor v2 template names contain `_`, so the prefix can't be ambiguous. The default instance keeps the template's names unchanged. Every name an instance's Traefik objects use is a name claim (§11.1): two templates whose default instances define the same router, service or middleware name are not both loaded (enabled templates first, then source order), since Traefik would merge them and one app would receive the other's traffic, forward-auth identity headers included.
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
  dashboards:                     # not grafana: core's monitoring service name is reserved (§3)
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
- **Host matching** (**NEW**, policy v5). group-gate takes the request host from `X-Forwarded-Host` (first value), lowercases it, strips a numeric `:<port>` and trailing dots, and looks it up **exactly** (`Grafana-A.Team-A.com.:443` → `grafana-a.team-a.com`). It never falls back to a subdomain-only or parent-domain match: a host with no entry gets `default` and no group, as an unlisted subdomain did before. A host that is not a valid hostname after normalisation is denied, and so is a host Portcullis can't serve: anything that is neither a core host, nor `<label>.<main domain>`, nor an enrolled domain `<d>` or `<label>.<d>` from `extra_domains` (as before, when only `<label>.<main domain>` was served). `extra_domains` entries that are the main domain, a parent of it, a core host or under one (`x.hub.<main domain>`) are malformed (deny).
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
- **Security:** group-gate returns these headers only on **allow** (after auth factors are satisfied). Client copies of `X-Forwarded-Attr-*` headers are stripped by `authResponseHeadersRegex: ^X-Forwarded-Attr-` on **every** forwardAuth middleware in Traefik (Traefik cannot delete headers by prefix in a headers middleware, so each middleware's regex is the mechanism). Routers **without** a forwardAuth middleware in their chain (such as `keycloak`, `enroll-invite`, `headscale`, `netbird`, and `docs`) do not strip these headers, so backends on those routes **must not trust** `X-Forwarded-Attr-*` headers.
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
    - **Forwarding:** Client copies of `X-Forwarded-Attr-*` headers are stripped by `authResponseHeadersRegex: ^X-Forwarded-Attr-` on **every** forwardAuth middleware. Traefik cannot delete headers by prefix in a headers middleware, so the regex on every forwardAuth middleware is the stripping mechanism. Routers **without** forwardAuth in their chain (such as `keycloak`, `enroll-invite`, `headscale`, `netbird`, and `docs`) do not strip these headers, so backends on those routes **must not trust** `X-Forwarded-Attr-*` headers.
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
    - **Second oauth2-proxy (core).** Core runs a second oauth2-proxy service, **`forward-auth-ext`**, that serves extra-domain hosts only. It uses the same Keycloak client (`portcullis-forward-auth`) and the same cookie secret source (`FORWARD_AUTH_COOKIE_SECRET`) as `forward-auth`, a **relative** redirect URL `/oauth2/callback` (resolved against the request host) and a **host-only** cookie named **`__Host-portcullis_ext`** (the `__Host-` prefix: browsers accept it only `Secure`, without `Domain`, with `Path=/`, so a sibling host can't plant or widen it; the CSRF and split-session cookies inherit the prefix). The distinct name keeps it apart from the main domain's `.<main domain>` cookie, which a host under an enrolled subdomain of the main domain also receives. Core defines its forwardAuth middleware **`portcullis-auth-ext`** (`http://forward-auth-ext:4180`) with the same `trustForwardHeader`, `authResponseHeaders` and `authResponseHeadersRegex` as `portcullis-auth`. `forward-auth`, `portcullis-auth`, the `auth.<main domain>` callback and the `.<main domain>` cookie stay exactly as they are.
    - **Certificates.** Traefik serves the enrolled domain's wildcard certificate, picked by SNI, which its HTTP provider fetches from the domains service (§12.4). The Hub assigns a host on an enrolled domain only while that domain is assignable (§12.3).
    - **Sign-in router.** For every extra-domain host on which any of the instance's routers, as rendered (including the `native_login` prepend), uses `portcullis-auth-ext@docker`, the Hub's override adds a router to `forward-auth-ext`. The labels go on the instance's first service, in `compose.yml` order, that has `traefik.enable: "true"`. Example host `grafana.team-b.example.org`, instance `grafana-team-b`, host router `grafana`:

        ```yaml
        traefik.http.routers.portcullis-oauth2-grafana-team-b_grafana.rule: Host(`grafana.team-b.example.org`) && PathPrefix(`/oauth2/`)
        traefik.http.routers.portcullis-oauth2-grafana-team-b_grafana.entrypoints: websecure
        traefik.http.routers.portcullis-oauth2-grafana-team-b_grafana.tls.options: authaware@file   # the host's tier
        traefik.http.routers.portcullis-oauth2-grafana-team-b_grafana.priority: "<above the public router and every router of the instance>"
        traefik.http.routers.portcullis-oauth2-grafana-team-b_grafana.service: forward-auth-ext@docker
        ```

        It is named `portcullis-oauth2-<instance-id>_<host router>` (the original router name, §3.1), carries no middlewares (like core's `oauth2-callback` router on `auth.<main domain>`), and is Host-scoped, so it gets the host's TLS options and core CI's "no host-less router" rule still holds. On extra-domain hosts the path prefix `/oauth2/` belongs to Portcullis: a `multi` template must not serve its own paths there. Router names starting with `portcullis-oauth2-` are reserved for the Hub.
    - **Callback and cookie.** On an extra-domain host the callback is `https://<host>/oauth2/callback` (served by `forward-auth-ext` through the sign-in router) and the session cookie is the host-only `__Host-portcullis_ext`. On main-domain hosts nothing changes: `forward-auth`, callback `https://auth.<main domain>/oauth2/callback`, cookie for `.<main domain>`. The user's Keycloak session at `auth.<main domain>` makes the extra-domain sign-in a silent redirect (no key touch) unless the instance's policy needs a stronger factor than the session has.
    - **Callback redirect URIs.** The Hub keeps `https://<host>/oauth2/callback` for every extra-domain host with a sign-in router in the redirect URIs of core's Keycloak client `portcullis-forward-auth` (shared by both oauth2-proxy services). It adds and removes only such entries (Keycloak has no wildcard host matching), on enable, hostname change, disable and delete, and when an enabled instance's sign-in mode changes (gateway ↔ native, `auth.native_login`): the change takes the instance's lock (`409` busy while another operation on it runs), the Keycloak update comes first, and a failure is a `502` with nothing changed. A failed enable removes the callbacks it added. Core's `./portcullis keycloak configure` keeps redirect URIs of that form that it didn't set itself, and the Hub's access sync loop (§8) re-asserts the running instances' callbacks.
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

The Hub reads `DOCKER_HOST` for both the `docker compose` CLI (only `up`/`down`) and its own Engine API calls (status, logs, exec, events, and for instance backups (§11.5): volume list / inspect / create / remove, image pull of the helper image, container create / remove and the archive endpoints `GET`/`PUT /containers/{id}/archive`). The Hub never starts a helper container: the daemon reads and writes the mounted volume itself. `CONTAINERS`, `IMAGES`, `VOLUMES` and `POST=1` above cover it, plus `ALLOW_ARCHIVE=1`: the proxy denies `/containers/{id}/archive` without it (the Hub's exec rights already reach any container's files, so it adds no new kind of access). Core CI checks that only the two proxies mount the socket and that each proxy network has exactly its two members. See [Security & Hardening](../operations/hardening.md#docker-socket-proxies).

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
- **Access role (NEW, instances).** A native-OIDC app that can't restrict sign-in to its access group itself lets every realm user in, and with several instances team B could open team A's. The Hub enforces the group in Keycloak for every instance whose template has `auth.method: native-oidc`, an `access_group`, and either `group_access: false` or `auth.keycloak_access_role: true` (a native-oidc template with `group_access: false` must declare an `access_group`; the Hub rejects it otherwise):
    - each of the instance's clients gets the client role `access`; exactly the instance's access group (the realm group core's LDAP group mapper imports from LLDAP) has it — other groups, direct user grants and composite roles containing it (e.g. `default-roles-portcullis`, or another client's role) lose it. A group Keycloak hasn't imported yet is imported with the mapper's "sync LDAP groups to Keycloak"; if LLDAP doesn't have it either, the client denies everybody until it exists.
    - the client's browser flow override is a Hub-managed flow `portcullis-client-access-<clientId>-<random>`. At its top level: a REQUIRED sub-flow with a copy of the realm's browser flow (core's `portcullis-universal`, without the identity-provider redirector); a CONDITIONAL sub-flow `<top>.member` — "Condition - user role" `<clientId>.access` → "Allow access"; a CONDITIONAL sub-flow `<top>.deny` — "Condition - sub-flow executed" (`<top>.member`, `not-executed`) → "Deny access". The check runs after every sign-in path, the SSO cookie included, and fails closed: a deleted `access` role (Keycloak's role condition is false for a role that doesn't exist) or a renamed member sub-flow skips the member check, and the deny fires.
    - the Hub reads the bound copy back on every sync and compares it with what it would build from the realm's current browser flow (structure, requirements, aliases, authenticator configs). When core rebuilds its browser flow, or someone edits the copy, the Hub builds a fresh copy (with its own configs), rebinds the client and deletes the old one.
    - direct access grants, implicit flow, service accounts, device and CIBA grants and standard token exchange are switched off on **every** client of such an instance — only the browser flow signs in. A template that needs any of them on its client can't use the access role.
    - Set up on enable (the Hub refuses to start the app if it can't), kept consistent after directory changes and every 10 minutes, removed on delete (§11.4 step 4) and when the template stops needing it (only the role the Hub created).
    - **Residuals.**
        - Keycloak checks the role at sign-in only, never at token refresh. Removing a member through the Hub (Users & Groups, rule evaluator, expiry, user delete) signs them out of Keycloak (`POST /users/{id}/logout`): that ends their sessions and sets the user's not-before, which Keycloak checks on every refresh, offline tokens included. Issued access tokens stay valid until they expire (5 minutes). Changes made directly in LLDAP sign nobody out: sessions and refresh/offline tokens live until they expire (the next sign-in is denied).
        - Invite links. Keycloak's broker endpoint finishes a brokered login through the invite IdP's post-broker flow (`portcullis-invite-session`), not the client's browser flow, so core restricts that flow to the one client setup links use: it admits only clients that have the marker client scope `portcullis-invite-client` as a default scope (`Condition - client scope`, not negated), then denies everything that check did not admit (`Condition - sub-flow executed`, `not-executed` → `Deny access`), so a missing scope or sub-flow denies too. It then records the session's LoA like the browser flow does for a passkey: LoA 1 (sub-flow `portcullis-invite-loa-1`) and LoA 2 (`portcullis-invite-loa`), amr `hwk` — so an mtls step-up right after a setup link asks only for the client certificate. `./portcullis keycloak configure` creates the scope (no mappers, not in tokens) and keeps it a default scope of `portcullis-forward-auth` only: it removes it from every other client and from the realm's default scopes. An unused link therefore can't sign in to an access-role app; it can still only do what it always could on `portcullis-forward-auth` (and so `forward-auth-ext`), where group-gate checks the groups. The Hub must never attach `portcullis-invite-client` to a client.
        - Token exchange is off on the instance's clients only. Another client with standard token exchange on and an audience mapper adding this client could exchange a user's token for one this client accepts, without the role check. The Hub creates no audience mappers; don't add them for such clients.
        - A realm admin can still open the client (remove the browser flow override; Keycloak then uses the realm's browser flow) until the Hub's next sync rebinds it. Keycloak refuses to delete a flow a client override binds.
- **Backchannel logout (NEW).** A `keycloak_clients[]` entry with `backchannel_logout_url` (`https://{{HOST_<ROUTER>}}/<path>`) gets it as the client's backchannel logout URL, with "backchannel logout session required" on; it moves with hostname changes (§11.3). Keycloak then POSTs a logout token there whenever a session ends, so the app ends its own session. The path must be reachable from Keycloak without forward-auth. Supported upstream by Nextcloud `user_oidc` (`/index.php/apps/user_oidc/backchannel-logout/<provider>`) and Synapse (`/_synapse/client/oidc/backchannel_logout`, `backchannel_logout_enabled: true`).

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
- **Collisions are refused** (`409`) before anything is created: a compose project, volume name, Keycloak client id or group name (case-insensitive) derived from the id (§11.2) that already exists and doesn't belong to this instance, or that equals a name the **default instance of any template of any source** would use (its volumes — `portcullis_<key>` for `multi`, a `single` template's declared names —, manifest `client_id`s, `access_group`, `admin_group` and Traefik names), enabled or not. The ids of instances whose template is missing keep `portcullis_<id>-*`, `<id>-*` and `<id>_*` reserved; an enabled instance whose template is missing also keeps the volume names, Keycloak client ids and Traefik names of its published snapshot. In the catalog, enabled templates claim volume and Traefik names first, then templates whose default instance has any other state (settings, policies, public access, sign-in mode, published snapshot, ops record), then the rest in source order. Creating an instance (and restoring into a new id) also lists the Docker volumes: an existing volume with one of the new instance's volume names, or labelled with its compose project, is a `409` — a new instance never adopts a deleted instance's leftover or anyone else's volume.
- **`instances: single`** templates have only the default instance (§3.1).

### 11.2 Derived names

| What | Default instance (id = template id) | Other instance `<id>` |
|------|-------------------------------------|-----------------------|
| Compose project | `portcullis-<template>` | `portcullis-<id>` |
| Hub files | `<data>/env/<template>.env`, `<data>/overrides/<template>.override.yml`, `<template>.user.yml`, `<data>/ops/<template>.json` | the same with `<id>` |
| Volume `<key>` | `multi`: `portcullis_<key>`; `single`: its declared `portcullis_<template-id>[-_…]` name, else `portcullis-<template>_<key>` | `portcullis_<id>-<key>` |
| Traefik routers, services, middlewares the template defines | the template's names | `<id>_<name>` (§3.1) |
| Public router / strip middleware | `portcullis-public-<template>`, `portcullis-public-strip-<template>` | `portcullis-public-<id>`, `portcullis-public-strip-<id>` |
| Keycloak clients | the manifest's `client_id`s | first `keycloak_clients` entry: `<id>`; each further entry: `<id>-<manifest client_id>` |
| Access group | manifest `access_group` | `users_<id>` |
| Admin group | manifest `admin_group` | `admin_<id>` |
| `PORTCULLIS_INSTANCE` | `<template>` | `<id>` |

- The Hub's override sets every volume's `name:` from this table for `multi` templates (which declare none), default instance included; a `single` template's volumes keep what compose names them.
- Creating an instance generates fresh values for every `generate: random` env entry, and creates `users_<id>` (if the manifest has `access_group`) and `admin_<id>` (if it has `admin_group`) in LLDAP as empty manual groups. The Hub tags each Keycloak client with the **instance id** that owns it and reconciles only clients with its own tag.
- **Enabling** an instance (`POST /api/templates/enable`, the default instance included) first creates its missing access / admin groups, but only derived names: `users_<id>` / `admin_<id>` for an instance; for a default instance the manifest's `access_group` / `admin_group` when they are exactly `users_<template>` / `admin_<template>`. They are created through the Users & Groups guardrails (`CreateGroup`, audited as `group.create`) as the enabling admin, who must resolve as an LLDAP administrator before anything is created. Existing groups are left alone; a missing group with any other name is never created (a warning). A failure creating a group leaves the instance not enabled (groups created before it stay). Without an `X-Forwarded-User` or without Users & Groups nothing is created (a warning). The answer is `{"status": "enabled", "id", "groups_created": [...], "warnings": [...]}`. A missing access group only ever denies (§8, fail closed).
- Settings, auth policies, public exceptions and share tokens, sign-in mode, the fail-closed `published` snapshot, ops records and drift are keyed by instance id.
- **Instance states.** `created` (exists, never started: `POST /api/instances` creates without enabling), `enabled` (the project is up), `disabled` (stopped, everything kept), `deleting` (a guarded delete started and hasn't finished, §11.4), `restoring` (a restore started and hasn't finished — same instance, or a new id being restored into, §11.6), `error` (the last lifecycle operation failed; its ops record says why).

### 11.3 Hostnames

- **Pre-filled.** For a new instance on domain `<domain>`, each host router with default subdomain `<sub>` (§3.1) gets `<sub>-<suffix>.<domain>`, where `<suffix>` is the instance id without a leading `<template>-` (the whole id if it has no such prefix). If the label `<sub>-<suffix>` would be longer than 63 characters, the suffix is truncated to fit (a trailing `-` dropped); if the hostname is then still not a valid hostname (§4), creation is refused with an error that names the host router and asks for an explicit hostname. `grafana-team-a` on `portcullis.example.com` → `grafana-team-a.portcullis.example.com`; an instance `litellm-lab` → `llm-lab.<domain>`. The default instance's hostnames are `<sub>.<main domain>`. Every hostname is individually editable.
- **Immutable hostnames.** A host router listed in the manifest's `hosts.immutable` (e.g. Synapse's `server_name`) keeps the hostname the instance was created with: creating an instance (or restoring into a new id, §11.6) may set it, every later change is refused (`409`), the default instance's too. The default instance's immutable hosts start as `<sub>.<main domain>` and are **pinned in `state.yaml` on its first enable**. A later change of Portcullis's main domain never moves them: the instance keeps its old hostnames and is listed as `error` (fail closed, through its published snapshot) until the old domain is enrolled as an extra domain (§12) or the hostnames are fixed — their data is bound to the old name.
- **Valid hostnames.** A hostname is a valid hostname (§4) and either lies on an **assignable** enrolled domain `<d>` (§12.3) — `<d>` itself or `<label>.<d>`; enrolled domains never nest (§12.3), so at most one matches — or, if it is at or under no enrolled domain, is a main-domain host `<label>.<main domain>`. `<label>` matches `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`. Deeper names are refused: the wildcard certificates cover one label. An enrolled subdomain of the main domain (e.g. `team-a.<main domain>`) is assignable as its own apex only as an extra-domain host, on that enrolled domain.
- **Refused before anything changes** (`400` invalid, `409` collision): a hostname that is invalid, on a domain that isn't enrolled or isn't assignable, a core host (§4), used by any other instance (enabled or not), still routed by another instance's running compose project (the Hub's runtime view; `409` "still routed by the running project of `<id>` — restart or stop it first"), or used twice within the instance. Templates still using `${PORTCULLIS_DOMAIN}` rules (§3.1) can't change hostnames at all (`409`).
- **Hostnames a router can't serve** are a `400` at create, hostname change and restore into a new id (not only at enable): a router whose hosts mix main-domain and extra-domain hostnames, and a router on extra-domain hosts that reaches `portcullis-auth` through the template's own chain middlewares (nested chains included, with or without `@docker`). The extra-domain sign-in (§5) swaps only a `portcullis-auth@docker` (or bare `portcullis-auth`) listed on the router itself, so templates list it on the router, never inside a chain.
- **A change applies immediately.** In order:
    1. **Validate** (the refusals above): nothing has changed yet.
    2. **Keycloak**: the instance's clients' redirect URIs and web origins, and the `portcullis-forward-auth` callback URIs (§5), are updated for the new hostnames.
    3. **Env and override**: the instance's `.env` and compose override are regenerated with the new hostnames.
    4. **Save state — the commit point.** The Hub records the new hostnames in its state. A failure before this step leaves the recorded hostnames, the policy file and the routing as they were; retrying the change reconciles Keycloak, env and override.
    5. **Policy**: the policy file and `portal-apps.json` are rewritten (the old hostnames vanish from them at once).
    6. **Restart** the instance (`compose up`).

    Public share links keep their tokens and move to the new host. **There are no redirects:** the old hostnames stop routing. A step that fails after the commit point is reported like any lifecycle operation (`OpError`, op `hosts`), and the instance is reconciled by retrying the change: the same hostnames again re-apply every step while the last **hostname-change** record (`<data>/ops/<id>.hosts.json`, kept apart from the instance's other op records) is a failure — another operation in between doesn't hide it.
- Audited as `instance.update` with the old and new hostnames.

### 11.4 Guarded delete

Deleting an instance is permanent and needs the instance id typed: `{"confirm": "<instance-id>"}` (missing or different: `400`). The acting admin must resolve as an LLDAP administrator (it deletes the groups); otherwise the delete is refused before step 1. The Hub:

1. **Takes a backup** (§11.5, reason `delete`). If it fails, the delete stops and nothing is removed.
2. Records `deleting` (and the backup path) in its state and marks the instance disabled. From here on the instance is listed as **partially deleted** until the delete completes, and the only action offered is Delete (retry).
3. Stops and removes the project (`down --remove-orphans`), marks it disabled (the policy file drops it), then removes its volumes: the volumes compose labelled with the project (`com.docker.compose.project=portcullis-<id>`); external volumes aren't the instance's and are never removed.
4. Removes its access roles and access flows (§8 "Access role"), deletes its Keycloak clients (only clients tagged with this instance; any other is kept with a warning) and the callback URIs of its hosts on `portcullis-forward-auth`.
5. Deletes its access and admin groups through the Users & Groups guardrails (`DeleteGroup` as the acting admin, which also purges the group from `directory.yaml` and signs former members out) — only groups named exactly `users_<id>` / `admin_<id>`. Kept, with a warning: a group with any other name (a manifest's own group of a default instance), a built-in, administrator, permission or rule group, and a group another instance or another template's default instance also uses (templates may share a group). Without Users & Groups (no LLDAP credentials) the groups stay, with a warning. Without Keycloak configured step 4 is a warning. An instance whose template is missing and whose snapshot lists no clients gets its derived first client id (`<id>`) deleted, with a warning.
6. Removes its env file, overrides, ops record, generated secrets, share tokens and state entry, and rewrites the policy file and `portal-apps.json`.

Every step is idempotent. A failure after step 2 is reported like a lifecycle failure (`OpError`, op `delete`); the instance stays `deleting` (enable, drift start/apply, settings, env, custom override, hostname changes, backup and same-instance restore are refused with `409`). A retry skips step 1 (the first backup is kept) and continues where the last attempt failed. Backups are not removed with the instance: they stay listed (`GET /api/backups`) and can be restored into a new instance (§11.6). Audited as `instance.delete` with the backup path. Disabling an instance stops it and keeps everything, except the callback URIs of its extra-domain hosts on `portcullis-forward-auth` (enable adds them back); its Keycloak clients and access role stay (the access role keeps denying sign-in to anyone outside the access group).

The **default instance** can be deleted the same way. That removes the manifest's `access_group` and `admin_group` (by convention `users_<template>` / `admin_<template>`) through the same guardrails; the template stays in the catalog and enabling it again creates a fresh default instance.

### 11.5 Backups

- **When.** On demand (`instance.backup`), before every delete and before every restore.
- **Path.** `<data>/backups/<instance-id>/<UTC timestamp>.tar`, the timestamp as `YYYYMMDDTHHMMSSZ` (e.g. `<data>/backups/grafana-team-a/20261102T153000Z.tar`). Written to a temporary name and renamed when complete; files `0600`, directories `0700`, owned by the Hub (uid 10001). Never pruned automatically.
- **Consistency.** A running instance is stopped (`compose down`, volumes kept) while its volumes are copied, then started again (not for the backups a delete or restore takes), so databases — SQLite included — are copied at rest. Manifests have no field marking database files, and none is needed while the app is down. A failed backup writes no archive and starts the instance again.
- **Free space.** A backup needs at least 64 MiB free on the Hub's data volume before it starts (otherwise `507` and nothing is stopped), and the staged size plus 64 MiB before the archive is assembled (otherwise `507` after the volumes were copied: no archive is written and a manual backup starts the instance again, as after any failed backup); staging an archive for a restore needs its size plus 64 MiB (otherwise `507` before anything changes).
- **Leftovers.** At startup the Hub removes helper containers (label `io.portcullis.hub.helper`), staging directories and `.partial` archives an interrupted backup or restore left behind.
- **Helper.** Volume I/O goes through a helper container per volume, through the Hub's socket proxy (§6): image `alpine:3.24.3@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a` (the same pin as core's `PORTCULLIS_HELPER_IMAGE`), pulled if missing, **created but never started** — the daemon itself reads (`GET /containers/{id}/archive?path=/data`) and writes (`PUT …?path=/` with `noOverwriteDirNonDir`, owners as archived) the one volume it mounts at `/data` (no copy-up). It has no network (`none`), every capability dropped, `no-new-privileges`, uid 65534, a pids and memory limit, and is removed afterwards. Backup helpers mount the volume read-only and have a read-only rootfs; restore helpers need a writable rootfs, because the daemon refuses an upload to `/` of a read-only rootfs and only an upload to `/` applies the volume root's own owner and mode. Restore replaces a volume's contents by removing it and creating it again with the same driver and labels — only plain `local` volumes without driver options (a bind or NFS device's data would survive the remove; otherwise `409`).
- **Layout** (an uncompressed tar):

    ```text
    MANIFEST.json
    config/instance.yaml       # the instance's state entry: template, hostnames, settings, auth policy,
                               # public exceptions and share tokens, sign-in mode, published snapshot
    config/env                 # <data>/env/<instance-id>.env (generated secrets included)
    config/override.yml        # the Hub override as last applied
    config/user.yml            # the custom override, only if there is one
    volumes/<volume key>.tar   # one inner tar per volume as the daemon's archive endpoint writes it: entries
                               # "data/" (the volume root) and "data/…"; numeric uid/gid, modes and mtimes preserved
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

    `reason` is `manual`, `delete` or `restore`; `volumes` maps each volume key to the volume name it was copied from (the volumes compose labelled with the instance's project; an instance that never ran has none); `template_commit` is the template checkout's git commit and is left out when unknown. Members are written with mode `0600`. `config/instance.yaml` holds `id`, `template`, `default`, `hosts`, `enabled`, `settings`, `auth_policy`, `public_access`, `public_mode`, `public_tokens`, `sign_in` and `published`.
- **Offsite.** Core's `./portcullis backup` archives the `hub_data` volume, so `<data>/backups/` is included (and shipped with `--offsite`).
- The archive contains the instance's generated secrets in clear; it is protected like the rest of `hub_data`.

### 11.6 Restore

A backup restores into the **same** instance (replacing its data) or into a **new** instance id. Audited as `instance.restore` with the archive and the target.

- **Checks first, nothing changes on failure:** `MANIFEST.json` is the first member and its `version` is 1; every listed file is present once, as a regular file, with a matching sha256 and there are no unlisted files; every volume archive's entries lie under `data/` (no `..`, no device files, hard links inside the volume); `config/instance.yaml` names the manifest's instance and template (any mismatch: `409`, refused). The archive's settings, sign-in mode, policy override and public exceptions must pass the same checks as saving them in the Hub's settings, against the template as it is now (`409` listing every problem). The archive is unpacked to a staging directory under `<data>/backups/.staging/` and verified there before anything else happens. The template exists and has every archived volume key. For a new id: the id rules and collisions of §11.1 (Docker volumes included), the template must be `multi`, and the hostnames (below) must be placeable and free, validated like a create (§11.3).
- **Same instance** (`POST /api/instances/{id}/restore`). The Hub takes a backup (reason `restore`) and stops the instance. It replaces every volume's contents, the env (`config/env`), the custom override (`config/user.yml`, removed if the archive has none) and the instance's state from `config/instance.yaml`, **except its hostnames: the current hostnames are kept**. The Hub override is **regenerated**, not restored (`config/override.yml` is informational). Before the first destructive step the Hub records `restoring` with the pre-restore backup in its state and marks the instance disabled; while `restoring` the instance is refused like a `deleting` one (`409`) and listed with state `restoring`. A restore the Hub didn't finish (it stopped half-way) is rolled back from that pre-restore backup at the next start or by the next restore of the instance — only if the recorded archive is the instance's own pre-restore backup (its directory and manifest name the instance, its template is the instance's, its reason is `restore`) and verifies; otherwise `409` and nothing is touched. The record is cleared when the restore or the rollback completes (an instance that was `created` stays `created`); a failed save of that is reported as a warning. Deleting a `restoring` instance warns with the pre-restore backup's name. A restored policy is stored normalised (a legacy factor rewritten, never weaker); public exceptions that can't be routed are refused like on save. The project's volumes the archive doesn't have are emptied (warning; their data is in the pre-restore backup). Then, if it was enabled, the Hub enables it again exactly like an enable (the Keycloak clients with the restored secrets, access role, forward-auth callback URIs, policy file and `portal-apps.json`, `compose up`); a disabled instance stays disabled. If any step fails, it puts the pre-restore backup back the same way (volumes it lacks are emptied) and reports the failure (`OpError`, op `restore`, `rolled_back: true`): the instance's previous data is kept.
- **New id** (`POST /api/instances/restore`), from any listed archive, including one of a deleted instance; the deleted instance's id may be reused. The Hub creates the instance from the archive's config with: the hostnames given in the request's optional `hosts`, otherwise the archive's hostname for each `hosts.immutable` router (an immutable router given a different hostname is a `409`) and the new id's defaults on the main domain (§11.3) for every other router, new empty groups `users_<id>` / `admin_<id>` (created through the Users & Groups guardrails; an existing group is kept with a warning — its members get access), new volumes (labelled with the new project) filled from the archive, the archive's settings, policy, public exceptions and share tokens, sign-in mode, custom override and env with the instance variables rewritten, except each Keycloak client's `secret_env`, which is regenerated. Its Keycloak clients are created when it is first enabled, as for any instance. `type: path` settings keep the same host path: the result warns that the two instances share that directory. The acting admin must resolve as an LLDAP administrator before anything is created. A volume is only filled if it really is new (it must not exist before, and must carry the new project's labels after creation). Setuid/setgid bits and every other mode bit are restored as archived (archives are written by the Hub). A failure after the instance was created removes it again (state, files, the volumes and groups it created). While it runs the new instance is in state `restoring` (`restore_as: <archive>` in `state.yaml`), and `created` (not started) once it completes — it is never started on its own: an admin enables it (which also creates any of its groups still missing); a restore into a new id that the Hub didn't finish is removed at the next Hub start (project volumes, files, per-instance state and the entry; the groups it may have created stay and are logged, as there is no acting admin at start-up).

### 11.7 Hub API and audit

Instance and domain operations live on the Hub listener only (never on the people listener, §5.1), are **admin-only** (`lldap_admin`; delegates get `403`) and pass the proxy-secret and CSRF guards. Each one is appended to `audit.jsonl` (§9.5) as one of `instance.create`, `instance.update`, `instance.delete`, `instance.backup`, `instance.restore`, `domain.enroll`, `domain.token`, `domain.delete`, with `result` `ok`, `refused` or `error`. DNS credentials never appear in audit entries, logs, errors or responses.

| Route | Body | Does |
|-------|------|------|
| `GET /api/instances` | — | Every instance (shape below) |
| `POST /api/instances` | `{"template": "grafana", "id": "grafana-team-a", "hosts": {"grafana": "grafana-team-a.portcullis.example.com"}}` | Create without enabling (state `created`; §11.1–11.3) and its empty groups `users_<id>` / `admin_<id>` through the Users & Groups guardrails as the acting admin (who must resolve as an LLDAP administrator before anything is created; an existing group is kept with a warning; a failure creating a group removes the instance again); `hosts` omitted = the defaults on the main domain; `201` with the instance plus `"warnings": [...]` |
| `GET /api/instances/defaults?template=<t>&id=<id>&domain=<d>` | — | For the hostname editor: `{"template", "id", "domain", "multi", "legacy", "routers": [{"router", "subdomain", "immutable"}], "domains": [{"name", "main", "state", "assignable"}], "hosts": {"<router>": "<pre-filled hostname>"}}` — the main domain first, then the enrolled domains (`assignable` only when `ready`); `hosts` are the pre-filled hostnames of `id` on `domain` (default: the main domain; §11.3), empty for an invalid id; an unknown `domain` is `400` |
| `PUT /api/instances/{id}/hosts` | `{"hosts": {"<host router>": "<hostname>"}}` | Change hostnames (§11.3); `200` with the instance |
| `DELETE /api/instances/{id}` | `{"confirm": "<id>"}` | Guarded delete (§11.4), in the background: `202` (below); result `backup` (the delete's archive) |
| `GET /api/backups` | — | Every archive under `<data>/backups/`, deleted instances' included (shape below) |
| `GET /api/instances/{id}/backups` | — | The same, for one instance id |
| `POST /api/instances/{id}/backups` | — | Back up now (§11.5), in the background: `202`; result `archive` |
| `POST /api/instances/{id}/restore` | `{"archive": "grafana-team-a/20261102T153000Z.tar"}` | Restore into the same instance (§11.6); the archive must belong to `{id}`; in the background: `202`; result `archive`, `pre_restore_backup` |
| `POST /api/instances/restore` | `{"archive": "grafana-team-a/20261102T153000Z.tar", "id": "grafana-team-c", "hosts": {"grafana": "grafana-team-c.portcullis.example.com"}}` | Restore into a new instance (§11.6); `hosts` optional (omitted routers: the archive's hostname for `hosts.immutable` routers, else the new id's default); in the background: `202`, the op record is the new id's; result `archive`, `instance` |
| `GET /api/instances/missing-groups` | — | Enabled instances whose access / admin groups are missing in LLDAP: `{"instances": [{"instance", "creatable": [...], "other": [...]}], "error"?}` — `creatable` are the derived names enable would create (§11.2), `other` any other name (create it in Users & Groups); `error` when Users & Groups didn't answer |
| `POST /api/instances/missing-groups` | `{}` (every enabled instance) or `{"ids": ["<id>", …]}` | Create the `creatable` groups as the acting admin (§11.2; actor resolved first, else nothing is created); `200` `{"results": [{"instance", "created", "warnings", "error"}]}` — a busy, unknown or disabled instance is reported in its row |
| `GET /api/keycloak/user-sweep` | — | The guarded stale-record cleanup: `{"configured", "paused", "reason", "paused_at", "skipped", "last_ok_count", "last_ok_at", "last_run_at", "resumed_by", "resumed_at"}` — paused when LLDAP lacks `admin` or the Hub's service account or its user count dropped > 20 % and > 2 since the last successful run; skipped while LLDAP or Keycloak is unreachable |
| `POST /api/keycloak/user-sweep/resume` | `{"confirm": "resume"}` | Resume a paused cleanup as the acting admin (LLDAP administrator); LLDAP's current user count becomes the baseline; audited `keycloak.sweep_resume`; `409` when not paused |
| `GET /api/instances/{id}/op` | — | The instance's op record (below), also of a deleted instance or of the new id of a restore; `404` when none was recorded |
| `GET /api/domains` | — | The domains service's list (§12.2), passed through; `503` with `{"error": "…", "domains": [<last known list>]}` while it is unreachable, plus `"disabled": true` without a readable secret file |
| `POST /api/domains` | `{"name": "team-b.example.org", "provider": "cloudflare", "credentials": {"api_token": "…"}}` | Enroll (§12.3); `202` with the domain object |
| `POST /api/domains/{name}/token` | `{"provider": "cloudflare", "credentials": {…}}` | Replace the credentials; `202` with the domain object |
| `DELETE /api/domains/{name}` | — | Remove; `204`, or `200` with the service's `{"warning"}`; `409` while any instance uses the domain |

`archive` is always `<instance-id>/<timestamp>.tar`, relative to `<data>/backups/`; anything else is `400`. Errors are plain text, or for a failed lifecycle step (`OpError`) JSON `{error, op, output, hint, rolled_back}`; `409` covers refusals and a busy instance (another operation holds its lock), `507` too little free space (§11.5). Bodies are strict JSON (unknown fields: `400`).

**Long operations run in the background.** Backup, restore, restore into a new id and delete can take minutes (stopping the instance, copying volumes), longer than a request may stay open through Traefik (its entrypoints keep the default timeouts). The Hub answers `202` with `{"op_id": "<16 hex>", "op": "backup|restore|delete", "instance": "<id>", "poll": "/api/instances/<id>/op"}` once the request is validated, the acting admin resolved and the instance's lock acquired; refusals before that are synchronous as above (bad body or archive name `400`, delete without the typed id `400`, busy `409`, unknown instance `404`, missing archive `404`, restore into an id that exists `409`, an actor that isn't an LLDAP administrator). The operation keeps the instance's lock until it ends, so another request on the instance meanwhile is `409` busy. Verifying the archive is part of the background work: a refusal there is the operation's failure, with nothing changed. Progress and outcome are the instance's op record (`<data>/ops/<id>.json`, also `GET /api/templates/lastop/{id}` while the instance exists): `{"op", "op_id", "at", "running": true}` while it works (`at` = start), then `{"op", "op_id", "at", "ok", "error", "status", "output", "hint", "rolled_back", "result": {…}, "warnings": [...]}` — `status` is the HTTP status the failure stands for (`409`, `507`, …), `result` the archive names / new instance id listed per route above. A client polls until `op_id` is its own and `running` is false. A deleted instance's record is kept (its id may be reused).

**Shutdown and interruption.** On shutdown the Hub waits up to about 50 s for running backups, restores and deletes (core gives the Hub container `stop_grace_period: 60s`). An op record still `running` when the Hub starts is rewritten as `ok: false`, `status: 500`, error `interrupted: …`. A `running` record is no failure: it doesn't count as a failed operation and doesn't put the instance in state `error`.

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

`state` is one of `created`, `enabled`, `disabled`, `deleting`, `restoring`, `error` (§11.2); `hosts` is keyed by the original host-router name (§3.1).

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

### 11.8 Template source sync (core ⇄ Hub)

- **When.** The Hub fast-forwards every git source it cloned (`git pull --ff-only`) at every start, before its first policy write; on `SIGHUP`; and on `POST /api/sources/sync`. Syncs run one at a time.
- **Fail-safe.** A failed pull leaves the checkout unchanged. If a source's new commit leaves an enabled instance without a valid template, the source is reset to its previous commit (`git reset --keep`) and reported as kept. A sync never opens access: an enabled instance whose template is missing stays denied (§4, published snapshot).
- **Status.** `<data>/source-sync.json` (and `GET /api/sources/sync` → `{"last": …}`), written when a sync starts (`running: true`) and when it ends:

    ```json
    {"trigger": "signal", "running": false, "started_at": "…", "finished_at": "…", "started_unix": 1793645564, "finished_unix": 1793645566,
     "ok": true, "sources": [{"name": "portcullis", "ok": true, "before": "<commit>", "after": "<commit>", "updated": true}],
     "missing_templates": []}
    ```

    `trigger` is `startup`, `signal` or `api`; a source's `error` is fixed text (never git output); `rolled_back` / `rolled_back_for` mark a reset version; `missing_templates` lists enabled instances still without a valid template.
- **Core.** `./portcullis upgrade` reads the file (`docker compose exec hub cat /data/source-sync.json`). Only when it was written since the running Hub container started (an older Hub never writes it, and would exit on `SIGHUP`) it sends `SIGHUP` (`docker compose kill -s HUP hub`), waits for a status with `started_unix` ≥ the time it signalled and `running: false`, and prints each source's result. It never fails the run.

## 12. Domains service (core ⇄ Hub ⇄ Traefik) — NEW (domains API)

Extra domains and subdomains (e.g. `team-b.example.org`, `team-a.portcullis.example.com`) are enrolled by Hub admins. A new core service, **`domains`**, owns their DNS credentials, creates their records, and obtains and renews a wildcard certificate per domain. The main domain is not handled by it: it keeps Traefik's built-in resolver and `./portcullis dns setup`.

### 12.1 Service, network and secrets (core)

- **Service.** `domains` (Go: `github.com/go-acme/lego/v4` as a library for ACME DNS-01, `github.com/libdns/<provider>` for records, `filippo.io/age` for encryption at rest). It listens on `:8080` on the internal network `portcullis-domains`, whose only members are `domains` and the Hub; it reaches ACME and the DNS providers over a separate network with internet access (`domains-egress`, its only member). Traefik never routes it. Image `portcullis-domains` (built locally from core's `domains/`), uid/gid 10004, read-only root filesystem, plus group 10001 to read the API secret it shares with the Hub.
- **Volumes.** `domains_data` (domains only, read-write): encrypted credentials, ACME account, per-domain state, issued certificates — all in one age-encrypted file (`store.age`, written to a temporary name and renamed, mode 0600). No volume is shared with Traefik: it fetches the certificates over HTTP (§12.4).
- **Certificate endpoint network.** `portcullis-certs` (`internal: true`), whose only members are `domains` and Traefik (CI checks the membership, like the socket-proxy networks); the Hub is not on it. It is defense in depth: the certificate endpoint (§12.4) requires a client certificate on every interface it listens on, so reaching the port is never enough.
- **API secret.** `secrets/domains/api-secret` (≥ 32 characters, generated by `./portcullis init` / `up`), mounted read-only into `domains` and into the Hub, group 10001, mode 0640. Never an env var.
- **Encryption key.** `secrets/domains/age.key` (an age X25519 identity, generated by `init` / `up`), mounted read-only into `domains` only.
- **Configuration.** `PORTCULLIS_DOMAIN` (the main domain), `ACME_EMAIL` and `ACME_CA_SERVER` (as for Traefik's resolver), and the server's public IPv4 and, when present, IPv6 (`DOMAINS_PUBLIC_IPV4` / `_IPV6`). They reach the service through `secrets/domains/public-ips.env` (mode 0600, compose `env_file` with `required: false`, so compose ≥ 2.24), which `./portcullis init` / `up` / `upgrade` write; a manual `docker compose up` uses the same file.
    - **Public addresses (fail closed).** An explicit `PORTCULLIS_PUBLIC_IPV4` / `_IPV6` (environment or `.env`; an empty `_IPV6` means "no IPv6") always wins. Otherwise `./portcullis up` (and `dns setup`, through the same helper) detects them over HTTPS only (`--proto =https --tlsv1.2`), requires at least two independent services to answer and all answers to agree, and accepts only global unicast addresses (no private, shared, loopback, link-local, documentation, benchmark, multicast or reserved ranges). Anything else gives no address: without an IPv4 the service publishes no record and sets the domain's `last_error`; without an IPv6 it publishes no AAAA (and removes existing AAAA records at `<d>` / `*.<d>`).
    - A detection that ran and failed keeps the last detected address (`secrets/domains/last-public-ipv4` / `last-public-ipv6`; only then — skipped lookups never use it), because "no IPv6" removes the AAAA records; an explicit empty `PORTCULLIS_PUBLIC_IPV6=` still means none. The service records the addresses it last set; records set to other addresses than the configured ones are redone at start.
    - **No lookups with nothing enrolled.** `./portcullis` skips both detections while the running domains service reports no enrolled domain (`domains enrolled`); when it can't tell (not running), the lookups run. With nothing enrolled, **no address is published** to the service unless `.env` sets `PORTCULLIS_PUBLIC_IPV4` / `_IPV6`. So the first enrolled domain may need one more `./portcullis up` (or the address set in `.env`) before its records are created.
    - **IPv4 unknown.** The service keeps the records it set before (the records check compares against the applied addresses) and still renews certificates; a configured IPv6 is still used; with no address ever known, it publishes no records.
    - **API network.** `portcullis-domains` has a fixed subnet (`PORTCULLIS_DOMAINS_SUBNET`, default `172.31.252.0/28`, passed as `DOMAINS_API_SUBNET`; `./portcullis` checks it is a valid CIDR of at least /29, overlaps neither the proxy nor the auth subnet, and matches the existing `portcullis_portcullis-domains` network); the API accepts only connections addressed to it there (or loopback, the health check), never from Traefik on `portcullis-certs` or on `domains-egress`.
    - `DOMAINS_RESOLVERS` (default `1.1.1.1:53,8.8.8.8:53`) are the resolvers of the records check, the zone (SOA) lookup and lego's propagation check; only CI changes it (to its fake DNS server).
- **Hub configuration.**

    | Env var (Hub) | Default | Meaning |
    |---|---|---|
    | `HUB_DOMAINS_API_URL` | `http://domains:8080` | Base URL of the domains API |
    | `HUB_DOMAINS_SECRET_FILE` | `/run/portcullis/domains/api-secret` | The API secret |

    Without a readable secret file the Hub's Domains section is disabled and says why; instances can then use only main-domain hosts.

### 12.2 API

Every request carries `Authorization: Bearer <api-secret>` (compared in constant time; otherwise `401`). `GET /healthz` is open (Docker health check). Bodies are JSON. Errors are non-2xx with `{"error": "<message>"}`; messages never contain credentials. The Hub is the only caller and the service trusts it: it doesn't check instance assignments (§12.3).

`{name}` is a valid hostname (§4), not the main domain, not a parent of it, and not at or under a core subdomain host `<sub>.<main domain>` (`auth`, `hub`, …; `400` otherwise).

| Request | Success | Errors |
|---------|---------|--------|
| `PUT /domains/{name}` `{"provider": "<p>", "credentials": {…}}` | `202` with the domain object (`state: pending`); work starts in the background | `400` bad name, provider or credential keys; `409` already enrolled |
| `GET /domains` | `200` with an array of domain objects, sorted by `name` | — |
| `POST /domains/{name}/token` `{"provider": "<p>", "credentials": {…}}` | `202` with the domain object; replaces the stored credentials (the provider may change) and re-runs records and, if needed, issuance. A running records step finishes (and records what it created) first | `400`; `404` not enrolled; `503` if a records step doesn't finish within the request's time (retry) |
| `DELETE /domains/{name}` | `204`; or `200` with `{"warning": "<message>"}` if some DNS records couldn't be removed. The certificate leaves the endpoint at once; if a records step is running, the answer waits for it, so the records it creates are removed too | `404` not enrolled; `503` if that step doesn't finish within the request's time (nothing changed; retry) |

Time budget of `DELETE`: waiting for a records step ≤ 90 s, removing records ≤ 60 s, the API's write timeout 3 min, the Hub's client timeout 4 min. When the Hub gets no answer, the domain stays `deleting` (not assignable) until the service's list shows the outcome. Every provider HTTP request has a 2-minute deadline, body included.

**Credentials per provider** (exactly these keys; strings of at least 8 characters — `hosted_zone_id` excepted — so redaction always applies; unknown keys are `400`):

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
- `last_error`: the last failure, `""` after a success. Every DNS-provider error is redacted against the domain's credentials before it is logged, stored or returned (providers may echo tokens or request bodies).
- A stored name that no longer passes the `{name}` rule (e.g. after a main-domain change) gets `state: error` and no records or ACME orders. An issued certificate that the endpoint would refuse (§12.4) is not stored; the attempt fails with backoff.
- Work never crosses enrollments: each enrollment and each credentials replacement gets a never-reused generation; work started for an older one (a deleted and re-enrolled name included) commits nothing.
- `state`:

    | `state` | Meaning |
    |---------|---------|
    | `pending` | Enrolled or credentials replaced; work not started yet |
    | `records` | Creating and verifying the A/AAAA records |
    | `issuing` | ACME DNS-01 order for `<name>` and `*.<name>` in progress |
    | `ready` | Records OK; a valid certificate is served on the certificate endpoint (§12.4) |
    | `renewing` | Less than 30 days left; renewal in progress, the current certificate stays served |
    | `error` | The last step failed (`last_error`); retried with backoff. A still-valid certificate stays served |

    The Hub adds one state of its own, `missing` (§12.3), for a domain the service no longer lists while instances use it.

Example: `PUT /domains/team-b.example.org` with `{"provider": "porkbun", "credentials": {"api_key": "pk1_…", "secret_api_key": "sk1_…"}}` → `202` `{"name": "team-b.example.org", "provider": "porkbun", "records_ok": false, "cert_not_after": null, "last_error": "", "state": "pending"}`.

### 12.3 What the Hub does

- **Enroll.** The Hub refuses (`409`) a name equal to, below or above an already enrolled domain (enrolled domains never nest), a name at or below any core subdomain host `<sub>.<main domain>` (e.g. `auth.<main domain>`, `x.hub.<main domain>`), and a hostname an instance uses. Other names under the main domain are allowed, deeper ones included (`team-a.<main domain>`, `lab.team-a.<main domain>`). It forwards the credentials once (`PUT`) and forgets them: they are never stored in its state, ops records, logs, audit or errors, and its API never returns them (the token field is write-only in the UI). Replacing them is `POST /domains/{name}/token`.
- **No reclassification.** Enrollment is also refused (`409`) for a name equal to or above any hostname the Hub knows: an instance's (any state, published snapshots included), a running app project's, or the default hostname `<sub>.<main domain>` of any template of any source — enrolling `team-a.<main domain>` while a template defaults to subdomain `team-a`, or while an instance routes `x.team-a.<main domain>`, would turn those hosts into extra-domain hosts. The main domain or a parent of it is `400`. The checks run before the credentials are forwarded and again after the service accepted them; a conflict found then deletes the enrollment again.
- **Assignable.** A domain may receive instance hostnames (create, hostname change, restore) only while `records_ok` is `true`, `cert_not_after` is in the future and the domains service is reachable (otherwise `503` for new hostnames on it). A domain that stops being assignable keeps its existing hostnames; the Hub shows a warning.
- **Known domains (fail closed).** The Hub keeps the enrolled domain names (with their provider and last known status, **never credentials**) in `state.yaml`. When the domains service is unreachable, new assignments (create, hostname change, restore onto an enrolled domain) and domain operations get `503`, and the last known list keeps feeding `extra_domains` in the policy file and `domains` in `portal-apps.json`.
- **The Hub is the authority on assignments.** It refuses `DELETE /api/domains/{name}` with `409` (naming the instances) while any instance (enabled or not, published snapshots included) has a hostname on the domain, before asking the service. The domains service doesn't check assignments (and the Hub doesn't send it any).
- **Deleting.** The Hub checks the users and marks the domain `deleting` (not assignable) under one lock before asking the service, so no hostname can be assigned between the check and the delete; a failed delete clears the mark.
- **The service's list is checked.** Entries that break the enrollment rules (not a valid hostname, the main domain or a parent, at or under a core host, nested) are ignored and logged. Unknown providers are refused (`400`) before anything is forwarded, logged or audited.
- **Refresh.** The Hub reads `GET /domains` every 30 s and on `GET /api/domains`; while reachable, the service's list replaces the known list (names, provider, status) in `state.yaml`.
- **Missing (fail closed).** A known domain the service no longer lists while instances still have hostnames on it is kept with state **`missing`** (`records_ok` false, `last_error` "no longer listed … still used by …", logged once on the transition). It stays in the known list, in `extra_domains` (§4) and in the portal's `domains` (§10); its hosts stay extra-domain hosts (sign-in routers, callbacks, §5); it is not assignable (`409` "no longer listed … re-enroll it"); existing hostnames are kept. A listed entry that would nest with an in-use missing name is dropped and logged. Re-enrolling the same name is allowed while the only hostnames under it are instances' (a template's default hostname there still refuses, as "No reclassification" above). It is dropped once no instance uses it.
- **Status.** The Domains section shows, per domain: records OK, certificate valid until, last error, state.

### 12.4 Records and certificates

- **Records.** `<name>` and `*.<name>`: A to the server's IPv4 and, when it has one, AAAA to its IPv6; TTL 300; existing A/AAAA records at those two names are replaced. The zone is found with a SOA lookup (lego's `dns01.FindZoneByFqdn`), so a subdomain of a zone works with that zone's credentials; for `route53`, `hosted_zone_id` skips the lookup. The service tracks the records it created per zone (the zone found may change over a domain's life) and `DELETE` removes all of them, in every zone. Without an IPv6, existing AAAA records at the two names are removed (the records check then expects none).
- **Certificates.** One certificate per domain with SANs `<name>` and `*.<name>`, from `ACME_CA_SERVER` by DNS-01 with the domain's own credentials (so two accounts at one provider can coexist). Renewed when less than 30 days remain. Failures back off.
- **Certificate endpoint (domains → Traefik).** Traefik's **HTTP provider** polls the domains service; there is no shared volume (Traefik's file provider doesn't watch subdirectories, and a reload sidecar in Traefik's PID namespace could read Traefik's environment, DNS-provider tokens included).
    - **Endpoint.** `GET https://domains:8443/traefik/dynamic`, reached by Traefik over the `portcullis-certs` network (a listener separate from the API on `:8080`). The listener requires and verifies a client certificate on **every** interface (TLS `RequireAndVerifyClientCert` against the endpoint CA); the network membership is only defense in depth.
    - **Authentication.** Mutual TLS, from files only — Traefik's provider can send custom headers only from its static configuration, which core sets through environment variables visible in `docker inspect`, so no bearer token. `./portcullis init` / `up` generate a private CA and two certificates under `secrets/domains/certs-endpoint/`: a server certificate for `domains` (SAN `DNS:domains`) and a client certificate for Traefik. `domains` mounts the CA, its server certificate and key read-only. Traefik mounts the CA, its client certificate and key read-only (group 0, mode 0640) and verifies the server against that CA. `domains` answers only clients with a certificate from that CA, so the Hub and other containers can't fetch private keys even if they reach the port.
        - **Validity and rotation.** The CA is valid 10 years; the server and client certificates are valid until the CA expires (ECDSA P-256, `extendedKeyUsage` `serverAuth` / `clientAuth` respectively). `./portcullis up` (and `upgrade`) renew a certificate with less than 30 days left (the CA with less than 1 year left: then all three) and, after any renewal, restart `domains`, wait for it to be healthy, then restart `traefik`, so both load the new files (neither re-reads them while running). `./portcullis status` warns when one expires within 30 days.
    - **Traefik static configuration** (core, shipped with the domains service — Traefik tolerates an unreachable endpoint: it retries with backoff, the other providers keep working, and the last fetched configuration stays in place while `domains` is down): `TRAEFIK_PROVIDERS_HTTP_ENDPOINT=https://domains:8443/traefik/dynamic`, `TRAEFIK_PROVIDERS_HTTP_POLLINTERVAL=10s`, `TRAEFIK_PROVIDERS_HTTP_POLLTIMEOUT=5s`, `TRAEFIK_PROVIDERS_HTTP_MAXRESPONSEBODYSIZE=4194304`, `TRAEFIK_PROVIDERS_HTTP_TLS_CA`, `_TLS_CERT` and `_TLS_KEY` set to the mounted file paths (paths only, never key material). Changes are live within one poll interval, no restart.
    - **Response.** JSON dynamic configuration with **only** `tls.certificates`: one entry per domain with a valid certificate, `certFile` the full chain and `keyFile` the private key as **inline PEM** (Traefik's `FileOrContent`), no `stores` key. With no certificates: `{"tls": {"certificates": []}}`. A renewal replaces the entry in place; `DELETE` drops it.
    - **Never anything else.** Traefik's HTTP provider applies whatever dynamic configuration it receives and can't be limited to certificates, so the restriction is the domains service's: it builds the response from a type that has only `tls.certificates` and must never emit routers, services, middlewares, TLS options, stores or servers transports (a router there could take over any host, e.g. `auth.<main domain>`).
    - **Only enrolled-domain names.** Every served certificate's SANs must be exactly `<d>` and `*.<d>` (both, nothing else, DNS names only; the subject common name, if any, is `<d>` or `*.<d>`) for a domain `<d>` that is currently enrolled in the domains service — the list the Hub publishes as `extra_domains` (§4), since the Hub enrolls and removes domains only through it; the service doesn't read the policy file — never the main domain, a core host or any other main-domain host. Traefik picks a certificate whose names match the SNI more exactly over the ACME wildcard, so a certificate naming `auth.<main domain>` would take over the sign-in host. The domains service checks this itself before serving: it parses every certificate it is about to emit and drops (and logs, without key material) one whose SANs aren't exactly `{<d>, *.<d>}` for an enrolled domain, or which names the main domain or a host at or under it — except an enrolled subdomain of the main domain `<d>` itself, which `extra_domains` allows (§4).
    - **Checks** (domains service tests and core CI, with the domains service): the served document's keys are exactly `{"tls": {"certificates": [...]}}` with only `certFile` / `keyFile` per entry (no `stores`; Traefik's API has no endpoint for TLS options and stores, so those are checked on the served document); every `certFile` is parsed and its SANs asserted as above; Traefik's API lists no `@http` object in `/api/http/routers`, `/api/http/services`, `/api/http/middlewares`, `/api/tcp/routers`, `/api/tcp/services`, `/api/tcp/middlewares`, `/api/udp/routers` or `/api/udp/services`, and no `@http` key anywhere in `/api/rawdata` (servers transports have no endpoint of their own); and after a test certificate is published, `auth.<main domain>` (and another core host) still serve the main domain's certificate.
    - **CI** (with the domains service): a certificate published there is served by SNI within ~20 s without restarting Traefik (`StartedAt` unchanged), and a deleted one stops being served. CI builds the image with the Go build tag `testprovider` (an extra provider `fake` whose records live in memory and are served as DNS by the container itself) and runs Pebble against it; the production image is built without it.
- **Secrets at rest.** Credentials exist only in `domains_data`, encrypted with the age key; the volume is in `./portcullis backup` only in that encrypted form. The same backup also contains `secrets/` (age key included), so it must be protected like the keys themselves, as for Vault's. Credentials are never logged, never returned by the API and never put in `last_error`.
