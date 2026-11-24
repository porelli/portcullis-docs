# 🗂 OxiCloud

> Lightweight self-hosted file storage and sync with WebDAV, CalDAV and CardDAV

**Category:** productivity  
**Tags:** `files`, `storage`, `sync`, `webdav`, `caldav`, `carddav`, `rust`  
**Website:** <https://atalayalabs.github.io/OxiCloud/>  
**Source:** <https://github.com/AtalayaLabs/OxiCloud>

## About

<div class="app-long-description">
<p>OxiCloud is a lightweight file storage and sync server written in Rust. It stores and shares files in the browser and serves them over WebDAV, with calendars over CalDAV and contacts over CardDAV.</p>
<p>Portcullis signs people in through OpenID Connect, its only login, limited to the access group.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :white_check_mark: |
| **Access Group** | `users_oxicloud` |
| **Admin Group** | `admin_oxicloud` |
| **Subdomain** | `drive` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Native OpenID Connect (OxiCloud 0.10.0) and nothing else: the login page redirects straight to Portcullis, and only members of the access group can sign in.</p>
<p><strong>OIDC only:</strong> <code>OXICLOUD_AUTH_METHODS=oidc</code> turns password login, sign-up and the OPAQUE endpoints off, and OIDC hard-disables magic links.</p>
<p><strong>Who can sign in:</strong> OxiCloud has no OIDC group restriction of its own, so the authorize endpoint (<code>/api/auth/oidc/authorize</code>, which mints the login state the callback requires) is behind Portcullis sign-in + group-gate (<code>access_group</code>), and the Hub's Keycloak access role restricts the client to <code>access_group</code> as well.</p>
<p><strong>Identity:</strong> accounts are created on the first SSO login and keyed on the OIDC issuer + <code>sub</code>; the OxiCloud username is the LLDAP username (<code>preferred_username</code>, lowercased; OxiCloud appends a suffix if it is taken). SSO logins are never linked to existing accounts by email (<code>OXICLOUD_OIDC_AUTO_LINK_EMAIL_MATCH=false</code>); a login whose email matches another account is refused instead, so two LLDAP users with the same email can't both sign in.</p>
<p><strong>Admins and owner:</strong></p>
<ul>
<li><code>admin_oxicloud</code> members become OxiCloud admins when their account is created (first login); OxiCloud does not re-evaluate the role later, so promote or demote existing users in its admin panel.</li>
<li>Nobody is the instance owner (OxiCloud never derives ownership from an IdP); an operator can name one with <code>oxicloud user promote-to-owner &lt;username&gt;</code> in the container.</li>
<li>The first-run setup endpoint (<code>POST /api/setup</code>, a password owner account for whoever calls it first) is closed by the <code>oxicloud-init</code> one-shot before OxiCloud starts (it marks the instance initialized), and the app is routed only while it reports itself initialized.</li>
</ul>
<p><strong>Sessions:</strong> Keycloak calls OxiCloud's back-channel logout (<code>/api/auth/oidc/backchannel-logout</code>) whenever a Keycloak session ends; the Hub signs a user out of Keycloak when they leave the group, so their OxiCloud sessions (7 d rotating refresh tokens) are revoked then. What remains until it expires or is revoked in OxiCloud: an access token already issued (at most 1 h) and app passwords (WebDAV/CalDAV/CardDAV, no expiry); deactivate the user in OxiCloud to cut those.</p>
<p><strong>Device sign-in</strong> (RFC 8628, <code>/api/auth/device</code>) is approved by a signed-in user: a member can be tricked into approving a code an outsider started, which signs the outsider in as that member (approve only codes you started).</p>
<p><strong>Public share links</strong> (<code>/api/s/{token}</code>, the share page and its assets) are answered by OxiCloud without Portcullis sign-in by design: the host router has no forward-auth (native OIDC). On a host whose policy requires a client certificate they are refused at the TLS layer like everything else; this template declares no <code>auth.public_access</code>, so no exception can be opened for them there.</p>
<p><strong>Clients:</strong> WebDAV, CalDAV and CardDAV clients use app passwords (created by the signed-in user under Settings); the Nextcloud-compatible API for Nextcloud desktop/mobile apps is off (it would add another login flow).</p>
<p><strong>Upgrades:</strong> read the OxiCloud release notes; don't bump the PostgreSQL major.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `oxicloud` | `drive.<domain>` | all | `default` | :x: |
| `oxicloud-sso` | `drive.<domain>` | `/api/auth/oidc/authorize` | `default` | :white_check_mark: |

## AI support

**No AI support:** No official or vetted community MCP server known (surveyed 2026-11-05).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `oxicloud` | `diocrafts/oxicloud:0.10.0` | `sha256:ef5174909d03…` |
| `oxicloud-db` | `postgres:17.11-alpine` | `sha256:3540c0362c80…` |
| `oxicloud-init` | `postgres:17.11-alpine` | `sha256:3540c0362c80…` |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `OXICLOUD_DB_PASSWORD` | OxiCloud database password | `random` |
| `OXICLOUD_JWT_SECRET` | OxiCloud session token signing key | `random` |
| `OXICLOUD_OIDC_SECRET` | OxiCloud OIDC client secret | `random` |

## Keycloak Clients

**OxiCloud** (`oxicloud`)

Redirect URI: `https://{{HOST_OXICLOUD}}/api/auth/oidc/callback`

## Access URLs

- **Files**: `https://{{HOST_OXICLOUD}}`
