# Certificates

Portcullis uses three kinds of certificates, each with its own name everywhere
(the Hub, the CLI, the pages and these docs):

| Name | What it is | Where it comes from |
|------|------------|---------------------|
| **Website certificate (HTTPS)** | The certificate browsers check for `https://<anything>.<domain>` | Let's Encrypt: Traefik for the main domain, the domains service for [added domains](dns.md) |
| **YubiKey certificate** / **Browser certificate** | A person's sign-in certificate: on a YubiKey, or a `.p12` file installed in a browser | Portcullis's **internal certificate authority** (Vault) |
| **Internal certificate authority** | The CA that issues YubiKey and browser certificates (admins and troubleshooting only) | Vault's PKI, created by `./portcullis pki setup` |

---

## Website certificates (HTTPS)

Portcullis has one TLS toggle in `.env`:

| Setting | `.env` variable | Default | What it controls |
|---------|----------------|---------|------------------|
| **Certificate source** | `ACME_STAGING` | `false` | Staging (test) vs production (trusted) Let's Encrypt certs |

After changing it, run:

```bash
./portcullis config apply
./portcullis up
```

`config apply` sets `ACME_CA_SERVER` in `.env` and rebuilds
`certs/ca-bundle.crt`. `up` recreates Traefik when its environment changed.

Whether browsers are asked for a **YubiKey or browser certificate** is not an
`.env` setting: it follows the sign-in methods switched on in the Hub and each
app's template ([TLS tiers](#tls-tiers)).

### ACME staging vs production

#### Production (`ACME_STAGING=false`, the default)

- Uses the Let's Encrypt **production** CA, which all browsers trust.
- Rate limits apply: 50 certificates per registered domain per week.
- One wildcard certificate (`<domain>` + `*.<domain>`) covers every app, so
  individual subdomains never appear in Certificate Transparency logs.

#### Staging (`ACME_STAGING=true`)

- Uses the Let's Encrypt **staging** CA. There are no rate limits, but
  **browsers will not trust the certificate**. Use it while you iterate on DNS
  setup.
- App containers that call Keycloak over HTTPS mount `certs/ca-bundle.crt`.
  `config apply` builds it from the system CAs, the internal Portcullis PKI
  chain, and the Let's Encrypt staging root (only when `ACME_STAGING=true`).
  `init`, `up` and `upgrade` rebuild it too, and restart the two forward-auth
  services when it changed: they read it only at start-up, and with a stale
  bundle every sign-in callback fails (`x509: certificate signed by unknown
  authority`).

Browser workarounds for staging certs: start Chrome with
`--ignore-certificate-errors`, accept the risk in Firefox, or use `curl -k`.

#### Switching

1. Set `ACME_STAGING=true` or `false` in `.env`.
2. Run `./portcullis config apply && ./portcullis up`. `config apply` notices
   the flip and clears Traefik's `acme.json`, so Traefik requests a new
   certificate; `up` restarts the forward-auth services, which now trust the
   new bundle.
3. Wait about 2 minutes for the DNS-01 challenge:
   `docker compose logs -f traefik 2>&1 | grep -i acme`.

---

## YubiKey and browser certificates

