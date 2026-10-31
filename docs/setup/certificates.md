# TLS Certificates & mTLS

Portcullis has two TLS toggles in `.env`. They are independent of each other:

| Setting | `.env` variable | Default | What it controls |
|---------|----------------|---------|------------------|
| **Certificate source** | `ACME_STAGING` | `false` | Staging (test) vs production (trusted) Let's Encrypt certs |
| **Client certificates** | `MTLS_ENABLED` | `true` | Whether Traefik requests mTLS client certs (PIV/YubiKey) |

After changing either one, run:

```bash
./portcullis config apply
./portcullis up
```

`config apply` rewrites `traefik/dynamic/tls.yml` (Traefik hot-reloads it),
sets `ACME_CA_SERVER` in `.env`, and rebuilds `certs/ca-bundle.crt`. `up`
recreates Traefik when its environment changed.

---

## ACME staging vs production

### Production (`ACME_STAGING=false`, the default)

- Uses the Let's Encrypt **production** CA, which all browsers trust.
- Rate limits apply: 50 certificates per registered domain per week.
- One wildcard certificate (`<domain>` + `*.<domain>`) covers every app, so
  individual subdomains never appear in Certificate Transparency logs.

### Staging (`ACME_STAGING=true`)

- Uses the Let's Encrypt **staging** CA. There are no rate limits, but
  **browsers will not trust the certificate**. Use it while you iterate on DNS
  setup.
- App containers that call Keycloak over HTTPS mount `certs/ca-bundle.crt`.
  `config apply` builds it from the system CAs, the internal Portcullis PKI
  chain, and the Let's Encrypt staging root (only when `ACME_STAGING=true`).
  `init`, `up` and `upgrade` rebuild it too.

Browser workarounds for staging certs: start Chrome with
`--ignore-certificate-errors`, accept the risk in Firefox, or use `curl -k`.

### Switching

1. Set `ACME_STAGING=true` or `false` in `.env`.
2. Run `./portcullis config apply && ./portcullis up`. `config apply` notices
   the flip and clears Traefik's `acme.json`, so Traefik requests a new
   certificate.
3. Wait about 2 minutes for the DNS-01 challenge:
   `docker compose logs -f traefik 2>&1 | grep -i acme`.

---

## mTLS (client certificates)

### TLS tiers

With `MTLS_ENABLED=true`, Traefik offers three TLS option sets
(`traefik/dynamic/tls.yml`):

| Tier | Traefik option | Behavior |
|------|---------------|----------|
| **protected** | `RequireAndVerifyClientCert` | Client cert **required**. Without one, the TLS handshake fails |
| **authaware** | `VerifyClientCertIfGiven` | Client cert **optional**. Verified against `certs/ca-chain.crt` if present |
| **public** | `NoClientCert` | No client cert requested |

