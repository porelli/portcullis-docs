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

A template can run as several **instances** (template contract v2,
[contracts §3.1](integration-contracts.md#31-template-contract-v2-instances-and-hostname-variables-new-contract-v2)): the default instance, whose id is the app ID, and any
number of others an admin creates in the Hub, each with its own id, hostnames,
data volumes, Keycloak clients and groups. When an admin enables an instance,
the Hub:

1. generates the instance's `.env` from the manifest (option values, `generate: random` secrets, referenced core variables) plus the instance variables: `PORTCULLIS_INSTANCE`, one `PORTCULLIS_HOST_<ROUTER>` per host router (the full hostname), `PORTCULLIS_OIDC_CLIENT_ID(_<KEY>)`, `PORTCULLIS_ACCESS_GROUP`, `PORTCULLIS_ADMIN_GROUP`
2. copies the directory to `<core>/templates/<app-id>/` (every instance shares it)
3. registers the instance's Keycloak clients (client id = the instance id)
4. starts the compose file with the Hub's override as its own project, `portcullis-<instance-id>`
5. publishes the instance's hostnames, group, admin paths and policy to group-gate (policy file keyed by full hostname)
6. delivers the rest of its settings: data files (written before the start), hooks, token claims and request headers (see [Declaring settings](#declaring-settings))

## Step 1: Pick an app ID and a default subdomain

The app ID is lowercase and matches `^[a-z0-9][a-z0-9_-]{0,63}$`, e.g.
`uptime-kuma`. It is the directory name and the default instance's id (other
instances get ids an admin chooses). Pick a default subdomain `<sub>` no other
template uses: the default instance runs on `<sub>.<main domain>`, a new
instance is pre-filled with `<sub>-<suffix>.<domain>` on the domain the admin
picks, and every hostname can be edited in the Hub. Core subdomains (`auth`,
`traefik`, `hub`, `directory`, `enroll`, `people`, `metrics`, `mcp`) are off limits. A
hostname belongs to at most one instance: the Hub refuses a second one.

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
| uses a vendor account system (e.g. plex.tv) | `custom` (+ [`auth.native_login`](manifest-reference.md#authnative_login) if it has its own login) | none: the Hub adds Portcullis sign-in through its override |
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
links:
  website: https://myapp.example.org/
  source: https://github.com/example/myapp
instances: multi   # contract v2: one or many instances

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
    url: "https://{{HOST_MYAPP}}"   # the instance's hostname of router myapp

ai:
  unsupported: "No official MCP server; community servers are small and not vetted by Portcullis"
```

### Declaring AI support

Every manifest has an `ai:` block
([reference](manifest-reference.md#ai), [contracts §3.2](integration-contracts.md#32-ai-support-the-ai-block-new-ai-support)),
in exactly one of two forms:

- **`unsupported`**: one sentence saying why the AI can't act in the app
  (no MCP server, no per-person identity, a password vault, a public site, …).
  Optionally an `alternative` `{name, source, note}`: a community server an
  admin may evaluate on their own. The Hub shows it labelled "not vetted by
  Portcullis" and never installs it.
- **`mcp`**: the app's companions. A companion is the app's built-in MCP
  server (`kind: builtin`) or a service running the upstream project's, or a
  vetted community project's, published image (`kind: companion`), pinned by
  digest. **Never MCP server, adapter or proxy code written for
  Portcullis.** Vet a community project first: maintained, an open licence,
  a multi-user identity that fits an identity mode, no shared admin identity
  running tool calls, a pinned release; record why in the template's notes.

Choose the identity mode by what the app offers:

| The app has | Mode | You write |
|-------------|------|-----------|
| per-person API tokens or app passwords an admin CLI can create | `app_token` | `mint` and `revoke` hooks (`when: [ai]`) that create a `portcullis-ai-<random>` credential for the given user (exit 3 when the person has no account yet; never create accounts) and delete credentials by id, or every `portcullis-ai-*` one for `revoke_all` |
| a server that trusts identity headers from one caller | `identity_headers` | a `caller_secret` (a `generate: random` env entry) the companion requires, and a trust network so the app trusts the headers only from the companion |
| its own OAuth-protected MCP route that signs in through Keycloak | `app_oauth` | a `revoke` hook that ends a person's AI tokens by their Keycloak id (`sub`), or everyone's for `revoke_all` |

Then classify the tools: `writes` (hidden in read-only mode), `confirm`
(deletes and anything that sends data out: the person approves with a
passkey) and `never` (tools that would put a secret in front of the model,
or open access). The gate also confirms tools the companion marks
destructive. Hooks get one JSON document on stdin, and their stdout is never
stored ([§15.5](integration-contracts.md#155-identity-modes-tool-policy-and-hook-io)).

The companion's alias and router are the Hub's: `portcullis-mcp-` appears
nowhere in `compose.yml`, the companion service has no Traefik labels, no
host ports and isn't on `portcullis-proxy`, and it reads
`${PORTCULLIS_AI_READONLY_<NAME>:-true}` to start read-only. See `gitea/`
(`app_token`), `grafana/` (`identity_headers`), `nextcloud/` (`app_token`
with HTTP Basic) and `homeassistant/` (`app_oauth`).

### Declaring settings

Anything an admin should be able to change (a library folder, a quota, a
role, an API key) is an option under `settings:`. The template declares what
the option is and how the app reads it; the Hub validates the value, works
out who gets what and delivers it. Copy the closest pilot: `immich/`
(per-person claims), `grafana/` (per-person header), `nextcloud/` (a live
hook), `firefox-sync/` (values each person enters, in a data file).

```yaml
settings:
  sections: [Library]
  options:
    - key: trash_days              # an identifier, not an env name
      label: Keep deleted items for
      type: int
      unit: days
      min: 0
      max: 3650
      default: 30
      section: Library
      applies: restart             # the app reads it at start
      delivery: [{env: IMMICH_TRASH_DAYS}]
```

Decide three things for each option:

1. **Its type**: `string`, `int`, `size`, `duration`, `bool`, `enum`,
   `multi_enum`, `list`, `table`, `path`, `secret`, `group(s)` or
   `user(s)`, with the type's constraints (`pattern`, `min` / `max`,
   `options`, …). Sizes are bytes and durations seconds; write them with
   units (`10GiB`, `30d`). Credentials the admin enters are `type: secret`,
   never an `env` entry.
2. **Its scope**: `instance` (the default: one value), `person` (a default
   plus values per group, resolved per person with `resolve`), `group`
   (records per group, delivered as a whole) or `person_entered` (each
   person enters their own, see below).
3. **How the app reads it** (`delivery`) and **when a change takes effect**
   (`applies`):

| The app reads it… | Delivery | `applies` |
|-------------------|----------|-----------|
| from an environment variable at start | `{env: NAME}`; compose uses `${NAME…}` | `restart` |
| as a bind-mounted host folder | `type: path` with `target: {service, mount}` (no `delivery`) | `restart` |
| from a token claim at sign-in (native OIDC) | `{claim: {client, name, json_type, render}}` | `next_sign_in` |
| from a request header (forward-auth / header-auth) | `{header: {name: X-Forwarded-Attr-<Name>}}` | `next_request` |
| from a JSON file at start | `{file: {name}}` + a `files:` entry | `restart` (or `reload`) |
| through its own API or CLI, while running | `{hook: <name>}` + a `hooks:` entry | `live` |

A `person` option needs a per-person delivery (claim, header, file or hook);
one environment variable can't carry a value per person. Values are rendered
per delivery with `render` (`unit: GiB`, `unlimited: "-1"`, `join: ","`,
`format: json`), so the Hub stores one canonical value and each app gets the
form it understands.

Per-person roles and admin flags are `privileged: true`: their default is
the lowest value, and `group_values` may preset only the instance's admin
group (`"{{ADMIN_GROUP}}": Admin`). The Hub then accepts rows only from
groups delegates can't steer.

The complete list of fields and rules is in the
[Manifest Reference](manifest-reference.md#settings); `tests/validate.py`
refuses exactly what the Hub refuses, with the same messages.

### Host folders, doctor checks and LAN-only ports

If the app reads or writes a host folder (media libraries, photos, a
recordings folder), give the `path` option a **`folder` block** instead of
`mode`, `needs` and `writes_as`. It tells the Hub what the app does there
and as which ids, so an admin can point the setting at a
[shared folder](../operations/hub.md#shared-folders) that several apps use
with consistent ownership:

```yaml
    - key: movies_path
      label: Movies folder
      type: path
      target: {service: jellyfin, mount: /data/movies}
      folder:
        access: read                  # read is always mounted read-only
        runs_as: {uid: 0, gid: 0}     # the ids the process has: here root, no compose user:
      applies: restart
```

Check what the image really does before you choose `runs_as` and
`joins_group`:

- **Which uid and gid** the app's process has (`docker exec … id`). With a
  compose `user:`, the numbers must match it; with `user:
  "${PUID:-1000}:${PGID:-1000}"`, use `uid_env: PUID` / `gid_env: PGID`
  (both instance `int` options).
- **Whether it keeps supplementary groups.** The default `group_add` adds
  the folder's gid as a supplementary group. Images that start the app
  through `s6-setuidgid`, `su -g` or a similar switch drop it. Then use
  `joins_group: gid_env` (the Hub writes the folder's gid into the
  `runs_as.gid_env` variable), as Plex does with `PLEX_GID`. All folder
  options of that service then share one primary group: they must use the
  same shared folder, so say so in the notes (Plex's "keep all three
  library settings on the same shared folder").
- **Other `group_add` entries** on that service (hardware transcoding's
  render group, for example) must be numbers or exactly one `${NAME}` of a
  declared `int` option: declare `render_gid` (env `RENDER_GID`, default
  `109`) and write `group_add: ["${RENDER_GID:-109}"]`. Group names are
  refused next to a folder block.
- **Never use gids 60000–60999**: they are the folder groups.

Add **`checks`** next to `folder` when the app needs something the Hub can
verify: a filesystem feature (`filesystem`, e.g. `needs: [xattr, acl]` for
macOS metadata), no second writer (`exclusive`), or `free_space`. The
doctor shows your `reason` with its finding.

Mark a port that should never be reachable from the internet (SMB, a local
discovery protocol) **`lan_only: true`**: the doctor then warns when it is
bound to all interfaces or a public address.

The fields are in
[Manifest Reference → Shared folders](manifest-reference.md#shared-folders-folder-checks-lan_only);
the full rule set and every refusal are in
[contracts §13.15](integration-contracts.md#1315-shared-folders-checks-and-lan-only-ports).

### One-off jobs

If the app has a setup or migration container that runs once and exits (e.g., `guacamole-init`, `nextcloud-db-init`), declare it in the manifest's `jobs:` list. The Hub treats job containers differently:

- A job that exited 0 is **done** (green) and counts as running
- A job that exited non-zero is **failed** (red) and triggers drift
- A job with no container is **missing** (red) and triggers drift
- A finished job never makes the app "not all running"

Most jobs are detected automatically: any service another service waits for with `depends_on: {<job>: {condition: service_completed_successfully}}` is a job. List the others explicitly:

```yaml
# manifest.yaml
jobs:
  - jellyfin-setup
  - immich-lock-local-users
```

Jobs show on the instance page's Overview tab as "setup job done", "setup job failed", "setup job running", or "setup job pending".

See [Manifest Reference → jobs](manifest-reference.md#jobs) for the complete rules.

### Setup options and compose profiles

Some apps need a choice made **before the first start** that can't change later (e.g., which database engine to use). Declare these as **setup options** with `setup: true` and `fixed_after_start: true`:

```yaml
# manifest.yaml (Nextcloud example)
settings:
  sections: [Database]
  options:
    - key: database
      label: Database engine
      section: Database
      type: enum
      options: [sqlite, mysql, postgres]
      default: postgres
      scope: instance
      setup: true
      fixed_after_start: true
      profiles:
        sqlite: []
        mysql: [db-mysql]
        postgres: [db-postgres]
      delivery:
        - env: NEXTCLOUD_DATABASE
      applies: restart
```

Setup options:

- Are asked in the setup form (Install… / + Add instance) before anything starts
- Show whether they're fixed or changeable after the first start (🔒 indicator)
- Can switch which compose services run using `profiles:` (one entry per option value)
- Are stored at creation and can't change after the instance's first successful start (for fixed ones)

**How `profiles` works:**

- Map each enum value to the compose profiles it starts: `{postgres: [db-postgres], mysql: [db-mysql], sqlite: []}`
- The Hub writes `COMPOSE_PROFILES='db-postgres,db-mysql'` (or `''` for none) into the instance's `.env`
- Compose starts only services with matching profiles (or no `profiles:` key)
- Every value must have an entry; use `[]` for values that start no additional profiles

**compose.yml structure:**

```yaml
# compose.yml (Nextcloud example)
services:
  nextcloud:
    # No profiles: always runs
    depends_on:
      nextcloud-mariadb:
        condition: service_healthy
        required: false    # Optional dependency
      nextcloud-postgres:
        condition: service_healthy
        required: false
    environment:
      # The entrypoint wrapper checks $NEXTCLOUD_DATABASE and exports only
      # the chosen database's variables, then waits for its TCP port
      NEXTCLOUD_DATABASE: ${NEXTCLOUD_DATABASE:-postgres}

  nextcloud-mariadb:
    image: mariadb:11.8.9@sha256:...
    profiles: [db-mysql]
    # ... rest of service definition

  nextcloud-postgres:
    image: postgres:17.11-alpine@sha256:...
    profiles: [db-postgres]
    # ... rest of service definition
```

**Validation rules:**

- Every profile name used in `profiles:` must appear in the manifest's `profiles` map
- Every service with `profiles:` must be started by at least one setup choice value
- A service without `profiles:` (unprofiled) may not depend on a profiled service (Compose can't start it when the profile is off)

See [Manifest Reference → Setup options](manifest-reference.md#setup-options-setup-fixed_after_start-profiles) and [contracts §13.18](integration-contracts.md#1318-setup-options-and-compose-profiles-new-apps) for the complete rules and the Hub's enforcement.

### Data files, hooks and reload

When the app reads a configuration file, or needs per-person values without
a claim or header, declare a **data file**. The Hub writes
`<mount>/<name>.json` (and `<name>.secrets.json` for secret options) and
bind-mounts the directory read-only into the service. An init one-shot
usually renders the app's own config from it:

```yaml
files:
  - name: allowlist
    service: firefox-sync-init
    mount: /portcullis
    on_membership_change: restart   # people joining or leaving: restart
```

The service must be able to read it: run it as root, or give it
`group_add: ["10001"]` for the data file (mode 0640). A secrets file (mode
0600) needs root or `user: "10001"`.

When the app can apply a change while it runs (an admin CLI, an API),
declare a **hook**. The Hub runs the command in the running container with
Docker exec and writes the full desired state as JSON on its standard input:

```yaml
hooks:
  - name: apply-settings
    service: nextcloud
    user: www-data
    command: [php, /portcullis/apply-settings.php]   # argv, no shell
    when: [start, settings_change]
    timeout: 10m                                      # default 30s, at most 10m
```

A hook must be idempotent (it gets the whole state every time, never a
diff), exit 0 only when everything was applied, and never print secrets
(the Hub blanks the ones it sent, but don't rely on it). Secrets reach a
hook only on standard input, never in its arguments or environment.

When the app re-reads its configuration on a signal, declare `reload`
(`{service, signal: HUP}`, or `{hook: <name>}`) and use `applies: reload`.

### Values each person enters

Some apps need something only the person knows. Firefox Sync accepts only
the Mozilla accounts on its allowlist, and Portcullis can't know which
Mozilla account belongs to whom. So each member of the access group enters
their own account ID on **My apps** (`people.<domain>`), and the Hub writes
the list into the data file above:

```yaml
auth:
  method: custom
  access_group: users_firefox-sync   # who may enter a value

settings:
  sections: [Accounts]
  options:
    - key: mozilla_uid
      label: Mozilla account ID
      description: >
        The uid of the Mozilla account you sign in to Firefox with
        (32 lowercase hexadecimal characters).
      section: Accounts
      type: string
      pattern: ^[0-9a-f]{32}$
      min_len: 32
      max_len: 32
      scope: person_entered
      unique: true            # no two people may register the same uid
      admin_override: true    # admins may enter one for someone
      applies: restart        # = the file's on_membership_change
      delivery:
        - file: {name: allowlist}
```

The data file then has an `entries` section with only the values of people
who currently have access, sorted by user (`values` holds the instance
options delivered to the same file):

```json
{
  "version": 1,
  "instance": "firefox-sync",
  "values": {"extra_accounts": ["fedcba9876543210fedcba9876543210"]},
  "people": {},
  "groups": {},
  "entries": {"mozilla_uid": [{"user": "alice", "value": "0123456789abcdef0123456789abcdef"}]}
}
```

Rules for person-entered options:

- types `string`, `int`, `bool` or `enum`; a `string` needs `max_len` (at
  most 256), a `pattern` or a `format`;
- no `default`, `required`, `resolve`, `group_values`, `privileged` or
  `requires`, and no `applies: account_creation`;
- `applies` must match the delivery: a file's `on_membership_change`, a hook
  with `membership_change` in `when` (`live`), a claim (`next_sign_in`) or a
  header (`next_request`). An env delivery carries the whole list as one
  variable (`render.join` or `render.format: json`, `applies: restart`);
- a template whose routes carry no Portcullis identity (method `public` or
  `custom`, or the app's own login only) must name `auth.access_group`: its
  members are the people who may enter a value.

The app must fail closed on this input: Firefox Sync's init refuses to start
the server on a missing, unreadable or foreign allowlist, and an empty list
lets nobody sync.

## Step 4: Write `compose.yml`

`tests/validate.py` checks every rule below.

### Rules

- **Networks.** Services with `traefik.enable: "true"` use
  `networks: [default, portcullis-proxy]`. Databases, caches and sidecars stay
  on `default` only. Declare `portcullis-proxy` as `external: true`. No other
  networks.
- **Routers.**
    - Use exactly the form
      `` rule: Host(`${PORTCULLIS_HOST_<ROUTER>:-<sub>.portcullis.local}`) ``,
      optionally `` && <path matchers> ``. `<ROUTER>` is the name of the host
      router (the one whose rule is `Host()` alone) upper-cased, with `-` and
      `.` turned into `_` (`myapp-ui` → `PORTCULLIS_HOST_MYAPP_UI`); the value is
      the instance's full hostname. Path routers on the same host reuse the
      host router's variable. The Hub parses the rule strictly and rejects
      anything it can't fully resolve (see
      [Hub → Template rules](../operations/hub.md#template-rules-enforced-by-the-hub)).
    - Use the same variable, with the same default, wherever the app needs its
      own hostname (base URL, redirect URIs, `hostname:`), and
      `{{HOST_<ROUTER>}}` in the manifest's `urls` and redirect URIs.
    - No `_` in Traefik router, service or middleware names (the Hub renames
      them per instance with `<instance-id>_<name>`).
    - Set `entrypoints: websecure`.
    - Set `tls.options` to `authaware@file`, `public@file` or `protected@file`.
      The Hub overrides it from the app's access policy.
    - Include `security-headers@file` in the middlewares.
- **Middleware order** for gated routers:
  `client-headers@file,portcullis-auth@docker,portcullis-groups@docker,security-headers@file`.
  List `portcullis-auth@docker` on the router itself, never inside a chain
  middleware of your own: on an extra-domain hostname the Hub swaps it for the
  extra-domain sign-in, and it refuses (400) extra-domain hostnames for a
  router whose own chain reaches `portcullis-auth`.
  `client-headers@file` first lets group-gate check client-cert revocation.
- **Volumes** declare **no** `name:` in a `multi` template: the Hub's override
  names them, `portcullis_<key>` for the default instance and
  `portcullis_<instance-id>-<key>` for the others. Never rename a volume key
  later: it is the default instance's data volume name.
- **Files** shipped with the template are mounted as
  `./templates/<app-id>/<file>`, never `./<file>`. Compose resolves relative
  paths against the core checkout on the host. From core, only
  `./certs/ca-bundle.crt:<path>:ro` may be mounted.
- **Variables.** Core variables (`PORTCULLIS_DOMAIN`, `PORTCULLIS_PROXY_SUBNET`,
  `PORTCULLIS_PROXY_IP_RANGE`, `PORTCULLIS_TRAEFIK_IP`) always use their default
  form. Instance values come from the instance variables, always in the
  default form with the default instance's value:
  `${PORTCULLIS_OIDC_CLIENT_ID:-myapp}`, `${PORTCULLIS_ACCESS_GROUP:-users_myapp}`,
  `${PORTCULLIS_ADMIN_GROUP:-admin_myapp}` (also in support files, passed through
  `environment:`). Every other variable must be declared in the manifest. Required ones
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
      traefik.http.routers.myapp.rule: Host(`${PORTCULLIS_HOST_MYAPP:-myapp.portcullis.local}`)
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: authaware@file
      traefik.http.routers.myapp.middlewares: client-headers@file,portcullis-auth@docker,portcullis-groups@docker,security-headers@file
      traefik.http.services.myapp.loadbalancer.server.port: "8080"

volumes:
  myapp-data: {}   # no name: the Hub sets it per instance

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
      OIDC_CLIENT_ID: ${PORTCULLIS_OIDC_CLIENT_ID:-myapp}
      OIDC_REDIRECT_URI: https://${PORTCULLIS_HOST_MYAPP:-myapp.portcullis.local}/callback
      OIDC_ALLOWED_GROUP: ${PORTCULLIS_ACCESS_GROUP:-users_myapp}
      OIDC_CLIENT_SECRET: ${MYAPP_OIDC_SECRET:?generated by the Hub}
      SSL_CERT_FILE: /certs/ca-bundle.crt   # trust the internal/staging CA
    volumes:
      - ./certs/ca-bundle.crt:/certs/ca-bundle.crt:ro
    networks:
      - default
      - portcullis-proxy
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: Host(`${PORTCULLIS_HOST_MYAPP:-myapp.portcullis.local}`)
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
    redirect_uri: "https://{{HOST_MYAPP}}/callback"
    name: My App
```

Gate an admin path of a native-OIDC app with a second router and
`auth.admin_paths: ["/admin"]`:

```yaml
      traefik.http.routers.myapp-admin.rule: Host(`${PORTCULLIS_HOST_MYAPP:-myapp.portcullis.local}`) && PathPrefix(`/admin`)
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

### The sign-in test

Every template also declares, in `manifest.yaml`, how CI signs real users in
to it ([`tests.signin`](manifest-reference.md#testssignin)). After your shell
test, CI creates a member, an admin and an outsider, signs each in through a
setup link with a virtual security key and the app's own sign-in, and checks
the member sees their username, only the admin has admin rights and the
outsider is refused:

```yaml
tests:
  signin:
    path: /login
    login: ["button:has-text('Sign in with SSO')"]   # the app's SSO button, if it has one
    signed_in:
      text: "{username}"
    admin:                                         # if auth.group_admin is true
      reach: /admin
```

`public`, `custom` and `mtls` apps set `skip: "<reason>"` instead. Dependabot
image bumps run it too, so a new release that breaks sign-in is caught in its
PR. On failure, the run's `e2e-<app>` artifact has a screenshot of every
step, a Playwright trace per user and the logs.

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

- [ ] App ID and default subdomain are unique; no core subdomain; `instances: multi`
- [ ] `manifest.yaml` passes the schema; auth method fits the app
- [ ] `compose.yml`: networks, `` Host(`${PORTCULLIS_HOST_<ROUTER>:-…}`) `` form, own hostname / client id / groups via the instance variables, middleware order, `security-headers@file`, volumes without `name:`, no `ports:`
- [ ] Secrets are `generate: random`; no default passwords; secrets an admin enters are `type: secret` options
- [ ] Every option has an explicit `applies` that matches how the app reads it; per-person roles are `privileged`; hooks are idempotent and fail on any error
- [ ] Host folders: a `folder` block with the `runs_as` ids the process really has, `joins_group: gid_env` where the image drops supplementary groups; LAN-only ports marked `lan_only: true`
- [ ] Header-auth: identity header trusted only from `PORTCULLIS_TRAEFIK_IP`
- [ ] An `ai:` block: `unsupported` with the reason, or vetted companions with an identity mode, `writes` / `confirm` / `never` and `when: [ai]` hooks
- [ ] Images pinned `tag@sha256:…`; directory added to `.github/dependabot.yml`
- [ ] `tests/apps/<app-id>.sh` added
- [ ] `tests.signin` in `manifest.yaml` (or `skip` with the reason for public / custom / mtls apps)
- [ ] `python3 tests/validate.py` and `tests/compose-config.sh` pass
