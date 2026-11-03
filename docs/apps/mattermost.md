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

!!! info "Auth Notes"
    Mattermost Team Edition 12.0 has no SSO that works with Portcullis: OpenID Connect (and Google / Entra ID / SAML / LDAP) need a paid license, and the free GitLab SSO provider reads a GitLab user API (numeric "id", "username"), which Keycloak's userinfo doesn't serve (the Hub creates clients without custom mappers, and LLDAP users have no numeric id) and which can't restrict sign-in to a group. So the whole host is behind Portcullis sign-in + group-gate (users_mattermost) and Mattermost keeps its own accounts behind it. Self sign-up is off (no email sign-up, which also closes the first-account and invite-link sign-ups; no open server; locked in the System Console). Team Edition's System Console can't create accounts; an admin creates them with mmctl in local mode, in the container (Hub exec or the server shell): `mmctl --local user create --username <LLDAP username> --email <email> --password <random placeholder>`, then `mmctl --local user change-password <username>`, which prompts for the real initial password on stdin (mmctl only takes the create password as an argument, so use a throwaway there), hands that password over out of band, and the user changes it after signing in. Local mode answers anyone who can run a process in the Mattermost container with full system-admin rights (no authentication); Hub exec into that container is admin access. Give each account the person's LLDAP username, since Mattermost doesn't know who passed the gateway. No admin group: Mattermost can't map one (no SSO), so admins are made in Mattermost (by a system admin, e.g. mmctl --local roles system-admin <username>). The bootstrap system admin is mmadmin-<first 12 characters of MATTERMOST_ADMIN_SUFFIX> with the generated password MATTERMOST_ADMIN_PASSWORD, created once by the mattermost-init one-shot over the local-mode socket and pinned by its user ID in the data volume: system_admin is granted only to the account that run created, never to an account found by name. If the bootstrap name later belongs to a different account (renamed and taken) or exists without the pinned ID, mattermost-init fails (the Hub reports the failed one-shot) and grants nothing; Mattermost itself keeps running (its image has no shell, so its healthcheck can't read the state file), and the account holding the name stays a plain user. Change the bootstrap password after the first sign-in. Team Edition can't lock usernames (LockProfileFieldsForEmailUsers is Enterprise-only), so users can rename themselves; Mattermost usernames are not an identity Portcullis vouches for. GitLab SSO, personal access tokens and the plugin marketplace are off, and so are plugin uploads (server-side code from any system-admin session). Plugins: a pinned list (plugins.py, each a GitHub release asset checked against its SHA-256): freemium 2.0.0 (dy0gu/mattermost-plugin-freemium, hides Team Edition's upsell UI) and Matterpoll 1.9.2 (/poll). Mattermost requires plugin signatures, and upstream doesn't sign these, so before every compose-managed start (what the Hub runs; a plain Docker restart reuses the last signatures, which is safe) the mattermost-plugins one-shot checks a private copy of each bundle (in its root-only tmpfs; file-store copies are opened without following symlinks, regular files only) against its SHA-256 (a mismatch or a swapped file fails it before anything is signed, and Mattermost doesn't start), signs that private copy with an OpenPGP key it generates in tmpfs for that start only (the private key never reaches a volume), writes bundle + signature into Mattermost's file store (locked to the data volume) and only the public key to a volume Mattermost mounts read-only (SignaturePublicKeyFiles). Mattermost installs from the file store at startup, so any other bundle, unsigned or signed by another key, is refused. The public key is placed before the signatures, so an interrupted job leaves only signatures the new key doesn't verify (those plugins are refused until the next run). Mattermost's built-in key still accepts any Mattermost-signed bundle, old versions included, if something writes one into the file store's plugins/ directory; that needs filesystem access to the data volume or local-mode access (both already full admin). mattermost-init enables the pinned plugins. Bump a plugin by editing its version, URL and SHA-256 in plugins.py (Dependabot doesn't see them). SSO, re-checked: the free GitLab provider can't use Keycloak today. Team Edition switches to the licensed OpenID provider whenever the GitLab scope contains "openid", while Keycloak's userinfo refuses tokens without the openid scope ("Missing openid scope"), and the provider needs a stable numeric "id" that no static Keycloak mapper can derive (LLDAP has no numeric attribute, Keycloak ids are UUIDs). It becomes possible once the Hub allocates a per-person numeric id (a user attribute mapped to "id"), plus mappers for username, which the Hub doesn't create yet. What doesn't work through the gateway: the Mattermost desktop and mobile apps and anything else that talks to the API directly (bots, incoming/outgoing webhooks, slash-command callbacks, personal or bot access tokens), because every request needs a Portcullis browser session first; use the web app. Networking: Mattermost is on the instance's private network only; the gate in front of it (nginx, mattermost-gate, the only container on portcullis-proxy) answers Traefik's address alone, so no other container can reach Mattermost past the gateway. The gate never forwards the Portcullis session (Authorization, access-token headers and the forward-auth cookies are removed) and passes the websocket through. Mattermost takes the client address (logs, rate limits) from X-Real-Ip, which Traefik sets to the peer it accepted (client-sent copies are deleted) and the gate passes on unchanged. Upgrades: follow Mattermost's upgrade path (extended support releases, one major at a time); don't bump the PostgreSQL major.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `mattermost` | `chat.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `mattermost` | `mattermost/mattermost-team-edition:12.0.1` | `sha256:8ca1050cb8a2…` |
| `mattermost-db` | `postgres:17.11-alpine` | `sha256:266d3c257594…` |
| `mattermost-gate` | `nginx:1.31.8-alpine` | `sha256:785835ea65db…` |
| `mattermost-init` | `python:3.15.2-alpine` | `sha256:20a82dbc2783…` |
| `mattermost-plugins` | `python:3.15.2-trixie` | `sha256:b9dc13dd9e9c…` |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `MATTERMOST_DB_PASSWORD` | Mattermost database password | `random` |
| `MATTERMOST_ADMIN_SUFFIX` | Random suffix of the bootstrap system admin's username (mmadmin-<first 12 characters>) | `random` |
| `MATTERMOST_ADMIN_PASSWORD` | Password of the bootstrap system admin | `random` |

## Access URLs

- **Chat**: `https://{{HOST_MATTERMOST}}`
