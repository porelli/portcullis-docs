# Upgrading

Upgrade an installation from the core checkout with:

```bash
git pull
./portcullis upgrade
```

`upgrade` is safe to re-run. Every step it performs is idempotent, and it backs
up first.

## What `portcullis upgrade` does

1. **Fills in rotatable secrets.** It generates `HUB_PROXY_SECRET`,
   `FORWARD_AUTH_CLIENT_SECRET`, `FORWARD_AUTH_COOKIE_SECRET` or
   `LLDAP_JWT_SECRET` if they are empty or missing. Nothing on disk depends on
   those. The database and admin passwords must already be in `.env`, and the
   command stops if one is missing.
2. **Checks the networks.** It validates the `portcullis-proxy` and
   `portcullis-auth` settings in `.env` against the existing Docker networks,
   and stops with instructions if they differ.
3. **Backs up** `.env`, `certs/`, `secrets/` and the Vault, PostgreSQL and
   LLDAP volumes to `backups/<timestamp>/` (`portcullis backup`). Skip this with
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

Check the result with `./portcullis status`.

Apps enabled in the Hub are separate compose projects. `upgrade` does not
restart them. The Hub reconciles them on start and reports anything that is
not running as [drift](hub.md#drift-detection).

## Backups

The backup made by `upgrade` is the same as `./portcullis backup`. It contains
the Vault unseal key and root token, so it can decrypt the CA. Protect it like
the keys themselves.

To roll back, check out the previous core commit and restore the backup:

```bash
./portcullis restore --list
./portcullis restore backups/<timestamp>
```

`restore` saves the current `.env`, `secrets/` and `certs/` to
`backups/pre-restore-<timestamp>/` before overwriting them. See the
[CLI Reference](cli.md#restore).

Off-host copies and monitoring of backups are covered in the core repo's
documentation.

## Versions and releases

How the four repositories are versioned is defined in
[Integration Contracts §1](../guides/integration-contracts.md#1-versions-and-releases):

- **Core**, **Hub**, **templates** and **docs** each use semver tags
  `vMAJOR.MINOR.PATCH`. A breaking change to an integration contract bumps
  MAJOR in every repo it affects.
- **Core images** are pinned `tag@sha256:digest` in `docker-compose.yml`, so a
  core commit fully determines which Traefik, Keycloak, Vault, LLDAP,
  oauth2-proxy, PostgreSQL and socket-proxy versions run.
- **Hub image.** Set by `HUB_IMAGE` in `.env`. The default is
  `ghcr.io/porelli/portcullis-hub:edge`, the latest build of the Hub's `main`.
  Releases are published as `X.Y.Z`, `X.Y`, `X` and `sha-<short>`. There is
  no `latest` tag. For production, pin a release by tag and digest:

    ```bash
    HUB_IMAGE=ghcr.io/porelli/portcullis-hub:1.2.3@sha256:<digest>
    ```

    Verify its signature before you pin it (see
    [Hub image tags](hub.md#image-tags-and-verification)).
- **Templates.** The Hub tracks the default branch of each template source.
  Pull updates with **Sync** in the Hub. The templates repo's CI tests against
  the core ref in its `.core-ref` file.

!!! note "No releases yet"
    No repository has been tagged yet, so today `HUB_IMAGE` defaults to `edge`
    and the templates CI tests against core `main`. Once releases exist, follow
    the release notes of each repo.

## Changing settings during an upgrade

| You changed | Run |
|-------------|-----|
| `ACME_STAGING` or `MTLS_ENABLED` | `./portcullis config apply && ./portcullis up` |
| `CLIENT_CERT_TTL` | `./portcullis upgrade` (or `./portcullis pki setup`); only new certificates are affected |
| `FORWARD_AUTH_CLIENT_SECRET` | `./portcullis oidc register && ./portcullis up` |
| An empty rotatable secret (to rotate it) | `./portcullis upgrade` generates a new one |
| `HUB_IMAGE` | `./portcullis up` |
| Network ranges | See [Security & Hardening → Networks](hardening.md#networks). Docker can't change an existing network in place |
