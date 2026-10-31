# Groups & Access Control

Portcullis uses LLDAP groups to control which users can access which apps. This page explains the group model, how groups flow through the system, and how to manage access.

## The Group Model

Every app in Portcullis has two associated LLDAP groups:

| Group | Pattern | Purpose |
|-------|---------|---------|
| **Access group** | `users_<app>` | Grants access to the app. Users not in this group get a 403 from group-gate. |
| **Admin group** | `admin_<app>` | Grants admin privileges within the app (if the app supports group-based admin). |

For example, Jellyfin has:

- `users_jellyfin` -- Members can access Jellyfin
- `admin_jellyfin` -- Members get Jellyfin admin privileges

These group names are defined in each app's `manifest.yaml` under `auth.access_group` and `auth.admin_group`.

## How Groups Flow

Groups originate in LLDAP and flow through the system:

```
LLDAP (source of truth)
  |
  v  LDAP federation (periodic sync)
Keycloak (identity provider)
  |
  v  OIDC groups claim
oauth2-proxy (forward auth)
  |
  v  X-Auth-Request-Groups header
group-gate (access check)
  |
  v  subdomain -> required group mapping
App (allowed or denied)
```

### Step by step:

1. **LLDAP** stores users and groups. An admin creates groups and assigns users to them.
2. **Keycloak** federates from LLDAP via its LDAP user storage provider. Groups are synced periodically (and can be triggered manually).
3. **oauth2-proxy** authenticates users via Keycloak's OIDC endpoint. The ID token includes a `groups` claim with the user's LLDAP groups.
4. **group-gate** receives the `X-Auth-Request-Groups` header (set by oauth2-proxy) and checks whether the user belongs to the required group for the requested subdomain.

## group-gate and the Subdomain Map

group-gate is the forward-auth service behind the `portcullis-groups@docker`
middleware. It maps **subdomains** to required groups. Two sources are merged,
and both are re-read on every request:

1. **`group-gate/group-gate-map.conf`** in the core repo (mounted read-only
   into group-gate) holds static entries, mainly for the core services:

    ```
    # subdomain=required_group
    auth=lldap_admin
    hub=lldap_admin
    grafana=users_grafana
    ```

    Edits take effect on the next request; no restart is needed.

2. **The Hub's `group-gate-policy.json`** (version 3, on the `hub_data` volume)
   has a `groups` map. The Hub rewrites it whenever an app is enabled,
   disabled or reconfigured. For every **enabled** template with
   `auth.group_access: true`, each subdomain the template routes maps to the
   manifest's `auth.access_group`. For example, Nextcloud routes
   `cloud.<domain>` and declares `users_nextcloud`, so it yields
   `cloud = users_nextcloud`. Hub entries add to or override the map file for
   app subdomains.

