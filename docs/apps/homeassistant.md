# 🏠 Home Assistant

> Open-source home automation hub with dashboards, automations and integrations

**Category:** home-automation  
**Tags:** `home-automation`, `smart-home`, `iot`, `dashboards`, `automations`  
**Website:** <https://www.home-assistant.io/>  
**Source:** <https://github.com/home-assistant/core>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :white_check_mark: |
| **Access Group** | `users_homeassistant` |
| **Admin Group** | `admin_homeassistant` |
| **Subdomain** | `home` |

!!! info "Auth Notes"
    Home Assistant 2026.10 has no OpenID Connect of its own; sign-in goes through the OpenID Connect custom integration auth_oidc (christiaangoossens/hass-oidc-auth, the integration HACS lists, here pinned to release 1.2.1 and installed by the homeassistant-init one-shot from the release asset after its SHA-256 matched; a mismatch stops the start. Its Python requirements ship in the Home Assistant image). It is the only auth provider: configuration.yaml (shipped read-only) sets auth_providers: [] so Home Assistant's own username/password login doesn't exist, and homeassistant-init marks onboarding done before the first start, so the onboarding wizard (which creates a password owner) never opens. The app is routed only while /auth/providers lists auth_oidc alone and onboarding is closed. Who can sign in: auth_oidc admits users in users_homeassistant (roles.user) and also users in admin_homeassistant alone (roles.admin implies access upstream), so the Hub's Keycloak access role (keycloak_access_role) restricts the client to users_homeassistant as well: in production only that group gets a token at all. admin_homeassistant members become Home Assistant administrators. Upstream sets roles only when the account is created (first login): change an existing user's administrator flag in Settings > People. Accounts are keyed on the OIDC issuer + sub, the display name is the LLDAP username (preferred_username), and SSO logins are never linked to existing accounts (automatic_user_linking off). No one is the instance owner; administrators can do everything an owner can except owner-only operations. Break-glass: there is no local login; an operator temporarily mounts a modified configuration.yaml (with a local provider) over the template's through the Hub's custom override. What works: the web UI and its websocket API (straight to Home Assistant, no forward-auth on the host), long-lived access tokens created by a signed-in user, and the Companion apps: upstream signs mobile apps in with a device code shown in the app and confirmed in a browser (Chrome/Safari or another computer) where the user signs in to Portcullis. That device-code step is phishable: a member can be tricked into entering a code an outsider's app shows, which signs that app in as the member (enter only codes from your own device). Limits: removing a user from the groups blocks new sign-ins only. Home Assistant refresh tokens stay valid until unused for 90 days and long-lived access tokens are effectively permanent (upstream has no session management or back-channel logout yet): deactivate the user in Home Assistant (Settings > People) to revoke them. Networking: the container is on Docker bridge networks only (never host networking, which would publish port 8123 past the gateway), so mDNS/SSDP/DHCP discovery, Bluetooth and USB radios are not available; use IP-based integrations (or MQTT / a network radio bridge). The HTTP server settings (Traefik as the only trusted proxy) are rewritten by homeassistant-init at every start; changes made in the UI don't persist. That is also why several instances can run side by side (instances: multi). Upgrades: read the Home Assistant and hass-oidc-auth release notes; bump auth_oidc (version and SHA-256 in init.py) together with Home Assistant when upstream requires it. AI support: the built-in MCP Server integration, with Home Assistant as its own OAuth server (people sign in through Portcullis); Home Assistant applies its own rules and Portcullis doesn't log or confirm its AI actions. Assist exposure is instance-wide, not a per-person boundary: every person's MCP client sees and controls the same exposed entities; the person's own account only decides attribution and whether administrator-only actions are allowed. Turning AI support on adds the integration with administrators-only off and the Assist API only; turning it off removes it, and the homeassistant service's entrypoint (portcullis/prestart.py) removes it again at every container start while AI support is off. A Home Assistant administrator can still add it by hand meanwhile: it then serves until the next container start (a restart from Home Assistant's own UI restarts only the process under s6 and doesn't run prestart.py). The AI hooks act as "Portcullis hooks", a system user prestart.py provisions with a new token at every container start: hidden from Settings > People, no credential of any sign-in provider (it can't sign in), local_only (Home Assistant then refuses its tokens from outside the local network, which still includes the LAN, not only this container). Its token lives in /config/.storage/auth, so instance backups carry it (rotated at the next start after a restore). When a person leaves while their account is matched, every Home Assistant refresh token of theirs ends (web sessions, Companion apps, long-lived tokens, AI clients); the account stays. The person is matched by the OIDC sub auth_oidc stored when they first signed in (the Hub sends each Keycloak id it saw for them), never by name: people can rename themselves. Someone the Hub couldn't match (no LLDAP uuid or Keycloak id recorded) costs everyone's AI client tokens of this instance when they leave, and their other tokens stay until an administrator deactivates or deletes them in Settings > People (the Hub lists them). An authorization code Home Assistant issued just before someone left stays usable for its 10 minutes. Switching AI support on or off ends every OAuth client token except Home Assistant's own web frontend and Companion apps; long-lived tokens are kept.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `homeassistant` | `home.<domain>` | all | `authaware@file` | :x: |

## AI support

People's AI assistants can use this app as themselves through these MCP servers, once an admin switches AI support on in the app's **AI support** tab (see [AI support](../operations/ai.md)).

**Home Assistant** (`homeassistant`)

| Property | Value |
|----------|-------|
| **Endpoint** | `https://home.<domain>/api/mcp` |
| **Server** | built into the app |
| **Upstream** | official (the app's own MCP server) |
| **Source** | <https://www.home-assistant.io/integrations/mcp_server/> |
| **Identity mode** | the app's own sign-in (`app_oauth`): the app is its own OAuth server and signs people in through Portcullis; mcp-gate is not in the path |
| **Modes** | read and write |
| **In "All my apps"** | :x: |
| **MCP versions** | `2025-11-25`, `2025-06-18` |

!!! warning "The app applies its own rules"
    This app signs AI clients in itself. Portcullis doesn't log, confirm, rate-limit or filter its AI actions; leaving the app's access group revokes the person's AI tokens through the template's revoke hook.

Why this choice, and what to know: [AI support → Home Assistant](../operations/ai.md#ai-homeassistant).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `homeassistant` | `ghcr.io/home-assistant/home-assistant:2026.10.4` | `sha256:23f4dfbb69ce…` |
| `homeassistant-init` | `ghcr.io/home-assistant/home-assistant:2026.10.4` | `sha256:23f4dfbb69ce…` |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `HOMEASSISTANT_OIDC_SECRET` | Home Assistant OIDC client secret | `random` |

## Keycloak Clients

**Home Assistant** (`homeassistant`)

Redirect URI: `https://{{HOST_HOMEASSISTANT}}/auth/oidc/callback`

## Access URLs

- **Home**: `https://{{HOST_HOMEASSISTANT}}`
