# Hub Management

The Hub is Portcullis's web dashboard for app templates. It lists the catalog,
enables and disables apps, edits their settings and access policies, and shows
status and logs. It is published as `ghcr.io/porelli/portcullis-hub` and run by
the core `docker-compose.yml` (`HUB_IMAGE`). There is nothing to build.

Open it at `https://hub.<your-domain>`. It requires a Keycloak login and
membership of `lldap_admin`.

## App Catalog

The main view lists every template from every [template source](#template-sources) as a card:

- icon, name and one-line description
- auth badges:

| Badge | Meaning |
|-------|---------|
| **SSO** | The app supports single sign-on via Keycloak (`auth.sso`) |
| **Group Access** | group-gate restricts the app's subdomains to the `users_<app>` group (`auth.group_access`) |
| **Group Admin** | The app maps the `admin_<app>` group to its admin role (`auth.group_admin`) |
| **Method** | `forward-auth`, `native-oidc`, `header-auth`, `mtls`, `custom` or `public` |

- whether the app is enabled and running

### Enabling an app

1. Open the app card and review the details.
2. Fill in its settings (media folders, ports, options) and, if needed, its
   [access policy](auth-policies.md).
3. Click **Enable**.

Before anything starts, the Hub refuses to enable the app if:

- one of its host ports is already used by another enabled app, or
- one of its subdomains is already routed by another enabled app (HTTP 409,
  "subdomain … is already routed by enabled app …"). Every subdomain has
  exactly one owner, because group-gate keys groups and policies by subdomain.

It then generates the per-app `.env` and compose override, copies the template
directory to `<core>/templates/<app-id>/`, registers the template's Keycloak
clients and runs `docker compose up`. The app is recorded as enabled only after
`compose up` succeeds. Then the Hub publishes its group, admin paths and policy
to group-gate.

### Disabling an app

Click **Disable** in the app's detail panel. The Hub runs
`docker compose down` for the project. The app is marked disabled only once
that succeeds. If stopping fails, the app stays enabled and the error is shown,
so you can retry instead of being left with orphaned containers. If the
template is gone or its compose file is broken, the Hub falls back to
`docker compose -p portcullis-<id> down`.

Keycloak clients are not deleted when you disable an app. Volumes are kept.

Only one lifecycle operation (enable, disable, restart) runs per app at a time.
A second request while one is in progress is rejected with a "try again
shortly" message.

## App detail panel

Each enabled app has four tabs: **Settings**, **Status**, **Logs** and **Expert**.

### Settings

- The **access policy** block: factors (mTLS / WebAuthn / password), any-of or
  all-of, or *inherit global default*. See [Authentication Policies](auth-policies.md).
- **Settings** declared in the manifest:
    - `path` / `paths`: host directories bind-mounted into a container, e.g. media libraries
    - `text`: free-form values
    - `boolean`: toggles
    - `select`: a dropdown of the manifest's options
- **Host ports** declared in the manifest: rebind them, or clear optional ones
  to disable the binding.

Saving restarts the app in the background. Clearing a text field clears the
value in the app's `.env`.

Input validation:

- Path settings may not contain `:` (Compose would read it as `host:container`)
  or newlines. Spaces, quotes and `#` are fine, because paths are quoted in the
  generated override.
- Port bind addresses must be IP addresses (e.g. `0.0.0.0`, `127.0.0.1`, `::1`).
  IPv6 is bracketed automatically.
- No setting value may contain newlines or other control characters.

### Status

Lists each container of the app's compose project with its state:

- **All containers running**
- **Some containers not running**
- **Containers stopped**

The information comes from the Docker Engine API through the Hub's socket proxy.

### Logs

Shows the last 100, 200 or 500 log lines of the app's containers. Use
**Refresh** to reload.

### Expert

Advanced tools with direct access to the compose configuration and the
containers.

- **compose.yml editor.** Edits the app's copy of the template's compose file.
  Changes apply on the next restart. The Hub re-validates the routing on save:
    - it rejects rules it can't fully parse (see [Template rules](#template-rules-enforced-by-the-hub))
    - it rejects routes to a core subdomain
    - it refuses a subdomain that another enabled app already routes
- **Compose override.** The Hub generates
  `${HUB_DATA_DIR}/overrides/<app>.override.yml` from the settings: bind
  mounts, host ports, and each router's `tls.options` derived from the access
  policy. Edits here take precedence over the generated file.
- **Environment variables.** Edit the app's own `.env` (stored in the Hub data
  directory), or add a variable. Names must match `[A-Za-z_][A-Za-z0-9_]*`, and
  values may not contain newlines.
