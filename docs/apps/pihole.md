# 🚫 Pi-hole

> Network-wide ad blocking via DNS sinkhole (every member of the access group is a full Pi-hole admin; Pi-hole has no roles)

**Category:** networking  
**Tags:** `dns`, `adblock`, `privacy`, `filtering`

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_pihole` |
| **Admin Group** | `admin_pihole` |
| **Subdomain** | `pihole` |

!!! info "Auth Notes"
    No SSO in Pi-hole; Portcullis sign-in (forward-auth + group-gate) is the only login. Pi-hole's own password is off (FTLCONF_webserver_api_password empty), which upstream allows: with no password the API needs no session. Safe here because Pi-hole's web server ACL (FTLCONF_webserver_acl, https://docs.pi-hole.net/ftldns/configfile/#acl) only lets Traefik and the container itself connect: other containers on portcullis-proxy get 403, and Traefik serves the host only through the gateway. The DNS ports (53) are unaffected; Pi-hole serves no DNS-over-HTTPS. Consequences: every member of users_pihole is a full Pi-hole admin (Pi-hole has no roles). Without a password FTL (v6.8, src/api/auth.c check_client_auth) still refuses browser requests sent by other websites, sibling hosts on the same parent domain included (Sec-Fetch-Site / Origin), and requests whose Host is not one of its own names (DNS rebinding); FTLCONF_webserver_domain is therefore set to the instance's hostname at every start. The previous PIHOLE_WEBPASSWORD is no longer used. Upgrades: keep an image with FTL v6.8 or later (these no-password checks).

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `pihole` | `pihole.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `pihole` | `pihole/pihole:2026.10.1` | `sha256:30f803ad5dd6…` |

## Host Ports

Ports this app binds on the host. Collisions with other enabled apps block enable; each binding can be rebound or disabled from the Hub UI.

| Port | Protocol | Default | Container | Required | Notes |
|------|----------|---------|-----------|----------|-------|
| **DNS (TCP)** | `tcp` | `53` | `53` | :white_check_mark: | — |
| **DNS (UDP)** | `udp` | `53` | `53` | :white_check_mark: | — |

## Access URLs

- **Dashboard**: `https://{{HOST_PIHOLE}}/admin`
