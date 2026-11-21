# 📝 DokuWiki

> Simple, file-based wiki — no database required, easy backups

**Category:** productivity  
**Tags:** `wiki`, `docs`, `knowledge-base`, `file-based`  
**Website:** <https://www.dokuwiki.org/>  
**Source:** <https://github.com/dokuwiki/dokuwiki>

## About

<div class="app-long-description">
<p>DokuWiki is a wiki that stores its pages as plain text files instead of in a database, so backups and moves are simple file copies. It has page history, access control lists and a large plugin collection.</p>
<p>Portcullis signs people in through OpenID Connect. Members of the access group can read, edit and upload; members of the admin group are DokuWiki superusers.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :white_check_mark: |
| **Access Group** | `users_dokuwiki` |
| **Admin Group** | `admin_dokuwiki` |
| **Subdomain** | `dokuwiki` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Native OIDC through the oauth + oauthgeneric plugins: the login page only offers the Portcullis button. Members of <code>users_dokuwiki</code> read, edit and upload; members of <code>admin_dokuwiki</code> are superusers (they must be in both groups).</p>
<p><strong>Plugins:</strong> oauth and oauthgeneric (<a target="_blank" rel="noopener noreferrer nofollow" href="https://www.dokuwiki.org/plugin:oauth">https://www.dokuwiki.org/plugin:oauth</a>, <a target="_blank" rel="noopener noreferrer nofollow" href="https://www.dokuwiki.org/plugin:oauthgeneric">https://www.dokuwiki.org/plugin:oauthgeneric</a>; maintained by CosmoCode, DokuWiki's authors), vendored in the template (<code>dokuwiki/plugins</code>, see <code>VENDORED</code>; no download at start) and configured by <code>init.sh</code> at every start (<code>conf/local.protected.php</code>, which the admin UI can't override).</p>
<p><strong>Fail closed:</strong> <code>init.sh</code> first locks the wiki down (<code>install.php</code> deleted, no auth backend so DokuWiki grants nothing, login disabled) and only its last step writes the OIDC configuration, so a failed start leaves a wiki that nobody can read or sign in to (the container log says why).</p>
<p><strong>Why not header auth:</strong> the header plugins in the DokuWiki repository (authserversso, genericsso, authremoteuser, authenvvars) read a server variable from any client, have no proxy allowlist, map no groups and are barely maintained (<a target="_blank" rel="noopener noreferrer nofollow" href="https://www.dokuwiki.org/plugins?pluginsort=p&amp;plugintype=128">https://www.dokuwiki.org/plugins?pluginsort=p&amp;plugintype=128</a>).</p>
<p><strong>Identity:</strong> the oauth plugin finds accounts by their email, and LLDAP emails are user-editable, so <code>init.sh</code> maps the plugin's mail field to <code>preferred_username</code> (the immutable LLDAP username) and disables profile edits; the account name is the username too. DokuWiki therefore has no real email addresses (no subscription mails).</p>
<p><strong>Rights:</strong></p>
<ul>
<li>Anonymous visitors get nothing (ACL <code>* @ALL 0</code>, re-applied at every start together with <code>* @users_dokuwiki 8</code>; rules for <code>@ALL</code>, <code>@user</code> and <code>@generic</code> are replaced, others kept).</li>
<li>Members of <code>users_dokuwiki</code> read, edit and upload, and members of <code>admin_dokuwiki</code> are superusers.</li>
<li>Groups follow the <code>groups</code> claim at each login (overwrite-groups); a realm user outside <code>access_group</code> can't sign in (Keycloak denies it, see below) and would get no rights anyway. Removing a user from the groups takes effect at their next login.</li>
<li>Sign-in is restricted to <code>access_group</code> in Keycloak (<code>keycloak_access_role</code>, contract §8 Access role): only <code>access_group</code> members can sign in, so a member of <code>admin_group</code> who is not also in <code>access_group</code> is denied — put the wiki's admins in both groups.</li>
</ul>
<p><strong>Break-glass:</strong> there is no password form (<code>singleService</code>). With shell access, add a local user with <code>bin/plugin.php usermanager</code> and set <code>singleService</code> to 0 in <code>conf/local.protected.php</code> (until the next restart).</p>
<p><strong>Hostname:</strong> <code>init.sh</code> writes <code>baseurl</code> from the instance's hostname at every start, so a hostname change only needs a restart. <code>install.php</code> is deleted at every start (the configuration is written by <code>init.sh</code>).</p>
<p>Existing local accounts keep their pages but can't sign in with a password; an LLDAP user whose name is taken by a local account gets a numbered account name (e.g. <code>admin1</code>).</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `dokuwiki` | `dokuwiki.<domain>` | all | `authaware@file` | :x: |

## AI support

**No AI support:** No official or vetted community MCP server known (surveyed 2026-11-05).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `dokuwiki` | `linuxserver/dokuwiki:2026-07-14c-ls332` | `sha256:fac142ae9f7d…` |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `DOKUWIKI_OIDC_SECRET` | DokuWiki OIDC client secret | `random` |

## Keycloak Clients

**DokuWiki** (`dokuwiki`)

Redirect URI: `https://{{HOST_DOKUWIKI}}/doku.php`

## Access URLs

- **Wiki**: `https://{{HOST_DOKUWIKI}}`
