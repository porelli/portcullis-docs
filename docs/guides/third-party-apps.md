# Third-Party Apps

This guide explains how to put existing Docker apps behind Portcullis authentication **without creating a Hub template**. Use this when you have an app that:

- Is already running (or you manage its compose file yourself)
- Doesn't need to appear in the Hub catalog
- Just needs to be reachable through Portcullis with SSO/group enforcement

## Quick Overview

Any Docker container can join the `portcullis-proxy` network and get Traefik routing + authentication by adding the right labels. No manifest, no Hub, no template repo required.

## Option 1: Forward Auth (app has no SSO support)

Best for apps that have no OIDC/SAML support — Portcullis handles authentication entirely.

### compose.yml

```yaml
services:
  myapp:
    image: myorg/myapp:latest
    networks:
      - default
      - portcullis-proxy
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: Host(`myapp.${PORTCULLIS_DOMAIN}`)
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: authaware@file
      traefik.http.routers.myapp.middlewares: client-headers@file,portcullis-auth@docker,portcullis-groups@docker,security-headers@file
      traefik.http.services.myapp.loadbalancer.server.port: "8080"
    restart: unless-stopped

networks:
  portcullis-proxy:
    external: true
```

### What this does

1. User visits `https://myapp.yourdomain.com`
2. `portcullis-auth@docker` (oauth2-proxy) checks for a session cookie
3. No cookie → redirect to Keycloak → user authenticates with YubiKey
4. `portcullis-groups@docker` (group-gate) checks the user's groups
5. If authorized → request forwarded to your app

### Group enforcement

Add your app's subdomain to `group-gate/group-gate-map.conf` in the core checkout:

```
myapp=users_myapp
```

Then create the group in LLDAP and add users to it. group-gate re-reads the map file on every request, so no restart is needed. If you skip this step, any authenticated Portcullis user can access the app (group-gate logs `ALLOW-UNMAPPED`).

!!! note "Use a subdomain no Hub app uses"
    group-gate keys everything by subdomain. If a Hub-enabled app routes the same subdomain, the Hub's `groups` entry overrides the map file. Hosts outside `<label>.<PORTCULLIS_DOMAIN>` are always denied by group-gate. Core subdomains (`auth`, `traefik`, `hub`, `directory`, `enroll`, `metrics`) cannot be reused.

`client-headers@file` must come **before** `portcullis-groups@docker`, so group-gate sees the client certificate and can enforce revocation. For admin-only paths, use a separate `PathPrefix` router; per-path groups (`path_groups`) are only published by the Hub for templates.

### Passing user identity

The authenticated user's LLDAP username is available to your app in the `X-Forwarded-User` header (set by the group-gate middleware), the email in `X-Forwarded-Email` and the groups in `X-Auth-Request-Groups`. Identify users by the username: LLDAP users can edit their own email. Many apps support "trusted header" authentication.

