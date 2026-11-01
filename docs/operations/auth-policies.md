# Authentication Policies

Portcullis lets you require any combination of three authentication factors for each app, with AND or OR semantics, plus a global default. This page explains the model and how to use it.

## Factors

| Factor | How the user proves it | Keycloak executor | `amr` value | LoA |
|--------|------------------------|-------------------|-------------|-----|
| **Password** | No password in the browser flow: met by any signed-in session (a passkey or a cert is stronger) | — | `pwd` | 1 |
| **WebAuthn** | Taps a hardware security key (YubiKey, platform authenticator) | `webauthn-authenticator-passwordless` | `hwk` | 2 |
| **mTLS** | Presents a client certificate over TLS (PIV / YubiKey cert) | `auth-x509-client-username-form` | `mtls` | 3 |

LoA = Level of Authentication, a number Keycloak uses for step-up. Every
sign-in is a passkey or a client cert and reaches LoA 2 in one touch
(oauth2-proxy asks for `hwk` by default); LoA 3 needs the cert. First passkeys
come from one-time setup links (`./portcullis invite`, the Hub's Users & Groups).

## Policy model

A policy has two parts:

1. **Factors** — zero or more of `mtls`, `webauthn`, `password`.
2. **Op** — `any` (any selected factor satisfies the policy) or `all` (every selected factor must have fired in the current session).

Special cases:

- Zero factors → **public** (no authentication required).
- One factor → the single factor is required; `op` is ignored.

Examples:

| Policy | Meaning |
|--------|---------|
| `{factors: [], op: ""}` | Public |
| `{factors: ["password"]}` | Username + password only |
| `{factors: ["mtls", "webauthn"], op: "any"}` | Either mTLS **or** WebAuthn |
| `{factors: ["mtls", "webauthn"], op: "all"}` | mTLS **and** WebAuthn (both must fire) |
| `{factors: ["mtls", "webauthn", "password"], op: "any"}` | Any one of the three |

## Configuring policies

### In the Hub UI

**Per-app** — open an app in the catalog and use the *Access policy* block above the settings form:

- Tick the factors you want.
- If two or more are ticked, pick *Require all checked* (AND) or *Any of checked* (OR).
- Tick *Inherit global default* to drop the override.

**Global default** — the *Settings* tab exposes the default policy that every app without an override uses. Changing it affects all apps whose per-app policy is unset.

!!! note "Fresh installs require hardware keys"
    Until an admin saves a global default, the Hub uses **WebAuthn** as the
    default. Every app without its own policy then requires a hardware security
    key: routers get `authaware@file`, Keycloak steps up to LoA 2, and
    group-gate requires `hwk` in `amr`. A password-only session gets the
    step-up page. To also accept YubiKey PIV certificates, save
    `any of [mtls, webauthn]`. An explicitly saved public default is stored and
    honoured. It is not the same as "never set".

The **safety score** next to each policy is a cosmetic sum: 0 for public, LoA for a single factor, LoA + 0.5 per extra required factor for AND policies.

## What happens when a user hits an app

### Same-LoA SSO (no step-up)

User logs into Docs (policy: public). Opens Grafana (policy: `any of [password]`). Their Keycloak session cookie carries `acr=pwd`, which satisfies Grafana's required LoA — Grafana gets a token with no further prompt. Same for any other apps with policies their session already satisfies.

### Step-up on a stricter app

User signed in with a passkey (`amr=[hwk]`, LoA 2). Opens Jellyfin with policy `mtls-required`. Keycloak sees the session's current LoA is 2, but Jellyfin's client requested `acr_values=mtls` (LoA 3). The `Condition - Level of Authentication` executor in the universal flow fires only the mTLS subflow — the certificate is asked for, nothing else. On success the session's LoA is upgraded to 3 and `amr` becomes `[hwk, mtls]`. No full re-login.

### Step-up on forward-auth apps

oauth2-proxy ≥ 7.10 accepts per-request `acr_values` via the `loginURLParameters` alpha-config setting, which is what Portcullis runs (allowed values `pwd`, `hwk`, `mtls`; default `hwk`; `kc_idp_hint=portcullis-invite` and `prompt=login` exist only for setup links). When `group-gate` detects a session that doesn't satisfy the app's policy, it returns a 403 "Additional authentication required" page with the URL in an `X-Stepup-URL` header: `https://auth.<domain>/oauth2/start?acr_values=<needed>&rd=https://<app>/`. The step-up always goes through `auth.<domain>`; there is no `/oauth2/` router on app hosts. There is no sign-out and no `prompt=login`: Keycloak's cookie authenticator runs the flow when the requested LoA is above the session's and asks only for the missing level. The new token reflects the step-up. When the missing factor is a hardware one (passkey / cert) the page does not auto-redirect: a **Continue** button, and links to register a passkey in the account console or enrol a certificate at `enroll.<domain>`. Other step-ups redirect after 2 seconds.

### Public policy

A policy with no factors means group-gate requires **no particular factor**, and the Hub sets the router's tier to `public@file`. The Hub only changes `tls.options`. The template's middlewares stay as they are, so a forward-auth app still requires a Keycloak login and its group. An app is only reachable without logging in if its template has no forward-auth middleware (`auth.method: public`).

## Traefik TLS tier

The policy also drives the TLS tier on each router via a Hub-generated compose override:

| Policy | Tier | Behaviour |
|--------|------|-----------|
| Public | `public@file` | No client cert, no forward-auth |
| mTLS-only, or `all of [..., mtls]` | `protected@file` | Requires client cert at TLS handshake |
| Everything else | `authaware@file` | Client cert tolerated but not required |

The tier change is emitted as a per-router `traefik.http.routers.<name>.tls.options` label in `${HUB_DATA_DIR}/overrides/<app>.override.yml`, for every router of the app. Base `compose.yml` files in templates are untouched. Changing the global default restarts only the inheriting apps whose tier actually changed.

**One tier per host.** Traefik selects TLS options per SNI host, before it
knows the path, so every router of a host must share one tier. If two routers
of a host disagree, Traefik falls back to its default TLS options and answers
`421 Misdirected Request`. The Hub therefore always writes the same tier for
all of an app's routers, including its [public router](#public-exceptions).

## Public exceptions

Templates can declare share-link paths in
[`auth.public_access`](../guides/manifest-reference.md#authpublic_access);
an admin turns them on per app in the [Hub](hub.md#public-exceptions). While
on, the Hub adds a router `portcullis-public-<app>` for those paths only:

- higher priority than every router of the app, so it wins for its paths;
- middlewares `portcullis-public-strip-<app>@docker,rate-limit@file,security-headers@file`
  only: **no forward-auth, no group-gate**, so no login, no group, no
  hardware key, no step-up and no access policy apply on these paths;
- the strip middleware deletes client-supplied identity headers (core's
  `X-Forwarded-User`, `X-Forwarded-Email`, `X-Forwarded-*`, `X-Auth-Request-*`,
  `Remote-*`, plus the template's `identity_headers`, each also in its
  `_` form), so a header-auth app can't be told who the visitor is;
- its first middleware, `portcullis-public-guard@docker` (group-gate
  `/public-guard`), re-checks the path against the published patterns and
  answers 403 to requests carrying `Authorization`, `Proxy-Authorization` or
  the template's credential headers, cookies or query parameters (names
  normalised the way PHP does), so a stolen password, API key or session
  can't get past the hardware key there;
- supporting paths serve static files only (by extension), plus single
  `exact` routes the template justifies;
- in mode `listed`, only the share tokens an admin listed are routed; any
  other token on the same prefix still goes through forward-auth.

**Exceptions vs mTLS.** A policy of `mtls` alone, or `all` including `mtls`,
normally gives the host `protected@file`: no client cert, no TLS handshake.
Anonymous visitors can't present one, so while the public router exists the
Hub uses `authaware@file` for **all** of the app's routers instead
(`policy.HostTier`). What still enforces mTLS:

| App type | Gated paths after the downgrade |
|----------|---------------------------------|
| `forward-auth` / `header-auth` | group-gate's [mTLS binding](#mtls-binding) requires a valid, unrevoked client certificate matching the user on **every** request, so mTLS stays enforced per request |
| `native-oidc` (no group-gate on the host-wide router) | mTLS is only enforced **at login**, through the Keycloak `acr` (`mtls`). An existing app session works from a browser without the key |
| any router without group-gate | loses the handshake check; the Hub lists such routers in the warning |

In mode `listed` with no listed share there is no public router and no
downgrade. Policies that already give `authaware@file` or `public@file` are
unchanged.

## Where policies are published

The Hub writes per-app policies into `group-gate-policy.json` **keyed by every subdomain the app routes** (never by template ID); apps that inherit the default publish nothing and group-gate uses the file's `default`. A policy with an unknown factor or op makes group-gate deny the request (fail closed). Format: [Integration Contracts §4](../guides/integration-contracts.md#4-policy-file-hub-group-gate).

For native-OIDC apps the policy also sets the Keycloak client's `default.acr.values`, so Keycloak prompts for the right level at login.

## Identity

Policies decide *how* a user signed in; *who* the user is always comes from the immutable LLDAP username (`preferred_username`, `X-Forwarded-User`), never from the email. LLDAP users can edit their own email, so Keycloak does not trust it (`trustEmail=false`) and nothing in Portcullis authorises or links accounts by it. See [Security & Hardening](hardening.md#header-spoofing-protections).

## mTLS binding

`amr=mtls` in a token only proves a certificate was used at login. When a policy is satisfied **only** through `mtls` (`mtls` alone, `all` including `mtls`, or `any` where `mtls` is the only factor in the token), group-gate additionally requires the current request to present an unrevoked client certificate whose CN equals the token's `preferred_username`. Otherwise the user gets the step-up page. A session opened with a since-revoked certificate, or replayed from a browser without the key, stops working at once. See [TLS & mTLS](../setup/certificates.md#mtls-binding-group-gate).

## Enforcement map

| Layer | Public | Password | WebAuthn | mTLS | AND combinations | OR combinations |
|-------|--------|----------|----------|------|------------------|-----------------|
| Traefik | `public` | `authaware` | `authaware` | `protected` | `protected` if `mtls` in set | `authaware` unless mTLS-only |
| Keycloak | none | LoA 1 flow | LoA 2 flow | LoA 3 flow | highest LoA + step-up | lowest LoA (any satisfies) |
| group-gate | no factor check | require `pwd ∈ amr` | require `hwk ∈ amr` | require `mtls ∈ amr` + mTLS binding | require all factors in `amr` (+ binding if `mtls`) | require `amr ∩ factors ≠ ∅` (+ binding if only `mtls` matched) |

## LLDAP passwords

The browser flow never asks for an LLDAP password. LLDAP passwords remain for LLDAP's own web UI and for apps that bind to LDAP themselves. A `password` policy factor is met by any signed-in session.

## Caveats

- **`acr_values` is advisory at Keycloak.** The OIDC spec treats it as a hint; Keycloak only hard-rejects when a client requests via the `claims` parameter with `essential: true`. Portcullis uses the LoA conditional executors instead, which hard-fail when the user can't satisfy the level (e.g. asking for `mtls` without a certificate). `group-gate` *also* verifies `acr`/`amr` from the issued token as a belt-and-braces check — trust doesn't depend on Keycloak honoring the request.
- **Session LoA accumulates.** Once a user steps up to LoA 3 via mTLS, every subsequent app within the same session sees `acr=mtls` and `amr ⊇ [mtls, ...]`. Stricter apps pass without additional prompts. Loosening policies mid-session doesn't downgrade the session.
- **`max_age` in the LoA conditions** is 10 hours (matching the session lifespan). Lower this in `realm-export.json` if you want the re-prompt window to be shorter.

## Troubleshooting

**"Step up required" page from group-gate**
Your session is missing the factor(s) the app requires. Click the link in the page body to re-authenticate at the right level.

**Client cert prompt loops indefinitely**
Your browser may not be sending the client certificate. Check that the cert is imported into your OS/keychain and that the origin matches the Traefik wildcard (`*.<your-domain>`).

**Keycloak login form appears when you expected SSO**
The session cookie expired (8 hours idle / 12 hours max by default). Re-authenticate.

**AND policy keeps failing with `amr=["pwd"]` even after a WebAuthn step-up**
Check that the `acr` client scope is attached to the app's Keycloak client and that the `acr loa level` protocol mapper has `Add to access token = true`. `./portcullis keycloak configure` does this for `portcullis-forward-auth`, and the Hub attaches the `acr` and `groups` scopes to every client it registers; a manually-created client may be missing them.
