# Header Auth Pattern

This guide shows how to configure apps that support "reverse proxy authentication" or "trusted header authentication" behind Portcullis. These apps read the authenticated user's identity from an HTTP header set by the forward-auth chain (oauth2-proxy + group-gate), rather than handling authentication themselves.

## Overview

```
User (YubiKey) --> Traefik --> oauth2-proxy --> group-gate --> App (trusts only Traefik's IP)
                                   |
                                   v
                               Keycloak
```

The user authenticates via oauth2-proxy (which redirects to Keycloak). group-gate then checks groups and policy and returns the identity headers, which Traefik adds to the request. The app reads `X-Forwarded-User` and logs the user in automatically -- no separate login step.

## When to Use Header Auth

Use this pattern when:

- The app supports reverse proxy / trusted header authentication
- You want automatic user login based on the Portcullis identity
- The app does not have native OIDC or SAML support, or you prefer the simpler header approach

In the manifest, this is `auth.method: header-auth`. The templates validator (`tests/validate.py`) requires such apps to restrict the header to Traefik and rejects trust-everything values.

## Step 1: Deploy the App

Create a compose.yml with the forward-auth middleware chain:

```yaml
services:
  myapp:
    image: myapp/myapp:latest
    environment:
      # Enable reverse proxy authentication (app-specific setting)
      AUTH_PROXY_ENABLED: "true"
      AUTH_PROXY_HEADER: "X-Forwarded-User"
      # Accept the header ONLY from Traefik (app-specific setting)
      AUTH_PROXY_TRUSTED_IPS: ${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}
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

networks:
  portcullis-proxy:
    external: true
```

After `portcullis-auth@docker` (oauth2-proxy) and `portcullis-groups@docker` (group-gate), the upstream request carries:

| Header | Content | Set by |
|--------|---------|--------|
| `X-Forwarded-User`, `X-Auth-Request-User` | The LLDAP **username** (the token's `preferred_username`) | group-gate |
| `X-Forwarded-Email`, `X-Auth-Request-Email` | The user's email address, for display only | group-gate |
| `X-Auth-Request-Groups` | Comma-separated LLDAP groups | group-gate (echoed from oauth2-proxy) |
| `X-Auth-Request-Preferred-Username` | The username | oauth2-proxy |
| `Authorization`, `X-Forwarded-Access-Token` | The Keycloak access token (`Bearer …`) | oauth2-proxy |

Traefik deletes every one of these from the client's request first and only adds the values the forward-auth services returned (CI's browser test sends spoofed copies and checks they are dropped).

!!! warning "Log users in by username, never by email"
    LLDAP lets every user edit their own email address, so an email can be set to someone else's. Configure the app to identify users by `X-Forwarded-User` as a **username** and to take the email from `X-Forwarded-Email`. Keycloak does not trust LLDAP's mail (`email_verified=false`).

## Step 2: Configure the App

Each app has its own way of enabling reverse proxy authentication. Here are common examples:

### Grafana

Grafana (log in by username, take the email from its own header):

```yaml
environment:
  GF_AUTH_PROXY_ENABLED: "true"
  GF_AUTH_PROXY_HEADER_NAME: X-Forwarded-User
  GF_AUTH_PROXY_HEADER_PROPERTY: username
  GF_AUTH_PROXY_HEADERS: Email:X-Forwarded-Email
  GF_AUTH_PROXY_AUTO_SIGN_UP: "true"
  GF_AUTH_PROXY_WHITELIST: ${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}
```

### Kanboard

As in the `kanboard` template (environment variables of the official image; Kanboard ignores the header unless `REMOTE_ADDR` is in `TRUSTED_PROXY_NETWORKS`):

```yaml
environment:
  REVERSE_PROXY_AUTH: "true"
  REVERSE_PROXY_USER_HEADER: HTTP_X_FORWARDED_USER
  REVERSE_PROXY_DEFAULT_ADMIN: admin
  TRUSTED_PROXY_NETWORKS: ${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}/32
```

### Gitea / Forgejo

```ini
[service]
ENABLE_REVERSE_PROXY_AUTHENTICATION = true
ENABLE_REVERSE_PROXY_AUTO_REGISTRATION = true
REVERSE_PROXY_AUTHENTICATION_USER = X-Forwarded-User
REVERSE_PROXY_AUTHENTICATION_EMAIL = X-Forwarded-Email
REVERSE_PROXY_TRUSTED_PROXIES = 172.31.250.2/32
```

### Wiki.js

In the admin panel, go to **Authentication** and add a **Header** strategy:

- **Header name**: `X-Forwarded-User`
- **Auto-create users**: enabled

### pgAdmin

```python
AUTHENTICATION_SOURCES = ['webserver']
WEBSERVER_REMOTE_USER = 'X-Forwarded-User'
```

