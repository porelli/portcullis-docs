# Upgrading & Releases

Upgrade an installation from the core checkout with:

```bash
git pull
./portcullis upgrade
```

`upgrade` is safe to re-run. Every step it performs is idempotent, and it backs
up first.

## What `portcullis upgrade` does

1. **Fills in missing secrets.** It generates `HUB_PROXY_SECRET`,
   `FORWARD_AUTH_CLIENT_SECRET`, `FORWARD_AUTH_COOKIE_SECRET`,
   `LLDAP_JWT_SECRET` or `BACKUP_PASSWORD` if they are empty or missing. Nothing on disk depends on
   those. The database and admin passwords must already be in `.env`, and the
   command stops if one is missing.
2. **Checks the networks.** It validates the `portcullis-proxy` and
   `portcullis-auth` settings in `.env` against the existing Docker networks,
   and stops with instructions if they differ.
3. **Backs up** with `portcullis backup`, a consistent online backup: Vault
   raft snapshot, `pg_dump`, the LLDAP/Hub/ACME volumes, `.env`, `certs/` and
   `secrets/`. It goes to `backups/<timestamp>/`. Skip this with
   `--skip-backup`.
4. **Pulls images.** Core images are pinned by digest in `docker-compose.yml`,
   so the pull only changes something when the pins changed in the commit you
   pulled. The Hub image comes from `HUB_IMAGE` (see below).
5. **Re-runs the setup steps.**
    - `vault init`: unseal, enroll AppRole and policy.
    - `pki setup`: rewrites the `client-cert` role, so a changed
      `CLIENT_CERT_TTL` applies to new certificates, and refreshes the Keycloak
      truststore and CRL settings. An existing CA is never replaced.
    - Rebuilds `certs/ca-bundle.crt`.
6. **Restarts the stack** with `docker compose up -d --build` and waits for
   Vault, PostgreSQL, LLDAP and Keycloak to be healthy. Traefik, forward-auth
   and Keycloak are restarted if the CA chain or truststore changed.
7. **Re-applies the identity config.** It runs `keycloak configure` (realm
   settings, X.509/CRL settings, scopes, LDAP bind) and `oidc register` (client
   secrets from `.env`), then recreates forward-auth so it picks up a newly
   generated client secret.