**Keys are subdomains only.** Policies, groups and path rules are never keyed
by template ID, because an ID could equal another app's subdomain. The Hub
refuses to enable a template that routes a subdomain another enabled app
already routes, and rejects templates whose `Host()` rules it can't fully
resolve (see [Hub → Template rules](hub.md#template-rules-enforced-by-the-hub)).

**Core subdomains** (`auth`, `traefik`, `hub`, `directory`, `enroll`, `metrics`) always
come from the map file. The Hub never publishes them, and group-gate ignores
them in the policy file. If they are missing from the map file they default to
`lldap_admin`.

### What group-gate checks

When a request for `grafana.<domain>` arrives, group-gate runs these checks in
order and stops at the first failure:

1. **Host.** It takes the host from `X-Forwarded-Host`, lowercases it, and
   strips any port and trailing dot. The host must be exactly
   `<label>.<PORTCULLIS_DOMAIN>`; anything else gets a 403. Traefik matches
   hosts case-insensitively, so without normalisation `HUB.<domain>` would
   miss the `hub` entry.
2. **Reserved group.** A user whose groups include `__portcullis_deny__` is
   denied.
3. **Revocation.** If the request carries a client certificate (via
   `client-headers@file`, which must come before `portcullis-groups@docker`),
   its serial must not be revoked. See [TLS & mTLS](../setup/certificates.md#revocation).
4. **Auth policy.** If the app has a policy (or there is a global default),
   the session's `acr`/`amr` must satisfy it. Otherwise group-gate returns the
   step-up page. Policies satisfied only through `mtls` also need the current
   request's certificate to match the user (mTLS binding). See
   [Authentication Policies](auth-policies.md).
5. **Group.** It looks up the subdomain's required group (`users_grafana`) and
   compares it with `X-Auth-Request-Groups` (set by oauth2-proxy). The header
   is split on commas only, and the match must be exact.
6. **Path rules.** If the subdomain has `path_groups`, the group of the matching
   path rule is required **in addition** (see below).
7. **Allow.** It returns `200 OK` and sets `X-Forwarded-User` /
   `X-Auth-Request-User` (the LLDAP username), `X-Forwarded-Email` /
   `X-Auth-Request-Email` and `X-Auth-Request-Groups` for the backend.
   Identity is always the immutable LLDAP username, never the user-editable
   email. Apps must never create, match or link accounts by email.
   Otherwise it returns `403 Forbidden`.

**Fail closed.** These all deny the request instead of falling back to
"public":

- a policy file that exists but can't be parsed
- a `version` newer than group-gate understands
- an unknown factor, op or rule shape

If a subdomain has no mapping at all, group-gate allows any authenticated user
and logs `ALLOW-UNMAPPED`. This is the passthrough for apps without group-based
access.

### The reserved group `__portcullis_deny__`

The Hub publishes `groups[sub] = "__portcullis_deny__"` for subdomains it knows
are routed but can't attribute a config to. That happens when:

- an enabled app has neither a template nor a stored snapshot
- a `portcullis-<id>` project runs without being enabled

Nobody is a member of that group, so every request to those subdomains is
denied ("The configuration of … is unavailable"). A user who *claims*
membership is denied everywhere.

!!! danger "Never create an LLDAP group named `__portcullis_deny__`"
    Membership would be treated as tampering and deny that user on every app.

See [Hub → Fail-closed behaviour](hub.md#fail-closed-behaviour).

### Path rules (`path_groups` and `admin_paths`)

Some apps keep an admin area on a path of the same subdomain, e.g.
Vaultwarden's `/admin`. A template lists such prefixes in its manifest:

```yaml
auth:
  admin_group: admin_vaultwarden
  admin_paths: ["/admin"]
```

For every subdomain of an enabled template, the Hub publishes
`path_groups[sub] = [{"prefix": "/admin", "group": "admin_vaultwarden"}]`. On
requests under that prefix, group-gate then requires `admin_group` **in
addition** to the subdomain's group.

Matching:

- **What is matched.** The path from `X-Forwarded-Uri` with the query and
  fragment stripped. It is percent-decoded **once**, `//` is collapsed, and dot
  segments (`/./`, `/../`) are resolved.
- **Ambiguous paths are denied.** If an encoded slash, backslash or NUL
  (`%2F`, `%5C`, `%00`) is still present after that one decode, or the path has
  control characters, the request is denied outright. Different backends read
  such paths differently.
- **Deny-biased variants.** A rule applies if it matches **any** of: the
  primary form, the fully decoded form, `\` read as `/`, `;` path parameters
  stripped. Each is compared both case-sensitively and case-insensitively. So
  `/%61dmin`, `//admin`, `/x/../admin` and `/ADMIN` all hit the `/admin` rule
  (CI's browser test checks exactly these).
- **Segment-boundary prefixes.** `/admin` matches `/admin` and `/admin/x`, but
  not `/administrator`. The longest matching prefix wins. If different variants
  hit rules with different groups, all of those groups are required.

!!! note "Only routers with group-gate are covered"
    Path rules only work on routers whose middlewares include
    `portcullis-auth@docker,portcullis-groups@docker`. For a native-OIDC app,
    the template routes the admin path through its own higher-priority
    `PathPrefix` router with forward-auth (`validate.py` in the templates repo
    checks that such a router exists).

### `/authenticated`: any signed-in user

group-gate also serves `/authenticated`, used by the core middleware
`portcullis-self@docker`. It runs every check except the subdomain group check
(step 5): host, revocation, policy, path rules, and a signed-in user. Core uses
it for `enroll.<domain>/self`, where every user may renew **their own**
certificate without being in `lldap_admin`.

## Per-App Enforcement

How group access is enforced depends on the auth method:

### Forward-Auth and Header-Auth Apps

The Traefik middleware chain handles everything:

```
client-headers@file --> portcullis-auth@docker --> portcullis-groups@docker --> App
(client cert info)      (oauth2-proxy)             (group-gate)
```

Both oauth2-proxy and group-gate run as Traefik forward-auth middleware. The app itself is unaware of groups (header-auth apps receive them in `X-Auth-Request-Groups`).

### Native OIDC Apps

Native OIDC apps receive the user's groups in the `groups` claim (the Hub attaches the `groups` client scope to every client it registers). Some apps enforce group-based access themselves, e.g. Jellyfin's SSO plugin requires `users_jellyfin` and maps `admin_jellyfin` to admin. Each app page in the [App Catalog](../apps/index.md) says what it does.

Apps that can't restrict OIDC logins by group (GitLab, LiteLLM, Vaultwarden) put only their interactive login paths behind forward-auth + group-gate on a higher-priority `PathPrefix` router, and keep their API router without forward-auth. Never put `portcullis-auth@docker` on the host-wide router of a native-OIDC app: it would break API clients and mobile apps.

### Public Apps

No group enforcement. Anyone can access the app.

## Managing Groups

### Creating Groups

Groups are created in LLDAP. You can use the LLDAP web UI or the GraphQL API.

**Via LLDAP Web UI:**

1. Open `https://directory.<your-domain>`
2. Log in as admin
3. Navigate to **Groups**
4. Click **Create group**
5. Enter the group name (e.g., `users_grafana`)

**Via LLDAP GraphQL API:**

```bash
# Get an auth token
TOKEN=$(curl -s http://localhost:17170/auth/simple/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"YOUR_LLDAP_PASSWORD"}' \
  | jq -r '.token')

# Create a group
curl -s http://localhost:17170/api/graphql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"mutation { createGroup(name: \"users_myapp\") { id } }"}'
```

### Adding Users to Groups

**Via LLDAP Web UI:**

1. Navigate to **Users** and click on a user
2. In the **Groups** section, click **Add to group**
3. Select the group

**Via LLDAP GraphQL API:**

```bash
# Add user "alice" to group with ID 42
curl -s http://localhost:17170/api/graphql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"mutation { addUserToGroup(userId: \"alice\", groupId: 42) { ok } }"}'
```

### Syncing Groups to Keycloak

Keycloak syncs groups from LLDAP periodically. To trigger an immediate sync:

1. Open Keycloak admin at `https://auth.<your-domain>/admin/`
2. Go to **User Federation**
3. Click on the LLDAP provider
4. Click **Synchronize all users**

Or via API:

```bash
# Get admin token
KC_TOKEN=$(curl -s http://localhost:8080/realms/master/protocol/openid-connect/token \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=YOUR_KC_ADMIN_PASSWORD" \
  -d "grant_type=password" | jq -r '.access_token')

# Find LDAP provider ID
LDAP_ID=$(curl -s http://localhost:8080/admin/realms/portcullis/components \
  -H "Authorization: Bearer $KC_TOKEN" | jq -r '.[] | select(.providerId=="ldap") | .id')

# Trigger full sync
curl -s -X POST \
  "http://localhost:8080/admin/realms/portcullis/user-storage/$LDAP_ID/sync?action=triggerFullSync" \
  -H "Authorization: Bearer $KC_TOKEN"
```

## Example: Giving a User Access to an App

To give user `alice` access to Grafana:

1. Create the `users_grafana` group in LLDAP if it doesn't exist yet (the Hub does not create groups)
2. Add `alice` to the `users_grafana` group in LLDAP
3. Wait for Keycloak sync (or trigger manually)
4. `alice` can now access `https://grafana.<your-domain>`

To also give `alice` admin privileges in Grafana, add her to `admin_grafana`.

## Example: Revoking Access

To revoke `alice`'s access to Grafana:

1. Remove `alice` from the `users_grafana` group in LLDAP
2. Trigger a Keycloak sync
3. `alice` will receive a 403 on her next request (after her oauth2-proxy session expires)

!!! tip
    oauth2-proxy sessions have a configurable expiry. For immediate revocation, you can also revoke the user's Keycloak sessions from the Keycloak admin panel.
