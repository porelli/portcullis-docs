# Testing & CI

Portcullis includes automated tests for both core infrastructure and individual apps. Tests run in GitHub Actions on every push and pull request, and can also be run locally using `act`.

## CI Overview

There are two GitHub Actions workflows:

| Workflow | File | What It Tests |
|----------|------|---------------|
| **CI** | `.github/workflows/ci.yml` | Core infrastructure: Vault PKI, Keycloak realm, LLDAP, OIDC discovery, mTLS, enrollment UI |
| **Test Apps** | `.github/workflows/test-apps.yml` (templates repo) | Per-app auth integration: forward-auth redirects, OIDC flows, group-gate, container health |

Both workflows:

1. Start core services (PostgreSQL, Vault, LLDAP, Keycloak)
2. Initialize Vault PKI and configure the Keycloak realm
3. Create test users and LLDAP groups
4. Run test assertions

The **Test Apps** workflow additionally starts Traefik, oauth2-proxy, and group-gate, then brings up each app template individually to verify its authentication integration.

### What triggers which app test

The templates workflow only tests apps affected by the push:

- A change under `<app>/` tests that app.
- A change to `tests/apps/<app>.sh` tests that app.
- A change to `tests/lib.sh` tests every app.

### Infra image cache

Core images (Traefik, Keycloak, Vault, LLDAP, oauth2-proxy, Postgres, …) are pre-pulled once per run and cached.

- **Image list** -- read from the core repo with `docker compose config --images`, excluding the locally built `portcullis-enroll` and the floating Hub image.
- **Cache key** -- a hash of that list. Bumping any image tag in core automatically invalidates the cache, so CI can never run against stale versions.

### Generated secrets in tests

The Hub generates every manifest `env:` entry with `generate: random`, and templates reference those with `${VAR:?}`, so they fail loudly if a value is missing. `tests/lib.sh` mirrors the Hub here: before each compose call it exports a random value for any such variable that isn't already set.

### Core unit tests

The core repo also has fast tests that need no containers:

- `python3 -m pytest tests/` (`test_group_gate.py`) covers group-gate:
    - host normalization and the case/port bypass regression
    - the merge of `group-gate-map.conf` with the Hub's `groups`
    - fail-closed policies
    - certificate revocation, by serial list and by a real openssl-generated CRL
- `bash tests/test_shell_libs.sh` tests the shell libraries against stub `docker`/`vault` commands:
    - `portcullis-proxy` subnet/range/Traefik-IP validation, and network recreation including every failure path and recovery
    - `revoke-cert.sh --sync`, which must never empty the list when Vault fails
    - `setup-vault-pki.sh` idempotency, including resuming a partial run
- `cd enroll && go test ./...` covers:
    - CSR subject/SAN validation
    - the admin requirement and the content-type check
    - Vault AppRole login, token caching and re-login

In CI these run as the `unit-tests` job. The `build-and-test` job then boots the stack and additionally verifies:

- **Vault**
    - init, unseal and the permissions on `secrets/`
    - a second `vault-init.sh` run changes nothing
    - after a Vault restart it auto-unseals and the CA is unchanged
    - the enroll AppRole can only sign, list and read certs
- **mTLS**
    - requests with no cert, or a cert from another CA, are rejected
    - cert info, including the serial, reaches the backend
    - requests arrive from the static Traefik IP
- **Revocation** end to end, once through `revoke-cert.sh` and once through Vault's CRL alone
- **Enroll** UI and the signing path (these steps now fail the job instead of printing INFO)

### Header-auth tests (templates repo)

`tests/lib.sh` provides two assertions for apps that trust identity headers:

- `assert_traefik_only_trust <compose> <SETTING>` checks statically that the trust setting uses `${PORTCULLIS_TRAEFIK_IP:-…}` and that nothing in the compose file trusts every peer (`"**"`, `0.0.0.0/0`, `::/0`).
- `assert_spoofed_identity_rejected <url> [expected]` sends a forged `X-Forwarded-User` from the CI host, which is never Traefik.

## Test Structure

```
tests/
  lib.sh              # Shared test library (assertions, helpers)
  apps/
    adguard.sh         # Per-app test scripts
    cloudbeaver.sh
    grafana.sh
    jellyfin.sh
    ...
```

### lib.sh -- Shared Library

The `tests/lib.sh` file provides:

