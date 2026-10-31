# Header Auth Pattern

This guide shows how to configure apps that support "reverse proxy authentication" or "trusted header authentication" behind Portcullis. These apps read the authenticated user's identity from an HTTP header set by oauth2-proxy, rather than handling authentication themselves.

## Overview

```
User (YubiKey) --> Traefik --> oauth2-proxy --> group-gate --> App
                                   |
                                   v
                               Keycloak (sets X-Forwarded-User header)
```

The user authenticates via oauth2-proxy (which redirects to Keycloak). After authentication, oauth2-proxy sets the `X-Forwarded-User` and `X-Forwarded-Email` headers. The app reads these headers and logs the user in automatically -- no separate login step.

## When to Use Header Auth

Use this pattern when:

- The app supports reverse proxy / trusted header authentication
- You want automatic user login based on the Portcullis identity
- The app does not have native OIDC or SAML support, or you prefer the simpler header approach

In the manifest, this is `auth.method: header-auth`.

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
    networks:
      - portcullis
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: "Host(`myapp.${PORTCULLIS_DOMAIN}`)"
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: authaware@file
      traefik.http.routers.myapp.middlewares: "portcullis-auth@docker,portcullis-groups@docker,security-headers@file"
      traefik.http.services.myapp.loadbalancer.server.port: "8080"

networks:
  portcullis:
    external: true
```

The `portcullis-auth@docker` middleware handles authentication via oauth2-proxy and sets these headers on the upstream request:

| Header | Content |
|--------|---------|
| `X-Forwarded-User` | Authenticated username (e.g., `alice`) |
| `X-Forwarded-Email` | User's email address |
| `X-Forwarded-Groups` | Comma-separated list of groups |
| `X-Forwarded-Preferred-Username` | Preferred username |

## Step 2: Configure the App

Each app has its own way of enabling reverse proxy authentication. Here are common examples:

### Grafana

```ini
[auth.proxy]
enabled = true
header_name = X-Forwarded-User
header_property = username
auto_sign_up = true
```

Or via environment variables in compose.yml:

```yaml
environment:
  GF_AUTH_PROXY_ENABLED: "true"
  GF_AUTH_PROXY_HEADER_NAME: "X-Forwarded-User"
  GF_AUTH_PROXY_HEADER_PROPERTY: "username"
  GF_AUTH_PROXY_AUTO_SIGN_UP: "true"
```

### Kanboard

In `config.php`:

```php
define('REVERSE_PROXY_AUTH', true);
define('REVERSE_PROXY_USER_HEADER', 'X-Forwarded-User');
define('REVERSE_PROXY_DEFAULT_ADMIN', 'admin');
```

### Gitea / Forgejo

```ini
[service]
ENABLE_REVERSE_PROXY_AUTHENTICATION = true
ENABLE_REVERSE_PROXY_AUTO_REGISTRATION = true
REVERSE_PROXY_AUTHENTICATION_USER = X-Forwarded-User
REVERSE_PROXY_AUTHENTICATION_EMAIL = X-Forwarded-Email
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

Set via environment variables:

```yaml
environment:
  AUTHENTICATION_GUARD: remote_user_guard
  AUTHENTICATION_GUARD_HEADER: HTTP_X_FORWARDED_USER
  AUTHENTICATION_GUARD_EMAIL: HTTP_X_FORWARDED_EMAIL
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

Clients on the internet can't spoof `X-Forwarded-User`. Traefik's forward-auth middleware deletes the header from every incoming request and only re-adds the value oauth2-proxy and group-gate return.

Containers are a different matter. Every app frontend shares the `portcullis-proxy` network, so any compromised container on it could connect to your app directly and claim to be any user. **A header-auth app must therefore accept identity headers only from Traefik.**

Core gives Traefik a fixed address for this. The `portcullis-proxy` network has the subnet `PORTCULLIS_PROXY_SUBNET` (default `172.31.250.0/24`), and Traefik always sits at `PORTCULLIS_TRAEFIK_IP` (default `172.31.250.2`). Both are in the core `.env`, and the Hub copies them into an app's env when its compose file references them. Use the default form so CI and older installs still resolve:

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

The template test helpers check both sides. `assert_traefik_only_trust <compose> <SETTING>` checks the allowlist statically. `assert_spoofed_identity_rejected <url>` sends a forged `X-Forwarded-User` from the CI host (which is never Traefik) and expects a 403.

Also make sure the app doesn't publish its HTTP port on the host: a published port would bypass both Traefik and the allowlist.

## Troubleshooting

### User shows as blank or anonymous

- Verify the header name matches what the app expects (some apps want `HTTP_X_FORWARDED_USER` instead of `X-Forwarded-User`)
- Check oauth2-proxy logs to confirm headers are being set
- Confirm the app's reverse proxy auth setting is enabled

### User created but lacks admin privileges

Header auth typically creates users with the lowest privilege level. Admin must be granted manually in the app (or via LDAP group mapping if the app supports it).

### "403 Forbidden" from group-gate

The user is authenticated but not in the required LLDAP group for this app. Add the user to the `users_<app>` group in LLDAP.

### App receives no headers

Ensure the middleware chain includes `portcullis-auth@docker`. Without it, requests go directly to the app with no identity headers.