- **Container shell.** Runs one command with `/bin/sh -c` in a chosen container
  through the Engine API and shows its output. The Hub stops waiting after
  15 minutes, or when the browser request is cancelled. A process that keeps
  running inside the container is not killed.
- **Restart.** A full `down` + `up` of the project, so compose and env changes
  take effect.

!!! warning
    Editing `compose.yml` can break the app or its Traefik routing. Only do it
    if you understand Docker Compose and Traefik labels.

## Settings tab (global)

- **Default access policy.** Applies to every app without its own policy.
  Changing it re-applies it to every enabled app that inherits it, and
  restarts only the apps whose Traefik TLS tier actually changed. Saving an
  unchanged default does nothing.
- **Users.** Lists Keycloak users. You can push the "register a passkey"
  required action onto a user's next login, e.g. before you make WebAuthn
  mandatory, or clear it again.

## Drift detection

The Hub keeps the desired state (enabled apps) in `state.yaml` and regularly
compares it with the compose projects Docker actually runs:

- every `HUB_RECONCILE_INTERVAL` (default `1m`, at least `5s`)
- on Docker events

Reconcile **reports** drift and never fixes it by itself. A yellow **State
drift** box at the top of the catalog lists each mismatch with a message, the
running/total container count, and buttons for the allowed actions:

| Kind (`kind` in the API) | Meaning | Actions |
|--------------------------|---------|---------|
| `enabled_not_running` | Enabled, but no container of the project runs (stopped, or none) | **Start** (`start`: compose up), **Disable** (`disable`) |
| `running_not_enabled` | Containers of `portcullis-<id>` run, but the app is not enabled | **Stop & remove** (`stop`: compose down). **Enable** (`adopt`: mark it enabled and compose up) when a template with that ID exists |
| `stopped_not_enabled` | Stopped containers left behind by an app that is not enabled | **Stop & remove** (`stop`) |
| `template_missing` | Enabled, but no valid template provides it any more (source removed, template deleted or now invalid) | **Disable** (`disable`) |

Destructive actions ask for confirmation. **Re-check** runs a reconcile
immediately. Apps that are in the middle of an operation are skipped.

The same is available over the API, which also needs the proxy secret:

```text
GET  /api/drift            latest report: {checked_at, error?, items: [{id, kind, message, running, total, template_exists, actions}]}
POST /api/drift            re-check now, returns the new report
POST /api/drift/resolve    {"id": "<app>", "action": "start|disable|stop|adopt"}
```

If Docker is unreachable, the report carries `error` and the UI shows
"Docker unreachable".

### Fail-closed behaviour

Drift must never open access. That is why `state.yaml` keeps a **snapshot**
(`published`) of each enabled app's last published config: subdomains, access
group, admin paths and policy override.

- **Template missing, snapshot present.** If an enabled app's template stops
  loading, the Hub keeps publishing the snapshot to group-gate, so the app
  stays protected exactly as before. The drift message says "template missing
  — still enforced from last known config".
- **No snapshot.** If an enabled app has no snapshot, or a `portcullis-<id>`
  project runs without being enabled, the Hub reads the `Host()` rules from the
  running containers' labels. It publishes the reserved group
  `__portcullis_deny__` for those subdomains. group-gate then denies every
  request to them ("The configuration of … is unavailable"), until you disable
  or adopt the app. Never create an LLDAP group with that name.
- **Corrupt `state.yaml`.** If the file can't be parsed (or is empty), the Hub
  refuses to start rather than overwrite it with empty state.

## Template rules enforced by the Hub

Templates must load cleanly, or the Hub skips them and logs why:

- The manifest must satisfy the templates repo's
  [schema](../guides/manifest-reference.md).
- The directory name must match `^[a-z0-9][a-z0-9_-]{0,63}$`.
- Setting, port and env keys must be valid `.env` keys.
- Port `bind` values must be IP addresses.

**Strict Traefik rule parsing.** group-gate keys every policy, group and path
rule by subdomain. A host the Hub doesn't see would get no policy and no group,
which fails open. So the Hub parses each `traefik.http.routers.<name>.rule`
label in `compose.yml` and rejects the template if:

