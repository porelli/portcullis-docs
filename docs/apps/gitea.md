# 🍵 Gitea

> Lightweight self-hosted Git forge — repositories, issues, pull requests, packages

**Category:** devops  
**Tags:** `git`, `forge`, `code-review`, `issues`, `packages`  
**Website:** <https://about.gitea.com/>  
**Source:** <https://github.com/go-gitea/gitea>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :white_check_mark: |
| **Access Group** | `users_gitea` |
| **Admin Group** | `admin_gitea` |
| **Subdomain** | `gitea` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Native OIDC: the login page goes straight to Portcullis, and only members of <code>users_gitea</code> can sign in; members of <code>admin_gitea</code> are site admins. Nothing is readable without signing in.</p>
<p><strong>The authentication source:</strong> a Gitea OAuth2 authentication source (&quot;Portcullis&quot;) that the <code>gitea-auth</code> job writes into Gitea's database at every start (client id, secret, discovery URL, groups), so a hostname, client or group change only needs a restart.</p>
<ul>
<li>Gitea loads the client id, secret and discovery URL when it starts, so a changed client secret takes effect once the <code>gitea</code> container itself restarts (rerunning the job is not enough); the required group and the admin group are read at every login.</li>
<li>The client secret never appears on a command line: Gitea's CLI only takes it as an argument, so the job uses <code>psql</code> with the values read from its environment.</li>
</ul>
<p><strong>No other way in:</strong> there is no password sign-in form (<code>POST /user/login</code> answers 403), no sign-up form, no passkey or OpenID 2.0 sign-in, no HTTP basic authentication with a password and no reverse-proxy header auth. Nothing is readable without signing in (<code>REQUIRE_SIGNIN_VIEW</code>). Any other authentication source added in the admin panel is switched off at the next start.</p>
<p><strong>Access and admin:</strong></p>
<ul>
<li>Gitea refuses the login (&quot;Sign-in prohibited&quot;) unless the <code>groups</code> claim contains <code>users_gitea</code>, checked at every login.</li>
<li>Gitea sets or clears the site-admin flag from <code>admin_gitea</code> at every login (an admin must also be in <code>users_gitea</code>).</li>
<li>Everyone else is a regular user (the least-privileged full account; Gitea's &quot;restricted&quot; users can't see public repositories, so that role is left to admins).</li>
<li>Removing a user from <code>users_gitea</code> blocks new logins only: open sessions, personal access tokens and SSH keys keep working (the AI tokens Portcullis minted are deleted); disable the user in Site Administration to cut access at once.</li>
</ul>
<p><strong>Identity:</strong> accounts are created on the first Portcullis login, named after <code>preferred_username</code> (the immutable LLDAP username, not renameable in Gitea) and keyed on the OIDC <code>sub</code>. <code>ACCOUNT_LINKING</code> is disabled, so a login is never attached to an existing account by name or email (LLDAP emails are user-editable); a clash with an existing username or email is refused (an error page, no takeover). The email is only taken at account creation and kept private by default.</p>
<p><strong>Break-glass admin:</strong> Gitea makes the first account it creates a site admin and never demotes the last admin, so <code>gitea-migrate</code> creates the local admin <code>portcullis-breakglass</code> before anyone signs in (random password, never printed or stored) and <code>gitea-auth</code> keeps it admin with sign-in prohibited; Gitea won't start without it. To recover admin rights on the server, add a user to <code>admin_gitea</code> in LLDAP, or run:</p>
<pre><code>docker compose -p portcullis-&lt;instance&gt; exec gitea-db psql -U gitea -d gitea -c &quot;UPDATE \&quot;user\&quot; SET is_admin = true WHERE lower_name = '&lt;username&gt;'&quot;
</code></pre>
<p><strong>AI support</strong> (off until the admin turns it on): the official gitea-mcp server runs as the companion. Every request runs as the person, with a Gitea access token named <code>portcullis-ai-&lt;random&gt;</code> that the Hub mints on their first AI request (read-only mode: read scopes only, and gitea-mcp hides its write tools) and deletes when they leave the instance's population, when AI support or its mode changes and after a restore. A person who never signed in to Gitea gets no token.</p>
<ul>
<li>The hooks (<code>portcullis/mcp-token.sh</code>) list and delete tokens through Gitea's API as <code>portcullis-hooks</code>, a second local admin that <code>gitea-migrate</code> creates and <code>gitea-auth</code> keeps active: it has a discarded random password and no way in but an access token minted inside the container, one per hook run, deleted by that run. It never runs AI requests. Deleting it breaks AI support until the next start recreates it.</li>
<li><strong>Re-used usernames:</strong> the Hub sends the person's Keycloak id with every mint and the hook mints only for the Gitea account Gitea signs that id in to. If a person is deleted and their username given to someone new, the newcomer gets no token for the former person's account (the mint fails, shown on the AI tab; their web sign-in is refused as well): delete or rename the former person's Gitea account (<strong>Site Administration &gt; User Accounts</strong>), then the newcomer signs in once.</li>
<li><strong>File writes:</strong> <code>create_or_update_file</code> can also delete files in the same commit (<code>files[].delete</code>) without a confirmation; the deletion is an ordinary commit, recoverable from the repository's history.</li>
<li>While AI support is on, <code>https://&lt;host&gt;/mcp</code> is the AI endpoint, so a Gitea user or organization named <code>mcp</code> loses its profile page (its repositories stay reachable): don't use that name.</li>
</ul>
<p><strong>Git over HTTPS:</strong> clone <code>https://&lt;host&gt;/&lt;owner&gt;/&lt;repo&gt;.git</code> with your username and a personal access token (<strong>User Settings &gt; Applications</strong>) as the password; git-credential-manager / git-credential-oauth can use Gitea's own OAuth2 provider instead.</p>
<p><strong>Git over SSH</strong> is off by default: turn on the <strong>Git over SSH</strong> setting and keep the SSH host port (default 2222, Gitea's built-in SSH server, keys from <strong>User Settings &gt; SSH Keys</strong>); every instance needs its own host port.</p>
<p>Webhooks and migrations to private addresses stay blocked (Gitea's defaults).</p>
<p><strong>Upgrades:</strong> the image is pinned; Gitea migrates its database on start and supports upgrading from older releases directly, but read the release notes of each major (28.x) before bumping. Keep <code>gitea</code> and <code>gitea-migrate</code> on the same image.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `gitea` | `gitea.<domain>` | all | `authaware@file` | :x: |

## AI support

People's AI assistants can use this app as themselves through these MCP servers, once an admin switches AI support on in the app's **AI support** tab (see [AI support](../operations/ai.md)).

**Gitea** (`gitea`)

| Property | Value |
|----------|-------|
| **Endpoint** | `https://gitea.<domain>/mcp` |
| **Server** | a companion container (`gitea-mcp`), scaled to 0 while AI support is off |
| **Upstream** | official companion (the app project's own MCP server) |
| **Source** | <https://gitea.com/gitea/gitea-mcp> |
| **Identity mode** | per-person app credential (`app_token`): the Hub mints one for each person in the app; mcp-gate sends it with every call |
| **Modes** | read only, read and write (default read and write) |
| **In "All my apps"** | :white_check_mark: |
| **MCP versions** | `2025-11-25` |
| **Needs the person's confirmation** | `*delete*`, `*:*delete*` |
| **Never offered** | `actions_config_write:upsert_repo_secret`, `actions_config_write:upsert_org_secret` |
| **Hidden in read-only mode** | `*_write`, `create_*`, `delete_*` |

Why this choice, and what to know: [AI support → Gitea](../operations/ai.md#ai-gitea).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `gitea` | `gitea/gitea:28.3.0-rootless` | `sha256:40c5a68a0463…` |
| `gitea-auth` | `postgres:16.15-alpine` | `sha256:aa6cb33cf4c1…` |
| `gitea-db` | `postgres:16.15-alpine` | `sha256:aa6cb33cf4c1…` |
| `gitea-mcp` | `docker.gitea.com/gitea-mcp-server:1.12.0` | `sha256:7abff2c58718…` |
| `gitea-migrate` | `gitea/gitea:28.3.0-rootless` | `sha256:40c5a68a0463…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Git over SSH** | `bool` | instance | `restart` | Start Gitea's built-in SSH server (container port 2222) and show SSH clone URLs. Off by default: git over HTTPS with a personal access token works without it. Default: `false`. |

## Host Ports

Ports this app binds on the host. Collisions with other enabled apps block enable; each binding can be rebound or disabled from the Hub UI.

| Port | Protocol | Default | Container | Required | Notes |
|------|----------|---------|-----------|----------|-------|
| **Git over SSH** | `tcp` | `2222` | `2222` | :x: | — |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `GITEA_DB_PASSWORD` | Gitea database password | `random` |
| `GITEA_SECRET_KEY` | Gitea SECRET_KEY (encrypts stored secrets such as 2FA seeds) | `random` |
| `GITEA_INTERNAL_TOKEN` | Gitea INTERNAL_TOKEN (git hooks to the internal API) | `random` |
| `GITEA_OIDC_SECRET` | Gitea OIDC client secret | `random` |

## Keycloak Clients

**Gitea** (`gitea`)

Redirect URI: `https://{{HOST_GITEA}}/user/oauth2/Portcullis/callback`

## Access URLs

- **Gitea**: `https://{{HOST_GITEA}}`
