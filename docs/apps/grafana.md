# 📊 Grafana

> Monitoring dashboards — protected by WebAuthn

**Category:** monitoring  
**Tags:** `monitoring`, `dashboards`, `metrics`  
**Website:** <https://grafana.com/oss/grafana/>  
**Source:** <https://github.com/grafana/grafana>  
**Minimum resources:** 512 MiB RAM

## About

<div class="app-long-description">
<p>Grafana builds dashboards and alerts from metrics, logs and traces in many data sources, such as Prometheus, Loki and SQL databases.</p>
<p>Portcullis signs people in and tells Grafana who they are and which role they have, set per group in the instance's settings. Dashboards can be shared publicly through share links when an admin lists them.</p>
<p>With AI support on, the official Grafana MCP server lets people's AI assistants search dashboards and query data with their own permissions.</p>
</div>

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

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Grafana signs people in by proxy auth: group-gate gates access and sends the user and their organization role; Grafana auto-creates users.</p>
<p><strong>Proxy auth:</strong> the <code>X-Forwarded-User</code> header is accepted only from Traefik (<code>GF_AUTH_PROXY_WHITELIST</code> = <code>PORTCULLIS_TRAEFIK_SOURCE</code>) and, while AI support is on, from the instance's <code>grafana-mcp</code> companion. Its trust network <code>mcp-trust</code> (internal, members <code>dashboards</code> and <code>grafana-mcp</code> only) is added by <code>trust.sh</code> at every start, read from Grafana's own interface, without the gateway, broadcast and Grafana's own address.</p>
<p><strong>Roles:</strong> each person's organization role (Viewer, Editor or Admin) comes from the instance's <strong>Role</strong> setting. group-gate sends it as <code>X-Forwarded-Attr-Grafana-Role</code> on every request and Grafana syncs it on every request (<code>GF_AUTH_PROXY_SYNC_TTL</code> 0).</p>
<ul>
<li>Members of the admin group are Admin by default, everyone else Viewer; other groups are set per group (privileged: only groups delegates can't steer).</li>
<li>A role changed in the Grafana UI is overwritten by the next request.</li>
<li>A request without the role header (the person's role can't be resolved, or group-gate can't read the Hub's attributes file) keeps the last synced role: Grafana doesn't fall back to Viewer, so remove a person from the instance's access group to take access away.</li>
</ul>
<p>Access gated by group-gate.</p>
</div>

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

## AI support

People's AI assistants can use this app as themselves through these MCP servers, once an admin switches AI support on in the app's **AI support** tab (see [AI support](../operations/ai.md)).

**Grafana** (`grafana`)

| Property | Value |
|----------|-------|
| **Endpoint** | `https://grafana.<domain>/mcp` |
| **Server** | a companion container (`grafana-mcp`), scaled to 0 while AI support is off |
| **Upstream** | official companion (the app project's own MCP server) |
| **Source** | <https://github.com/grafana/mcp-grafana> |
| **Identity mode** | identity headers (`identity_headers`): mcp-gate tells the companion who the person is, with a caller secret only it holds |
| **Modes** | read only, read and write (default read only) |
| **In "All my apps"** | :white_check_mark: |
| **MCP versions** | `2025-11-25`, `2025-06-18` |
| **Needs the person's confirmation** | `delete_*`, `alerting_rules_write`, `alerting_silences_write` |
| **Never offered** | `grafana_api_request`, `alerting_routing_write` |
| **Hidden in read-only mode** | `create_*`, `update_*`, `delete_*`, `*_write`, `add_activity_to_incident`, `install_plugin` |

Why this choice, and what to know: [AI support → Grafana](../operations/ai.md#ai-grafana).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `dashboards` | `grafana/grafana:13.3.0` | `sha256:488984b716c0…` |
| `grafana-mcp` | `grafana/mcp-grafana:2.2.0` | `sha256:697336440e34…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Role** | `enum` | per person | `next_request` | Grafana organization role. A person in several groups gets the highest; applied on their next request. Choices: `Viewer`, `Editor`, `Admin`. Default: `Viewer`. Preset for the admin group: `Admin`. Privileged: per-group values only from [groups delegates can't steer](../operations/groups.md#guarding-groups). |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `GRAFANA_ADMIN_PASSWORD` | Password of Grafana's built-in admin (never used for sign-in; basic auth and the login form are off) | `random` |
| `MCP_GRAFANA_SERVER_TOKEN` | Caller secret of the grafana-mcp AI companion (the gate sends it; mcp-grafana refuses every request without it) | `random` |

## Access URLs

- **Dashboard**: `https://{{HOST_GRAFANA}}`
