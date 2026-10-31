# Integration Contracts

Portcullis is split across four repositories that meet at a few well-defined interfaces. This page is the **single source of truth** for those interfaces. Change it first, then change the repos on both sides.

| Repo | Role |
|------|------|
| `porelli/portcullis` (core) | Compose stack, scripts/CLI, group-gate, enroll |
| `porelli/portcullis-hub` | Hub image (`ghcr.io/porelli/portcullis-hub`) |
| `porelli/portcullis-templates` | App templates (public; accepts outside contributions) |
| `porelli/portcullis-docs` | This site |

## 1. Versions and releases

- **Tags.** Every repo uses semver tags `vMAJOR.MINOR.PATCH`. A breaking change to any contract on this page bumps MAJOR in every repo it affects.
- **Hub image.** It is published as `X.Y.Z`, `X.Y`, `X` and `sha-<short>` for tags, and `edge` for `main`. Each release image is signed with cosign (keyless, GitHub OIDC) and carries SBOM and provenance attestations. There is **no `latest` tag**.
- **Core pins the Hub.** Core sets `HUB_IMAGE` to a released tag plus digest, e.g. `ghcr.io/porelli/portcullis-hub:1.4.0@sha256:…`. `HUB_IMAGE` can be overridden in `.env`.
- **Templates pin core.** The templates CI tests against the core ref in `.core-ref` in the templates repo: a tag, or `main` during development.
- **Templates are versioned by tag.** The Hub tracks the source's default branch.

## 2. Core environment variables available to templates

When a template's `compose.yml` references a variable, the Hub copies its value from the core `.env` into the app's env. Templates may rely on:

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
  "policies": {"<template-id or subdomain>": {"factors": ["mtls", "webauthn"], "op": "any|all"}},
  "groups":   {"<subdomain>": "<required LLDAP group>"},
  "path_groups": {
    "<subdomain>": [{"prefix": "/admin", "group": "<LLDAP group>"}]
  }
}
```

- **`factors`** is a subset of `mtls`, `webauthn` and `password`. `op` is `any` or `all`, and is ignored when there is at most one factor. An empty factor list means public.
- **Unknown values fail closed.** An unknown factor, op or key shape makes group-gate deny the request.
- **`policies`** contains entries keyed by template ID **and** by each lowercase subdomain the template routes (taken from `Host(\`<sub>.${PORTCULLIS_DOMAIN…}\`)` rules). Only enabled templates publish subdomain keys.
- **`groups`** comes from enabled templates with `auth.group_access: true`: subdomain maps to `auth.access_group`.
- **`path_groups`** comes from enabled templates that declare `auth.admin_paths` (a list of path prefixes). Each prefix requires `auth.admin_group`, **in addition** to the subdomain's group.
    - Matching uses group-gate's normalized `X-Forwarded-Uri` path: percent-decoded once, `//` collapsed, dot-segments resolved.
    - It is a prefix match on segment boundaries (`/admin` matches `/admin` and `/admin/x`, not `/administrator`). The longest matching prefix wins.
- **Core subdomains** (`auth`, `traefik`, `hub`, `directory`, `enroll`) are never taken from this file. `group-gate-map.conf` in core owns them.
- **Older files.** A file without `version`, `groups` or `path_groups` is valid and is treated as empty for the missing keys.

## 5. Hub ⇄ Traefik

- **Proxy secret.** Traefik adds the header `X-Portcullis-Proxy-Secret: ${HUB_PROXY_SECRET}` to every request it routes to the Hub, using a `headers.customRequestHeaders` middleware on the Hub router.
    - The Hub rejects any request without a matching header, compared in constant time.
    - The only exception is `GET /healthz`.
    - `HUB_PROXY_SECRET` is generated by `portcullis init`, and the Hub refuses to start without it.
- **Identity headers.** The Hub reads `X-Forwarded-User`. Traefik guarantees it because it is listed in group-gate's `authResponseHeaders`.

## 6. Docker access

Neither Traefik nor the Hub mounts `/var/run/docker.sock` directly. Each gets its own socket proxy, on its own internal network:

| Client | Proxy endpoint | Allowed |
|--------|----------------|---------|
| Traefik | `tcp://socket-proxy-traefik:2375` | read-only: containers, networks, events, version |
| Hub | `tcp://socket-proxy-hub:2375` | containers, images, networks, volumes, exec, events, info, version, plus POST/DELETE. No swarm, plugins, secrets, configs, nodes or system prune |

The Hub reads `DOCKER_HOST` for both the `docker compose` CLI and its own Engine API calls.

## 7. Docs ⇄ templates

- **Generator.** `scripts/generate-app-docs.py` in the docs repo reads every `<app-id>/manifest.yaml` and writes `docs/apps/*.md` plus `docs/apps/.nav.yml`.
- **Triggers.**
    - On push to `main`, the templates repo sends a `repository_dispatch` event (`templates-updated`) to the docs repo, which rebuilds the site. This needs the `DOCS_DISPATCH_TOKEN` secret in the templates repo.
    - The docs repo also rebuilds daily as a fallback.
