# 🍽 Mealie

> Self-hosted recipe manager, meal planner and shopping lists

**Category:** productivity  
**Tags:** `recipes`, `cooking`, `meal-planning`, `shopping-list`, `food`  
**Website:** <https://mealie.io/>  
**Source:** <https://github.com/mealie-recipes/mealie>

## About

<div class="app-long-description">
<p>Mealie is a recipe manager and meal planner. It imports recipes from websites by URL, scales them, plans meals by week and builds shopping lists from them.</p>
<p>Portcullis signs people in through OpenID Connect, with no password login. Members of the access or admin group can sign in, and members of the admin group are Mealie administrators.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :white_check_mark: |
| **Access Group** | `users_mealie` |
| **Admin Group** | `admin_mealie` |
| **Subdomain** | `recipes` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Native OIDC (Mealie v3.30.0): the login page redirects straight to Portcullis, and only members of <code>users_mealie</code> or <code>admin_mealie</code> may sign in. There is no password login at all.</p>
<p><strong>Sign-in:</strong> the login page redirects straight to Portcullis (<code>OIDC_AUTO_REDIRECT</code>). Only members of <code>users_mealie</code> or <code>admin_mealie</code> may sign in (<code>OIDC_USER_GROUP</code> / <code>OIDC_ADMIN_GROUP</code>, checked by Mealie on the <code>groups</code> claim); accounts are created on the first SSO login and keyed on the LLDAP username (<code>OIDC_USER_CLAIM</code> <code>preferred_username</code>).</p>
<ul>
<li><code>admin_mealie</code> members are Mealie admins, re-evaluated at every login; everyone else is a plain user of the default group/household (an admin can move them).</li>
<li>Self sign-up, invitations and LDAP / reverse-proxy logins are off.</li>
</ul>
<p><strong>No password login:</strong> Mealie's <code>ALLOW_PASSWORD_LOGIN=false</code> only hides the form and its token API still accepts passwords, so the <code>mealie-init</code> one-shot (<code>guard.py</code>, before the app starts, every start) installs a database trigger that makes every account an OIDC account (Mealie refuses passwords for those), and retires the admin Mealie seeds on an empty database (well-known password) by giving it a username and email no SSO login can match.</p>
<p><strong>Identity:</strong> Mealie matches an SSO login to an existing account by the <code>preferred_username</code> claim in the username column, then in the email column, and lets users edit both. So the trigger keeps the username and email of every account fixed (an edit is refused), refuses emails without <code>@</code> (LLDAP usernames never contain one) and any account whose email equals another account's username or the reverse: the email lookup can never hand one user's login to another.</p>
<ul>
<li>That is also why <code>OIDC_REQUIRES_EMAIL_VERIFICATION</code> can be off (Keycloak marks LLDAP emails unverified).</li>
<li>The name claim is <code>preferred_username</code> (<code>OIDC_NAME_CLAIM</code>; Keycloak omits <code>name</code> for users without a first/last name).</li>
<li>An admin who creates a user in Mealie pre-provisions it for the LLDAP user of that username (no password).</li>
<li>The app's healthcheck fails (Traefik stops routing) if the trigger is missing or an account has a password login.</li>
</ul>
<p><strong>Emails:</strong> users need an email in LLDAP (Mealie requires the claim). Two LLDAP users with the same email can't both sign in (Mealie's email column is unique), and a member who sets their LLDAP email to someone else's before that person's first login blocks that person's account creation on purpose (an admin has to correct the email in LLDAP).</p>
<p><strong>Revoking access:</strong> removing a user from the groups blocks new SSO logins, not sessions (<code>TOKEN_TIME</code>, 48 h) or API tokens already issued; delete or lock the user in Mealie for that.</p>
<p>Mobile/desktop apps use the OIDC native flow (register their redirect URI on the Keycloak client).</p>
<p><strong>Upgrades:</strong> read the Mealie release notes; database migrations run in <code>mealie-init</code> and fail closed if one would change an account's username or email. Keep <code>mealie</code>, <code>mealie-init</code> and <code>mealie-perms</code> on the same image; don't bump the PostgreSQL major.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `mealie` | `recipes.<domain>` | all | `default` | :x: |

## AI support

**No AI support:** No official or vetted community MCP server known (surveyed 2026-11-05).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `mealie` | `ghcr.io/mealie-recipes/mealie:v3.30.0` | `sha256:90f83da6f3ab…` |
| `mealie-db` | `postgres:17.11-alpine` | `sha256:3540c0362c80…` |
| `mealie-init` | `ghcr.io/mealie-recipes/mealie:v3.30.0` | `sha256:90f83da6f3ab…` |
| `mealie-perms` | `ghcr.io/mealie-recipes/mealie:v3.30.0` | `sha256:90f83da6f3ab…` |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `MEALIE_DB_PASSWORD` | Mealie database password | `random` |
| `MEALIE_OIDC_SECRET` | Mealie OIDC client secret | `random` |

## Keycloak Clients

**Mealie** (`mealie`)

Redirect URIs:

- `https://{{HOST_MEALIE}}/login`
- `https://{{HOST_MEALIE}}/login?direct=1`

## Access URLs

- **Recipes**: `https://{{HOST_MEALIE}}`
