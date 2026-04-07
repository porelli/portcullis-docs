# Adding an App

This guide walks through creating a new app template for Portcullis. App templates live in `templates/<app-id>/` and consist of a manifest file and a Docker Compose file.

## Overview

Each app template contains:

- `manifest.yaml` -- Metadata, auth configuration, settings, environment variables, and Keycloak clients
- `compose.yml` -- Docker Compose services with Traefik labels for routing and middleware

The Hub reads these templates to present the app catalog. When a user enables an app, the Hub starts the compose services and registers any required Keycloak clients.

## Step 1: Create the Template Directory

Choose a short, lowercase app identifier (e.g., `myapp`):

```bash
mkdir -p templates/myapp
```

## Step 2: Create manifest.yaml

The manifest describes your app to the Hub. See the [Manifest Reference](manifest-reference.md) for full field documentation.

```yaml
name: My App
description: A brief description of what the app does
icon: "\U0001F4E6"
category: productivity
tags: [example, demo]
conflicts: []

auth:
  method: forward-auth          # or: native-oidc, header-auth, public
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

## Step 3: Create compose.yml

Write a standard Docker Compose file. The key addition is Traefik labels for routing.

### For Forward-Auth Apps

Apps without native SSO use the `portcullis-auth@docker` and `portcullis-groups@docker` middleware chain:

```yaml
services:
  myapp:
    image: myapp/myapp:latest
    environment:
      - SOME_SETTING=${SOME_SETTING:-default}
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

The `portcullis-auth@docker` middleware delegates authentication to oauth2-proxy. The `portcullis-groups@docker` middleware checks group membership via group-gate.

### For Native OIDC Apps

Apps with built-in OIDC support connect to Keycloak directly. No forward-auth middleware is needed:

```yaml
services:
  myapp:
    image: myapp/myapp:latest
    environment:
      OIDC_ISSUER: "https://auth.${PORTCULLIS_DOMAIN}/realms/portcullis"
      OIDC_CLIENT_ID: myapp
      OIDC_CLIENT_SECRET: "${MYAPP_OIDC_SECRET}"
      # If using ACME staging, the app needs to trust the staging CA
      SSL_CERT_FILE: /certs/ca-bundle-with-staging.crt
    volumes:
      - ./certs/ca-bundle-with-staging.crt:/certs/ca-bundle-with-staging.crt:ro
    networks:
      - portcullis
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: "Host(`myapp.${PORTCULLIS_DOMAIN}`)"
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: authaware@file
      traefik.http.services.myapp.loadbalancer.server.port: "8080"

networks:
  portcullis:
    external: true
```

Add the Keycloak client to `manifest.yaml`:

```yaml
keycloak_clients:
  - client_id: myapp
    secret_env: MYAPP_OIDC_SECRET
    redirect_uri: "https://myapp.{{DOMAIN}}/callback"
    name: My App
```

### For Header-Auth Apps

Apps that accept a trusted identity header from the reverse proxy. Use the forward-auth middleware (which sets `X-Forwarded-User`) plus group-gate:

```yaml
services:
  myapp:
    image: myapp/myapp:latest
    environment:
      AUTH_PROXY_HEADER: X-Forwarded-User
      AUTH_PROXY_ENABLED: "true"
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

### For Public Apps

Apps that need no authentication:

```yaml
services:
  myapp:
    image: myapp/myapp:latest
    networks:
      - portcullis
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: "Host(`myapp.${PORTCULLIS_DOMAIN}`)"
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: public@file
      traefik.http.services.myapp.loadbalancer.server.port: "8080"

networks:
  portcullis:
    external: true
```

## Step 4: Handle Staging CA Certificates

If your app makes HTTPS calls to Keycloak (common for native OIDC apps), it needs to trust the Let's Encrypt staging CA when `ACME_STAGING=true`. Mount the CA bundle:

```yaml
volumes:
  - ./certs/ca-bundle-with-staging.crt:/certs/ca-bundle-with-staging.crt:ro
```

Then configure the app to use it. Common patterns:

| Runtime | Environment Variable |
|---------|---------------------|
| Node.js | `NODE_EXTRA_CA_CERTS=/certs/ca-bundle-with-staging.crt` |
| Go | `SSL_CERT_FILE=/certs/ca-bundle-with-staging.crt` |
| Python (requests) | `REQUESTS_CA_BUNDLE=/certs/ca-bundle-with-staging.crt` |
| Java | Mount into Java truststore |
| Generic | `SSL_CERT_FILE` or `CURL_CA_BUNDLE` |

## Step 5: Test Your App

1. **Enable via Hub**: Navigate to the Hub and enable your app
2. **Check container status**: Verify the container is running and healthy
3. **Test authentication**: Open the app URL and verify the auth flow works
4. **Check logs**: Review app and Traefik logs for errors

```bash
# Check container status
docker compose -f templates/myapp/compose.yml ps

# View logs
docker compose -f templates/myapp/compose.yml logs -f
```

## Step 6: Add an Automated Test

Create a test script at `tests/apps/myapp.sh`:

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

# Verify unauthenticated access redirects to Keycloak
assert_redirect_to_keycloak "https://${SUBDOMAIN}.${DOMAIN}/"

# Add app-specific assertions here

compose_down "$APP_ID"
```

See [Testing & CI](../operations/testing.md) for details on the test framework and available assertion functions.

## Checklist

- [ ] `templates/myapp/manifest.yaml` created with correct auth method
- [ ] `templates/myapp/compose.yml` with Traefik labels and correct middleware
- [ ] Keycloak clients listed in manifest (for native OIDC apps)
- [ ] Staging CA bundle mounted (for apps that call Keycloak over HTTPS)
- [ ] App tested manually via the Hub
- [ ] `tests/apps/myapp.sh` created and passing