### Firefly III

Firefly III. `remote_user_guard` has no proxy allow-list, so the template's nginx additionally rejects the header from any peer other than Traefik (see below):

```yaml
environment:
  AUTHENTICATION_GUARD: remote_user_guard
  AUTHENTICATION_GUARD_HEADER: HTTP_X_FORWARDED_USER
  AUTHENTICATION_GUARD_EMAIL: HTTP_X_FORWARDED_EMAIL
  TRUSTED_PROXIES: ${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}
```

## Step 3: Test the Integration

1. Navigate to `https://myapp.<your-domain>`
2. You should be redirected to Keycloak (via oauth2-proxy)
3. Authenticate with your YubiKey
4. You should be logged into the app automatically as the authenticated user

If the app creates users on first login, the user account will be created with the username from the `X-Forwarded-User` header.

## Apps Without Header Auth Support

Some apps do not support trusted header authentication at all. For these, you have two options:

1. **Use forward-auth for access gating only** -- The app has its own login system, but oauth2-proxy + group-gate ensure only authorized users can reach it. Set `auth.method: forward-auth` and `auth.sso: false` in the manifest.

2. **Use native OIDC** -- If the app supports OpenID Connect, configure it to authenticate directly with Keycloak. See the [Architecture](../architecture.md#native-oidc) page for the flow.

## Header Security

Clients on the internet can't spoof `X-Forwarded-User`. Traefik's forward-auth middleware deletes the header from every incoming request and only re-adds the value oauth2-proxy and group-gate return (see [Security & Hardening](../operations/hardening.md#header-spoofing-protections)).

Containers are a different matter. Every app frontend shares the `portcullis-proxy` network, so any compromised container on it could connect to your app directly and claim to be any user. **A header-auth app must therefore accept identity headers only from Traefik.**

Core gives Traefik a fixed address for this. The `portcullis-proxy` network has the subnet `PORTCULLIS_PROXY_SUBNET` (default `172.31.250.0/24`), and Traefik always sits at `PORTCULLIS_TRAEFIK_IP` (default `172.31.250.2`). Both are in the core `.env`; the Hub receives them through `secrets/hub/core.env` and copies them into an app's env when its compose file references them. Always use the default form (`validate.py` enforces it), so the compose file also resolves outside the Hub:

```yaml
environment:
  GF_AUTH_PROXY_WHITELIST: ${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}            # Grafana
  TRUSTED_PROXY_NETWORKS: ${PORTCULLIS_TRAEFIK_IP:-172.31.250.2}/32          # Kanboard
```

If an app has no proxy allowlist (Firefly III, Guacamole, CloudBeaver), block the header in front of it. The built-in templates show three ways to do that:

| Pattern | Example | How |
|---------|---------|-----|
| App's own web server | Firefly III | An nginx rule returns 403 when `X-Forwarded-User` comes from any peer other than Traefik |
| Servlet container | Guacamole | A Tomcat RewriteValve does the same check |
| Gate container | CloudBeaver | The app stays off `portcullis-proxy`. A small nginx `*-gate` service is the only thing Traefik can reach; it rejects spoofed identity headers and strips extra role/team headers |

Never use "trust everything" values such as `"**"`, `0.0.0.0/0` or `::/0`.

The template test helpers in `tests/lib.sh` check both sides, and header-auth templates must use both. `assert_traefik_only_trust <compose> <SETTING>` checks the allowlist statically. `assert_spoofed_identity_rejected <url>` sends a forged `X-Forwarded-User` from the CI host (which is never Traefik) and expects a 403.

Also make sure the app doesn't publish its HTTP port on the host: a published port would bypass both Traefik and the allowlist.

## Troubleshooting

### User shows as blank or anonymous

- Verify the header name matches what the app expects (some apps want `HTTP_X_FORWARDED_USER` instead of `X-Forwarded-User`)
- `X-Forwarded-User` carries the username; the email is in `X-Forwarded-Email`
- Check that the request really comes from Traefik's IP: the app's allow-list must contain `PORTCULLIS_TRAEFIK_IP`
- Check oauth2-proxy and group-gate logs (`docker compose logs forward-auth group-gate`)
- Confirm the app's reverse proxy auth setting is enabled

### User created but lacks admin privileges

Header auth typically creates users with the lowest privilege level. Admin must be granted manually in the app (or via LDAP group mapping if the app supports it).

### "403 Forbidden" from group-gate

The user is authenticated but not in the required LLDAP group for this app. Add the user to the `users_<app>` group in LLDAP.

### App receives no headers

Ensure the middleware chain includes `portcullis-auth@docker,portcullis-groups@docker` in that order. Without group-gate the app gets no `X-Forwarded-User`, because group-gate is what sets it.
