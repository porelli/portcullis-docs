# ✅ Vikunja

![Vikunja logo](logos/vikunja.svg){ width="64" height="64" }

<p class="app-logo-credit"><small>Logo: © 2018-present Vikunja and contributors, <code>AGPL-3.0-or-later</code>, <a href="https://github.com/go-vikunja/vikunja/blob/5b9d4fcc720fe65548ab6c3f7c974c12b28d13af/frontend/originalMedia/images/logo.svg" target="_blank" rel="noopener noreferrer nofollow">source</a>. Shown only to identify the app; any trademark stays its owner's.</small></p>

> Self-hosted to-do lists, kanban boards and project planning

**Category:** productivity  
**Tags:** `tasks`, `todo`, `kanban`, `projects`, `caldav`  
**Website:** <https://vikunja.io/>  
**Source:** <https://github.com/go-vikunja/vikunja>

## About

<div class="app-long-description">
<p>Vikunja is a to-do and project planning app. Tasks live in projects, and each project can be viewed as a list, a Kanban board, a table or a Gantt chart. Tasks have labels, due dates, reminders and assignees.</p>
<p>Portcullis signs people in through OpenID Connect, limited to the access group. Every person is a regular user.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_vikunja` |
| **Subdomain** | `tasks` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Native OIDC (Vikunja v2.7.1): the login page redirects straight to Portcullis, and only members of <code>users_vikunja</code> may sign in. Every SSO user is a regular user.</p>
<p><strong>No local accounts:</strong> local accounts are off (<code>auth.local.enabled</code> false), so Vikunja registers no password login, sign-up, password reset or invite link route at all, and LDAP is off.</p>
<p><strong>Who may sign in:</strong> Vikunja has no OIDC group restriction of its own, so the Hub enforces <code>users_vikunja</code> in Keycloak (<code>keycloak_access_role</code>: the client's access role and browser flow; direct grants and the other non-browser grants are off on the client).</p>
<p><strong>Identity:</strong> accounts are created on the first SSO login, keyed on the OIDC issuer + <code>sub</code> and named after <code>preferred_username</code> (the LLDAP username; Vikunja picks a random one if that name is taken); they are never linked to an existing account by email or username (<code>emailfallback</code> / <code>usernamefallback</code> false). Users need an email in LLDAP (Vikunja requires the claim; it is display/notification only).</p>
<p><strong>Admins and teams:</strong></p>
<ul>
<li>Every SSO user is a regular user: Vikunja's instance admin is a paid feature (admin panel license) set only with the CLI, so <code>admin_vikunja</code> is not used.</li>
<li>Team sync: Vikunja reads teams only from a custom <code>vikunja_groups</code> claim (objects with <code>name</code> and <code>oidcID</code>), which the Hub's Keycloak clients don't send; teams are managed in Vikunja.</li>
</ul>
<p><strong>Tokens and sharing:</strong></p>
<ul>
<li>CalDAV and the API take Vikunja's own CalDAV / API tokens (created by a signed-in user), never a password.</li>
<li>Public project links are off unless <strong>Link sharing</strong> is turned on.</li>
<li>Outgoing requests to URLs users enter (webhooks, imports, avatars) may not reach private addresses.</li>
</ul>
<p><strong>Revoking access:</strong> removing a user from the group blocks new sign-ins (and the Hub signs them out of Keycloak), not Vikunja sessions or API / CalDAV tokens already issued. Refresh sessions end after 24 h without use (<code>VIKUNJA_SERVICE_JWTTTL</code>, upstream 72 h / 30 days); an active one keeps refreshing. Disable the user in Vikunja to end it, effective within 10 min (<code>vikunja user change-status</code>).</p>
<p>Mobile and desktop apps sign in through Vikunja's own OAuth flow in the browser, i.e. through Portcullis.</p>
<p><strong>Upgrades:</strong> database migrations run when Vikunja starts; don't bump the PostgreSQL major.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `vikunja` | `tasks.<domain>` | all | `default` | :x: |

## AI support

**No AI support:** No official MCP server; community servers are not vetted by Portcullis.

An alternative **not vetted by Portcullis**, for an admin to evaluate on their own: democratize-technology/vikunja-mcp (<https://github.com/democratize-technology/vikunja-mcp>) — community, 113★, API token (surveyed 2026-11-06). Portcullis never installs it.

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `vikunja` | `vikunja/vikunja:2.7.1` | `sha256:f7dc8428d10a…` |
| `vikunja-db` | `postgres:17.12-alpine` | `sha256:f9cf3e1f0066…` |
| `vikunja-perms` | `postgres:17.12-alpine` | `sha256:f9cf3e1f0066…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Link sharing** | `bool` | instance | `restart` | Let users share a project through a public link (anyone with the link, optionally a password, gets the rights the link grants; no Portcullis sign-in). Default: `false`. |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `VIKUNJA_DB_PASSWORD` | Vikunja database password | `random` |
| `VIKUNJA_SECRET` | Vikunja service secret (signs session tokens) | `random` |
| `VIKUNJA_OIDC_SECRET` | Vikunja OIDC client secret | `random` |

## Keycloak Clients

**Vikunja** (`vikunja`)

Redirect URIs:

- `https://{{HOST_VIKUNJA}}/auth/openid/portcullis`

## Access URLs

- **Tasks**: `https://{{HOST_VIKUNJA}}`