- a `Host()` argument is anything but a literal `` `<label>.${PORTCULLIS_DOMAIN}` ``
  (a default such as `${PORTCULLIS_DOMAIN:-portcullis.local}` is allowed).
  That rules out other domains, bare domains, and variables in the label part
  (`${SUB}.${PORTCULLIS_DOMAIN}`)
- the rule uses `HostRegexp`, `HostHeader`, `HostSNI` or `HostSNIRegexp`
- some way the rule can match is not restricted by `Host()`: a top-level `||`
  branch without `Host()`, a negation, or a path-only rule
- a router has no rule, or a `traefik.enable=true` service has no HTTP router.
  Traefik would then apply its default rule
- it declares a TCP router, which would bypass forward-auth
- it routes a core subdomain (`auth`, `traefik`, `hub`, `directory`, `enroll`)

## Keycloak clients

For templates with `keycloak_clients`, the Hub creates confidential OIDC
clients in the `portcullis` realm. Each client gets:

- the secret from the app's generated env
- the manifest's redirect URIs, with `{{DOMAIN}}` replaced
- `default.acr.values` set from the app's policy
- the default client scopes `openid`, `profile`, `email`, plus **`acr`** (puts
  `acr`/`amr` in tokens for step-up) and **`groups`** (claim `groups` with
  plain group names, so apps can map `users_<app>` / `admin_<app>`)

**Ownership.** Each client the Hub creates is tagged with the attribute
`portcullis.hub.template=<template-id>`. When the client already exists, the
Hub updates its secret, redirect URIs, ACR and scopes only if:

- **the client is tagged** and the tag names this template, or
- **the client is untagged** and the Hub can prove it belongs to the template.
  That means it has at least one redirect URI, and every redirect URI and web
  origin is a plain `http(s)` URL without wildcards whose host is one of the
  template's own `<sub>.<domain>` hosts.

Anything else fails closed: the existing client is left untouched and the Hub
logs a warning (`failed to register client …`). The app still starts, but its
OIDC login won't work until you resolve the clash, e.g. by deleting or tagging
the foreign client in Keycloak.
Core and built-in clients are reserved and never touched:
`portcullis-forward-auth`, `admin-cli`, `account`, `account-console`,
`broker`, `realm-management` and `security-admin-console`.

## Per-app isolation

- **Separate compose project.** Each app runs as `portcullis-<app-id>`, with its
  own containers and `default` network.
- **Networks.** Frontends join the external `portcullis-proxy` network (shared
  with Traefik) and the app's `default` network. Internal services join only
  `default`. Apps can't reach each other or the core services directly.
- **Template files.** Before every `compose up`, the Hub copies the app's
  template directory to `<core>/templates/<app-id>/`. Compose resolves relative
  paths against the core checkout on the host
  (`--project-directory = PROJECT_HOST_DIR`), which is what makes bind mounts
  like `./templates/immich/setup.sh` work.
