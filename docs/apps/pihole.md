# 🚫 Pi-hole

> Network-wide ad blocking via DNS sinkhole (every member of the access group is a full Pi-hole admin; Pi-hole has no roles)

**Category:** networking  
**Tags:** `dns`, `adblock`, `privacy`, `filtering`  
**Website:** <https://pi-hole.net/>  
**Source:** <https://github.com/pi-hole/pi-hole>  
**Minimum resources:** 512 MiB RAM, 2 GiB disk

## About

<div class="app-long-description">
<p>Pi-hole is a DNS sinkhole that blocks ads and trackers for every device on the network. It filters queries with blocklists and shows a query log and statistics.</p>
<p>Portcullis sign-in and the access group are the only login to the web interface. Pi-hole has no roles, so every member is a full administrator.</p>
</div>

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

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>No SSO in Pi-hole; Portcullis sign-in (forward-auth + group-gate) is the only login. Every member of <code>users_pihole</code> is a full Pi-hole admin (Pi-hole has no roles).</p>
<p><strong>No Pi-hole password:</strong> Pi-hole's own password is off (<code>FTLCONF_webserver_api_password</code> empty), which upstream allows: with no password the API needs no session. Safe here because Pi-hole's web server ACL (<code>FTLCONF_webserver_acl</code>, <a target="_blank" rel="noopener noreferrer nofollow" href="https://docs.pi-hole.net/ftldns/configfile/#acl">https://docs.pi-hole.net/ftldns/configfile/#acl</a>) only lets Traefik and the container itself connect: other containers on <code>portcullis-proxy</code> get 403, and Traefik serves the host only through the gateway.</p>
<ul>
<li>The DNS ports (53) are unaffected; Pi-hole serves no DNS-over-HTTPS.</li>
<li>Without a password FTL (v6.8, <code>src/api/auth.c</code> <code>check_client_auth</code>) still refuses browser requests sent by other websites, sibling hosts on the same parent domain included (<code>Sec-Fetch-Site</code> / <code>Origin</code>), and requests whose <code>Host</code> is not one of its own names (DNS rebinding). <code>FTLCONF_webserver_domain</code> is therefore set to the instance's hostname at every start.</li>
<li>The previous <code>PIHOLE_WEBPASSWORD</code> is no longer used.</li>
</ul>
<p><strong>Upgrades:</strong> keep an image with FTL v6.8 or later (these no-password checks).</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `pihole` | `pihole.<domain>` | all | `authaware@file` | :white_check_mark: |

## AI support

**No AI support:** No MCP server known, and every member of the access group is a full administrator of the app (no per-person rights to act with).

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
