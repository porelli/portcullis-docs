# 💬 Matrix (Synapse + Element)

> Self-hosted Matrix chat server (Synapse) with the Element web client

**Category:** communication  
**Tags:** `chat`, `matrix`, `synapse`, `element`, `messaging`, `e2ee`  
**Website:** <https://element-hq.github.io/synapse/>  
**Source:** <https://github.com/element-hq/synapse>

## About

<div class="app-long-description">
<p>Matrix is an open standard for secure, decentralised chat. This template runs Synapse, the reference homeserver, and Element Web, its browser client: rooms, direct messages, end-to-end encryption and file sharing.</p>
<p>Portcullis signs people in through OpenID Connect, and only members of the access group get an account. Federation with other servers is off unless an admin lists peers.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_matrix` |
| **Admin Group** | `admin_matrix` |
| **Admin Paths** | `/_synapse/admin` (require `admin_matrix` in addition to access) |
| **Subdomain** | `element`, `matrix` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>A Matrix homeserver (Synapse) with Element Web. Only members of <code>users_matrix</code> get an account; federation is off unless the admin lists peers.</p>
<p><strong>Two hosts per instance:</strong></p>
<ul>
<li>The homeserver (<code>matrix.&lt;domain&gt;</code>, Synapse) does its own OIDC login against Keycloak and has no forward-auth, so Element, the Element mobile apps and other Matrix clients and bots reach the client API directly. Synapse only lets in users whose <code>groups</code> claim contains <code>users_matrix</code> (oidc <code>attribute_requirements</code>): outsiders get no account and no session.</li>
<li>Element Web (<code>element.&lt;domain&gt;</code>) is a static client behind forward-auth + group-gate, so only members even get the page; it is fixed to this homeserver (no server picker) and redirects straight to SSO. It is the one native-OIDC host router behind forward-auth (<code>validate.py</code> <code>GATED_CLIENT_ROUTERS</code>): a static client with no login of its own and no server data.</li>
</ul>
<p><strong>Revoking access:</strong> Synapse checks the group only at the SSO login, so a user removed from <code>users_matrix</code> (or disabled in LLDAP) keeps the sessions they already have; every session expires after 7 days (<code>session_lifetime</code>) and must sign in again through the group-checked login. To cut a user off at once, deactivate them through the Admin API from inside the synapse container (<code>POST /_synapse/admin/v1/deactivate/&lt;user id&gt;</code> with an admin access token) or log out their devices (<code>DELETE /_synapse/admin/v2/users/&lt;user id&gt;/devices/&lt;device id&gt;</code>).</p>
<p><strong>Identity:</strong> accounts are keyed on the OIDC <code>sub</code>; the Matrix id is <code>@&lt;LLDAP username&gt;:&lt;homeserver host&gt;</code> (<code>localpart_template</code> <code>preferred_username</code>).</p>
<ul>
<li><code>allow_existing_users</code> is false, so an SSO login is never attached to an existing account, and the email is not imported.</li>
<li>No password login (<code>password_config.enabled</code> false), no open registration, no 3PID changes.</li>
<li>A reused LLDAP username (new Keycloak <code>sub</code>) gets a new id with a numeric suffix, never the old account.</li>
</ul>
<p><strong><code>server_name</code></strong> is the homeserver's hostname, so no <code>.well-known</code> on the apex is needed (Synapse serves <code>/.well-known/matrix/client</code> itself). It is permanent: every user and room id contains it.</p>
<ul>
<li>Synapse refuses to start if the instance's homeserver hostname changes after the first start; pick it when creating the instance (<code>hosts.immutable</code>: the Hub refuses to change it once the instance exists; the Element host can change any time).</li>
<li>The default instance's homeserver host is <code>matrix.&lt;main domain&gt;</code>: changing Portcullis's main domain breaks it.</li>
<li>A backup restores into the same instance only, never a new id.</li>
</ul>
<p><strong>Admins:</strong> Synapse has no group-to-admin mapping, so <code>admin_matrix</code> grants nothing inside Synapse.</p>
<ul>
<li>Promote the first admin after their first SSO login with <code>UPDATE users SET admin = 1 WHERE name = '@alice:&lt;homeserver host&gt;';</code> in the <code>matrix-db</code> container (<code>psql -U synapse -d synapse</code>), then restart the synapse container; later admins via the Admin API (<code>PUT /_synapse/admin/v2/users/&lt;user id&gt;</code> <code>{&quot;admin&quot;: true}</code>).</li>
<li>The Admin API (<code>/_synapse/admin</code>, including shared-secret registration) is additionally behind forward-auth + group-gate and requires <code>admin_matrix</code> (<code>auth.admin_paths</code>), so call it from a browser session of an <code>admin_matrix</code> member or from inside the synapse container (<code>curl http://localhost:8008/_synapse/admin/...</code> with an admin access token, Element: Settings, Help &amp; About).</li>
</ul>
<p><strong>Federation</strong> is off: <code>federation_domain_whitelist</code> is <code>[]</code> and the listener serves no federation resource. To federate with specific servers, list their server names in the <strong>Federation peers</strong> setting: Synapse then serves the federation API and <code>/.well-known/matrix/server</code> on the homeserver host (port 443) and federates with those servers only. Open federation is not offered.</p>
<p><strong>Secrets</strong> (database, OIDC, registration shared secret, macaroon and form secrets) are generated per instance; the config is rendered at every start into a tmpfs. The server signing key is created once in the <code>synapse-data</code> volume (back it up with the volume: losing it breaks federation and other servers' trust).</p>
<p>Synapse trusts <code>X-Forwarded-For</code> from any peer on <code>portcullis-proxy</code> (client IPs in logs and rate limits only).</p>
<p><strong>Upgrades:</strong> Synapse supports rolling upgrades between releases but read <code>docs/upgrade.md</code> for each step; keep <code>matrix-db</code> on PostgreSQL 16. Element Web is independent of the Synapse version.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `element` | `element.<domain>` | all | `default` | :white_check_mark: |
| `matrix` | `matrix.<domain>` | all | `default` | :x: |
| `matrix-admin` | `matrix.<domain>` | `/_synapse/admin` | `default` | :white_check_mark: |

## AI support

**No AI support:** No official or vetted community MCP server known (surveyed 2026-11-05).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `element` | `vectorim/element-web:v1.12.33` | `sha256:b0aa4b5a4fc1…` |
| `matrix-db` | `postgres:16.15-alpine` | `sha256:aa6cb33cf4c1…` |
| `synapse` | `ghcr.io/element-hq/synapse:v1.164.2` | `sha256:f0df87cff259…` |
| `synapse-init` | `ghcr.io/element-hq/synapse:v1.164.2` | `sha256:f0df87cff259…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Federation peers** | `list` of `string` | instance | `restart` | Matrix server names this homeserver may federate with (e.g. matrix.example.org). Empty = federation off (default). |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `MATRIX_DB_PASSWORD` | Synapse PostgreSQL password | `random` |
| `MATRIX_OIDC_SECRET` | Synapse OIDC client secret | `random` |
| `SYNAPSE_REGISTRATION_SECRET` | Synapse registration_shared_secret (Admin API break-glass registration) | `random` |
| `SYNAPSE_MACAROON_SECRET` | Synapse macaroon_secret_key (signs access and login tokens) | `random` |
| `SYNAPSE_FORM_SECRET` | Synapse form_secret (signs consent and SSO forms) | `random` |

## Keycloak Clients

**Matrix (Synapse)** (`matrix`)

Redirect URI: `https://{{HOST_MATRIX}}/_synapse/client/oidc/callback`

## Access URLs

- **Element**: `https://{{HOST_ELEMENT}}`
- **Homeserver**: `https://{{HOST_MATRIX}}`
