# Upgrading

Upgrade an existing install from the core checkout with:

```bash
git pull
./scripts/upgrade.sh            # --dry-run to preview, --help for all options
```

`upgrade.sh` backs up the volumes, `certs/` and `secrets/` to `backups/` before changing anything. The backup includes Vault's unseal key, so protect it like the key itself.

## 2026-10 security release

This release hardens authentication across all four repos. Several changes are visible to operators, so read this before upgrading.

### 1. Vault leaves dev mode (opt-in, needs cert re-enrollment)

Older installs ran Vault in **dev mode**: storage was in memory, the root token was `myroot`, and the whole PKI was lost on every restart. Vault now runs in server mode with persistent raft storage, unseals itself automatically on start, and gives enroll a least-privilege AppRole. See [TLS & mTLS](../setup/certificates.md#vault-storage-unsealing-tokens).

The old CA keys were generated as non-exportable inside the in-memory Vault, so they **cannot be carried over**:

- `upgrade.sh` detects dev mode and **stops** unless you pass `--migrate-vault` or confirm interactively. An unattended run fails safely.
- Migrating creates a new root and intermediate CA and rewrites `certs/*.crt`. The old files go to `backups/certs-before-vault-migration-*`.
- **Every YubiKey/PIV client certificate must be re-enrolled.** Devices that imported the old `root-ca.crt` need the new one. WebAuthn logins are unaffected.
- **Store `secrets/vault-init.json` offline.** It contains the root token and the unseal key.
- `VAULT_DEV_TOKEN` in `.env` is no longer used and can be deleted.

### 2. `portcullis-proxy` gets a fixed subnet and Traefik a static IP

Header-auth apps now trust identity headers **only from Traefik** (see [Header Auth Pattern](../guides/header-auth-app.md#header-security)). To make that possible, the shared network has fixed addressing, set in `.env` (change these only if they collide with a host network):

| Variable | Default |
|----------|---------|
| `PORTCULLIS_PROXY_SUBNET` | `172.31.250.0/24` |
| `PORTCULLIS_PROXY_IP_RANGE` | `172.31.250.128/25` (dynamic addresses for other containers) |
| `PORTCULLIS_TRAEFIK_IP` | `172.31.250.2` |

An existing network can't be changed in place. `upgrade.sh` therefore records the attached containers (in `backups/proxy-network-members-*.tsv`), recreates the network, and reconnects them with their aliases. Apps keep running, and routing drops for a few seconds.

**Afterwards, disable and re-enable** Grafana, Firefly III, Kanboard, Guacamole and CloudBeaver in the Hub. This regenerates their env with `PORTCULLIS_TRAEFIK_IP`.

### 3. Group membership is now enforced for more apps

Apps with `group_access: true` in their manifest now actually require their `access_group`. Before this release, Nextcloud and Guacamole let in any logged-in user. **Add existing users to `users_nextcloud` and `users_guacamole` in LLDAP before upgrading.** See [Groups & Access Control](groups.md).

Per-app auth policies set in the Hub now apply to every app. Previously they were silently ignored for 13 apps whose subdomain differs from their template ID, such as `vaultwarden` → `passwords`.

### 4. Secrets and default accounts

- **Forward-auth client secret.** Fresh installs get a random secret. Existing installs keep the public default until you set `FORWARD_AUTH_CLIENT_SECRET` in `.env`, run `./scripts/register-oidc-clients.sh`, then `docker compose up -d forward-auth`.
- **Guacamole.** The default `guacadmin/guacadmin` account is only replaced on a *fresh* database. On existing installs, change its password by hand.
- **Immich.** The admin password is now generated separately and password login is off when OIDC is configured. The new admin password only applies to fresh databases. Use `immich-admin grant-admin` to promote a user.

### 5. Template support files

The Hub now publishes each app's template files to `<core>/templates/<app-id>/` before starting it, through a new read-write `./templates` mount in the core compose. In older releases, apps that bind-mount config files (Immich, NetBird, Headscale, Jellyfin, CloudBeaver, Docs) received **empty directories** instead of their configs. Restart those apps from the Hub after upgrading.

### 6. Other changes you may notice

- **Hosts outside `<label>.<PORTCULLIS_DOMAIN>`** get a 403 from group-gate, and changing a host's letter case or adding a port no longer bypasses group checks.
- **`/realms/master`** (Keycloak admin login) on `auth.<domain>` now requires forward-auth plus `lldap_admin`.
- **Vault** listens on `127.0.0.1:8200` only.
- **Certificate revocation** is now enforced by group-gate, using a revoked-serial list plus Vault's CRL. See [TLS & mTLS](../setup/certificates.md#revoking-client-certificates).
- **Enroll** only signs CSRs whose subject is exactly the user, and requires `lldap_admin`.
- **Hub** rejects cross-origin and non-JSON writes and validates all inputs. See [Hub Management](hub.md#security-model).
