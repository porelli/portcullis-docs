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

!!! info "Auth Notes"
    Proxy auth with X-Forwarded-User header, accepted only from Traefik (GF_AUTH_PROXY_WHITELIST = PORTCULLIS_TRAEFIK_IP). Auto-creates users as Viewer role. Admin role requires manual promotion in Grafana. Access gated by group-gate.

## Access URLs

- **Dashboard**: `https://grafana.{{DOMAIN}}`