- **Separate `.env`.** The Hub writes a per-app `.env` with the app's settings,
  generated secrets (`generate: random` → 32 hex characters), and the core
  variables its compose file references. It takes those core variables from
  `/project/.env`, which is **not** the core `.env`: it is the generated subset
  `secrets/hub/core.env` (see [Security & Hardening](hardening.md#container-hardening)).
  Files are written atomically with mode `0600`.

## Template sources

Each source is a git repository with one directory per app (`manifest.yaml` +
`compose.yml`).

- **Default source.** On first start, the Hub clones
  [porelli/portcullis-templates](https://github.com/porelli/portcullis-templates)
  (`DEFAULT_TEMPLATES_URL`) as the source named `portcullis`. It cannot be
  removed.
- **Sync.** Runs `git pull --ff-only` on every source and reports which failed
  to fast-forward. Local edits made in the Expert tab block the fast-forward.
- **Community sources.** Add more repositories in the **Template Sources** tab.
    - Source names use lowercase letters, digits, `-` and `_`.
    - URLs must be `https://…`, `http://…`, `ssh://…` or `user@host:path`.
    - Removing a source first stops every enabled app from it.

Templates from all sources are merged into one catalog. Remember that a
template runs with what is effectively host-root power (see below). Only add
sources you trust.

## Security model

- **Authentication.** The Hub has no login of its own. Traefik enforces
  forward-auth and the `lldap_admin` group (`hub=lldap_admin` in core's
  `group-gate-map.conf`) before a request reaches it.
- **Proxy secret.** Every request except `GET /healthz` must carry
  `X-Portcullis-Proxy-Secret` equal to `HUB_PROXY_SECRET`. The comparison is
  constant-time, the secret must be at least 32 characters, and the Hub won't
  start without it. Traefik's `hub-proxy-secret@docker` middleware adds the
  header after forward-auth, so a container that reaches the Hub directly on
  the `portcullis` network can't impersonate an admin by sending
  `X-Forwarded-User`. See [Security & Hardening](hardening.md#hub-proxy-secret).
- **CSRF.** Every state-changing request (POST/PUT/DELETE) must be same-origin
  (checked through `Sec-Fetch-Site`/`Origin`) and carry
  `Content-Type: application/json`. The forward-auth cookie is shared across
  all `*.<domain>` subdomains, so without this a page on any other app would
  count as "same-site".
- **Docker access.** The Hub has no Docker socket. It uses
  `DOCKER_HOST=tcp://socket-proxy-hub:2375` both for the `docker compose` CLI
  (only `up`/`down`) and for its own Engine API calls (status, logs, exec,
  events). The socket proxy denies swarm, plugins, builds, secrets, configs and
  system prune. The Hub can still start containers with any configuration, so
  treat it as host-root-equivalent.
- **Runtime user.** The image runs as **uid/gid 10001** with a read-only root
  filesystem. It writes only `/data` (the `hub_data` volume), `/project/templates`
  (chowned to 10001 by `./portcullis up`) and tmpfs. `secrets/` and `backups/`
  of the core checkout are masked with empty tmpfs mounts.
- **Outbound calls.** The Keycloak admin API and LLDAP are called with Go's
  HTTP client: 20 s timeout, TLS verification, no shelling out to `curl`.
  Credentials never appear in process arguments.
- **Timeouts.** compose up 15 min, compose down 5 min, shell 15 min, git 5 min.
- **Policy file.** The Hub writes `group-gate-policy.json` (version 2)
  atomically to `hub_data`. It is keyed **by subdomain only**:
    - `policies` for apps with an override (apps that inherit publish nothing;
      group-gate uses `default`)
    - `groups` for enabled apps with `group_access: true`
    - `path_groups` from `auth.admin_paths`
    - core subdomains are never published

    The format is defined in [Integration Contracts §4](../guides/integration-contracts.md#4-policy-file-hub-group-gate).

## Image tags and verification

| Tag | Published when |
|-----|----------------|
| `X.Y.Z`, `X.Y`, `X`, `sha-<short>` | A release tag `vX.Y.Z` is pushed |
| `edge` | Every push to `main` |

There is **no `latest` tag**. Core defaults to
`HUB_IMAGE=ghcr.io/porelli/portcullis-hub:edge`. For production, pin a release
by tag **and** digest in `.env`, then run `./portcullis up`.

Images are multi-arch (amd64, arm64) and carry SBOM and provenance attestations.
Each one is signed with cosign (keyless, GitHub OIDC). Verify a tag before you
pin it:

```bash
cosign verify ghcr.io/porelli/portcullis-hub:<tag> \
  --certificate-identity-regexp '^https://github.com/porelli/portcullis-hub/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## Common tasks

### Changing an app's subdomain

Edit the `Host()` rule in the app's `compose.yml` in the Expert tab, and keep
it in the strict form above. The new subdomain must not be used by another
enabled app. The Hub re-publishes the group and policy under the new
subdomain.

### Adding custom middleware

Add Traefik middleware labels in the compose override. Keep the forward-auth
pair in this order, and keep `security-headers@file`:

```yaml
services:
  myapp:
    labels:
      traefik.http.middlewares.myapp-ratelimit.ratelimit.average: "100"
      traefik.http.routers.myapp.middlewares: "client-headers@file,portcullis-auth@docker,portcullis-groups@docker,myapp-ratelimit,security-headers@file"
```

### Backing up app data

App data lives in Docker volumes named `portcullis_<name>` (templates declare
explicit names). `./portcullis backup` covers the core volumes only. Back up
app volumes with your usual tooling, e.g.:

```bash
docker run --rm -v portcullis_jellyfin_config:/data -v "$PWD":/backup \
  alpine tar czf /backup/jellyfin-config.tar.gz -C /data .
```
