# Adding an App

This guide walks through creating a new app template for Portcullis. App templates live in the [porelli/portcullis-templates](https://github.com/porelli/portcullis-templates) repository under `templates/<app-id>/` and consist of a manifest file and a Docker Compose file.

## Overview

Each app template contains:

- `manifest.yaml` -- Metadata, auth configuration, settings, environment variables, and Keycloak clients
- `compose.yml` -- Docker Compose services with Traefik labels for routing and middleware

The Hub reads these templates to present the app catalog. When a user enables an app, the Hub generates a per-app `.env` file, starts the compose services as an isolated project (`portcullis-<app-id>`), and registers any required Keycloak clients.

!!! note "Templates repo"
    Templates are maintained in the `porelli/portcullis-templates` repo, not in the core `porelli/portcullis` repo. The Hub clones this repo automatically on first startup. After adding or modifying a template, push your changes to the templates repo and use the Hub UI to sync the latest version.

## Step 1: Create the Template Directory

Clone the templates repo (if you haven't already) and create a directory for your app:

```bash
git clone git@github.com:porelli/portcullis-templates.git
cd portcullis-templates
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

### Network Configuration

All app compose files use the same two-network pattern:

- **`portcullis-proxy`** -- External network shared with Traefik. Frontend services (those with Traefik labels) must join this network so Traefik can route to them.
- **`default`** -- The app's own internal network, automatically created per compose project. Internal services (databases, caches) should only be on this network.

Frontend services use `networks: [default, portcullis-proxy]`. Internal services omit the networks key (they default to `default` only).

### Volume Naming

Because each app runs as its own compose project (`portcullis-<app-id>`), Docker would normally prefix volume names with the project name. To keep volume names stable and preserve data, always set an explicit `name:` on volumes:

```yaml
volumes:
  myapp-data:
    name: portcullis_myapp_data
```

### Per-App Environment

The Hub generates a per-app `.env` file (stored in the Hub data directory) containing the app's settings and secrets. You do not need to add app-specific variables to the root `.env` file. The root `.env` is only for core Portcullis settings (`PORTCULLIS_DOMAIN`, `ACME_STAGING`, etc.).

### For Forward-Auth Apps

Apps without native SSO use the `portcullis-auth@docker` and `portcullis-groups@docker` middleware chain:

```yaml
services:
  myapp:
    image: myapp/myapp:latest
    environment:
      - SOME_SETTING=${SOME_SETTING:-default}
    networks:
      - default
      - portcullis-proxy
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: "Host(`myapp.${PORTCULLIS_DOMAIN}`)"
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: authaware@file
      traefik.http.routers.myapp.middlewares: "portcullis-auth@docker,portcullis-groups@docker,security-headers@file"
      traefik.http.services.myapp.loadbalancer.server.port: "8080"

networks:
  portcullis-proxy:
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
      SSL_CERT_FILE: /certs/ca-bundle.crt
    volumes:
      - ./certs/ca-bundle.crt:/certs/ca-bundle.crt:ro
    networks:
      - default
      - portcullis-proxy
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: "Host(`myapp.${PORTCULLIS_DOMAIN}`)"
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: authaware@file
      traefik.http.services.myapp.loadbalancer.server.port: "8080"

networks:
  portcullis-proxy:
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
      - default
      - portcullis-proxy
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: "Host(`myapp.${PORTCULLIS_DOMAIN}`)"
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: authaware@file
      traefik.http.routers.myapp.middlewares: "portcullis-auth@docker,portcullis-groups@docker,security-headers@file"
      traefik.http.services.myapp.loadbalancer.server.port: "8080"

networks:
  portcullis-proxy:
    external: true
```

### For Public Apps

Apps that need no authentication:

```yaml
services:
  myapp:
    image: myapp/myapp:latest
    networks:
      - default
      - portcullis-proxy
    labels:
      traefik.enable: "true"
      traefik.http.routers.myapp.rule: "Host(`myapp.${PORTCULLIS_DOMAIN}`)"
      traefik.http.routers.myapp.entrypoints: websecure
      traefik.http.routers.myapp.tls.options: public@file
      traefik.http.services.myapp.loadbalancer.server.port: "8080"

networks:
  portcullis-proxy:
    external: true
```

## Step 4: Handle Staging CA Certificates

If your app makes HTTPS calls to Keycloak (common for native OIDC apps), it needs to trust the Let's Encrypt staging CA when `ACME_STAGING=true`. Mount the CA bundle:

```yaml
volumes:
  - ./certs/ca-bundle.crt:/certs/ca-bundle.crt:ro
```

Then configure the app to use it. Common patterns:

| Runtime | Environment Variable |
|---------|---------------------|
| Node.js | `NODE_EXTRA_CA_CERTS=/certs/ca-bundle.crt` |
| Go | `SSL_CERT_FILE=/certs/ca-bundle.crt` |
| Python (requests) | `REQUESTS_CA_BUNDLE=/certs/ca-bundle.crt` |
| Java | Mount into Java truststore |
| Generic | `SSL_CERT_FILE` or `CURL_CA_BUNDLE` |

## Step 5: Test Your App

1. **Enable via Hub**: Navigate to the Hub and enable your app
2. **Check container status**: Verify the container is running and healthy
3. **Test authentication**: Open the app URL and verify the auth flow works
4. **Check logs**: Review app and Traefik logs for errors

```bash
# Check container status (use the per-app project name)
docker compose -p portcullis-myapp -f templates/myapp/compose.yml ps

# View logs
docker compose -p portcullis-myapp -f templates/myapp/compose.yml logs -f

# Manual deploy (outside of Hub)
COMPOSE_IGNORE_ORPHANS=true docker compose -p portcullis-myapp \
  --project-directory . -f templates/myapp/compose.yml up -d
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

## Step 7: Push and Sync

After testing locally, push your template to the templates repo and sync via the Hub:

1. Commit and push your changes to `porelli/portcullis-templates`
2. In the Hub UI, go to the template sources and click **Sync** on the "portcullis" source
3. Your new app will appear in the catalog

## Checklist

- [ ] `templates/myapp/manifest.yaml` created with correct auth method
- [ ] `templates/myapp/compose.yml` with Traefik labels and correct middleware
- [ ] Keycloak clients listed in manifest (for native OIDC apps)
- [ ] Staging CA bundle mounted (for apps that call Keycloak over HTTPS)
- [ ] App tested manually via the Hub
- [ ] `tests/apps/myapp.sh` created and passing
- [ ] Changes pushed to `porelli/portcullis-templates` and synced via Hub
