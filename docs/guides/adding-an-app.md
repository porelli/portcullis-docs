# Adding an App

This guide walks through creating a new app template. Templates live in
[porelli/portcullis-templates](https://github.com/porelli/portcullis-templates),
one directory per app at the repo root. The repo accepts outside contributions,
including pull requests from forks.

!!! tip "Start with CONTRIBUTING.md"
    The templates repo's
    [CONTRIBUTING.md](https://github.com/porelli/portcullis-templates/blob/main/CONTRIBUTING.md)
    is the authoritative checklist: auth method choice, compose and security
    rules, image pinning, and what CI runs. This page explains the same steps
    with examples.

## Overview

A template is:

```
<app-id>/
  manifest.yaml   # what the Hub shows and how auth is wired
  compose.yml     # how the app runs behind Traefik
  ...             # optional support files (config templates, setup scripts)
tests/apps/<app-id>.sh   # its CI test
```

When a user enables the app, the Hub:

1. generates a per-app `.env` from the manifest (settings, `generate: random` secrets, referenced core variables)
2. copies the directory to `<core>/templates/<app-id>/`
3. registers the manifest's Keycloak clients
4. starts the compose file as its own project, `portcullis-<app-id>`
5. publishes the app's subdomains, group, admin paths and policy to group-gate

## Step 1: Pick an app ID and a subdomain

The app ID is lowercase and matches `^[a-z0-9][a-z0-9_-]{0,63}$`, e.g.
`uptime-kuma`. It is the directory name and the compose project scope. Pick a
subdomain no other template routes. Core subdomains (`auth`, `traefik`, `hub`,
`directory`, `enroll`, `metrics`) are off limits. The Hub refuses to enable two apps that
route the same subdomain.

```bash
git clone https://github.com/porelli/portcullis-templates.git
cd portcullis-templates
mkdir myapp
```

## Step 2: Choose the auth method

| The app... | `auth.method` | Router middlewares |
|------------|---------------|--------------------|
| speaks OpenID Connect and can be pointed at Keycloak | `native-oidc` (+ `keycloak_clients`) | **no** `portcullis-auth`; the app logs users in itself |
| can create/log in users from a trusted header (`X-Forwarded-User`) | `header-auth` | `portcullis-auth@docker,portcullis-groups@docker` |
| has its own login (or none) and no SSO | `forward-auth` | `portcullis-auth@docker,portcullis-groups@docker` |
| is protected by client certificates only | `mtls` | `tls.options: protected@file`, no forward-auth |
| uses a vendor account system (e.g. plex.tv) | `custom` | none |
| is meant to be public | `public` | none |

Prefer `native-oidc` when the app supports it well: mobile apps, API tokens and
CLI clients keep working. Then check **who can log in**:

- **The app can restrict OIDC logins to a group.** Configure it with
  `access_group` (`users_<app-id>`) and set `group_access: true`.
- **It cannot.** Then any Keycloak realm user could sign in. Put only the
  interactive login paths behind forward-auth + group-gate, on a
  higher-priority `PathPrefix` router. Keep the API on the host-wide router
  without forward-auth. See `gitlab/`, `litellm/` and `vaultwarden/`.
- **It has an admin panel on a path** (e.g. Vaultwarden's `/admin`). Route the
  path through a gated `PathPrefix` router and list it in `auth.admin_paths`.
  group-gate then also requires `admin_group` there.

Give SSO-created users the least-privileged role the app has.

If the app has share links for people without an account (public file
shares, shared dashboards), declare them in
[`auth.public_access`](manifest-reference.md#authpublic_access) instead of
adding an ungated router: the Hub generates the public router when an admin
turns the exception on. Read the app's routes at the pinned version and keep
the list narrow: `{token}` paths for per-share listing, static-only
`supporting` paths, `exact` routes with a justification, and the app's login
headers, cookies and query parameters in `credential_*`.

## Step 3: Write `manifest.yaml`

Copy a template with the same auth method and adapt it: `grafana/` for
header-auth, `scrutiny/` for forward-auth, `vaultwarden/` for native OIDC. All
fields are documented in the [Manifest Reference](manifest-reference.md).

```yaml
# yaml-language-server: $schema=../schema/manifest.schema.json
name: My App
description: A brief description of what the app does
icon: "\U0001F4E6"
category: productivity
tags: [example, demo]

auth:
  method: forward-auth
  sso: false
  group_access: true
  group_admin: false
  access_group: users_myapp
  admin_group: admin_myapp
  notes: Access gated by group-gate. No SSO -- uses its own login.

env:
  - key: MYAPP_SECRET
    description: Secret key for My App
    generate: random

keycloak_clients: []
config_files: []

urls:
  - label: My App
    url: "https://myapp.{{DOMAIN}}"
```

## Step 4: Write `compose.yml`

`tests/validate.py` checks every rule below.

### Rules

- **Networks.** Services with `traefik.enable: "true"` use
  `networks: [default, portcullis-proxy]`. Databases, caches and sidecars stay
  on `default` only. Declare `portcullis-proxy` as `external: true`. No other
  networks.
- **Routers.**
    - Use exactly the form
      `` rule: Host(`<sub>.${PORTCULLIS_DOMAIN:-portcullis.local}`) ``. The Hub
      parses it strictly and rejects anything it can't fully resolve (see
      [Hub → Template rules](../operations/hub.md#template-rules-enforced-by-the-hub)).
    - Set `entrypoints: websecure`.
    - Set `tls.options` to `authaware@file`, `public@file` or `protected@file`.
      The Hub overrides it from the app's access policy.
    - Include `security-headers@file` in the middlewares.
- **Middleware order** for gated routers:
  `client-headers@file,portcullis-auth@docker,portcullis-groups@docker,security-headers@file`.
  `client-headers@file` first lets group-gate check client-cert revocation.
- **Volumes** declare `name: portcullis_<volume>`, unique across templates.
- **Files** shipped with the template are mounted as
  `./templates/<app-id>/<file>`, never `./<file>`. Compose resolves relative
  paths against the core checkout on the host. From core, only
  `./certs/ca-bundle.crt:<path>:ro` may be mounted.
- **Variables.** Core variables (`PORTCULLIS_DOMAIN`, `PORTCULLIS_PROXY_SUBNET`,
  `PORTCULLIS_PROXY_IP_RANGE`, `PORTCULLIS_TRAEFIK_IP`) always use their default
  form. Every other variable must be declared in the manifest. Required ones
  (`${VAR:?…}`) must be `env` entries with `generate: random`. Use `$$VAR` for
  variables the container shell should expand.
- **No** `ports:` (declare host ports in the manifest), `build:`,
  `container_name:` or `env_file:`.
- **Images** are pinned by version tag **and** digest (Step 5).

### Forward-auth / header-auth

```yaml
services:
  myapp:
    image: myorg/myapp:1.4.2@sha256:<index digest>
    environment:
      MYAPP_SECRET: ${MYAPP_SECRET:?generated by the Hub}
    volumes:
      - myapp-data:/data
    networks:
      - default
      - portcullis-proxy
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: Host(`myapp.${PORTCULLIS_DOMAIN:-portcullis.local}`)
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: authaware@file
      traefik.http.routers.myapp.middlewares: client-headers@file,portcullis-auth@docker,portcullis-groups@docker,security-headers@file
      traefik.http.services.myapp.loadbalancer.server.port: "8080"

volumes:
  myapp-data:
    name: portcullis_myapp_data

networks:
  portcullis-proxy:
    external: true
```

A **header-auth** app must accept `X-Forwarded-User` only from
`${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}`. See
[Header Auth Pattern](header-auth-app.md#header-security).

### Native OIDC

```yaml
services:
  myapp:
    image: myorg/myapp:1.4.2@sha256:<index digest>
    environment:
      OIDC_ISSUER: https://auth.${PORTCULLIS_DOMAIN:-portcullis.local}/realms/portcullis
      OIDC_CLIENT_ID: myapp
      OIDC_CLIENT_SECRET: ${MYAPP_OIDC_SECRET:?generated by the Hub}
      SSL_CERT_FILE: /certs/ca-bundle.crt   # trust the internal/staging CA
    volumes:
      - ./certs/ca-bundle.crt:/certs/ca-bundle.crt:ro
    networks:
      - default
      - portcullis-proxy
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: Host(`myapp.${PORTCULLIS_DOMAIN:-portcullis.local}`)
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: authaware@file
      traefik.http.routers.myapp.middlewares: security-headers@file
      traefik.http.services.myapp.loadbalancer.server.port: "8080"

networks:
  portcullis-proxy:
    external: true
```

Then add the client and its secret to the manifest:

```yaml
env:
  - key: MYAPP_OIDC_SECRET
    description: My App OIDC client secret
    generate: random

keycloak_clients:
  - client_id: myapp
    secret_env: MYAPP_OIDC_SECRET
    redirect_uri: "https://myapp.{{DOMAIN}}/callback"
    name: My App
```

Gate an admin path of a native-OIDC app with a second router and
`auth.admin_paths: ["/admin"]`:

```yaml
      traefik.http.routers.myapp-admin.rule: Host(`myapp.${PORTCULLIS_DOMAIN:-portcullis.local}`) && PathPrefix(`/admin`)
      traefik.http.routers.myapp-admin.priority: "100"
      traefik.http.routers.myapp-admin.entrypoints: websecure
      traefik.http.routers.myapp-admin.tls.options: authaware@file
      traefik.http.routers.myapp-admin.middlewares: client-headers@file,portcullis-auth@docker,portcullis-groups@docker,security-headers@file
      traefik.http.routers.myapp-admin.service: myapp
```

### Public

Same as above with `tls.options: public@file`, only `security-headers@file` as
middleware, and `auth.method: public` / `group_access: false` in the manifest.

### Trusting the internal CA

Apps that call Keycloak over HTTPS must trust `certs/ca-bundle.crt` (system CAs,
the Portcullis PKI chain, and the LE staging root when `ACME_STAGING=true`).
Mount it read-only and point the runtime at it:

| Runtime | Setting |
|---------|---------|
| Node.js | `NODE_EXTRA_CA_CERTS=/certs/ca-bundle.crt` |
| Go | `SSL_CERT_FILE=/certs/ca-bundle.crt` |
| Python (requests) | `REQUESTS_CA_BUNDLE=/certs/ca-bundle.crt` |
| Java | Import into the JVM truststore |
| Generic | `SSL_CERT_FILE` or `CURL_CA_BUNDLE` |

## Step 5: Pin the images

Every image is pinned to an explicit release **and** its multi-arch index
digest:

```yaml
image: grafana/grafana:13.3.0@sha256:488984b716c0862639f91a698adbe2862677a5a07bad42da5f03f3030883b205
```

Get the digest with `docker buildx imagetools inspect grafana/grafana:13.3.0`
(the top-level `Digest:`). Floating tags (`latest`, `stable`, `main`,
`16-alpine`, `2`, ...) are rejected.

**Add your directory to `.github/dependabot.yml`** (the docker-compose
`directories:` list). Dependabot then proposes tag and digest updates weekly;
`validate.py` fails if the directory is missing. Some updates need care:

- Don't bump database majors (PostgreSQL, MySQL, Redis). That needs a data migration.
- Apps with several images move in lockstep.
- Apps with upstream upgrade paths say so in `auth.notes`.

## Step 6: Add a test

Create `tests/apps/<app-id>.sh`. At minimum, a static test (copy
`tests/apps/scrutiny.sh`). Boot the container with `compose_up` when the app
starts reliably in CI. Header-auth apps must call `assert_traefik_only_trust`
and `assert_spoofed_identity_rejected`.

```bash
#!/usr/bin/env bash
# Test: My App (forward-auth + group-gate)
set -euo pipefail
cd "$(dirname "$0")/../.."
source tests/lib.sh
TEST_NAME="myapp"
section "My App"

APP_ID=myapp
SUBDOMAIN=myapp

compose_up "$APP_ID"
IP=$(app_container_ip "$APP_ID")
wait_for_url "http://${IP}:8080" 60 "$APP_ID"

# Unauthenticated access must redirect to Keycloak
assert_redirect_to_keycloak "https://${SUBDOMAIN}.${DOMAIN}/"

compose_down "$APP_ID"
```

See [Testing & CI](../operations/testing.md) for the helpers.

## Step 7: Run the local checks

No Docker daemon is needed:

```bash
python3 -m venv .venv && .venv/bin/pip install -r tests/requirements.txt
.venv/bin/python tests/validate.py myapp      # schema + repo rules (cross-template checks still run)
PATH=.venv/bin:$PATH bash tests/compose-config.sh myapp   # docker compose config -q
shellcheck -S warning tests/apps/*.sh ./*/*.sh
```

`validate.py` prints one line per problem with a hint, for example:

```
ERROR myapp/compose.yml: services.web: image tag 'latest' is floating
      hint: pin the exact release, e.g. postgres:16.15-alpine instead of postgres:16-alpine; ...
```

The integration tests (`tests/apps/*.sh` against a real
Keycloak/LLDAP/Traefik stack) need the core repo, so you normally let CI run
them.

## Step 8: Open a pull request

Fill in the checklist of the PR template. What CI does:

| Workflow | When | What |
|----------|------|------|
| **Lint** (`lint.yml`) | Every push and PR, **including forks** (no secrets) | `validate.py`, `docker compose config` for every template, shellcheck, actionlint |
| **Test Apps** (`test-apps.yml`) | Push to `main`, every PR **including forks** (no secrets), manual runs | Boots core at the ref in `.core-ref`, then runs `tests/apps/<app>.sh` for every changed template |

**Fork PRs get the full integration tests automatically**: core is public and cloned without a token, and no job references a secret. Your PR is tested against the core version in the base branch's `.core-ref`. The workflow deliberately avoids `pull_request_target`. Details:
[Testing & CI](../operations/testing.md#templates-ci).

After the merge, the docs site regenerates the [App Catalog](../apps/index.md)
from your manifest, and Hub users get the template with **Sync**.

## Trying it on your own instance

Before your PR is merged, add your fork as a template source in the Hub
(**Template Sources**), then enable the app. Useful commands on the core host:

```bash
docker compose -p portcullis-myapp ps
docker compose -p portcullis-myapp logs -f
docker compose logs group-gate | grep myapp   # DENIED / ALLOW-UNMAPPED / STEPUP lines
```

## Checklist

- [ ] App ID and subdomain are unique; no core subdomain
- [ ] `manifest.yaml` passes the schema; auth method fits the app
- [ ] `compose.yml`: networks, `Host()` form, middleware order, `security-headers@file`, named volumes, no `ports:`
- [ ] Secrets are `generate: random`; no default passwords
- [ ] Header-auth: identity header trusted only from `PORTCULLIS_TRAEFIK_IP`
- [ ] Images pinned `tag@sha256:…`; directory added to `.github/dependabot.yml`
- [ ] `tests/apps/<app-id>.sh` added
- [ ] `python3 tests/validate.py` and `tests/compose-config.sh` pass