All core routers (`auth`, `hub`, `enroll`, `traefik`, `directory`) use
`authaware`. For apps, the Hub derives the tier from the app's
[access policy](../operations/auth-policies.md#traefik-tls-tier) and writes it
into a per-app compose override. You change it by editing the policy in the Hub,
not the template's `compose.yml`.

### Issuing certificates

Client certificates come from Vault's PKI (`pki_int`, role `client-cert`). The
key is generated on the YubiKey and never leaves it.

- **Admin enrollment**: at `https://enroll.<domain>` (requires `lldap_admin`),
  either by pasting a CSR made with `ykman` or through the guided flow, or on
  the host with `./portcullis cert enroll <user> [email]`.
- **What Vault signs**: the role takes the CN from the caller, never from the
  CSR, and enroll only signs CSRs whose subject is exactly the user. The
  certificate has the `clientAuth` EKU.

### Lifetime and renewal

Certificates live **`CLIENT_CERT_TTL`**, default `720h` (30 days).

**Why 30 days.** A very short lifetime (say 24 hours) would mean renewing with
the YubiKey every day; in practice certificates expire and users fall back to
weaker factors. A short lifetime would only be standing in for revocation, and
Portcullis enforces revocation everywhere a certificate is accepted (see
[Revocation](#revocation)), so the lifetime just sets how often people renew.
90 days (`2160h`) is reasonable if you revoke lost keys promptly.

`./portcullis pki setup` (also run by `upgrade`) rewrites the Vault role with
the current value. Only certificates issued afterwards are affected.

**Self-service renewal** at `https://enroll.<domain>/self` is open to any
signed-in user, for their own certificate only. It runs on router
`enroll-self` with `portcullis-self@docker`, which is group-gate's
`/authenticated` check: revocation and host checks, but no `lldap_admin`
requirement. Renewal succeeds only if all of these hold:

- the browser presents the user's **current, valid, unrevoked** certificate (Traefik passes it to enroll via `client-cert-pem@file`)
- its CN is the signed-in user
- Vault issued exactly that certificate
- the pasted CSR is for **the same public key**: `ykman piv keys export 9a` + `ykman piv certificates request`

An expired or revoked certificate cannot be renewed this way. An admin
re-enrolls the key instead.

**CLI renewal** on the host, with the YubiKey attached:
`./portcullis cert renew <user>`.

**Expiry warnings.** These list users whose newest certificate has fewer than
`CERT_EXPIRY_WARN_DAYS` (default 7) days left:

- `./portcullis status` (and `vault.certs_expiring` in `status --json`)
- `./portcullis cert list`, which marks them `expiring`
- the enrollment UI, which flags them

### mTLS login through Keycloak

`auth.<domain>` uses the **authaware** tier, so the browser can present the
YubiKey cert to Keycloak:

1. Traefik verifies the cert against `certs/ca-chain.crt`.
2. Traefik forwards it PEM-encoded in `X-Forwarded-Tls-Client-Cert` (middleware `client-cert-pem@file`).
3. Keycloak reads the header with its built-in **`traefik` x509 lookup provider** (`--spi-x509cert-lookup--provider=traefik`). The provider understands Traefik's `passTLSClientCert` `pem: true` format.

The realm's X.509 authenticator (`x509-config`) then:

- maps the Subject CN to the LLDAP username
- **re-validates** the chain against `certs/truststore/` (written by `pki setup`, mounted as Keycloak's truststore), and checks the validity period and the `clientAuth` EKU
- **checks the CRL** at `http://vault:8200/v1/pki_int/crl`. Keycloak caches it for at most 60 s; Vault rebuilds it on every revoke
- **fails closed on the CRL**: if the CRL cannot be fetched, the X.509 login fails. `x509-cert-auth-crl-abort-if-non-updated=true` also rejects a CRL past its `nextUpdate`. Vault never lets it get that stale: `pki setup` sets `pki_int/config/crl` to `expiry=72h auto_rebuild=true auto_rebuild_grace_period=12h`

`./portcullis keycloak configure` pushes the `x509-config` settings from
`keycloak/realm-export.json` to an existing realm.

#### Trusted proxy address

A cert header carries only the public certificate, so anyone who could put one
in front of Keycloak could log in as that user. Three things prevent it:

- **Keycloak only trusts the header from Traefik.** Keycloak's header-based
  lookup providers (`traefik` included) return no certificate unless the
  request comes from a trusted proxy. With
  `--proxy-trusted-addresses=${PORTCULLIS_AUTH_TRAEFIK_IP}`, Keycloak decides
  that **from the TCP peer address of each request**. It overwrites any
  trust-marker header the client sent. The only trusted address is Traefik's
  fixed IP on the internal `portcullis-auth` network. That IP is outside the
  network's dynamic range, so no other container can get it. These sources are
  untrusted, so the cert header and their `X-Forwarded-*` are ignored:
    - requests via `127.0.0.1:8080` (the CLI's admin API access)
    - requests from the `portcullis` network
    - requests from any other container attached to `portcullis-auth`
- **Traefik strips client-supplied cert headers.** It deletes
  `X-Forwarded-Tls-Client-Cert*` sent by the client on the entrypoint, also
  for requests without a TLS client cert, and drops their `_`/`.` aliases
  (`aliasHeadersStrategy=delete`).
- **CI tests it.** The `build-and-test` job logs in through Traefik with a real
  cert, which must succeed. Then it sends the same cert as a forged header
  straight to Keycloak from the `portcullis` and `portcullis-auth` networks and
  from `127.0.0.1:8080`, which must not yield an authorization code.

See [Security & Hardening](../operations/hardening.md#header-spoofing-protections).

### mTLS binding (group-gate)

A token with `amr=mtls` proves that a cert was used **at login**. Sometimes an
app's policy is satisfied **only** through the `mtls` factor:

- `mtls` alone
- `all` including `mtls`
- `any` where `mtls` is the only factor present in the token

Then group-gate also requires the **current request** to carry a client cert
that is not revoked and whose CN equals the session's `preferred_username`.
Otherwise the user gets the step-up page (`acr_values=mtls`).

So a session opened with a cert that is revoked later stops working
immediately. So does a session replayed from another browser without the key.

### Revocation

```bash
./portcullis cert list                # find the serial (--all includes revoked)
./portcullis cert revoke <serial>     # revoke (add --yes to skip the prompt)
./portcullis cert sync                # rewrite the serial list from Vault
```

**Traefik does not check CRLs.** A TLS handshake with a revoked but unexpired
cert still succeeds. Revocation is enforced in three places:

1. **group-gate, on every request** (`portcullis-groups@docker` and
   `portcullis-self@docker`). `client-headers@file` (Traefik
   `passTLSClientCert` with `serialNumber: true`) passes
   `X-Forwarded-Tls-Client-Cert-Info` to the backend and to every later
   forward-auth middleware. group-gate returns 403 when the cert's serial is
   revoked, before any other check. It has two sources:
    - **The serial list** `certs/revocation/revoked-serials.txt`. `cert revoke`
      and `cert sync` rewrite it atomically from Vault's list of revoked
      serials, and group-gate re-reads it when it changes. If Vault can't be
      queried, the file is left unchanged and the command fails: it never
      "un-revokes" by writing an empty list. If the file exists but can't be
      read, group-gate denies every request that presents a cert (fail closed).
    - **Vault's CRL** (`http://vault:8200/v1/pki_int/crl`), re-fetched every
      60 s. It also covers revocations made directly through the Vault API or
      UI. If Vault is unreachable, the last good CRL is kept and the serial
      list still applies.
2. **Keycloak X.509 login**: the CRL check above. It fails closed when the CRL
   is unavailable or stale.
3. **mTLS binding**: sessions on mTLS-only policies need the unrevoked cert on
   every request.

**Coverage.** Revocation covers:

- every router whose middleware chain has `client-headers@file` **before** `portcullis-groups@docker` (all core routers and the default templates)
- new Keycloak X.509 logins
- sessions on mTLS-only policies

**Not covered.** Routers that rely on the TLS client cert alone, e.g. a
`protected`-tier router without `portcullis-groups@docker`. There the cert
works until it expires. Password and WebAuthn sessions of the same user are
also not affected; sign them out in the Keycloak admin console if needed.

---

## Vault: server mode, auto-unseal and AppRole

Vault runs in **server mode** with integrated (raft) storage on the
`vault_data` volume (`vault/vault.hcl`, data in `/vault/file`), so the CA
survives restarts. The listener is plain HTTP on the internal `portcullis`
network, and on `127.0.0.1:8200` on the host only. The container runs as the
image's non-root `vault` user (100:1000).

`./portcullis vault init` is idempotent and is run by `init`, `upgrade` and
`restore`. It does three things:

1. **Init**, on the first run only, with **one key share, threshold 1**. It
   writes to `secrets/` (dir `0700`, gitignored):
    - `secrets/vault-init.json`: the root token and unseal key (`0600`)
    - `secrets/vault-unseal/unseal-key`: mounted read-only into the vault
      container. Owned by you, group 1000, `0640` (dir `0750`)
2. **Unseal.** After that, `vault/entrypoint.sh` unseals automatically on every
   container start: `up`, restart, host reboot.
3. **Least privilege for enroll.** It creates the AppRole `portcullis-enroll`
   with policy `vault/policies/enroll.hcl`, which allows only
   `pki_int/sign/client-cert`, listing `pki_int/certs` and reading
   `pki_int/cert/*`. The credentials in `secrets/enroll/` (group 10002 = the
   enroll user, `0640`) are mounted read-only into enroll. Enroll logs in for
   1-hour tokens and logs in again before expiry or on a 403. There is no
   static or root token in `.env`. Rotate the secret-id with
   `./portcullis vault rotate-enroll-secret`.

The admin commands (`pki setup`, `cert enroll|renew|revoke|list|sync`,
`status`) use the root token from `secrets/vault-init.json`, or `VAULT_TOKEN`
if exported. They use the host `vault` CLI if it is installed, otherwise the CLI
inside the vault container. The token is passed by environment-variable name,
never on the command line. `secrets/` and `backups/` are masked from the Hub
container with empty tmpfs mounts.

`pki setup` never replaces an existing CA. If Vault has no CA but
`certs/ca-chain.crt` exists (Vault data lost), it refuses to create a new one.
Restore a backup, or pass `--force` and re-enroll every certificate. See the
[CLI Reference](../operations/cli.md#pki-setup).

**Trade-off of auto-unseal.** The unseal key lives on the same host as the
encrypted data. Root on the host, or anyone who can read `secrets/`, can unseal
Vault. What it does protect: a copy of the `vault_data` volume alone is useless.
Several Shamir shares on the same disk would add nothing, hence one share.

For stronger guarantees, remove the `secrets/vault-unseal` mount and unseal by
hand after each restart (`docker compose exec vault vault operator unseal`), or
use a cloud KMS auto-unseal.

**Keep an offline copy of `secrets/vault-init.json`.** Backups made by
`portcullis backup` and `upgrade` include `secrets/`, so protect them like the
keys themselves.

---

## Disabling mTLS (`MTLS_ENABLED=false`)

All three tiers then behave like `public`: no client certificates are requested
anywhere. Authentication is purely Keycloak (WebAuthn / password). You don't
need `ykman` or PIV setup. This is a good choice if you only want YubiKey
tap-to-authenticate.

!!! danger "Routers that rely on mTLS alone become unauthenticated"
    WebAuthn only protects routers that also run forward-auth
    (`portcullis-auth@docker`). A router on the `protected` tier with no
    forward-auth middleware, such as the Vault UI template, relied on the
    client certificate *as* its authentication. With `MTLS_ENABLED=false`,
    that router becomes **open**: there is no WebAuthn fallback. Before you
    disable mTLS, add `portcullis-auth@docker,portcullis-groups@docker` to such
    routers, or disable them.

Also note:

- App policies that require the `mtls` factor can no longer be satisfied, so
  users get the step-up page.
- X.509 login in Keycloak never fires.

```bash
# .env: MTLS_ENABLED=false
./portcullis config apply
./portcullis up
```

---

## Common scenarios

| Scenario | `ACME_STAGING` | `MTLS_ENABLED` | Notes |
|----------|----------------|----------------|-------|
| First DNS/ACME experiments | `true` | `false` | Untrusted certs, WebAuthn only |
| Production, WebAuthn only | `false` | `false` | Trusted certs, no certificate management |
| Production, full mTLS | `false` | `true` | PIV certs for browsers and CLI/API, WebAuthn fallback |
| Development / CI | `true` | `true` | Everything, including mTLS flows |

---

## Troubleshooting

### "Your connection is not private" / `NET::ERR_CERT_AUTHORITY_INVALID`
You are on staging certificates. Switch to `ACME_STAGING=false`, or launch
Chrome with `--ignore-certificate-errors`.

### App shows "unable to get local issuer certificate"
The app container cannot verify Keycloak's TLS cert. Check that:

- `certs/ca-bundle.crt` exists (`./portcullis config apply --bundle-only`)
- the container mounts it (`./certs/ca-bundle.crt:<path>:ro` in the template's `compose.yml`)
- the runtime uses it: `NODE_EXTRA_CA_CERTS` for Node.js, `SSL_CERT_FILE` for Go

### mTLS: `ERR_BAD_SSL_CLIENT_AUTH_CERT`
The client certificate is invalid, expired, or not signed by the Portcullis CA.
Renew it at `https://enroll.<domain>/self` while it is still valid; otherwise
an admin re-enrolls it.

### mTLS: `ERR_SSL_CLIENT_AUTH_CERT_NEEDED`
The router is on the `protected` tier and requires a client cert. Enroll a PIV
cert, or change the app's access policy in the Hub.

### 403 "Your client certificate has been revoked"
group-gate found the cert's serial in the revoked list or the CRL. Remove the
cert from the browser/keychain and have an admin re-enroll the key.

### 403 "The certificate revocation list is unavailable"
group-gate cannot read `certs/revocation/revoked-serials.txt` and therefore
denies requests that present a cert. Run `./portcullis cert sync` and check the
file's permissions.

### X.509 login in Keycloak does nothing
Check the Keycloak logs:

- `HTTP header "X-Forwarded-Tls-Client-Cert" is not trusted` means the request
  did not come from Traefik's `portcullis-auth` address. Check
  `PORTCULLIS_AUTH_TRAEFIK_IP` and that Traefik is attached to `portcullis-auth`.
- A CRL error means Vault is sealed or unreachable (`./portcullis status`).