!!! danger "Trust the header only from Traefik"
    Every container on `portcullis-proxy` can connect to your app directly. Configure the app to accept identity headers only from `PORTCULLIS_TRAEFIK_IP` (default `172.31.250.2`), never from the whole subnet. See [Header Auth Pattern → Header Security](header-auth-app.md#header-security).

| App Framework | Config |
|--------------|--------|
| **Grafana** | `GF_AUTH_PROXY_ENABLED=true`, `GF_AUTH_PROXY_HEADER_NAME=X-Forwarded-User`, `GF_AUTH_PROXY_HEADER_PROPERTY=username`, `GF_AUTH_PROXY_WHITELIST=172.31.250.2` |
| **Kanboard** | `REVERSE_PROXY_AUTH=true`, `REVERSE_PROXY_USER_HEADER=HTTP_X_FORWARDED_USER`, `TRUSTED_PROXY_NETWORKS=172.31.250.2/32` |
| **Firefly III** | `AUTHENTICATION_GUARD=remote_user_guard` |
| **Generic** | Read `X-Forwarded-User` header in your app |

## Option 2: Native OIDC (app supports OpenID Connect)

Best for apps that have built-in OIDC/OAuth2 support. The app handles its own login flow with Keycloak.

### Step 1: Register a Keycloak client

```bash
# Get admin token
TOKEN=$(curl -s http://localhost:8080/realms/master/protocol/openid-connect/token \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=$KEYCLOAK_ADMIN_PASSWORD" \
  -d "grant_type=password" | jq -r '.access_token')

# Register client
curl -s http://localhost:8080/admin/realms/portcullis/clients \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clientId": "myapp",
    "enabled": true,
    "protocol": "openid-connect",
    "publicClient": false,
    "secret": "your-client-secret-here",
    "redirectUris": ["https://myapp.yourdomain.com/callback"],
    "standardFlowEnabled": true,
    "directAccessGrantsEnabled": false,
    "defaultClientScopes": ["openid", "profile", "email", "acr", "groups"]
  }'
```

### Step 2: Configure your app

Point your app's OIDC settings to:

| Setting | Value |
|---------|-------|
| **Issuer / Authority** | `https://auth.yourdomain.com/realms/portcullis` |
| **Discovery URL** | `https://auth.yourdomain.com/realms/portcullis/.well-known/openid-configuration` |
| **Client ID** | `myapp` |
| **Client Secret** | `your-client-secret-here` |
| **Scopes** | `openid email profile groups` |
| **Redirect URI** | `https://myapp.yourdomain.com/callback` |

### Step 3: compose.yml

Native OIDC apps don't need `portcullis-auth@docker` — they handle auth themselves:

```yaml
services:
  myapp:
    image: myorg/myapp:latest
    environment:
      OIDC_ISSUER: https://auth.${PORTCULLIS_DOMAIN}/realms/portcullis
      OIDC_CLIENT_ID: myapp
      OIDC_CLIENT_SECRET: your-client-secret-here
    networks:
      - default
      - portcullis-proxy
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: Host(`myapp.${PORTCULLIS_DOMAIN}`)
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: authaware@file
      traefik.http.routers.myapp.middlewares: client-headers@file,security-headers@file
      traefik.http.services.myapp.loadbalancer.server.port: "8080"
    restart: unless-stopped

networks:
  portcullis-proxy:
    external: true
```

!!! note "No `portcullis-auth@docker` middleware"
    Native OIDC apps handle their own auth flow. Don't add `portcullis-auth@docker` or `portcullis-groups@docker` — the app redirects to Keycloak itself.

### Staging certificates

If you're using Let's Encrypt staging (`ACME_STAGING=true`), your app needs to trust the staging CA. Mount the CA bundle:

```yaml
services:
  myapp:
    volumes:
      - /path/to/portcullis/certs/ca-bundle.crt:/etc/ssl/certs/ca-certificates.crt:ro
    environment:
      # For Node.js apps:
      NODE_EXTRA_CA_CERTS: /etc/ssl/certs/ca-certificates.crt
      # For Go apps:
      SSL_CERT_FILE: /etc/ssl/certs/ca-certificates.crt
```

## Option 3: Public (no authentication)

For apps that should be publicly accessible:

```yaml
services:
  myapp:
    image: myorg/myapp:latest
    networks:
      - default
      - portcullis-proxy
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: Host(`myapp.${PORTCULLIS_DOMAIN}`)
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: public@file
      traefik.http.routers.myapp.middlewares: security-headers@file
      traefik.http.services.myapp.loadbalancer.server.port: "8080"
    restart: unless-stopped

networks:
  portcullis-proxy:
    external: true
```

Note: `tls.options: public@file` (no client cert request) and no auth middleware.

## Running Alongside Portcullis

Start your app with its own project name to keep it isolated:

```bash
docker compose -p myapp -f /path/to/your/compose.yml up -d
```

Your app gets its own containers, network, and lifecycle — completely independent of the Portcullis core stack.

## Comparison: Template vs Third-Party

| Feature | Hub Template | Third-Party |
|---------|-------------|-------------|
| Appears in Hub catalog | Yes | No |
| One-click enable/disable | Yes | Manual compose up/down |
| Auto-generated secrets | Yes | Manual |
| Per-app settings UI | Yes | Edit compose/env directly |
| Status/logs in Hub | Yes | `docker compose logs` |
| Keycloak client auto-registration | Yes | Manual registration |
| Group-gate mapping | Via manifest (`access_group`, `admin_paths`) | Edit `group-gate/group-gate-map.conf` |
| Auth badges in UI | Yes | N/A |

For apps you manage frequently or share with others, consider [creating a proper template](adding-an-app.md). For one-off apps or quick experiments, the third-party approach is simpler.