It also checks the Hub image: before the upgrade it warns when `HUB_IMAGE` is
pinned (in `.env` or the environment: a pinned Hub doesn't move with core), and after the start it
compares the Hub's policy file version with the one group-gate serves (and
looks for group-gate's "is not supported" log line). On a mismatch it prints
the fix — drop or align `HUB_IMAGE`, then `./portcullis up` — and never fails
the run: until then group-gate denies every app request (the Hub and core must
be upgraded together).

Check the result with `./portcullis status`.

Apps enabled in the Hub are separate compose projects. `upgrade` does not
restart them. The Hub reconciles them on start and reports anything that is
not running as [drift](hub.md#drift-detection).

## Backups and rollback

The backup made by `upgrade` is a normal local backup (see [Backups](backups.md)).
It contains the Vault unseal key and root token, so it can decrypt the CA.
Protect it like the keys themselves. `upgrade` does not upload it off-host:
run `./portcullis backup --offsite` first if you want an off-host copy of the
pre-upgrade state.

To roll back, check out the previous core commit (or release) and restore the
backup:

```bash
./portcullis restore --list
./portcullis restore backups/<timestamp>
```

`restore` saves the current `.env`, `secrets/` and `certs/` to
`backups/pre-restore-<timestamp>/` before overwriting them.

## Versions and releases

How the four repositories are versioned is defined in
[Integration Contracts §1](../guides/integration-contracts.md#1-versions-and-releases):

- **Tags.** Every repo uses semver tags `vMAJOR.MINOR.PATCH`. A breaking change
  to an integration contract bumps MAJOR in every repo it affects.
- **Core images** are pinned `tag@sha256:digest` in every compose file and
  profile, so a core commit fully determines which Traefik, Keycloak, Vault,
  LLDAP, oauth2-proxy, PostgreSQL, socket-proxy and monitoring versions run.
  Dependabot proposes updates weekly; CI fails on anything unpinned.
- **Templates.** The Hub tracks the default branch of each template source;
  pull updates with **Sync** in the Hub. The templates CI tests against the
  core ref in its `.core-ref`.

Check what you run:

```bash
./portcullis version          # core version (VERSION file or git describe) + Hub image
./portcullis version --json
```

### Core releases

A core release is a `vX.Y.Z` tag. `.github/workflows/release.yml` publishes it
only if all of the following holds:

1. **Tag and changelog.** The tag is `vMAJOR.MINOR.PATCH`, and `CHANGELOG.md`
   ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)) has a
   `## [X.Y.Z]` section.
2. **Pinned Hub.** The `HUB_IMAGE` default in `docker-compose.yml` is a
   **released** Hub tag pinned by digest
   (`ghcr.io/porelli/portcullis-hub:A.B.C@sha256:…`). That tag must be a
   published, non-prerelease Hub release that still resolves to that digest.
3. **CI.** The full core CI (`ci.yml`, called as a reusable workflow) passes on
   the tagged commit.

Then it publishes:

- release notes: the changelog section, the pinned Hub image, and GitHub's
  generated notes
- `portcullis-X.Y.Z.tar.gz`: the checkout without `.git`, plus a `VERSION`
  file. The tarball is reproducible: sorted, numeric owner, commit time
- `portcullis-X.Y.Z.tar.gz.sha256`

Install or upgrade from a release tarball:

```bash
sha256sum -c portcullis-X.Y.Z.tar.gz.sha256
tar -xzf portcullis-X.Y.Z.tar.gz && cd portcullis-X.Y.Z
```

Or check out the tag in your git checkout: `git fetch --tags && git checkout vX.Y.Z`.

### Hub image

`HUB_IMAGE` selects the Hub:

- **On core `main`** the default is `ghcr.io/porelli/portcullis-hub:edge`,
  the latest build of the Hub's `main`.
- **A core release** pins a released Hub tag by digest, as described above.
- **Overriding it in `.env`?** Use a released tag **and** its digest, never
  `edge` in production:

    ```bash
    HUB_IMAGE=ghcr.io/porelli/portcullis-hub:1.2.3@sha256:<digest>
    ```

Hub releases are published as `X.Y.Z`, `X.Y`, `X` and `sha-<short>`. There is
no `latest` tag. Each image is signed with cosign (keyless, GitHub OIDC).
Verify it before you pin it:

```bash
cosign verify ghcr.io/porelli/portcullis-hub:1.2.3 \
  --certificate-identity-regexp '^https://github.com/porelli/portcullis-hub/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
docker buildx imagetools inspect ghcr.io/porelli/portcullis-hub:1.2.3   # top-level Digest:
```

!!! note "No releases yet"
    No repository has been tagged yet. Core `main` therefore runs the Hub's
    `edge`, and the templates CI tests against core `main`. `CHANGELOG.md`
    collects everything under `[Unreleased]`.

## Upgrade notes

Changes that need an admin action when you upgrade. The templates repo keeps
the same notes in its `CHANGELOG.md`.

### App instances and extra domains (Hub v5, core v5, templates contract v2)

- **Nextcloud admins must be in `users_nextcloud`.** The Nextcloud template
  now sets [`keycloak_access_role`](../guides/manifest-reference.md#auth):
  Keycloak lets only members of the instance's access group (`users_nextcloud`
  for the default instance, `users_<instance-id>` for others) sign in. A member
  of `admin_nextcloud` who isn't also in `users_nextcloud` could sign in before
  (user_oidc's group whitelist) and is now denied. Before you upgrade, add every
  Nextcloud admin to `users_nextcloud` (Hub → Users & Groups).
- Paperless-ngx, Vaultwarden and GitLab set `keycloak_access_role` too; their
  sign-in already required the access group, so nothing changes for their
  users.
- **Vaultwarden** runs with `SSO_ONLY`: the email + master password login is
  off; the master password only decrypts the vault after the SSO login.
- **Jellyfin**: the local `admin` account loses its password login (setup moves
  it to the SSO plugin's provider). Administrators sign in through SSO
  (`admin_jellyfin`).
- **Guacamole**: header logins as `guacadmin*` are refused (403). Databases
  created from now on name the built-in administrator
  `guacadmin-<generated suffix>`.
- The Hub and core must be upgraded together (policy file version 5, see
  above).
- **Failed hostname changes are not re-applied.** The Hub now keeps the last
  hostname change in its own record. A hostname change that failed under an
  older Hub isn't re-applied after the upgrade: repeat it once (save the same
  hostnames again).

## Changing settings during an upgrade

| You changed | Run |
|-------------|-----|
| `ACME_STAGING` or `MTLS_ENABLED` | `./portcullis config apply && ./portcullis up` |
| `CLIENT_CERT_TTL` | `./portcullis upgrade` (or `./portcullis pki setup`); only new certificates are affected |
| `FORWARD_AUTH_CLIENT_SECRET` | `./portcullis oidc register && ./portcullis up` |
| An empty rotatable secret (to rotate it) | `./portcullis upgrade` generates a new one |
| `HUB_IMAGE` | `./portcullis up` |
| Network ranges | See [Security & Hardening → Networks](hardening.md#networks). Docker can't change an existing network in place |
