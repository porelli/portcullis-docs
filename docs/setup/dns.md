# DNS Configuration

Portcullis uses wildcard DNS to route all subdomains to a single server. This page covers how to set up DNS records and configure your DNS provider for automatic certificate issuance.

## Prerequisites

- A domain you control (e.g., `example.com`)
- DNS hosted on a supported provider (Cloudflare, Porkbun, Route53, DigitalOcean, Hetzner, or [any lego provider](https://doc.traefik.io/traefik/https/acme/#providers))
- A server with a public IP running Portcullis

## Step 1: Configure DNS

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
    If using Cloudflare, **disable the orange cloud (proxy)** for the wildcard record. Cloudflare's proxy interferes with mTLS client certificate verification.

### Option B: Individual DNS Records

If you prefer explicit records, create one for each service:

```
auth.portcullis.example.com       A  203.0.113.10
hub.portcullis.example.com        A  203.0.113.10
directory.portcullis.example.com  A  203.0.113.10
traefik.portcullis.example.com    A  203.0.113.10
```

You will need to add a record each time you enable a new app.

## Step 2: Create a DNS Provider API Token

Portcullis needs a DNS API token to solve ACME DNS-01 challenges for wildcard certificate issuance. Only `*.portcullis.example.com` appears in Certificate Transparency logs -- individual subdomain names are never leaked.

### Cloudflare

1. Go to [API Tokens](https://dash.cloudflare.com/profile/api-tokens)
2. Click "Create Token" and use the "Edit zone DNS" template
3. **Permissions**: Zone > DNS > Edit
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

### DigitalOcean

```
DNS_PROVIDER=digitalocean
DO_AUTH_TOKEN=your-token
```

### Hetzner

```
DNS_PROVIDER=hetzner
HETZNER_API_KEY=your-key
```

### Other Providers

Traefik supports 80+ DNS providers via [lego](https://doc.traefik.io/traefik/https/acme/#providers). Set `DNS_PROVIDER=<lego-provider-name>` and its required environment variables in `.env`.

If your provider's environment variables are not already listed in `docker-compose.yml`, add them to the Traefik service's `environment` section.

## Step 3: Configure Portcullis

### First-time setup

`./portcullis init` asks for your domain and DNS provider (credentials are read
from the environment or a hidden prompt), writes them to `.env` and, for the
providers it knows, creates the records from Step 1 for you:

```bash
./portcullis init
```

### Creating or checking the records later

```bash
./portcullis dns setup           # create/update A (and AAAA) for <domain> and *.<domain>
./portcullis dns setup --check   # only compare what resolves (via 1.1.1.1) with the public IP
```

`dns setup` supports `cloudflare`, `porkbun`, `digitalocean`, `hetzner` and
`route53` (needs the `aws` CLI). For other providers it prints the records to
create by hand. See the [CLI Reference](../operations/cli.md#dns-setup).

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

Traefik requests and renews the wildcard certificate automatically.

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

## How ACME DNS-01 Works

Unlike HTTP-01 challenges (which require port 80 access for each hostname), DNS-01 proves domain ownership by creating a TXT record in your DNS zone:

1. Traefik requests a wildcard certificate for `*.portcullis.example.com`
2. Let's Encrypt responds with a challenge token
3. Traefik uses your DNS provider's API to create a `_acme-challenge.portcullis.example.com` TXT record
4. Let's Encrypt verifies the TXT record exists
5. The wildcard certificate is issued, covering all subdomains

This is why Portcullis needs your DNS provider API token -- it creates and cleans up the challenge TXT record automatically.

## Multiple Domains

Portcullis is built around **one** base domain. group-gate denies (403) every
host that is not exactly `<label>.<PORTCULLIS_DOMAIN>`, and the Hub rejects
templates that route any other domain, so a second domain can only serve
routers that don't use `portcullis-groups@docker` (e.g. public pages, or apps
with their own native OIDC login).

If you need that anyway:

1. Add the wildcard DNS records for the second domain.
2. Traefik's static configuration comes only from the `TRAEFIK_*` environment
   variables in `docker-compose.yml`. Add a second certificate domain in
   `config/docker-compose.override.yml` (and the DNS provider credentials for
   it, if it is hosted elsewhere):

    ```yaml
    services:
      traefik:
        environment:
          TRAEFIK_ENTRYPOINTS_WEBSECURE_HTTP_TLS_DOMAINS_1_MAIN: internal.corp.io
          TRAEFIK_ENTRYPOINTS_WEBSECURE_HTTP_TLS_DOMAINS_1_SANS: "*.internal.corp.io"
    ```

3. Use the full hostname in the service's labels:

    ```yaml
    labels:
      traefik.http.routers.myapp.rule: Host(`myapp.internal.corp.io`)
    ```

4. Run `./portcullis up`.

## Local Development (No Public Domain)

For local development without a real domain or ACME:

1. Run `./portcullis init --domain portcullis.local --dns-provider none`. `init`
   already issues a self-signed `*.portcullis.local` server certificate from the
   internal PKI (`certs/server.crt`; `./portcullis pki setup --with-server-cert`
   recreates it)
2. Add entries to `/etc/hosts`:

```
127.0.0.1  auth.portcullis.local hub.portcullis.local directory.portcullis.local traefik.portcullis.local
```

3. Import `certs/root-ca.crt` into your browser or OS trust store to avoid certificate warnings

!!! note
    mTLS with client certificates works the same way locally. The only difference is the server certificate is self-signed instead of from Let's Encrypt.
