# 📊 Grafana

> Monitoring dashboards — protected by WebAuthn

**Category:** monitoring  
**Tags:** `monitoring`, `dashboards`, `metrics`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `header-auth` |
| **SSO** | :warning: Partial |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_grafana` |
| **Admin Group** | `admin_grafana` |
| **Subdomain** | `grafana` |

!!! info "Auth Notes"
    Proxy auth with X-Forwarded-User header, accepted only from Traefik (GF_AUTH_PROXY_WHITELIST = PORTCULLIS_TRAEFIK_IP). Auto-creates users as Viewer role. Admin role requires manual promotion in Grafana. Access gated by group-gate.

## Public Exceptions

Externally shared dashboards (/public-dashboards/&lt;access token&gt;) for people without a Portcullis account. Grafana serves them read-only and anonymously; identity headers are stripped on these paths.

When an admin turns them on in the Hub, these paths skip forward-auth and group-gate (see [Public exceptions](../operations/auth-policies.md#public-exceptions)).

**Default:** on, mode `listed`  
**Share token:** `^([0-9a-f]{32}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})$`  
**Refused by the public guard (login credentials):** header `Authorization`, header `Proxy-Authorization`, header `X-Access-Token`, header `X-Grafana-Id`, cookie `grafana_session`, cookie `renderKey`, query `auth_token`  
**Identity headers stripped:** `X-Forwarded-User` (plus the core ones)  

| Prefix | Opened | Description |
|--------|--------|-------------|
| `/public-dashboards/{token}` | per listed share; mode `all`: every share | Shared dashboard viewer page |
| `/api/public/dashboards/{token}` | per listed share; mode `all`: every share | Dashboard JSON, annotations and panel queries of the shared dashboard |
| `/public/build` | always (supporting); static files only | JS/CSS bundles, favicon and logos |
| `/public/fonts` | always (supporting); static files only | Fonts |
| `/public/plugins` | always (supporting); static files only | Assets of non-core panel plugins (reveals which plugins are installed) |

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `grafana` | `grafana.<domain>` | all | `public@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `grafana` | `grafana/grafana:13.3.0` | `sha256:488984b716c0…` |

## Access URLs

- **Dashboard**: `https://grafana.{{DOMAIN}}`