- **Configuration**: Domain, Keycloak URL, LLDAP credentials
- **Output functions**: `pass()`, `fail()`, `info()`, `section()`
- **Wait helpers**: `wait_for_url()`, `wait_for_container()`
- **Keycloak helpers**: `keycloak_admin_token()`, `keycloak_user_token()`, `keycloak_register_client()`
- **LLDAP helpers**: `lldap_create_user()`, `lldap_create_group()`, `lldap_add_to_group()`, `lldap_sync_keycloak()`
- **Assertions**: `assert_http_code()`, `assert_redirect_to_keycloak()`, `assert_body_contains()`, `assert_container_can_reach()`
- **Compose helpers**: `compose_up()`, `compose_down()`, `app_container_ip()`, `app_logs()`

### Per-App Test Scripts

Each app test script follows a standard pattern:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
source tests/lib.sh
TEST_NAME="myapp"
section "My App"

APP_ID=myapp
SUBDOMAIN=myapp

# Start the app
compose_up "$APP_ID"

# Get the container IP and wait for it to be ready
IP=$(app_container_ip "$APP_ID")
wait_for_url "http://${IP}:8080" 60 "$APP_ID"

# Run assertions
assert_redirect_to_keycloak "https://${SUBDOMAIN}.${DOMAIN}/"

# App-specific checks...

# Clean up
compose_down "$APP_ID"
```

## What Each Test Verifies

Tests vary by auth method:

### Forward-Auth Apps (Pi-hole, DokuWiki, Scrutiny, etc.)

- Unauthenticated request redirects to Keycloak (via oauth2-proxy)
- Container is running and healthy
- App-specific health endpoints respond

### Header-Auth Apps (Grafana, Kanboard, Firefly III)

- Unauthenticated request redirects to Keycloak
- Proxy auth environment variables are set correctly in the container
- Container is running and healthy

### Native OIDC Apps (Jellyfin, Immich, Vaultwarden, etc.)

- Container can reach Keycloak's OIDC discovery endpoint
- App's SSO/OIDC redirect endpoint points to Keycloak
- Startup wizard or initial setup is complete
- Container is running and healthy

### Public Apps (Plex, Docs)

- App responds with HTTP 200 (no auth required)
- Container is running and healthy

## Running Tests Locally with act

[act](https://github.com/nektos/act) lets you run GitHub Actions workflows locally using Docker.

### Install act

```bash
# macOS
brew install act

# Linux (or download from GitHub releases)
sudo apt install act
```

### List Available Jobs

```bash
act -l -W .github/workflows/test-apps.yml   # run from portcullis-templates
```

### Run All App Tests

```bash
act -W .github/workflows/test-apps.yml -s PORTCULLIS_PAT=<token>
```

### Run a Specific Job

```bash
act -j test -W .github/workflows/test-apps.yml -s PORTCULLIS_PAT=<token>
```

### Run the Infrastructure CI

```bash
act -W .github/workflows/ci.yml
```

### Dry Run (No Containers)

```bash
act -n -W .github/workflows/app-tests.yml
```

!!! note
    `act` requires Docker to be running. The first run will download the runner images, which may take a few minutes.

## Writing a New App Test

1. Create `tests/apps/<app-id>.sh`
2. Source the shared library and set `TEST_NAME`
3. Start the app with `compose_up`
4. Wait for the container to be ready
5. Run assertions appropriate for the auth method
6. Clean up with `compose_down`

### Template: Forward-Auth App

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

# Unauthenticated access should redirect to Keycloak
assert_redirect_to_keycloak "https://${SUBDOMAIN}.${DOMAIN}/"

compose_down "$APP_ID"
```

### Template: Native OIDC App

```bash
#!/usr/bin/env bash
# Test: My App (native OIDC)
set -euo pipefail
cd "$(dirname "$0")/../.."
source tests/lib.sh
TEST_NAME="myapp"
section "My App"

APP_ID=myapp
SUBDOMAIN=myapp

compose_up "$APP_ID"

IP=$(app_container_ip "$APP_ID")
wait_for_url "http://${IP}:8080" 90 "$APP_ID"

# Container can reach Keycloak OIDC discovery
assert_container_can_reach "portcullis-${APP_ID}-1" \
  "http://keycloak:8080/realms/portcullis/.well-known/openid-configuration"

# App-specific OIDC assertions
assert_body_contains "http://${IP}:8080/health" "ok"

compose_down "$APP_ID"
```

## Common Assertion Functions

| Function | Description |
|----------|-------------|
| `assert_http_code URL CODE` | Verify a URL returns the expected HTTP status code |
| `assert_redirect_to_keycloak URL` | Verify unauthenticated access redirects to Keycloak |
| `assert_redirect_contains URL STRING` | Verify a redirect URL contains a specific string |
| `assert_body_contains URL STRING` | Verify the response body contains a string |
| `assert_container_can_reach CONTAINER URL` | Verify a container can make an HTTP request to a URL |

All assertion functions use the shared `RESOLVE_OPTS` variable for DNS resolution and CA certificate trust in the CI environment.
