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
- **Core pins the Hub.** Once the Hub has releases, core's default `HUB_IMAGE` is a released tag plus digest, e.g. `ghcr.io/porelli/portcullis-hub:1.4.0@sha256:…`. Until then it is `ghcr.io/porelli/portcullis-hub:edge`. Operators override it in `.env` and should pin tag + digest in production.
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
- **Support files.** Files that ship with a template are bind-mounted as `./templates/<app-id>/<file>`. Compose resolves relative paths against the core checkout on the host. Before every `compose up`, the Hub copies the template directory to `<core>/templates/<app-id>/`; core mounts `./templates` read-write into the Hub at `/project/templates`.
- **Networks.** Frontends join the external network `portcullis-proxy`; internal services join only `default`. Volumes declare `name: portcullis_<name>`.
- **Middlewares.** Forward-auth and header-auth routers use `portcullis-auth@docker,portcullis-groups@docker`. Native-OIDC routers must not.

## 4. Policy file (Hub → group-gate)

The Hub writes `group-gate-policy.json` atomically (temp file + rename) to the `hub_data` volume. group-gate mounts that volume read-only and re-reads the file on every request.

```json
{
  "version": 2,
  "default":  {"factors": ["webauthn"], "op": ""},
  "policies": {"<subdomain>": {"factors": ["mtls", "webauthn"], "op": "any|all"}},
  "groups":   {"<subdomain>": "<required LLDAP group>"},
  "path_groups": {
    "<subdomain>": [{"prefix": "/admin", "group": "<LLDAP group>"}]
  }
}
```

- **`factors`** is a subset of `mtls`, `webauthn` and `password`. `op` is `any` or `all`, and is ignored when there is at most one factor. An empty factor list means public.
- **Unknown values fail closed.** An unknown factor, op or key shape, a file that exists but can't be parsed, or a `version` newer than group-gate supports (currently 2) makes group-gate deny the request.
- **Keys are subdomains only.** group-gate looks everything up by the request's subdomain, so `policies`, `groups` and `path_groups` are keyed by the lowercase subdomains that **enabled** templates route — never by template ID, which could equal another app's subdomain.
- **Routing must be fully visible.** The Hub parses every `traefik.http.routers.*.rule` label in a template's compose file and only accepts literal `Host(\`<sub>.${PORTCULLIS_DOMAIN…}\`)` hosts. It rejects any template with `HostRegexp`/`HostHeader`/`HostSNI`, other domains, variables in the label, routers without a rule, TCP routers, or a rule branch that is not restricted by `Host()`. A host the Hub can't see would get no policy and no group (fail open).
- **`policies`** has an entry for each subdomain of an enabled template that has a per-app policy. Templates that inherit the default publish nothing; group-gate falls back to `default`.
- **One owner per subdomain.** The Hub refuses to enable a template (or save an Expert-tab compose edit) that routes a subdomain another enabled template already routes. If a collision still reaches the writer, it publishes the stricter policy (higher LoA, then `all` over `any`), merges path groups, keeps the group of the lowest template ID, and logs the collision.
- **`groups`** comes from enabled templates with `auth.group_access: true`: subdomain maps to `auth.access_group`.
- **Fail closed when a template goes missing.** At enable time the Hub stores each app's published config (subdomains, groups, admin paths, policy override) in its state. If an enabled app's template later stops loading, the Hub keeps publishing that last known config and reports it as drift. If there is no stored config, every subdomain the app's running containers route (or a running app project that isn't enabled) gets `groups[sub] = "__portcullis_deny__"`. group-gate matches groups exactly and nobody is in that group, so all requests are denied. Never create an LLDAP group with that name.
- **`path_groups`** comes from enabled templates that declare `auth.admin_paths` (a list of path prefixes). Each prefix requires `auth.admin_group`, **in addition** to the subdomain's group.
    - Matching uses group-gate's normalized `X-Forwarded-Uri` path: percent-decoded once, `//` collapsed, dot-segments resolved.
    - It is a prefix match on segment boundaries (`/admin` matches `/admin` and `/admin/x`, not `/administrator`). The longest matching prefix wins.
- **Core subdomains** (`auth`, `traefik`, `hub`, `directory`, `enroll`, `metrics`) are never taken from this file. `group-gate-map.conf` in core owns them.
    - Core's group-gate additionally reserves `metrics` (Grafana of core's optional monitoring profile). The Hub (`policy.CoreSubdomains`) and the templates validator (`CORE_SUBDOMAINS`) still list only the five above, so they must be extended to match.
- **Older files.** A file without `version`, `groups` or `path_groups` is valid and is treated as empty for the missing keys.

## 5. Hub ⇄ Traefik

- **Proxy secret.** Traefik adds the header `X-Portcullis-Proxy-Secret: ${HUB_PROXY_SECRET}` to every request it routes to the Hub, using a `headers.customRequestHeaders` middleware on the Hub router.
    - The Hub rejects any request without a matching header, compared in constant time.
    - The only exception is `GET /healthz`.
    - `HUB_PROXY_SECRET` is generated by `portcullis init`, and the Hub refuses to start without it.
- **Identity headers.** The Hub reads `X-Forwarded-User` (the LLDAP username). Traefik guarantees it because it is listed in the forward-auth middlewares' `authResponseHeaders`, so client copies are deleted.
- **Order.** On the Hub router, `hub-proxy-secret@docker` comes **after** `portcullis-auth@docker,portcullis-groups@docker`, so the secret is never sent to oauth2-proxy or group-gate.

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
