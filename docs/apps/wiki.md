# 📖 Wiki.js

> Modern wiki with Portcullis sign-in (OpenID Connect) and group-based rights

**Category:** productivity  
**Tags:** `wiki`, `docs`, `knowledge-base`  
**Website:** <https://js.wiki/>  
**Source:** <https://github.com/requarks/wiki>  
**Minimum resources:** 1 GiB RAM

## About

<div class="app-long-description">
<p>Wiki.js is a wiki with a visual editor and a Markdown editor, page history, full-text search and fine-grained permissions.</p>
<p>Portcullis signs people in through OpenID Connect, with no password login. Members of the access group are editors, and members of the admin group are Wiki.js administrators.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :white_check_mark: |
| **Access Group** | `users_wiki` |
| **Admin Group** | `admin_wiki` |
| **Subdomain** | `wiki` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Native OIDC through Wiki.js' generic OpenID Connect strategy: the login page offers only &quot;Portcullis&quot;, and there is no password login. Rights come only from the groups <code>users_wiki</code> (editors) and <code>admin_wiki</code>; put the wiki's admins in both groups.</p>
<p><strong>Setup:</strong> the strategy (key <code>portcullis</code>) is configured by the <code>wiki-setup</code> sidecar at every start over the internal network (GraphQL, with its own API key kept in the <code>wiki-setup-data</code> volume).</p>
<p><strong>No password login:</strong> the sidecar disables the local strategy (and its self-registration), so the internet-facing GraphQL login and register mutations refuse local accounts. Traefik only routes the wiki while its healthcheck passes, which needs the Portcullis strategy enabled and the local one disabled: the setup wizard of a fresh install, and a re-enabled local login, get 404 from Traefik.</p>
<p><strong>Identity:</strong> Wiki.js keys accounts on the OIDC subject (the Keycloak id of the LLDAP user, never the email; Wiki.js has no username-claim option). It requires an email claim and keeps emails unique per strategy, so an account's email is only profile data, but:</p>
<ul>
<li>it would link a login to a user an admin pre-created for this strategy with the same email (never pre-create users for the Portcullis strategy);</li>
<li>a user who sets their LLDAP email to another user's address makes the later login of whichever of them is second fail (denial of service, no takeover; fix the email in LLDAP).</li>
</ul>
<p><strong>Rights</strong> come only from groups: new accounts get no group, and at each login Wiki.js sets the user's membership of the Wiki.js groups <code>users_wiki</code> (editors, created once; adjust its rights in Wiki.js) and <code>admin_wiki</code> (<code>manage:system</code>, re-applied every start) from the <code>groups</code> claim.</p>
<ul>
<li>A realm user outside <code>access_group</code> can't sign in (Keycloak denies it, see below) and would have no rights anyway.</li>
<li>The Guests group has no permissions (re-applied before every boot by <code>wiki-init</code> and by the sidecar), so nothing is readable anonymously.</li>
<li>Removing a user from the groups takes effect at their next login (Wiki.js sessions last up to 14 days).</li>
<li>Sign-in is restricted to <code>access_group</code> in Keycloak (<code>keycloak_access_role</code>, contract §8 Access role): only <code>access_group</code> members can sign in, so a member of <code>admin_group</code> who is not also in <code>access_group</code> is denied — put the wiki's admins in both groups.</li>
</ul>
<p><strong>Break-glass, on the server only:</strong></p>
<ol>
<li><code>docker compose -p portcullis-&lt;instance&gt; exec wiki-db psql -U wiki -d wiki -c &quot;UPDATE authentication SET \&quot;isEnabled\&quot; = true WHERE key = 'local'&quot;</code></li>
<li>restart the wiki container;</li>
<li>open Wiki.js directly on its container address (e.g. an SSH tunnel to <code>&lt;container ip&gt;:3000</code>; Traefik serves 404 meanwhile) and sign in as <code>admin@wiki.invalid</code> with <code>WIKI_ADMIN_PASSWORD</code>.</li>
</ol>
<p>The next start of the app (Hub) disables the local login again.</p>
<p><strong>Existing installs:</strong> local accounts can no longer sign in; reset or remove them in <strong>Administration &gt; Users</strong> (as an SSO admin) since their passwords stay valid if the local login is ever re-enabled. If the sidecar has neither its API key nor the local admin <code>admin@wiki.invalid</code> / <code>WIKI_ADMIN_PASSWORD</code> (installs whose first admin had another email), it can't configure anything and the wiki stays unrouted: create that local admin through the break-glass steps and restart.</p>
<p><strong>Hostname:</strong> <code>wiki-init</code> writes the site URL from the instance's hostname before Wiki.js boots, so a hostname change only needs a restart.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `wiki` | `wiki.<domain>` | all | `default` | :x: |

## AI support

**No AI support:** No official or vetted community MCP server known (surveyed 2026-11-05).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `wiki` | `requarks/wiki:2.5.317` | `sha256:e4708eed80c0…` |
| `wiki-db` | `postgres:16.16-alpine` | `sha256:f2f98726820d…` |
| `wiki-init` | `postgres:16.16-alpine` | `sha256:f2f98726820d…` |
| `wiki-setup` | `python:3.15.2-alpine` | `sha256:0f9552bb2871…` |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `WIKI_DB_PASSWORD` | Wiki.js database password | `random` |
| `WIKI_ADMIN_PASSWORD` | Password of the local Wiki.js admin admin@wiki.invalid (its login is off; break-glass only) | `random` |
| `WIKI_OIDC_SECRET` | Wiki.js OIDC client secret | `random` |

## Keycloak Clients

**Wiki.js** (`wiki`)

Redirect URI: `https://{{HOST_WIKI}}/login/portcullis/callback`

## Access URLs

- **Wiki**: `https://{{HOST_WIKI}}`
