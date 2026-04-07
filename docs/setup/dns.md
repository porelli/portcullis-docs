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

### First-Time Setup (Bootstrap)

The bootstrap script will prompt for your domain and DNS provider:

```bash
./scripts/bootstrap.sh
```

### Updating an Existing Installation

Edit `.env`:

```bash
PORTCULLIS_DOMAIN=portcullis.example.com
ACME_EMAIL=admin@example.com
DNS_PROVIDER=porkbun
PORKBUN_API_KEY=pk1_...
PORKBUN_SECRET_API_KEY=sk1_...
LLDAP_BASE_DN=dc=portcullis,dc=example,dc=com
```

Then restart services:

```bash
docker compose down
docker compose up -d
```

Traefik will automatically request and renew the wildcard certificate.

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

To serve apps under multiple domains (e.g., `portcullis.example.com` and `internal.corp.io`):

1. Add wildcard DNS records for both domains
2. Update `traefik/traefik.yml` to request certificates for both:

```yaml
entryPoints:
  websecure:
    address: ":443"
    http:
      tls:
        certResolver: letsencrypt
        domains:
          - main: "portcullis.example.com"
            sans:
              - "*.portcullis.example.com"
          - main: "internal.corp.io"
            sans:
              - "*.internal.corp.io"
```

3. Use the full hostname in service labels:

```yaml
labels:
  traefik.http.routers.myapp.rule: Host(`myapp.internal.corp.io`)
```

## Local Development (No Public Domain)

For local development without a real domain or ACME:

1. Set `PORTCULLIS_DOMAIN=portcullis.local` in `.env`
2. Run the Vault PKI setup with `--with-server-cert` to generate a self-signed wildcard certificate
3. Add entries to `/etc/hosts`:

```
127.0.0.1  auth.portcullis.local hub.portcullis.local directory.portcullis.local traefik.portcullis.local
```

4. Import `certs/root-ca.crt` into your browser or OS trust store to avoid certificate warnings

!!! note
    mTLS with client certificates works the same way locally. The only difference is the server certificate is self-signed instead of from Let's Encrypt.
