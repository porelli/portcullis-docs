# DNS Configuration

Portcullis uses wildcard DNS to route all subdomains to a single server. This
page covers the records Portcullis wants (its **DNS plan**), how
`./portcullis dns plan / setup / check` creates and checks them, CAA and
DNSSEC, and the DNS provider credentials for automatic certificate issuance.

## Prerequisites

- A domain you control (e.g., `example.com`)
- DNS hosted on a supported provider (Cloudflare, Porkbun, Route 53,
  DigitalOcean, Hetzner (legacy DNS or Hetzner Cloud), or
  [any lego provider](https://doc.traefik.io/traefik/https/acme/#providers),
  whose records you then create by hand)
- A server with a public IP running Portcullis

## Step 1: Configure DNS

For the providers it knows, `./portcullis init` (and later
`./portcullis dns setup`) creates every record below for you. For the others
it prints them, and you create them by hand. See [Record sets](#record-sets)
for the full list, CAA included.

### Option A: Wildcard DNS Record (Recommended)

Create a single wildcard A record pointing all subdomains to your server:

```
*.portcullis.example.com  A  203.0.113.10
```

This means `auth.portcullis.example.com`, `hub.portcullis.example.com`, `grafana.portcullis.example.com`, and every other service subdomain all resolve to your server without creating individual records.

You also need a record for the bare subdomain:

```
portcullis.example.com    A  203.0.113.10
```

!!! warning "Cloudflare proxy"
    If using Cloudflare, **disable the orange cloud (proxy)** for the wildcard record. Cloudflare's proxy terminates TLS itself, so YubiKey and browser certificates never reach Portcullis. The DNS plan shows a proxied record as a wrong address and names it "proxied (orange cloud)".

### Option B: Individual DNS Records

If you prefer explicit records, create one for each service:

```
portcullis.example.com            A  203.0.113.10
auth.portcullis.example.com       A  203.0.113.10
directory.portcullis.example.com  A  203.0.113.10
enroll.portcullis.example.com     A  203.0.113.10
hub.portcullis.example.com        A  203.0.113.10
people.portcullis.example.com     A  203.0.113.10
traefik.portcullis.example.com    A  203.0.113.10
metrics.portcullis.example.com    A  203.0.113.10   (monitoring profile only)
```

You will need to add a record each time you enable a new app. `dns setup`
only writes the wildcard pair (Option A); with Option B, `dns plan` shows
the wildcard as missing.

## Step 2: Create a DNS Provider API Token

Portcullis needs a DNS API token to solve ACME DNS-01 challenges for wildcard
certificate issuance. Only `*.portcullis.example.com` appears in Certificate
Transparency logs -- individual subdomain names are never leaked. The same
token lets `./portcullis dns setup` write the [record sets](#record-sets).

### Cloudflare

1. Go to [API Tokens](https://dash.cloudflare.com/profile/api-tokens)
2. Click "Create Token" and use the "Edit zone DNS" template
3. **Permissions**: Zone > DNS > Edit. To let `dns setup --dnssec` turn on
   [DNSSEC signing](#dnssec), also add Zone > DNS Settings > Edit
4. Set in `.env`:

```
DNS_PROVIDER=cloudflare
CLOUDFLARE_API_TOKEN=your-token
```

### Porkbun

1. Go to [API Access](https://porkbun.com/account/api)
2. Enable API access for your domain
3. Create an API key and secret key
4. Set in `.env`:

```
DNS_PROVIDER=porkbun
PORKBUN_API_KEY=pk1_...
PORKBUN_SECRET_API_KEY=sk1_...
```

### AWS Route 53

```
DNS_PROVIDER=route53
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_HOSTED_ZONE_ID=Z1234567890
```

`AWS_HOSTED_ZONE_ID` is optional: without it the zone is found with a SOA
lookup. No AWS CLI is needed.

### DigitalOcean

```
DNS_PROVIDER=digitalocean
DO_AUTH_TOKEN=your-token
```

See [DigitalOcean](#digitalocean) below for what Portcullis can and can't do there.

### Hetzner

Hetzner has two DNS APIs, so Portcullis has two providers:

```
# legacy DNS API (dns.hetzner.com)
DNS_PROVIDER=hetzner
HETZNER_API_KEY=your-key

# DNS in the Hetzner Cloud API (console.hetzner.com)
DNS_PROVIDER=hetzner-cloud
HETZNER_API_TOKEN=your-cloud-token
```

See [Hetzner: legacy DNS and Hetzner Cloud](#hetzner-legacy-dns-and-hetzner-cloud) for which one to pick.

### Other lego providers

See [Other providers](#other-providers): Traefik can still issue the
certificate, but you create the records by hand.

## Step 3: Configure Portcullis

### First-time setup

`./portcullis init` asks for your domain and DNS provider (credentials are read
from the environment or a hidden prompt), writes them to `.env` and, for the
providers it knows, creates the records from Step 1 for you (`dns setup`).
At that point Traefik has no ACME account yet, so the CAA is the CA-only form
(see [CAA](#caa)); the end of `init` pins it to Traefik's account once Traefik
has registered:

```bash
./portcullis init
```

### Creating or checking the records later

```bash
./portcullis dns plan            # every record Portcullis wants vs what is live; changes nothing
./portcullis dns setup           # show the plan, confirm, write it through the provider API
./portcullis dns check           # public checks only (no credentials); exit 1 on a problem
```

- **`dns plan`** prints one row per record (set, name, type, wanted, live,
  status), the steps left, the CAA judgement ("would issue: yes") and the
  DNSSEC state of the zone. With an automated provider it reads the
  provider's records too, and lists records under your domain that aren't
  Portcullis' (a CNAME to a name that doesn't exist, an address that isn't
  this server's, a leftover `_acme-challenge` TXT). `--json` prints the plan
  object ([contract §12.2](../guides/integration-contracts.md#122-api)).
- **`dns setup`** shows the plan and asks before it writes anything (`--yes`
  skips the question and is required without a terminal). It applies the
  `address` and `caa` sets (plus `nomail` with `DNS_NOMAIL=true`, or one set
  with `--only address|caa|nomail`), waits up to 5 minutes for the public
  resolvers, then runs `dns check`. `--dnssec` also turns on DNSSEC signing
  (the question then says so: signing is zone-wide), see [DNSSEC](#dnssec). With a provider it can't write to, it prints the
  records to create by hand and exits 0.
- **`dns check`** asks only the public resolvers (1.1.1.1 and 8.8.8.8), so it
  needs no credentials. It exits 1 when a record or the DNSSEC state is a
  Problem.

The provider work runs in the domains image's one-shot tool (the `dns-tool`
service): the credentials from `.env` reach it as JSON on its stdin, never on
a command line, in a container's environment or in `docker inspect`, and its
provider errors are redacted. See
[Security & Hardening](../operations/hardening.md#the-dns-tool) and the
[CLI Reference](../operations/cli.md#dns-plan).

`./portcullis status` has a **DNS** block for the main domain and every
added domain: the addresses, the CAA pin, the DNSSEC state and records that
aren't Portcullis'. It reads the domains service's plans, so it shows "DNS
checks unavailable" while that service isn't running.

### Changing the provider or credentials

Edit `.env`:

```bash
ACME_EMAIL=admin@example.com
DNS_PROVIDER=porkbun
PORKBUN_API_KEY=pk1_...
PORKBUN_SECRET_API_KEY=sk1_...
```

Then restart the stack so Traefik picks up the new environment:

```bash
./portcullis up
```

Traefik requests and renews the wildcard certificate automatically. Run
`./portcullis dns setup` to write the records at the new provider.

!!! warning "Changing the domain"
    `PORTCULLIS_DOMAIN` is baked into the Keycloak realm (redirect URIs, hostname),
    `LLDAP_BASE_DN`, the server certificate and every enabled app's config. Pick
    it before `init`; changing it later means a new install.

## Step 4: Verify

Check that the certificate was issued:

```bash
# Check Traefik logs for ACME
docker compose logs traefik | grep -i acme

# Test with curl
curl -v https://auth.portcullis.example.com 2>&1 | grep "subject:"
```

You should see a Let's Encrypt certificate for `*.portcullis.example.com`.

Then check the records, the CAA pin and DNSSEC:

```bash
./portcullis dns check
dig +short CAA portcullis.example.com @1.1.1.1   # issue and issuewild, accounturi=… once Traefik has registered
```

## Record sets

A **record set** is the unit Portcullis owns: it writes, replaces and removes
only the records of its sets, at three names: `<d>`, `*.<d>` and
`_dmarc.<d>`. It never touches NS, SOA, the apex of a zone it doesn't own
(`example.com` when `<d>` is `portcullis.example.com`) or any other record,
except under the [CAA merge rule](#caa).

| Set | Records | TTL | Default |
|-----|---------|-----|---------|
| `address` | `<d>` and `*.<d>`: A → the server's IPv4, AAAA → its IPv6 (no AAAA without one) | 300 | on |
| `caa` | at `<d>` only (it also covers `*.<d>`): `issue` and `issuewild` for the ACME CA, optional `iodef` | 300 | on (`DNS_CAA=true`), when the CA is known |
| `nomail` | at `<d>`: null MX `0 .` and TXT `v=spf1 -all`; at `_dmarc.<d>`: TXT `v=DMARC1; p=reject;` | 3600 | off |

- **`address`** is refused while a CNAME exists at `<d>` or `*.<d>`: the plan
  shows the CNAME as a record that isn't Portcullis' and names it, and you
  remove it by hand.
- **`nomail`** says "this domain sends no mail", so nobody can send mail that
  passes as yours. Turn it on for the main domain with `DNS_NOMAIL=true` (then
  `dns setup`); for an added domain, use its **Fix** in the Hub's DNS panel.
  The plan recommends it (Info) when `<d>` has no MX and no SPF record and
  `ALERT_SMTP_FROM` isn't at or under `<d>`. It replaces an existing SPF, MX
  or DMARC record at those names, and the plan says so first. Other TXT
  records at `<d>` (site verifications) stay.

## CAA

A CAA record says which certificate authorities may issue certificates for
a name. Portcullis' CAA allows **only** the ACME CA in use, **only** its own
ACME account, and **only** by DNS-01, so nobody else (another CA, another
Let's Encrypt account, an HTTP-01 challenge) can get a certificate for your
names:

```
portcullis.example.com  CAA  0 issue "letsencrypt.org; accounturi=https://acme-v02.api.letsencrypt.org/acme/acct/123; validationmethods=dns-01"
portcullis.example.com  CAA  0 issuewild "letsencrypt.org; accounturi=https://acme-v02.api.letsencrypt.org/acme/acct/123; validationmethods=dns-01"
```

`issuewild` is written explicitly because every Portcullis certificate is a
wildcard. With `DNS_CAA_IODEF` set (e.g. `mailto:security@example.com`) a
`0 iodef "<DNS_CAA_IODEF>"` entry is added: where CAs may report refused
orders (few act on it).

**Pin vs CA-only.** The **pin** names the account (`accounturi=`). While no
account is known yet, Portcullis writes the **CA-only** form, which still
allows only one CA and only DNS-01:

```
portcullis.example.com  CAA  0 issue "letsencrypt.org; validationmethods=dns-01"
portcullis.example.com  CAA  0 issuewild "letsencrypt.org; validationmethods=dns-01"
```

**Which account.** The main domain is pinned to **Traefik's** ACME account
(`./portcullis` reads only its URI from Traefik's `acme.json`, which never
leaves its volume). Each added domain is pinned to the **domains service's**
account. So the domains service can't get a certificate for the main domain,
and Traefik can't for an added domain. An added subdomain of the main domain
(`team-a.<d>`) gets its own CAA at its name: the closest CAA wins, so the main
domain's pin neither blocks it nor gets widened.

**Merge rule.** At a name that already has CAA records, Portcullis replaces
only the entries for **its** CA (matched case-insensitively, ignoring a
trailing dot and spaces); `iodef` only when `DNS_CAA_IODEF` is set. Other CAs'
entries stay, and the plan shows an Info "other CAs may also issue for
<d>: digicert.com". Writing `issuewild` takes wildcard issuance away from
another CA that had only `issue`, and the plan says so. On an added zone apex
the plan notes that the CAA covers every name in the zone without CAA of its
own.

**Would issue.** The plan judges the live CAA the way the CA does: it finds the
closest CAA set for `<d>` and for `*.<d>` (climbing the labels), at both
public resolvers, and asks whether that set allows the CA, the account and
DNS-01. A failed lookup or a critical entry it doesn't know counts as **no**.

**Account switches.** CAA isn't checked when an account registers, only
when it orders, so the order of steps matters:

- **Added domains.** The domains service registers a new account (the first
  time, or when `ACME_CA_SERVER` or `ACME_EMAIL` changed), writes the new pin
  to every added domain, waits until **both** public resolvers see it, and
  only then orders. There is never a gap.
- **Main domain.** Traefik registers and orders in one go, so `./portcullis`
  works around it. The CAA is CA-only while Traefik has no account.
  `./portcullis up` and `upgrade` read Traefik's account URI once its
  resolver is running (waiting up to 3 minutes for a first registration),
  record it in `secrets/domains/main-domain.env`, and tighten the pin when the
  live one differs. A failure there only warns. `./portcullis config apply`
  on an `ACME_STAGING` flip relaxes the CAA to CA-only **before** it clears
  `acme.json` (see [Certificates → Switching](certificates.md#switching)).
- **Lost account.** When Traefik's `acme.json` is gone (the volume deleted or
  recreated), Traefik registers a new account by itself, and its renewal then
  fails on CAA. `./portcullis status` shows the Problem "CAA allows another
  ACME account than Traefik's — fix: ./portcullis dns setup" when
  `secrets/domains/main-domain.env` names a different account than
  Traefik's current one. A missing `main-domain.env` (Traefik hadn't
  registered yet when `up` ran) is only a Warning; `dns plan`, `dns setup`
  and `dns check` write it as soon as they read Traefik's account. Backup and
  restore keep both accounts, so a restore doesn't cause this.

**Settings** (`.env`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `DNS_CAA` | `true` | Write the `caa` set (`true` or `false` only: anything else fails, so a typo can't switch CAA off). `false` removes the entries Portcullis wrote: for an added domain exactly those it tracked; for the main domain (`dns setup`) the entries for its CA that carry `validationmethods=dns-01`. Your own entries for the same CA without that parameter stay |
| `DNS_CAA_ISSUER` | empty | The CAA identifier of a CA other than Let's Encrypt. Let's Encrypt production and staging are both `letsencrypt.org`. Any other `ACME_CA_SERVER` without it: no `caa` set, and an Info "CAA skipped: unknown CA" |
| `DNS_CAA_IODEF` | empty | The `iodef` target (`mailto:` or `https:`); empty: no `iodef` entry |
| `DNS_NOMAIL` | `false` | Add the `nomail` set to the main domain (`dns setup`) |

After changing them, run `./portcullis up` (the domains service reads them)
and `./portcullis dns setup`.

**Providers without automation.** With a lego-only provider, `dns plan`
prints the exact CAA records to add by hand: CA-only before Traefik has
registered, pinned after. `dns check` and `status` check them. `up` doesn't
tighten them and `config apply` can't relax them for you: change them by hand
before an `ACME_STAGING` flip (to CA-only) and after (to the new pin that
`dns plan` shows).

## DNSSEC

DNSSEC signs a zone's records, so validating resolvers can tell forged
answers from real ones. It needs two things: the zone signed at your DNS
provider, and a **DS record** (a digest of the zone's signing key) published
at the parent zone, which you do at your registrar. Portcullis checks the
chain for every name, at both public resolvers, and shows one state with the
step that is left:

| State | Meaning | Severity | What to do |
|-------|---------|----------|------------|
| `secure` | The DS matches the zone's key and both resolvers validate | ok | Nothing |
| `unsigned` | No signing key, no DS | Info | Turn on signing at the provider (Cloudflare: `./portcullis dns setup --dnssec`, or one click in the Hub for an added domain), then publish the DS |
| `ds_missing` | Signed, but no DS at the parent | Warning | Add the DS the plan shows (key tag, algorithm, digest type 2, digest) at your registrar |
| `ds_mismatch` / `bogus` | A DS that matches no key, or validation fails | **Problem** | Validating resolvers can't reach the domain. Fix the DS at the registrar to the values the plan shows, or remove the DS |
| `unknown` | The lookups failed, or the chain can't be checked | Warning | Retry; the plan shows the resolver error |

!!! danger "Never turn signing off while a DS record is published"
    **Never turn signing off while a DS record is published**: validating
    resolvers then can't reach the domain. To stop using DNSSEC, remove the DS
    at the registrar first, wait for its TTL to expire, then turn signing off
    at the provider. Portcullis never turns signing off and never removes a
    DS.

**Turning signing on** is opt-in and never automatic, because it is
**zone-wide**: it also affects your other names in the zone (for
`portcullis.example.com`, all of `example.com`).

- Main domain: `./portcullis dns setup --dnssec` (Cloudflare only; with other
  providers it prints the steps).
- Added domain: **Turn on DNSSEC signing** in the Hub's DNS panel, or the
  doctor's one-click fix, both behind a confirmation naming the zone.
- Through its API only Cloudflare can sign. A `403` means the token lacks
  Zone > DNS Settings > Edit. Route 53 signing needs a KMS key and stays
  manual (the plan reads the DS values when the IAM policy allows
  `GetDNSSEC`). Porkbun's API doesn't sign zones. DigitalOcean has no
  DNSSEC.

**Publishing the DS at the registrar.** Once the zone is signed, `dns plan`
(or the Hub's DNS panel, with a **Copy** button per value) shows the DS:

```
DS: key tag 2371, algorithm 13, digest type 2, digest 1F98…
```

At the registrar, open the domain's DNSSEC (or "DS records") settings, add
a record with exactly these four values, and save. With Cloudflare as
registrar Cloudflare publishes it by itself. The state moves from
`ds_missing` to `secure` once the parent zone serves the DS (minutes to a
few hours, depending on the registry).

## Hetzner: legacy DNS and Hetzner Cloud

Hetzner moved DNS into the Hetzner Cloud API, and new zones can't be created
on the legacy `dns.hetzner.com` any more. Pick the provider by where the
zone lives:

| Provider | Zone at | `.env` credential | Hub field |
|----------|---------|-------------------|-----------|
| `hetzner` | the legacy DNS console (dns.hetzner.com) | `HETZNER_API_KEY` | DNS API token (legacy dns.hetzner.com) |
| `hetzner-cloud` | a Hetzner Cloud project (console.hetzner.com) | `HETZNER_API_TOKEN` (a Cloud API token with Read & Write) | Hetzner Cloud API token (Read & Write) |

The main domain's certificate works with both: Traefik's lego provider
`hetzner` uses the Cloud API when `HETZNER_API_TOKEN` is set, and the legacy
API with `HETZNER_API_KEY`. `config apply` (which `up` runs too) maps
`hetzner-cloud` to it, so set only the one variable that matches
`DNS_PROVIDER`: it refuses
`hetzner` with `HETZNER_API_TOKEN` set (lego would use the Cloud API) and
`hetzner-cloud` with `HETZNER_API_KEY` set. Neither API signs zones through
Portcullis; the plan shows the DNSSEC steps.

## DigitalOcean

Portcullis writes DigitalOcean records through DigitalOcean's own API
client, so CAA records get their flags and tag. DigitalOcean has **no
DNSSEC**: the plan's step for an unsigned zone is "digitalocean can't sign:
move the zone to sign it".

Portcullis' DigitalOcean support is tested only against a stand-in for
DigitalOcean's API, not yet on a real account. In particular, whether
DigitalOcean accepts the null MX `0 .` of the `nomail` set, and stores CAA
flags and tags exactly as written, is unverified. After `dns setup` (or a Fix
in the Hub), run `./portcullis dns check` and look at the `caa` and `nomail`
rows. If DigitalOcean refuses a record, the tool exits with the provider's
(redacted) error.

## Other providers

Traefik supports 80+ DNS providers via
[lego](https://doc.traefik.io/traefik/https/acme/#providers). Set
`DNS_PROVIDER=<lego-provider-name>` and its required environment variables in
`.env`. Traefik then issues the certificate, but `./portcullis` can't write
records there: `init` and `dns setup` print the records of the
[record sets](#record-sets) to create by hand, CAA included (see
[Providers without automation](#caa)). `dns check` and `status` check them
all the same. Added domains in the Hub need one of the automated providers.

Traefik is configured entirely through environment variables in the core
`docker-compose.yml` (there is no `traefik.yml`). If your provider's
environment variables are not already listed there, add them to the `traefik`
service's `environment` section in a `docker-compose.override.yml` (it is part
of every backup).

## How ACME DNS-01 Works

Unlike HTTP-01 challenges (which require port 80 access for each hostname), DNS-01 proves domain ownership by creating a TXT record in your DNS zone:

1. Traefik requests a wildcard certificate for `*.portcullis.example.com`
2. Let's Encrypt responds with a challenge token
3. Traefik uses your DNS provider's API to create a `_acme-challenge.portcullis.example.com` TXT record
4. Let's Encrypt verifies the TXT record exists
5. The wildcard certificate is issued, covering all subdomains

This is why Portcullis needs your DNS provider API token -- it creates and cleans up the challenge TXT record automatically.

## One domain per installation

A Portcullis installation serves exactly **one** base domain,
`PORTCULLIS_DOMAIN`, and every app lives at `<subdomain>.${PORTCULLIS_DOMAIN}`.
This is enforced, not just a default:

- group-gate denies every request whose host is not exactly
  `<label>.${PORTCULLIS_DOMAIN}`, because it looks policies and groups up by
  that label
- the Hub rejects templates whose routers use any other domain
  ([Integration Contracts §4](../guides/integration-contracts.md#4-policy-file-hub-group-gate))
- Traefik requests one wildcard certificate (`${PORTCULLIS_DOMAIN}` and
  `*.${PORTCULLIS_DOMAIN}`)
- oauth2-proxy's cookie and redirect whitelist cover `.${PORTCULLIS_DOMAIN}` only
- Keycloak's hostname is `auth.${PORTCULLIS_DOMAIN}`

**To serve a second domain, run a second installation.** Supporting several
domains in one installation would need all of the following:

- group-gate keyed by full host, or by a domain list
- the Hub's host validation and policy file keyed the same way
- a certificate and DNS records per domain
- oauth2-proxy cookies per domain: a session cookie can't span unrelated
  domains, so users would sign in once per domain
- Keycloak redirect URIs for each domain

## Local Development (No Public Domain)

For local development without a real domain or ACME:

1. Run `./portcullis init --domain portcullis.local --dns-provider none`. `init`
   already issues a self-signed `*.portcullis.local` server certificate from the
   internal PKI (`certs/server.crt`; `./portcullis pki setup --with-server-cert`
   recreates it)
2. Add entries to `/etc/hosts`:

```
127.0.0.1  portcullis.local auth.portcullis.local directory.portcullis.local enroll.portcullis.local hub.portcullis.local people.portcullis.local traefik.portcullis.local
```

3. Import `certs/root-ca.crt` into your browser or OS trust store to avoid certificate warnings

!!! note
    YubiKey and browser certificates work the same way locally. The only difference is the website certificate (HTTPS) is self-signed instead of from Let's Encrypt.

## Adding extra domains

Beyond the main domain, Portcullis can serve **extra domains** with their own
wildcard website certificates (HTTPS). Extra domains are added in the Hub's
**Settings → Domains** section with **+ Add domain** (see [Hub Management](../operations/hub.md#adding-extra-domains)).

Each added domain:

- has its own A/AAAA records (`<d>` and `*.<d>`) managed by the domains service
- gets its own CAA, pinned to the domains service's ACME account (see [CAA](#caa))
- gets its own Let's Encrypt wildcard certificate via DNS-01
- can host app instances with hostnames on that domain
- has a DNS panel in the Hub with its plan, a **Fix** button per record set
  and its DNSSEC state (see [Hub Management](../operations/hub.md#the-dns-panel))

**Supported providers**: Cloudflare, Porkbun, Route 53, DigitalOcean, Hetzner
(legacy DNS) and Hetzner Cloud (the same list as the main domain's
`dns setup`, minus `none`).

**Server addresses.** The records point at the server's public IPv4 (and
IPv6), from `PORTCULLIS_PUBLIC_IPV4` / `_IPV6` in `.env` or detected by
`./portcullis up`. While no domain is added, `./portcullis` doesn't look them
up and publishes no address unless `.env` sets them: the first added domain
may need one more `./portcullis up` (or set `PORTCULLIS_PUBLIC_IPV4` / `_IPV6`
in `.env`) (see
[Security & Hardening](../operations/hardening.md#public-ip-detection)).

**Added subdomains of the main domain** (e.g. `team-a.<main domain>`) are
allowed. This lets you delegate zones of your main domain to Portcullis without
changing the main domain's DNS setup. The added subdomain gets its own
wildcard certificate, and app instances on it use the cross-domain sign-in flow
(see [Hub Management](../operations/hub.md#cross-domain-sign-in)).

**Core services stay on the main domain**: the portal, Hub, people, auth,
directory, enroll (setup links), traefik, metrics and `mcp` endpoints are never served on extra domains (an app's own MCP endpoint is on the app's host, wherever it is).

**Removing an added domain** is allowed only when no app instance has a
hostname on it. The domains service removes the DNS records it created, its
CAA entries included (only the exact values it wrote; other CAs' entries
and your own records stay, also on Porkbun and the legacy Hetzner API, where
it deletes each record by its ID), and retries once on failure.
