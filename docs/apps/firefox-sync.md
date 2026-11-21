# 🦊 Firefox Sync

> Self-hosted Firefox Sync server (bookmarks, passwords, history, tabs) for Mozilla accounts

**Category:** productivity  
**Tags:** `firefox`, `sync`, `bookmarks`, `browser`, `mozilla`  
**Website:** <https://mozilla-services.github.io/syncstorage-rs/>  
**Source:** <https://github.com/porelli/firefox-sync>

## About

<div class="app-long-description">
<p>Firefox Sync keeps bookmarks, passwords, history, open tabs and add-ons in step across a person's Firefox browsers. This template runs the sync storage server yourself, so the synced data is stored on your server instead of Mozilla's.</p>
<p>People still sign in to Firefox with their Mozilla account. Each member of the access group enters their own account id on My apps, and only listed accounts can sync. Firefox can't pass a Portcullis sign-in, so the sync host is open to the internet.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `custom` |
| **SSO** | :x: No |
| **Group Access** | :x: |
| **Group Admin** | :x: |
| **Access Group** | `users_firefox-sync` |
| **Subdomain** | `firefox-sync` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>A self-hosted Firefox Sync server. People sign in to Firefox with their Mozilla account, and only the Mozilla accounts on this instance's allowlist can sync; the host is open to the internet, with no Portcullis sign-in, because Firefox can't pass one.</p>
<p><strong>What runs:</strong> Mozilla's syncstorage-rs 0.24.0 (Sync storage + tokenserver; upstream <a target="_blank" rel="noopener noreferrer nofollow" href="https://github.com/mozilla-services/syncstorage-rs">https://github.com/mozilla-services/syncstorage-rs</a>), as built by porelli/firefox-sync (PostgreSQL image; <code>links.source</code>). Firefox signs in with a Mozilla account at accounts.firefox.com, then calls this server's tokenserver with that account's OAuth token, which the tokenserver verifies with Mozilla and exchanges for a short-lived storage token (1 h).</p>
<p><strong>Why no Portcullis sign-in</strong> (<code>method: custom</code>, no <code>native_login</code>): Firefox makes every Sync and tokenserver request in the background as an anonymous request, without cookies, HTTP authentication or a client certificate (RESTRequest <code>LOAD_ANONYMOUS</code>, <code>resource.sys.mjs</code> fetch; tested by porelli/firefox-sync with a sign-in proxy and with mTLS: <code>no_node_found</code> / <code>NS_ERROR_NET_UNCLEAN_SHUTDOWN</code>). Portcullis sign-in, group-gate or a client-certificate tier in front of this host would break every Firefox, so the host is open (<code>public@file</code>, <code>rate-limit</code>; the tokenserver path <code>/1.0/</code> the stricter <code>rate-limit-auth</code>; syncstorage-rs enforces its own request size limits) and access is decided by the server itself.</p>
<p><strong>Exposed on the host:</strong></p>
<ul>
<li><code>GET /1.0/sync/1.5</code> (tokenserver: a Mozilla OAuth token with the Sync scope is required, 401 otherwise)</li>
<li><code>/1.5/&lt;uid&gt;/...</code> (storage: Hawk-signed with this instance's secret, 401 otherwise)</li>
<li><code>/__heartbeat__</code>, <code>/__lbheartbeat__</code>, <code>/__version__</code>, <code>/__error__</code> (a test error), <code>/</code> and the API docs (<code>/swagger-ui</code>, <code>/api-doc/openapi.json</code>)</li>
</ul>
<p>No password, no sign-up page, no admin UI.</p>
<p><strong>Database roles:</strong> the internet-facing server connects as <code>firefoxsync_app</code>, which owns no table and is no superuser (it can't drop or disable the allowlist trigger, change <code>session_replication_role</code> or write the allowlist) and may create no database object (an event trigger; it keeps <code>CREATE</code> on the schema only for syncstorage-rs' no-op migration check). It runs no migrations; <code>firefox-sync-migrate</code> and <code>firefox-sync-init</code> use the owner and are not reachable.</p>
<p><strong>Who can sync:</strong> the Mozilla accounts on the allowlist:</p>
<ul>
<li>the uids the members of the access group (<code>users_firefox-sync</code>) entered themselves on My apps (Mozilla account ID; one uid per person, and no two people may register the same uid; admins may enter or clear one for someone);</li>
<li>plus the instance's <strong>Other allowed accounts</strong> (uids not tied to a Portcullis person).</li>
</ul>
<p>The Hub writes them to the data file <code>allowlist.json</code>. At every start <code>firefox-sync-init</code> (<code>guard.sql</code>) installs exactly that list before the server starts, and a database trigger refuses every other account: no tokenserver row, no token, no storage.</p>
<ul>
<li>Nobody listed (the default) = nobody syncs; a missing, unparsable or invalid <code>allowlist.json</code> stops the instance (fail closed).</li>
<li>Someone who leaves the access group drops off the list at the next delivery (the instance restarts within about a minute): that account's tokenserver rows are deleted, its tokens expire within the hour and it can't get new ones (its encrypted data stays, unreachable). Their entered uid is kept and comes back if they rejoin.</li>
</ul>
<p><strong>Identity:</strong> Mozilla accounts, not Portcullis. Firefox has no way to use Keycloak or LLDAP for Sync (the self-hosted Mozilla accounts stack has no external OIDC login and is not published as an image), so the access group decides only who may register a uid, not who signs in to Firefox: whoever holds a listed Mozilla account can sync. Sync data is end-to-end encrypted with keys derived from the Mozilla account: this server, and whoever controls it, can't read it.</p>
<p><strong>Self-hosted Mozilla accounts</strong> (porelli/firefox-sync's fxa-mono option) are not offered: they need an SMTP server, MySQL and Redis, three more public hosts, a 5 GB image and 3–4 GB of RAM, and they are a second, password-based account system on the internet that Portcullis can't gate (Firefox calls the accounts API anonymously too). A separate template may add them later.</p>
<p><strong>The allowlist</strong> uses firefox-sync's table (<code>sync_allowed_accounts</code>) with a stricter trigger: it raises (no row, no token) instead of skipping the row, and an empty list refuses everybody instead of turning the allowlist off.</p>
<p><strong>Finding a uid:</strong> in a Firefox signed in to the account, Browser Console (<code>devtools.chrome.enabled = true</code>):</p>
<pre><code>(await ChromeUtils.importESModule(&quot;resource://gre/modules/FxAccounts.sys.mjs&quot;).getFxAccountsSingleton().getSignedInUser()).uid
</code></pre>
<p>Or let the person try: the refused uid is in the <code>firefox-sync-db</code> log (<code>portcullis: Firefox account &lt;uid&gt; is not on the allowlist</code>).</p>
<p><strong>Firefox setup:</strong> <code>about:config</code> <code>identity.sync.tokenserver.uri</code> = <code>https://&lt;this host&gt;/1.0/sync/1.5</code> (Android: Sync Debug &gt; Custom Sync server; iOS: Advanced Sync Settings), before signing in to the account. After a hostname change every Firefox must be pointed at the new URL; the accounts move to the new node at the next start.</p>
<p><strong>Node load:</strong> the tokenserver counts a new account in the node's load before the trigger refuses it, so one valid Mozilla token replayed would otherwise fill the node; every start sets the node's capacity to the maximum (2147483647) and recounts the load from its accounts.</p>
<p><strong>Residuals:</strong> the tokenserver needs outbound HTTPS to oauth.accounts.firefox.com.</p>
<p><strong>Upgrades:</strong> keep <code>firefox-sync</code> and <code>firefox-sync-migrate</code> on the same image; don't bump the PostgreSQL major.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `firefox-sync` | `firefox-sync.<domain>` | all | `public@file` | :x: |
| `firefox-sync-token` | `firefox-sync.<domain>` | `/1.0/` | `public@file` | :x: |

## AI support

**No AI support:** Signs people in with Mozilla accounts, not Portcullis identities; no MCP server known.

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `firefox-sync` | `ghcr.io/porelli/firefox-sync:syncstorage-rs-postgres-0.24.0` | `sha256:6b4ad5b6ed19…` |
| `firefox-sync-db` | `postgres:17.11-alpine` | `sha256:3540c0362c80…` |
| `firefox-sync-init` | `postgres:17.11-alpine` | `sha256:3540c0362c80…` |
| `firefox-sync-migrate` | `ghcr.io/porelli/firefox-sync:syncstorage-rs-postgres-0.24.0` | `sha256:6b4ad5b6ed19…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Mozilla account ID** | `string` | entered by each person | `restart` | The uid of the Mozilla account you sign in to Firefox with (32 lowercase hexadecimal characters). Only accounts listed here can sync with this server. No two people may enter the same value. Admins may set it for someone. |
| **Other allowed accounts** | `list` of `string` | instance | `restart` | Mozilla account uids (32 lowercase hexadecimal characters) that may sync without being entered by a member of the access group. |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `FIREFOX_SYNC_DB_PASSWORD` | Firefox Sync database owner password (migrations, allowlist) | `random` |
| `FIREFOX_SYNC_APP_DB_PASSWORD` | Firefox Sync database password of the server's own role (no owner rights) | `random` |
| `FIREFOX_SYNC_MASTER_SECRET` | syncstorage-rs master secret (signs the storage tokens) | `random` |
| `FIREFOX_SYNC_METRICS_SECRET` | tokenserver metrics hash secret | `random` |

## Access URLs

- **Token server (identity.sync.tokenserver.uri)**: `https://{{HOST_FIREFOX_SYNC}}/1.0/sync/1.5`
