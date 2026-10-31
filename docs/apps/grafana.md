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
