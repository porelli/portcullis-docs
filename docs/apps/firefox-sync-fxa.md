# 🦊 Firefox Sync + own accounts

> Firefox Sync with its own self-hosted Mozilla accounts, for the access group by verified email; nothing depends on Mozilla

**Category:** productivity  
**Tags:** `firefox`, `sync`, `bookmarks`, `browser`, `mozilla`, `accounts`  
**Website:** <https://mozilla-services.github.io/syncstorage-rs/>  
**Source:** <https://github.com/porelli/firefox-sync>  
**Minimum resources:** 4 GiB RAM, 18 GiB disk

## About

<div class="app-long-description">
<p>Firefox Sync keeps bookmarks, passwords, history, open tabs and add-ons in step across a person's Firefox browsers, on desktop and phone. This template runs the whole stack on your server, Mozilla's account service included, so nothing depends on Mozilla and the data is stored only on your server.</p>
<p>Sync data is end-to-end encrypted with keys from each person's account: the server stores it but can't read it.</p>
<p>Portcullis decides who may have an account: the instance's access group, matched by each person's verified Portcullis email. The accounts of people who leave the group are disabled and signed out, and the account pages and the admin UI sit behind Portcullis sign-in.</p>
<p>Needs about 4 GB of RAM and 18 GB of disk (upstream's sizes), plus about 5 GB for Mozilla's accounts image.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :warning: Partial |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :white_check_mark: |
| **Access Group** | `users_firefox-sync-fxa` |
| **Admin Group** | `admin_firefox-sync-fxa` |
| **Subdomain** | `firefox-sync-fxa`, `firefox-sync-fxa-accounts`, `firefox-sync-fxa-admin`, `firefox-sync-fxa-api`, `firefox-sync-fxa-pairing`, `firefox-sync-fxa-profile` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Firefox Sync with its own, self-hosted Mozilla accounts: Firefox signs in and syncs on this server, and nothing depends on Mozilla. Only members of the instance's access group with a <strong>verified</strong> Portcullis email can have an account.</p>
<p><strong>Hosts</strong> (the default instance's names; each instance has its own, shown on its page):</p>
<ul>
<li>Behind Portcullis sign-in: <code>firefox-sync-fxa-accounts.&lt;domain&gt;</code>, the account pages (sign-up, sign-in, settings), for the access group; and <code>firefox-sync-fxa-admin.&lt;domain&gt;</code>, the admin UI, for the admin group only.</li>
<li>Open to the internet, because Firefox calls them in the background without cookies: <code>firefox-sync-fxa-api.&lt;domain&gt;</code> (the accounts API), <code>firefox-sync-fxa-profile.&lt;domain&gt;</code> (profiles and avatars), <code>firefox-sync-fxa.&lt;domain&gt;</code> (Sync storage, each request signed with the account's own keys) and <code>firefox-sync-fxa-pairing.&lt;domain&gt;</code> (an encrypted relay for pairing a phone by QR code).</li>
<li>On the accounts host, the start page <code>/</code>, <code>/.well-known/fxa-client-configuration</code>, <code>/.well-known/change-password</code> and <code>/metrics-flow</code> stay open too: Firefox reads them before anyone has signed in.</li>
<li>Every open host is rate-limited; creating an account and getting a Sync token have a stricter limit.</li>
<li><strong>The Sync, API and accounts hostnames are fixed</strong> once the instance exists. The Sync data depends on them: the Sync server keeps every account as <code>&lt;account id&gt;@&lt;API host&gt;</code> on its node, the Sync host, and every Firefox keeps the accounts and API addresses it was set up with. A new name would leave every Sync store behind and every Firefox calling the old addresses. The profile, pairing and admin hostnames can change. A change of Portcullis's main domain doesn't move them either: the instance is listed as error until the old domain is added as an extra domain. A restore into a new instance id keeps the archive's fixed hostnames, so the old instance must be gone first; the other three get the new id's own. Other fixed hostnames mean a new instance, with new accounts.</li>
</ul>
<p><strong>Who may have an account:</strong> the members of the instance's access group with a <strong>verified</strong> Portcullis email. Each person verifies their email with a code sent to it (this needs the server's mail provider): verify it on your People page. An admin can also mark someone else's email verified there. A member without a verified email can't sign up: no verified email, no account. <code>fxa-access-sync</code> writes the verified emails to the sign-up list at every start and whenever the group changes.</p>
<ul>
<li>Someone who leaves the group, or whose email changes or stops being verified, is taken off the list. Their account is disabled and signed out everywhere. Firefox can keep syncing for up to about 2 hours after that: the sign-out can't take back an access token Firefox already holds (it lasts up to 60 minutes), and the Sync token Firefox gets for it lasts another hour.</li>
<li>Every run also disables and signs out any enabled account whose <strong>current</strong> primary email isn't on the list. An account's email can't be changed here, but if one was changed some other way, this catches it.</li>
<li>That sweep has a brake: if it would disable more accounts than the run expects (the people who left, plus 2), it disables none. The run is then reported as failed with the numbers only, and isn't tried with a higher limit. Check the accounts in the admin UI.</li>
<li>When they come back, their account is enabled again, even one an admin disabled before the person left.</li>
<li>An account an admin disables stays disabled while its owner stays in the group: routine runs never enable it.</li>
<li>If the list delivered by Portcullis can't be read, nothing changes and the run is reported as failed.</li>
</ul>
<p><strong>Admin UI</strong> (porelli/firefox-sync's admin UI), for the instance's <strong>admin group</strong> only. Others get 403 at the gateway, members of the access group included. After the Portcullis sign-in, the admin UI signs in by OpenID Connect with Portcullis's Keycloak (client <code>firefox-sync-fxa-admin</code>, redirect URI exactly <code>https://&lt;admin host&gt;/auth/callback</code>), which admits only the admin group (<code>admin_firefox-sync-fxa</code>, from the <code>groups</code> claim, never by email). There is no password sign-in.</p>
<ul>
<li><strong>Portcullis decides who may sign up and sync, not the admin UI</strong> (<em>access managed elsewhere</em>): the sign-up policy, its allowlist, invitations, the account cap and Sync's max users are shown read-only, and their forms answer 403. The account cap is the instance setting <strong>Maximum accounts</strong>.</li>
<li>Kept for incidents: monitoring, the event log, account pages and notes, per-account sign-out, disable and enable, deleting an account, and the Sync data tools. <strong>Enable refuses an account whose current primary email isn't on the list</strong> (&quot;not on the access list managed elsewhere&quot;). <strong>Deleting an account leaves the list alone</strong>, so a member whose account was deleted can sign up again.</li>
<li><strong>Confirm email and Confirm this sign-in are refused</strong> (403 at the gateway). Only the code sent to the address proves an account's email, so an admin can't vouch for one. Someone who signed up with a member's address, or signed in with a stolen password, would get in without that mailbox.</li>
<li>Its Connect a device page shows the Firefox setup below with this server's values.</li>
</ul>
<p><strong>Mail:</strong> the sign-up and sign-in codes go out through the server's mail provider (Settings, Mail) by default, at most 10 messages a minute and 60 an hour; or through another SMTP server (the instance's Mail settings). Without either, the accounts server doesn't start, and <code>fxa-mail-check</code> says why.</p>
<ul>
<li>STARTTLS on 587 is required, never opportunistic: a server that doesn't offer it gets no mail and never sees the password. Use TLS from the start on 465. TLS on 587 or STARTTLS on 465 stops the start.</li>
<li>The mail server's certificate is checked against the server's CA bundle (<code>certs/ca-bundle.crt</code>: the host's system CAs, Portcullis's own CA, and Let's Encrypt staging while <code>ACME_STAGING=true</code>). For a mail server with a self-signed certificate, add its CA to the host's system trust store, run <code>./portcullis config apply --bundle-only</code>, then restart the instance.</li>
</ul>
<p><strong>What's refused, and why:</strong></p>
<ul>
<li><strong>Adding a second email or changing an account's email</strong> is refused at the gateway (403). An account's email is its Portcullis email, and access follows that email.</li>
<li><strong>Confirming an email or a sign-in in the admin UI</strong> is refused at the gateway (403): only the code sent to the address counts.</li>
<li><strong>Passwordless sign-in and Google or Apple sign-in</strong> are refused (403). Every account is created through the sign-up gate, which checks the list.</li>
<li><strong>Email addresses that aren't plain ASCII</strong> are refused by the accounts database. Emails are compared byte for byte, so a look-alike address (an accent or a full-width letter) never matches a member's. An existing account with such an email is disabled and signed out at every start.</li>
</ul>
<p><strong>Backups:</strong> the <code>fxa-keys</code> volume holds the accounts' signing keys; a Hub instance backup copies it with the databases. Losing it signs everyone out: every Firefox must sign in again.</p>
<p><strong>Firefox setup</strong> (the accounts URL is the instance's accounts host, <code>https://firefox-sync-fxa-accounts.&lt;domain&gt;</code> for the default one). Sign out of Firefox first, if it's signed in.</p>
<ul>
<li><strong>Desktop:</strong> in <code>about:config</code>, set <code>identity.fxaccounts.autoconfig.uri</code> to the accounts URL. Restart Firefox, then sign in and turn on Sync.</li>
<li><strong>Android:</strong> Settings, About Firefox, tap the logo 5 times. Back in Settings, open Sync Debug and set <strong>Custom Mozilla account server</strong> to the accounts URL. Leave <strong>Custom Sync server</strong> empty. Restart Firefox when it asks, then sign in.</li>
<li><strong>iOS:</strong> in Settings, tap the version number 5 times. Open Advanced Sync Settings, turn on <strong>Use Custom FxA Content Server</strong> and set <strong>Custom Account Content Server URI</strong> to the accounts URL. Then sign in.</li>
<li>A phone can also pair from a signed-in desktop (Settings, Sync, Connect another device) once its accounts URL is set.</li>
</ul>
<p><strong>What runs:</strong> Mozilla's accounts (auth, content and profile servers, v1.350.0) on MySQL with Redis, the pairing channel server, syncstorage-rs 0.25.2 on PostgreSQL, and porelli/firefox-sync's admin UI and sign-up gate, as built by porelli/firefox-sync (<code>links.source</code>; upstream <a target="_blank" rel="noopener noreferrer nofollow" href="https://github.com/mozilla/fxa">https://github.com/mozilla/fxa</a> and <a target="_blank" rel="noopener noreferrer nofollow" href="https://github.com/mozilla-services/syncstorage-rs">https://github.com/mozilla-services/syncstorage-rs</a>). <code>fxa-gate</code>, an nginx that answers only Traefik, is in front of every host; no other service of the instance is reachable from other apps.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `firefox-sync-fxa` | `firefox-sync-fxa.<domain>` | all | `public@file` | :x: |
| `firefox-sync-fxa-accounts` | `firefox-sync-fxa-accounts.<domain>` | all | `default` | :white_check_mark: |
| `firefox-sync-fxa-accounts-change-password` | `firefox-sync-fxa-accounts.<domain>` | `/.well-known/change-password (exact)` | `default` | :x: |
| `firefox-sync-fxa-accounts-config` | `firefox-sync-fxa-accounts.<domain>` | `/.well-known/fxa-client-configuration (exact)` | `default` | :x: |
| `firefox-sync-fxa-accounts-metrics` | `firefox-sync-fxa-accounts.<domain>` | `/metrics-flow (exact)` | `default` | :x: |
| `firefox-sync-fxa-accounts-root` | `firefox-sync-fxa-accounts.<domain>` | `/ (exact)` | `default` | :x: |
| `firefox-sync-fxa-admin` | `firefox-sync-fxa-admin.<domain>` | all | `default` | :white_check_mark: |
| `firefox-sync-fxa-api` | `firefox-sync-fxa-api.<domain>` | all | `public@file` | :x: |
| `firefox-sync-fxa-pairing` | `firefox-sync-fxa-pairing.<domain>` | all | `public@file` | :x: |
| `firefox-sync-fxa-profile` | `firefox-sync-fxa-profile.<domain>` | all | `public@file` | :x: |
| `firefox-sync-fxa-signup` | `firefox-sync-fxa-api.<domain>` | `/v1/account/create (exact)` | `public@file` | :x: |
| `firefox-sync-fxa-token` | `firefox-sync-fxa.<domain>` | `/1.0/` | `public@file` | :x: |

## AI support

**No AI support:** Signs people in with its own Mozilla accounts, not Portcullis identities, and Sync data is end-to-end encrypted; no MCP server known (surveyed 2026-11-26).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `ffs-admin` | `ghcr.io/porelli/firefox-sync:admin-68ea7b80db3a` | `sha256:bab736d6a61e…` |
| `firefox-sync-fxa` | `ghcr.io/porelli/firefox-sync:syncstorage-rs-postgres-0.25.2` | `sha256:e31d2d17d136…` |
| `firefox-sync-fxa-db` | `postgres:17.11-alpine` | `sha256:3540c0362c80…` |
| `firefox-sync-fxa-db-init` | `ghcr.io/porelli/firefox-sync:syncstorage-rs-postgres-init-0.25.1-20261124T171959` | `sha256:a43d7e844d66…` |
| `firefox-sync-fxa-init` | `postgres:17.11-alpine` | `sha256:3540c0362c80…` |
| `firefox-sync-fxa-migrate` | `ghcr.io/porelli/firefox-sync:syncstorage-rs-postgres-0.25.2` | `sha256:e31d2d17d136…` |
| `fxa-access-sync` | `mysql:9.7.4` | `sha256:1f2ca53a9e94…` |
| `fxa-auth` | `ghcr.io/porelli/firefox-sync:fxa-mono-v1.350.0` | `sha256:0ec0804fe9a0…` |
| `fxa-content` | `ghcr.io/porelli/firefox-sync:fxa-mono-v1.350.0` | `sha256:0ec0804fe9a0…` |
| `fxa-db` | `mysql:9.7.4` | `sha256:1f2ca53a9e94…` |
| `fxa-db-guard` | `mysql:9.7.4` | `sha256:1f2ca53a9e94…` |
| `fxa-db-users` | `mysql:9.7.4` | `sha256:1f2ca53a9e94…` |
| `fxa-gate` | `nginx:1.31.8-alpine` | `sha256:fed7e14be83c…` |
| `fxa-keys-owner` | `ghcr.io/porelli/firefox-sync:fxa-mono-v1.350.0` | `sha256:0ec0804fe9a0…` |
| `fxa-mail-check` | `redis:8.12.0-alpine` | `sha256:5af80107c1ee…` |
| `fxa-migrations` | `ghcr.io/porelli/firefox-sync:fxa-mono-v1.350.0` | `sha256:0ec0804fe9a0…` |
| `fxa-pairing` | `ghcr.io/porelli/firefox-sync:fxa-channelserver-1.6.0` | `sha256:cfc3319d79ba…` |
| `fxa-policy` | `ghcr.io/porelli/firefox-sync:admin-68ea7b80db3a` | `sha256:bab736d6a61e…` |
| `fxa-profile` | `ghcr.io/porelli/firefox-sync:fxa-mono-v1.350.0` | `sha256:0ec0804fe9a0…` |
| `fxa-profile-static` | `ghcr.io/porelli/firefox-sync:fxa-mono-v1.350.0` | `sha256:0ec0804fe9a0…` |
| `fxa-profile-worker` | `ghcr.io/porelli/firefox-sync:fxa-mono-v1.350.0` | `sha256:0ec0804fe9a0…` |
| `fxa-redis` | `redis:8.12.0-alpine` | `sha256:5af80107c1ee…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Send mail through** | `enum` | instance | `restart` | Where the sign-up and sign-in codes go out. The server's mail provider needs one wired (Settings, Mail); without a working mail server the accounts server doesn't start. Choices: `provider`, `external`. Default: `provider`. |
| **SMTP server** | `string` | instance | `restart` | Another SMTP server only. Its host name. |
| **SMTP port** | `int` | instance | `restart` | Another SMTP server only. 587 for STARTTLS, 465 for TLS; the accounts server doesn't start with TLS on 587 or STARTTLS on 465. Default: `587`. |
| **SMTP security** | `enum` | instance | `restart` | Another SMTP server only. STARTTLS on 587 or TLS from the start on 465. Choices: `starttls`, `tls`. Default: `starttls`. |
| **SMTP user** | `string` | instance | `restart` | Another SMTP server only. Empty when it takes mail without signing in. |
| **SMTP password** | `secret` | instance | `restart` | Another SMTP server only. The password of the SMTP user; it can't contain ', \ or a line break. |
| **Sender address** | `string` | instance | `restart` | Another SMTP server only. The address the mail comes from, shown as Firefox accounts. |
| **Maximum accounts** | `int` | instance | `restart` | At most this many accounts; sign-ups are refused once they exist. Empty: no limit, the access group decides. |
| **Account email** | `verified_email` | instance | `restart` | Each member's verified Portcullis email: the email they may create their Firefox account with. Members without a verified email can't. |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `FXA_MYSQL_PASSWORD` | Accounts database (MySQL) root password, for the one-shots only (migrations, policy, database users) | `random` |
| `FXA_AUTH_DB_PASSWORD` | Accounts database password of the auth server (fxa_auth; not root, nothing on ffs) | `random` |
| `FXA_PROFILE_DB_PASSWORD` | Accounts database password of the profile server (fxa_profile; its own database only) | `random` |
| `FXA_ADMIN_DB_PASSWORD` | Accounts database password of the admin UI (ffs_admin) | `random` |
| `FXA_ACCESS_DB_PASSWORD` | Accounts database password of Portcullis's access sync (ffs_access, the sign-up allowlist) | `random` |
| `FXA_OAUTH_SECRET` | Accounts OAuth server secret (also the key the MFA JWT key is derived from) | `random` |
| `FXA_AUTH_SECRET` | Accounts auth server shared secret | `random` |
| `FXA_PROFILE_SECRET` | Accounts profile server bearer token | `random` |
| `FXA_FLOW_ID_KEY` | Accounts flow id key | `random` |
| `FXA_SESSION_TOKEN_HANDLE_KEY` | Accounts session token handle key | `random` |
| `FXA_CONTENT_SESSION_SECRET` | Account pages' session cookie secret | `random` |
| `FIREFOX_SYNC_FXA_DB_PASSWORD` | Sync database owner password (migrations, init) | `random` |
| `FIREFOX_SYNC_FXA_APP_DB_PASSWORD` | Sync database password of the server's own role (no owner rights) | `random` |
| `FIREFOX_SYNC_FXA_ADMIN_DB_PASSWORD` | Sync database password of the admin UI's own roles (its database, its reader of the Sync data) | `random` |
| `FIREFOX_SYNC_FXA_MASTER_SECRET` | syncstorage-rs master secret (signs the storage tokens) | `random` |
| `FIREFOX_SYNC_FXA_METRICS_SECRET` | tokenserver metrics hash secret | `random` |
| `FIREFOX_SYNC_FXA_ADMIN_OIDC_SECRET` | OpenID Connect client secret of the admin UI (Keycloak client firefox-sync-fxa-admin) | `random` |

## Keycloak Clients

**Firefox Sync + own accounts admin UI** (`firefox-sync-fxa-admin`)

Redirect URI: `https://{{HOST_FIREFOX_SYNC_FXA_ADMIN}}/auth/callback`

## Access URLs

- **Accounts (Firefox's identity.fxaccounts.autoconfig.uri)**: `https://{{HOST_FIREFOX_SYNC_FXA_ACCOUNTS}}`
- **Admin UI**: `https://{{HOST_FIREFOX_SYNC_FXA_ADMIN}}/`
