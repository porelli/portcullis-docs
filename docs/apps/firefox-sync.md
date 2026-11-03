# 🦊 Firefox Sync

> Self-hosted Firefox Sync server (bookmarks, passwords, history, tabs) for Mozilla accounts

**Category:** productivity  
**Tags:** `firefox`, `sync`, `bookmarks`, `browser`, `mozilla`  
**Website:** <https://mozilla-services.github.io/syncstorage-rs/>  
**Source:** <https://github.com/porelli/firefox-sync>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `custom` |
| **SSO** | :x: No |
| **Group Access** | :x: |
| **Group Admin** | :x: |
| **Access Group** | `users_firefox-sync` |
| **Subdomain** | `firefox-sync` |

!!! info "Auth Notes"
    Mozilla's syncstorage-rs 0.24.0 (Sync storage + tokenserver; upstream https://github.com/mozilla-services/syncstorage-rs), as built by porelli/firefox-sync (PostgreSQL image; links.source). Firefox signs in with a Mozilla account at accounts.firefox.com, then calls this server's tokenserver with that account's OAuth token, which the tokenserver verifies with Mozilla and exchanges for a short-lived storage token (1 h). Why no Portcullis sign-in (method custom, no native_login): Firefox makes every Sync and tokenserver request in the background as an anonymous request, without cookies, HTTP authentication or a client certificate (RESTRequest LOAD_ANONYMOUS, resource.sys.mjs fetch; tested by porelli/firefox-sync with a sign-in proxy and with mTLS: "no_node_found" / NS_ERROR_NET_UNCLEAN_SHUTDOWN). Portcullis sign-in, group-gate or a client-certificate tier in front of this host would break every Firefox, so the host is open (public@file, rate-limit; the tokenserver path /1.0/ the stricter rate-limit-auth; syncstorage-rs enforces its own request size limits) and access is decided by the server itself. Exposed on the host: GET /1.0/sync/1.5 (tokenserver: a Mozilla OAuth token with the Sync scope is required, 401 otherwise), /1.5/<uid>/... (storage: Hawk-signed with this instance's secret, 401 otherwise), /__heartbeat__, /__lbheartbeat__, /__version__, /__error__ (a test error), / and the API docs (/swagger-ui, /api-doc/openapi.json). No password, no sign-up page, no admin UI. Database roles: the internet-facing server connects as firefoxsync_app, which owns no table and is no superuser (it can't drop or disable the allowlist trigger, change session_replication_role or write the allowlist) and may create no database object (an event trigger; it keeps CREATE on the schema only for syncstorage-rs' no-op migration check). It runs no migrations; firefox-sync-migrate and firefox-sync-init use the owner and are not reachable. Who can sync: the Mozilla accounts on the allowlist, which is the uids the members of the access group (users_firefox-sync) entered themselves on My apps (Mozilla account ID; one uid per person, and no two people may register the same uid; admins may enter or clear one for someone), plus the instance's Other allowed accounts (uids not tied to a Portcullis person). The Hub writes them to the data file allowlist.json; at every start firefox-sync-init (guard.sql) installs exactly that list before the server starts, and a database trigger refuses every other account: no tokenserver row, no token, no storage. Nobody listed (the default) = nobody syncs; a missing, unparsable or invalid allowlist.json stops the instance (fail closed). Someone who leaves the access group drops off the list at the next delivery (the instance restarts within about a minute): that account's tokenserver rows are deleted, its tokens expire within the hour and it can't get new ones (its encrypted data stays, unreachable). Their entered uid is kept and comes back if they rejoin. Identity: Mozilla accounts, not Portcullis. Firefox has no way to use Keycloak or LLDAP for Sync (the self-hosted Mozilla accounts stack has no external OIDC login and is not published as an image), so the access group decides only who may register a uid, not who signs in to Firefox: whoever holds a listed Mozilla account can sync. Sync data is end-to-end encrypted with keys derived from the Mozilla account: this server, and whoever controls it, can't read it. Self-hosted Mozilla accounts (porelli/firefox-sync's fxa-mono option) are not offered: they need an SMTP server, MySQL and Redis, three more public hosts, a 5 GB image and 3-4 GB of RAM, and they are a second, password-based account system on the internet that Portcullis can't gate (Firefox calls the accounts API anonymously too). A separate template may add them later. The allowlist uses firefox-sync's table (sync_allowed_accounts) with a stricter trigger: it raises (no row, no token) instead of skipping the row, and an empty list refuses everybody instead of turning the allowlist off. Finding a uid: in a Firefox signed in to the account, Browser Console (devtools.chrome.enabled = true) - (await ChromeUtils.importESModule("resource://gre/modules/FxAccounts.sys.mjs").getFxAccountsSingleton().getSignedInUser()).uid - or let the person try: the refused uid is in the firefox-sync-db log ("portcullis: Firefox account <uid> is not on the allowlist"). Firefox setup: about:config identity.sync.tokenserver.uri = https://<this host>/1.0/sync/1.5 (Android: Sync Debug > Custom Sync server; iOS: Advanced Sync Settings), before signing in to the account. After a hostname change every Firefox must be pointed at the new URL; the accounts move to the new node at the next start. Node load: the tokenserver counts a new account in the node's load before the trigger refuses it, so one valid Mozilla token replayed would otherwise fill the node; every start sets the node's capacity to the maximum (2147483647) and recounts the load from its accounts. Residuals: the tokenserver needs outbound HTTPS to oauth.accounts.firefox.com. Upgrades: keep firefox-sync and firefox-sync-migrate on the same image; don't bump the PostgreSQL major.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `firefox-sync` | `firefox-sync.<domain>` | all | `public@file` | :x: |
| `firefox-sync-token` | `firefox-sync.<domain>` | `/1.0/` | `public@file` | :x: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `firefox-sync` | `ghcr.io/porelli/firefox-sync:syncstorage-rs-postgres-0.24.0` | `sha256:6b4ad5b6ed19…` |
| `firefox-sync-db` | `postgres:17.11-alpine` | `sha256:266d3c257594…` |
| `firefox-sync-init` | `postgres:17.11-alpine` | `sha256:266d3c257594…` |
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
