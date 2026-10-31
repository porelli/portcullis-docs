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
  v  X-Forwarded-Groups header
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

group-gate is a lightweight forward-auth middleware that maps subdomains to required groups. It combines two sources, both re-read on every request:

1. **`group-gate-map.conf`** (core repo, `scripts/`) holds static entries, mainly for core services:

    ```
    # subdomain = required_group
    auth = lldap_admin
    hub = lldap_admin
    grafana = users_grafana
    ```

2. **The Hub's `group-gate-policy.json`** has a `groups` map that the Hub writes whenever apps are enabled or disabled. For every enabled template with `auth.group_access: true`, it maps each subdomain the template routes to the manifest's `auth.access_group`.

    For example, Nextcloud routes `cloud.<domain>` and declares `users_nextcloud`, so it yields `cloud = users_nextcloud`.

For core subdomains (`auth`, `traefik`, `hub`, `directory`, `enroll`), the map file always wins. A template can never relax them, and they default to `lldap_admin` even if missing from the map file.

When a request arrives at `grafana.<domain>`, group-gate:

1. **Normalizes the host** -- it takes the host from `X-Forwarded-Host`, lowercases it, and strips any port and trailing dot. With `PORTCULLIS_DOMAIN` set, the host must be exactly `<label>.<PORTCULLIS_DOMAIN>`; anything else gets a `403`. Without this, `HUB.<domain>` would have missed the `hub` entry, because Traefik matches hosts case-insensitively.
2. **Checks the auth policy** -- it applies the Hub's per-app auth policy (mTLS / WebAuthn / password) if one is set. A malformed policy (unknown factor or operator) **denies** access rather than falling back to public.
3. **Looks up the group** -- it finds the required group (`users_grafana`) for the subdomain.
4. **Compares groups** -- it reads the user's groups from `X-Auth-Request-Groups` (set by oauth2-proxy), splits them on commas only, and requires an exact match.
5. **Responds** -- it returns `200 OK` and echoes `X-Auth-Request-User`, `X-Auth-Request-Groups` and `X-Forwarded-User` to the backend, or `403 Forbidden`.

If a subdomain has no mapping, group-gate allows any authenticated user and logs `ALLOW-UNMAPPED`. This is the passthrough for apps without group-based access.

!!! warning "Upgrading"
    Apps whose manifest sets `group_access: true` now really require their `access_group` once the updated Hub writes the policy file. Before upgrading, add existing users to those groups in LLDAP, notably `users_nextcloud` and `users_guacamole`. Previously these apps were reachable by any logged-in user.

## Per-App Enforcement

How group access is enforced depends on the auth method:

### Forward-Auth and Header-Auth Apps

The Traefik middleware chain handles everything:

```
portcullis-auth@docker  -->  portcullis-groups@docker  -->  App
(oauth2-proxy)               (group-gate)
```

Both oauth2-proxy and group-gate run as Traefik forward-auth middleware. The app itself is unaware of groups.

### Native OIDC Apps

Native OIDC apps receive the user's groups in the OIDC token from Keycloak. Some apps can enforce group-based access internally:

- **Jellyfin**: The SSO-Auth plugin checks for `users_jellyfin` in the groups claim and maps `admin_jellyfin` to the admin role
- **Immich**: Group claims are available but not yet enforced
- **Vaultwarden**: No group-based restriction

For native OIDC apps that do not enforce groups themselves, you can optionally add the `portcullis-groups@docker` middleware to their Traefik router for external enforcement.

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

1. Ensure the `users_grafana` group exists in LLDAP (it is created automatically when Grafana is enabled in the Hub)
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