Two sign-in methods are certificates ([Sign-in methods](../operations/auth-policies.md#methods)):

| | YubiKey certificate | Browser certificate |
|---|---|---|
| Strength | 4.0 | 2.5 |
| Lives | on a YubiKey (PIV slot 9a); the key never leaves it | in a `.p12` file the person installs in a browser or the OS |
| Issued by | the YubiKey CA (`pki_int`) | the browser CA (`pki_file`) |
| Issued through | an admin: `./portcullis cert enroll`, or a CSR on the person's Sign-in tab | the person, on the [Sign-in page](../operations/auth-policies.md#the-sign-in-page) |
| Renewed | by the person on the Sign-in page, or `./portcullis cert renew` | not renewed: the person creates a new one |
| amr at sign-in | `mtls` | `file` |
| Starts | on | off |

The two kinds are always told apart by their **issuer**, never by their
name: a browser certificate never counts as a YubiKey certificate, in
Keycloak or in group-gate.

### TLS tiers

Core's `traefik/dynamic/tls.yml` is static (`config apply` never writes it)
and defines four TLS option sets:

| Tier | Traefik option | Trusts | Behavior |
|------|---------------|--------|----------|
| **protected** | `RequireAndVerifyClientCert` | `certs/ca-chain-yubikey.crt` (root + YubiKey CA) | A **YubiKey** certificate is **required**. Without one, the TLS handshake fails; a browser certificate never passes |
| **protected-any** | `RequireAndVerifyClientCert` | `certs/ca-chain.crt` (root + both CAs) | A YubiKey or browser certificate is **required** |
| **authaware** | `VerifyClientCertIfGiven` | `certs/ca-chain.crt` | A certificate is **optional**, verified if present |
| **public** | no `clientAuth` | — | No certificate requested |

Which method a certificate counts as decides Keycloak and group-gate by its
issuer.

**Certificate requests follow the switches.** All core routers (`auth`,
`hub`, `people`, the portal, `enroll-invite`, `traefik`, `directory`,
`metrics`, `mcp`) always use `authaware`: core pages always offer an optional
certificate, and a browser without one shows nothing. For apps, the Hub picks
the tier from the app's
[sign-in template](../operations/auth-policies.md#traefik-tls-tier) and the
certificate methods that are switched on, and writes it into a per-app
compose override:

- an `mtls` app always gets `protected` (YubiKey certificates only);
- every alternative of the template needs the YubiKey certificate →
  `protected`;
- every alternative needs a certificate, and at least one accepts the
  browser certificate → `protected-any`;
- some alternative has one → `authaware`;
- none has one (for example both certificate methods are off), or the app
  has no Portcullis sign-in → `public`, so the browser is never asked.

While an app has open [public exceptions](../operations/auth-policies.md#public-exceptions),
`protected` and `protected-any` become `authaware` for all of its routers.

You change it in the Hub (Settings → Sign-in, or the app's template), not in
the template's `compose.yml`.

### Issuing YubiKey certificates

YubiKey certificates come from the internal certificate authority's
`pki_int` (role `client-cert`). The key is generated on the YubiKey and never
leaves it.

- **On the host:** `./portcullis cert enroll <user> [email]` makes the key
  and the request on the attached YubiKey, has Vault sign it and imports the
  certificate ([CLI](../operations/cli.md#cert-enroll)).
- **In the Hub:** an administrator opens the person's **Sign-in** tab on
  people.&lt;domain&gt;, pastes a CSR made on the YubiKey with `ykman`, and
  confirms with a fresh sign-in. Administrators' own certificates are issued
  and revoked only from the server.
- **What Vault signs:** the role takes the CN from the caller (the person's
  username), never from the CSR, and enroll only signs CSRs whose subject is
  exactly the user. The certificate has the `clientAuth` EKU.

### Browser certificates

A person creates a browser certificate on their
[Sign-in page](../operations/auth-policies.md#browser-certificates), once an
admin has switched the method on. Portcullis (enroll) generates the key
(ECDSA P-256), has the browser CA (`pki_file`, role `browser-cert`) sign it
with the person's username as CN, and packs key and certificate into a
`.p12` encrypted with a generated password:

- the password is shown **once**, next to the download; Portcullis doesn't
  keep it and can't show it again;
- the private key is never stored, so the file can't be downloaded again;
- the lifetime is at most the **browser certificate lifetime** limit (30 days
  by default, never more than `CLIENT_CERT_TTL`), and each person has at most
  3 active ones (Hub → Settings → Sign-in → Limits);
- creating one needs a fresh passkey or YubiKey sign-in that
  people.&lt;domain&gt;'s template accepts, never a password or another
  browser certificate.

The `.p12` imports into **Firefox** (Settings → Privacy & Security →
Certificates → View Certificates → Your Certificates → Import), **Chrome /
Edge on Windows 10 or newer** (open the file: the Windows certificate
import wizard), and **macOS Keychain Access**.

!!! note "macOS 14 or newer"
    The `.p12` is encrypted with AES-256 (PBKDF2-SHA256, SHA-256 MAC).
    Keychain Access imports it on macOS 14 or newer; older macOS versions
    only read the legacy encryption and refuse the file.

### Lifetime and renewal

YubiKey certificates live **`CLIENT_CERT_TTL`**, default `720h` (30 days).
Browser certificates live at most that long, and at most the Hub's browser
certificate lifetime limit.

**Why 30 days.** A very short lifetime (say 24 hours) would mean renewing with
the YubiKey every day; in practice certificates expire and users fall back to
weaker factors. A short lifetime would only be standing in for revocation, and
Portcullis enforces revocation everywhere a certificate is accepted (see
[Revocation](#revocation)), so the lifetime just sets how often people renew.
90 days (`2160h`) is reasonable if you revoke lost keys promptly.

`./portcullis pki setup` (also run by `upgrade`) rewrites both Vault roles
with the current value. Only certificates issued afterwards are affected.

**Renewing a YubiKey certificate yourself** on the
[Sign-in page](../operations/auth-policies.md#the-sign-in-page): the page
shows the `ykman` commands that make a CSR for the key already on the
YubiKey (`ykman piv keys export 9a` + `ykman piv certificates request`); you
paste it. Renewal succeeds only if all of these hold:

- the browser presents the person's **current, valid, unrevoked** YubiKey
  certificate on that request (Traefik passes it to the Hub via
  `client-cert-pem@file` on the people router)
- its CN is the signed-in user
- Vault issued exactly that certificate
- the pasted CSR is for **the same public key**

An expired or revoked certificate cannot be renewed this way. An admin
issues a new one instead.

**CLI renewal** on the host, with the YubiKey attached:
`./portcullis cert renew <user>`.

**Expiry warnings.** These list users whose newest YubiKey certificate has
fewer than `CERT_EXPIRY_WARN_DAYS` (default 7) days left:

- `./portcullis status` (and `vault.certs_expiring` in `status --json`)
- `./portcullis cert list`, which marks them `expiring`
- the Sign-in page and the person's Sign-in tab, which show `expiring` for
  any certificate with fewer than `CERT_EXPIRY_WARN_DAYS` (default 7) days left

### Certificate login through Keycloak

`auth.<domain>` uses the **authaware** tier, so the browser can present a
YubiKey or browser certificate to Keycloak:

1. Traefik verifies the certificate against `certs/ca-chain.crt`.
2. Traefik forwards it PEM-encoded in `X-Forwarded-Tls-Client-Cert` (middleware `client-cert-pem@file`).
3. Keycloak reads the header with its built-in **`traefik` x509 lookup provider** (`--spi-x509cert-lookup--provider=traefik`). The provider understands Traefik's `passTLSClientCert` `pem: true` format.

The realm's sign-in flow has two certificate steps, both the sign-in
extension's `portcullis-x509`, which runs Keycloak's stock X.509 code:

| Step (config) | Method | Accepts a certificate issued by | CRLs | amr |
|---|---|---|---|---|
| `x509-config` | YubiKey certificate | the YubiKey CA (`portcullis-yubikey-ca.pem`) | `pki_int/crl`, `pki_int/crl/delta` | `mtls` |
| `x509-browser-config` | Browser certificate | the browser CA (`portcullis-browser-ca.pem`) | `pki_file/crl`, `pki_file/crl/delta` | `file` |

Each step runs only while its method is on, and only for a certificate whose
issuer **and** signature match its own CA; otherwise it steps aside. It
reads its CA file only when a certificate is presented, and logs an ERROR if
the file is missing. Each step then:

- maps the Subject CN to the LLDAP username, without a confirmation page
  (`x509-cert-auth.confirmation-page-disallowed`)
- **re-validates** the chain against `certs/truststore/` (written by `pki setup`, mounted as Keycloak's truststore), and checks the validity period and the `clientAuth` EKU
- **checks its CA's CRLs** at `http://vault:8200/v1/<mount>/crl` and `.../crl/delta` (`##`-separated in `crl-relative-path`). Keycloak caches each for at most 60 s. Both intermediates have `auto_rebuild=true` (keeps the full CRL from going stale) and therefore `enable_delta=true`: Vault does **not** rebuild the full CRL on revoke. New revocations land in the delta CRL, rebuilt every minute, until the next full rebuild. `./portcullis cert revoke` and a revocation on the web also rotate the full CRL immediately
- **fails closed on the CRL**: if the CRL cannot be fetched, the certificate login fails. `x509-cert-auth-crl-abort-if-non-updated=true` (Keycloak's actual key, with a dash) also rejects a CRL past its `nextUpdate`. Vault never lets it get that stale: `pki setup` sets each mount's `config/crl` to `expiry=72h auto_rebuild=true auto_rebuild_grace_period=12h`

`./portcullis keycloak configure` pushes each config from
`keycloak/realm-export.json` onto its `portcullis-x509` execution, by alias.

#### Trusted proxy address

A cert header carries only the public certificate, so anyone who could put one
in front of Keycloak could log in as that user. Three things prevent it:

- **Keycloak only trusts the header from Traefik.** Keycloak's header-based
  lookup providers (`traefik` included) return no certificate unless the
  request comes from a trusted proxy (`HttpRequest.isProxyTrusted()`). With
  `--proxy-trusted-addresses=${PORTCULLIS_AUTH_TRAEFIK_IP}`, Keycloak (Quarkus)
  decides that **from the TCP peer address of each request**, and overwrites
  any `X-Forwarded-Trusted-Proxy` header the client sent (`ForwardedParser`,
  run before routing). The only trusted address is Traefik's
  fixed IP on the internal `portcullis-auth` network. That IP is outside the
  network's dynamic range, so no other container can get it. These sources are
  untrusted, so the cert header and their `X-Forwarded-*` are ignored:
    - requests via `127.0.0.1:8080` (the CLI's admin API access; it arrives from the Docker gateway)
    - requests from the `portcullis` network
    - requests from any other container attached to `portcullis-auth`
- **Traefik strips client-supplied cert headers.** It deletes
  `X-Forwarded-Tls-Client-Cert*` sent by the client on the entrypoint, also
  for requests without a certificate, and drops their `_`/`.` aliases
  (`aliasHeadersStrategy=delete`).
- **CI tests it.** The `build-and-test` job logs in through Traefik with a real
  YubiKey certificate (`pc_method=yubikey_cert`), which must succeed. Then it sends the same cert as a forged header
  straight to Keycloak from the `portcullis` and `portcullis-auth` networks and
  from `127.0.0.1:8080`, with the realm's HTTPS requirement temporarily off so
  only the proxy gate can stop it. None may yield an authorization code.

See [Security & Hardening](../operations/hardening.md#header-spoofing-protections).

### Sign-in methods (Keycloak browser flow)

The realm's browser flow `portcullis-universal` (kept equal to
`keycloak/realm-export.json` by `./portcullis keycloak configure`) offers
exactly the [sign-in methods](../operations/auth-policies.md#methods) that are
switched on: the YubiKey certificate and the browser certificate (automatic
when the browser presents one), a passkey of any kind, or a password. Each
records its own `amr` value:

| Method | amr |
|--------|-----|
| YubiKey certificate | `mtls` |
| Security key passkey | `hwk` |
| Device-bound passkey | `dpk` |
| Synced passkey | `spk` |
| Browser certificate | `file` |
| Password | `pwd` |

`mtls` is emitted **only** for a YubiKey (`pki_int`) certificate; a browser
(`pki_file`) certificate emits `file`. A step-up asks Keycloak for one method
(`pc_method`), and Keycloak asks only for that method. The flow ends with a
check of the app's template for apps that sign in with OIDC themselves.

A user's first passkey comes from a one-time setup link
(`./portcullis invite <user>`, or the Hub). The setup link signs the user in
through the hidden identity provider `portcullis-invite` (enroll) after the
passkey registration it requires, with `amr` `inv`: a session that meets no
template, so the person touches their new passkey once more to open apps.
Details: [Security & Hardening](../operations/hardening.md#setup-links-enroll)
and [Sign-in Methods and Templates](../operations/auth-policies.md).

### Certificate binding (group-gate)

A token with `amr=mtls` or `amr=file` proves that a certificate was used
**at login**. group-gate counts a certificate method only while the
**current request** carries a certificate of that kind that is not revoked
and whose CN equals the session's `preferred_username`. It tells the kinds
apart by the certificate's issuer, compared with the two CA files it mounts
(`certs/yubikey-ca.crt` and `certs/browser-ca.crt`); if the two CAs had the
same name, or either file can't be read, no certificate counts. A template
that needs the certificate then shows the present-certificate page, the
step-up page or the needs-stronger page.

So a session opened with a certificate that is revoked later stops working
normally within a minute. So does a session replayed from another browser without it.

### Revocation

```bash
./portcullis cert list                # find the serial and its KIND (--all includes revoked)
./portcullis cert revoke <serial>     # revoke (add --yes to skip the prompt)
./portcullis cert sync                # rewrite the serial list from Vault
```

People revoke their own browser certificates on the Sign-in page; admins and
sign-in helpers revoke anyone's (but an administrator's) on the person's
Sign-in tab. A revoked certificate **normally stops working within a minute** and
shows as revoked everywhere (the Sign-in page, the Sign-in tab,
`cert list --all`).

**Traefik does not check CRLs.** A TLS handshake with a revoked but unexpired
certificate still succeeds. Revocation is enforced in three places:

1. **group-gate, on every request** (`portcullis-groups@docker`).
   `client-headers@file` or `client-cert-pem@file` (Traefik
   `passTLSClientCert` with `serialNumber: true`) passes
   `X-Forwarded-Tls-Client-Cert-Info` to the backend and to every later
   forward-auth middleware. group-gate returns 403 when the certificate's
   serial is revoked, before any other check. It has two sources:
    - **The serial list** `certs/revocation/revoked-serials.txt`. `cert revoke`
      and `cert sync` rewrite it atomically from Vault's lists of revoked
      serials of both CAs, and group-gate re-reads it when it changes. If
      Vault can't be queried, the file is left unchanged and the command
      fails: it never "un-revokes" by writing an empty list. If the file
      exists but can't be read, group-gate denies every request that
      presents a certificate (fail closed).
    - **Vault's full and delta CRLs of both CAs** (`GATE_CRL_URLS` =
      `http://vault:8200/v1/pki_int/crl http://vault:8200/v1/pki_file/crl`,
      `GATE_DELTA_CRL_URLS` = the two `.../crl/delta`), re-fetched every
      60 s (`GATE_CRL_REFRESH_SECONDS`). The union is enforced. A revocation
      on the web or with `cert revoke` rotates its CA's full CRL at once, so
      it is enforced within 60 s. Revocations made directly through the Vault
      API or UI reach the delta CRL within about 2 minutes (Vault's periodic
      rebuild runs once a minute) and are denied at group-gate's next
      refresh. If Vault is unreachable, the last good copy of each CRL is
      kept and the serial list still applies.
2. **Keycloak certificate login**: each certificate step checks its own CA's
   CRLs (above). It fails closed when the CRL is unavailable or stale.
3. **Certificate binding**: sessions on templates that need a certificate
   need the unrevoked certificate on every request.

**Coverage.** Revocation covers:

- every router whose middleware chain has `client-headers@file` or `client-cert-pem@file` **before** `portcullis-groups@docker` (all core routers and the default templates)
- new Keycloak certificate logins
- sessions on templates that need a certificate

**Not covered.** Routers that rely on the TLS handshake alone, e.g. a
`protected`-tier router without `portcullis-groups@docker`. There the
certificate works until it expires. Password and passkey sessions of the same
user are also not affected; sign them out in the Keycloak admin console if
needed.

---

## Internal certificate authority

Vault holds the internal certificate authority: a root (`pki`) and two
intermediates signed by it, one per certificate kind:

| Mount | CN | Issues | Role | Exported as |
|---|---|---|---|---|
| `pki` | `<domain> Root CA` | the two intermediates | — | `certs/root-ca.crt` |
| `pki_int` | `<domain> Intermediate CA` (the YubiKey CA) | YubiKey certificates | `client-cert` | `certs/yubikey-ca.crt` (also `certs/intermediate-ca.crt`) |
| `pki_file` | `<domain> Browser Certificate CA` | browser certificates | `browser-cert` | `certs/browser-ca.crt` |

`./portcullis pki setup` creates them and keeps them in place:

- `pki_file` has a 43800 h (5-year) lifetime and the same URL and CRL
  configuration as `pki_int` (`expiry=72h auto_rebuild=true
  auto_rebuild_grace_period=12h enable_delta=true delta_rebuild_interval=1m`).
- The `browser-cert` role copies the `client-cert` role's settings (client
  certificates only, EC P-256 keys, the CN never taken from a request,
  `max_ttl=$CLIENT_CERT_TTL`) and is rewritten on every run.
- `certs/ca-chain.crt` is root + `pki_int` + `pki_file`, in that order (the
  `protected-any` and `authaware` TLS options), `certs/ca-chain-yubikey.crt`
  is root + `pki_int` only (the `protected` option, so a browser certificate
  never passes it), and Keycloak's truststore (`certs/truststore/`) gets
  `portcullis-ca-chain.pem`, `portcullis-yubikey-ca.pem` and
  `portcullis-browser-ca.pem`. Whenever `pki_file` is created or either chain
  on disk is out of date, `pki setup` rewrites both chain files and the
  truststore, and the next `./portcullis up` restarts Traefik and Keycloak so
  they load them.
- It refuses (exit 1) when the two intermediates would have the same CN:
  every reader tells the kinds apart by issuer.
- It creates `pki_file` when it is missing, even while `pki_int` exists.
- `--force` destroys both CAs.

### Vault: server mode, auto-unseal and AppRole

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
   with policy `vault/policies/enroll.hcl`, which allows only signing
   (`pki_int/sign/client-cert`, `pki_file/sign/browser-cert`), listing
   (`pki_int/certs`, `pki_file/certs`) and reading (`pki_int/cert/*`,
   `pki_file/cert/*`) certificates, revoking (`pki_int/revoke`,
   `pki_file/revoke`) and rotating the CRLs (`pki_int/crl/rotate`,
   `pki_file/crl/rotate`). The credentials in `secrets/enroll/` (group 10002 = the
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

`pki setup` is idempotent and never replaces an existing CA: it only recreates
missing pieces such as `pki_file`, the `client-cert` and `browser-cert` roles
or the exported CA files. If it
finds an incomplete PKI (an earlier run aborted before the intermediate was
signed), it wipes and recreates it; any Vault error aborts instead of being
mistaken for "no PKI". If Vault has no CA but `certs/ca-chain.crt` exists
(Vault data lost), it refuses to create a new one. Restore a backup, or pass
`--force` and issue every certificate again. See the
[CLI Reference](../operations/cli.md#pki-setup).

`certs/server.key` is written `0640` with group 0 (Traefik runs as root but
without `CAP_DAC_OVERRIDE`). When the CLI is not run as root, it changes group
ownership through a throwaway root container (pinned `alpine`, only
`CAP_CHOWN`, no network).

**Trade-off of auto-unseal.** The unseal key lives on the same host as the
encrypted data. Root on the host, or anyone who can read `secrets/`, can unseal
Vault. What it does protect: a copy of the `vault_data` volume alone is useless.
Several Shamir shares on the same disk would add nothing, hence one share.

For stronger guarantees, remove the `secrets/vault-unseal` mount and unseal by
hand after each restart (`docker compose exec vault vault operator unseal`), or
use a cloud KMS auto-unseal.

**Keep an offline copy of `secrets/vault-init.json`.** Backups made by
`portcullis backup` and `upgrade` include `secrets/` (and a raft snapshot of
Vault), so protect them like the keys themselves. Off-host copies are encrypted
with `BACKUP_PASSWORD` (see [Backups](../operations/backups.md)).

---

## Without YubiKey or browser certificates

Switch the **YubiKey certificate** method off (and leave **Browser
certificate** off) in Hub → Settings → Sign-in (once no enabled template
needs them: Standard, for instance, still accepts any passkey). Then no app
asks for a certificate any more: every app whose template has no certificate
method left gets the `public` tier, and sign-in is passkeys only (plus
passwords, if you switch them on). Core pages keep the optional certificate
request; a browser without a certificate shows nothing. You don't need
`ykman` or PIV setup.

!!! danger "`mtls` apps rely on the certificate alone"
    An app with `auth.method: mtls` has no forward-auth: the YubiKey
    certificate at the TLS handshake **is** its sign-in, and it always keeps
    the `protected` tier, which trusts only the YubiKey certificate
    authority (a browser certificate is refused at the handshake). Without
    issued YubiKey certificates nobody reaches it.

---

## Common scenarios

| Scenario | `ACME_STAGING` | YubiKey certificate method | Notes |
|----------|----------------|----------------------------|-------|
| First DNS/ACME experiments | `true` | off | Untrusted certs, passkeys only |
| Production, passkeys only | `false` | off | Trusted certs, no certificate management |
| Production, with YubiKey certificates | `false` | on | PIV certificates for browsers and CLI/API, passkeys too; browser certificates optional |
| Development / CI | `true` | on | Everything, including certificate flows |

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

### `ERR_BAD_SSL_CLIENT_AUTH_CERT`
The YubiKey or browser certificate is invalid, expired, or not issued by the
internal certificate authority. Renew a YubiKey certificate on the
[Sign-in page](../operations/auth-policies.md#the-sign-in-page) while it is
still valid (otherwise an admin issues a new one); create a new browser
certificate there.

### `ERR_SSL_CLIENT_AUTH_CERT_NEEDED`
The router is on the `protected` tier (a YubiKey certificate required; a
browser certificate is never accepted there) or `protected-any` (a YubiKey or
browser certificate required). Get a YubiKey certificate (or, on
`protected-any`, create a browser certificate), or move the app to a template
that doesn't need a certificate in every alternative (Hub → the app's
Settings).

### 403: the certificate has been revoked
group-gate found the certificate's serial in the revoked list or a CRL.
Remove it from the browser/keychain; then create a new browser certificate on
the Sign-in page, or have an admin issue a new YubiKey certificate.

### 403: the certificate revocation list is unavailable
group-gate cannot read `certs/revocation/revoked-serials.txt` and therefore
denies requests that present a cert. Run `./portcullis cert sync` and check the
file's permissions.

### Certificate login in Keycloak does nothing
Check the Keycloak logs:

- `HTTP header "X-Forwarded-Tls-Client-Cert" is not trusted` means the request
  did not come from Traefik's `portcullis-auth` address. Check
  `PORTCULLIS_AUTH_TRAEFIK_IP` and that Traefik is attached to `portcullis-auth`.
- A CRL error means Vault is sealed or unreachable (`./portcullis status`).
- `portcullis` ERROR naming a CA file: `certs/truststore/portcullis-yubikey-ca.pem`
  or `portcullis-browser-ca.pem` is missing or not a CA. Run
  `./portcullis pki setup && ./portcullis up`.
- No certificate attempt at all: that certificate's method is off (Settings →
  Sign-in), or Keycloak has no valid `signin-keycloak.json` from the Hub
  (every method off, see [Sign-in flows in Keycloak](../operations/auth-policies.md#sign-in-flows-in-keycloak)).
