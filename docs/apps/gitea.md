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

!!! info "Auth Notes"
    Native OIDC through a Gitea OAuth2 authentication source ("Portcullis") that the gitea-auth job writes into Gitea's database at every start (client id, secret, discovery URL, groups), so a hostname, client or group change only needs a restart. Gitea loads the client id, secret and discovery URL when it starts, so a changed client secret takes effect once the gitea container itself restarts (rerunning the job is not enough); the required group and the admin group are read at every login. The client secret never appears on a command line: Gitea's CLI only takes it as an argument, so the job uses psql with the values read from its environment. The login page goes straight to Portcullis: there is no password sign-in form (POST /user/login answers 403), no sign-up form, no passkey or OpenID 2.0 sign-in, no HTTP basic authentication with a password and no reverse-proxy header auth. Nothing is readable without signing in (REQUIRE_SIGNIN_VIEW). Any other authentication source added in the admin panel is switched off at the next start. Access: Gitea refuses the login ("Sign-in prohibited") unless the groups claim contains users_gitea, checked at every login. Admin: Gitea sets or clears the site-admin flag from admin_gitea at every login (an admin must also be in users_gitea). Everyone else is a regular user (the least-privileged full account; Gitea's "restricted" users can't see public repositories, so that role is left to admins). Removing a user from users_gitea blocks new logins only: open sessions, personal access tokens and SSH keys keep working (the AI tokens Portcullis minted are deleted); disable the user in Site Administration to cut access at once. Identity: accounts are created on the first Portcullis login, named after preferred_username (the immutable LLDAP username, not renameable in Gitea) and keyed on the OIDC sub. ACCOUNT_LINKING is disabled, so a login is never attached to an existing account by name or email (LLDAP emails are user-editable); a clash with an existing username or email is refused (an error page, no takeover). The email is only taken at account creation and kept private by default. Break-glass admin: Gitea makes the first account it creates a site admin and never demotes the last admin, so gitea-migrate creates the local admin portcullis-breakglass before anyone signs in (random password, never printed or stored) and gitea-auth keeps it admin with sign-in prohibited; Gitea won't start without it. To recover admin rights on the server, add a user to admin_gitea in LLDAP, or run docker compose -p portcullis-<instance> exec gitea-db psql -U gitea -d gitea -c "UPDATE \"user\" SET is_admin = true WHERE lower_name = '<username>'". AI support (off until the admin turns it on): the official gitea-mcp server runs as the companion; every request runs as the person, with a Gitea access token named portcullis-ai-<random> that the Hub mints on their first AI request (read-only mode: read scopes only, and gitea-mcp hides its write tools) and deletes when they leave the instance's population, when AI support or its mode changes and after a restore. A person who never signed in to Gitea gets no token. The hooks (portcullis/mcp-token.sh) list and delete tokens through Gitea's API as portcullis-hooks, a second local admin that gitea-migrate creates and gitea-auth keeps active: it has a discarded random password and no way in but an access token minted inside the container, one per hook run, deleted by that run. It never runs AI requests. Deleting it breaks AI support until the next start recreates it. AI and re-used usernames: the Hub sends the person's Keycloak id with every mint and the hook mints only for the Gitea account Gitea signs that id in to. If a person is deleted and their username given to someone new, the newcomer gets no token for the former person's account (the mint fails, shown on the AI tab; their web sign-in is refused as well): delete or rename the former person's Gitea account (Site Administration > User Accounts), then the newcomer signs in once. AI file writes: create_or_update_file can also delete files in the same commit (files[].delete) without a confirmation; the deletion is an ordinary commit, recoverable from the repository's history. While AI support is on, https://<host>/mcp is the AI endpoint, so a Gitea user or organization named mcp loses its profile page (its repositories stay reachable): don't use that name. Git over HTTPS: clone https://<host>/<owner>/<repo>.git with your username and a personal access token (User Settings > Applications) as the password; git-credential-manager / git-credential-oauth can use Gitea's own OAuth2 provider instead. Git over SSH is off by default: turn on the "Git over SSH" setting and keep the SSH host port (default 2222, Gitea's built-in SSH server, keys from User Settings > SSH Keys); every instance needs its own host port. Webhooks and migrations to private addresses stay blocked (Gitea's defaults). Upgrades: the image is pinned; Gitea migrates its database on start and supports upgrading from older releases directly, but read the release notes of each major (28.x) before bumping. Keep gitea and gitea-migrate on the same image.

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
| `gitea-auth` | `postgres:16.15-alpine` | `sha256:0cefaabd882e…` |
| `gitea-db` | `postgres:16.15-alpine` | `sha256:0cefaabd882e…` |
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
