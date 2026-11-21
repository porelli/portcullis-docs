# 💬 Mattermost

> Team chat with channels, threads, file sharing and integrations (Team Edition)

**Category:** productivity  
**Tags:** `chat`, `messaging`, `team`, `collaboration`, `slack-alternative`  
**Website:** <https://mattermost.com/>  
**Source:** <https://github.com/mattermost/mattermost>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_mattermost` |
| **Subdomain** | `chat` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Mattermost Team Edition 12.0 behind Portcullis sign-in: the whole host is behind Portcullis sign-in + group-gate (<code>users_mattermost</code>), and Mattermost keeps its own accounts behind it, which an admin creates with <code>mmctl</code>.</p>
<p><strong>Why no SSO:</strong> Team Edition has no SSO that works with Portcullis. OpenID Connect (and Google / Entra ID / SAML / LDAP) need a paid license, and the free GitLab SSO provider reads a GitLab user API (numeric <code>id</code>, <code>username</code>), which Keycloak's userinfo doesn't serve (the Hub creates clients without custom mappers, and LLDAP users have no numeric id) and which can't restrict sign-in to a group.</p>
<p><strong>Accounts:</strong> self sign-up is off (no email sign-up, which also closes the first-account and invite-link sign-ups; no open server; locked in the System Console). Team Edition's System Console can't create accounts; an admin creates them with mmctl in local mode, in the container (Hub exec or the server shell):</p>
<ol>
<li><code>mmctl --local user create --username &lt;LLDAP username&gt; --email &lt;email&gt; --password &lt;random placeholder&gt;</code> (mmctl only takes the create password as an argument, so use a throwaway there);</li>
<li><code>mmctl --local user change-password &lt;username&gt;</code>, which prompts for the real initial password on stdin;</li>
<li>hand that password over out of band; the user changes it after signing in.</li>
</ol>
<ul>
<li>Local mode answers anyone who can run a process in the Mattermost container with full system-admin rights (no authentication); Hub exec into that container is admin access.</li>
<li>Give each account the person's LLDAP username, since Mattermost doesn't know who passed the gateway.</li>
<li>Team Edition can't lock usernames (<code>LockProfileFieldsForEmailUsers</code> is Enterprise-only), so users can rename themselves; Mattermost usernames are not an identity Portcullis vouches for.</li>
</ul>
<p><strong>Admins:</strong> no admin group: Mattermost can't map one (no SSO), so admins are made in Mattermost (by a system admin, e.g. <code>mmctl --local roles system-admin &lt;username&gt;</code>).</p>
<ul>
<li>The bootstrap system admin is <code>mmadmin-&lt;first 12 characters of MATTERMOST_ADMIN_SUFFIX&gt;</code> with the generated password <code>MATTERMOST_ADMIN_PASSWORD</code>, created once by the <code>mattermost-init</code> one-shot over the local-mode socket and pinned by its user ID in the data volume: <code>system_admin</code> is granted only to the account that run created, never to an account found by name.</li>
<li>If the bootstrap name later belongs to a different account (renamed and taken) or exists without the pinned ID, <code>mattermost-init</code> fails (the Hub reports the failed one-shot) and grants nothing; Mattermost itself keeps running (its image has no shell, so its healthcheck can't read the state file), and the account holding the name stays a plain user.</li>
<li>Change the bootstrap password after the first sign-in.</li>
</ul>
<p><strong>Off:</strong> GitLab SSO, personal access tokens and the plugin marketplace are off, and so are plugin uploads (server-side code from any system-admin session).</p>
<p><strong>Plugins:</strong> a pinned list (<code>plugins.py</code>, each a GitHub release asset checked against its SHA-256): freemium 2.0.0 (dy0gu/mattermost-plugin-freemium, hides Team Edition's upsell UI) and Matterpoll 1.9.2 (<code>/poll</code>). <code>mattermost-init</code> enables the pinned plugins. Bump a plugin by editing its version, URL and SHA-256 in <code>plugins.py</code> (Dependabot doesn't see them).</p>
<p><strong>Plugin signatures:</strong> Mattermost requires plugin signatures, and upstream doesn't sign these. So before every compose-managed start (what the Hub runs; a plain Docker restart reuses the last signatures, which is safe) the <code>mattermost-plugins</code> one-shot:</p>
<ul>
<li>checks a private copy of each bundle (in its root-only tmpfs; file-store copies are opened without following symlinks, regular files only) against its SHA-256 (a mismatch or a swapped file fails it before anything is signed, and Mattermost doesn't start);</li>
<li>signs that private copy with an OpenPGP key it generates in tmpfs for that start only (the private key never reaches a volume);</li>
<li>writes bundle + signature into Mattermost's file store (locked to the data volume) and only the public key to a volume Mattermost mounts read-only (<code>SignaturePublicKeyFiles</code>).</li>
</ul>
<p>Mattermost installs from the file store at startup, so any other bundle, unsigned or signed by another key, is refused. The public key is placed before the signatures, so an interrupted job leaves only signatures the new key doesn't verify (those plugins are refused until the next run). Mattermost's built-in key still accepts any Mattermost-signed bundle, old versions included, if something writes one into the file store's <code>plugins/</code> directory; that needs filesystem access to the data volume or local-mode access (both already full admin).</p>
<p><strong>SSO, re-checked:</strong> the free GitLab provider can't use Keycloak today. Team Edition switches to the licensed OpenID provider whenever the GitLab scope contains <code>openid</code>, while Keycloak's userinfo refuses tokens without the <code>openid</code> scope (&quot;Missing openid scope&quot;), and the provider needs a stable numeric <code>id</code> that no static Keycloak mapper can derive (LLDAP has no numeric attribute, Keycloak ids are UUIDs). It becomes possible once the Hub allocates a per-person numeric id (a user attribute mapped to <code>id</code>), plus mappers for username, which the Hub doesn't create yet.</p>
<p><strong>What doesn't work through the gateway:</strong> the Mattermost desktop and mobile apps and anything else that talks to the API directly (bots, incoming/outgoing webhooks, slash-command callbacks, personal or bot access tokens), because every request needs a Portcullis browser session first; use the web app.</p>
<p><strong>Networking:</strong> Mattermost is on the instance's private network only; the gate in front of it (nginx, <code>mattermost-gate</code>, the only container on <code>portcullis-proxy</code>) answers Traefik's address alone, so no other container can reach Mattermost past the gateway.</p>
<ul>
<li>The gate never forwards the Portcullis session (<code>Authorization</code>, access-token headers and the forward-auth cookies are removed) and passes the websocket through.</li>
<li>Mattermost takes the client address (logs, rate limits) from <code>X-Real-Ip</code>, which Traefik sets to the peer it accepted (client-sent copies are deleted) and the gate passes on unchanged.</li>
</ul>
<p><strong>Upgrades:</strong> follow Mattermost's upgrade path (extended support releases, one major at a time); don't bump the PostgreSQL major.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `mattermost` | `chat.<domain>` | all | `authaware@file` | :white_check_mark: |

## AI support

**No AI support:** The Agents plugin's MCP endpoint for AI clients needs a Mattermost Enterprise licence (this template runs Team Edition), and Team Edition lets people rename their accounts.

Why this choice, and what to know: [AI support → Mattermost](../operations/ai.md#ai-mattermost).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `mattermost` | `mattermost/mattermost-team-edition:12.0.2` | `sha256:0e435f339739…` |
| `mattermost-db` | `postgres:17.11-alpine` | `sha256:3540c0362c80…` |
| `mattermost-gate` | `nginx:1.31.8-alpine` | `sha256:fed7e14be83c…` |
| `mattermost-init` | `python:3.15.2-alpine` | `sha256:0f9552bb2871…` |
| `mattermost-plugins` | `python:3.15.2-trixie` | `sha256:2a01fe7b84cc…` |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `MATTERMOST_DB_PASSWORD` | Mattermost database password | `random` |
| `MATTERMOST_ADMIN_SUFFIX` | Random suffix of the bootstrap system admin's username (mmadmin-<first 12 characters>) | `random` |
| `MATTERMOST_ADMIN_PASSWORD` | Password of the bootstrap system admin | `random` |

## Access URLs

- **Chat**: `https://{{HOST_MATTERMOST}}`
