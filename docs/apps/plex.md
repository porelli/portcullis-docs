# 🎬 Plex

> Media server for movies, TV, music with transcoding and client apps

**Category:** media  
**Tags:** `media`, `movies`, `tv`, `music`, `streaming`  
**Website:** <https://www.plex.tv/personal-media-server/>  
**Source:** none (Plex Media Server is proprietary; Plex publishes no source code for it)

## About

<div class="app-long-description">
<p>Plex Media Server organises movies, TV shows, music and photos and streams them to Plex apps on phones, TVs and browsers, transcoding when a device needs it.</p>
<p>Plex signs people in with their plex.tv accounts, so single sign-on isn't possible. By default Portcullis sign-in and the access group come before Plex's own login.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `custom` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_plex` |
| **Subdomain** | `plex` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Plex uses its own plex.tv account system; no SSO is possible. By default the Hub puts Portcullis sign-in (<code>users_plex</code>) in front of Plex's own login.</p>
<p>The Hub's <strong>Sign-in</strong> setting can switch to Plex's own login only (no Portcullis, TLS tier public), which Plex's native apps need.</p>
<p>Claim token required for initial setup.</p>
<p><strong>Shared folders:</strong> pms-docker's first-run script sets the <code>plex</code> user's uid / gid from <code>PLEX_UID</code> / <code>PLEX_GID</code>, and Plex starts through <code>s6-setuidgid plex</code>, which resets the supplementary groups to plex's own in <code>/etc/group</code> (a <code>group_add</code> gid wouldn't reach Plex). So the library settings join a shared folder's group through <code>PLEX_GID</code> (<code>joins_group: gid_env</code>): the Hub writes the folder gid there.</p>
<p>Keep all three library settings on the same shared folder (subfolders are fine), or all on host paths; a library left empty doesn't count.</p>
</div>

## Sign-in

The app has its own login. The Hub's per-app **Sign-in** setting chooses who signs users in ([Apps with their own login](../operations/auth-policies.md#apps-with-their-own-login)):

- **Portcullis sign-in, then the app's own login** (default): forward-auth and group-gate in front, members of `users_plex`.
- **App's own login only (no Portcullis)**: allowed by this template. No forward-auth, TLS tier `public@file`: anyone on the internet reaches the app's login page.

> Plex signs users in with plex.tv accounts. Behind Portcullis sign-in only the web app in a browser works; Plex's TV, mobile and desktop apps can't pass forward-auth and need "App's own login only".

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `plex` | `plex.<domain>` | all | `public@file` | :x: |

As written in `compose.yml`. With the default [Sign-in](#sign-in) the Hub's override adds `portcullis-auth@docker,portcullis-groups@docker` to every router.

## AI support

**No AI support:** Signs people in with Plex accounts, not Portcullis identities; no MCP server known.

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `plex` | `plexinc/pms-docker:1.43.5.11079-b3b13e506` | `sha256:6d778d41daae…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Movies folder** | `path` | instance | `restart` | Host path to your movies library. Mounted at `/data/movies` (ro). [Shared folder](../operations/hub.md#shared-folders) ready: reads (read-only) as uid `PLEX_UID`, gid `PLEX_GID`; joins the folder's group as its primary group: the Hub writes the folder's gid to `PLEX_GID`. |
| **TV Shows folder** | `path` | instance | `restart` | Host path to your TV shows library. Mounted at `/data/tv` (ro). [Shared folder](../operations/hub.md#shared-folders) ready: reads (read-only) as uid `PLEX_UID`, gid `PLEX_GID`; joins the folder's group as its primary group: the Hub writes the folder's gid to `PLEX_GID`. |
| **Music folder** | `path` | instance | `restart` | Host path to your music library. Mounted at `/data/music` (ro). [Shared folder](../operations/hub.md#shared-folders) ready: reads (read-only) as uid `PLEX_UID`, gid `PLEX_GID`; joins the folder's group as its primary group: the Hub writes the folder's gid to `PLEX_GID`. |
| **Plex user id** | `int` | instance | `restart` | User id Plex Media Server runs as inside the container (PLEX_UID; default 1001, the image's own plex user); it needs read access to the library folders. Default: `1001`. |
| **Plex group id** | `int` | instance | `restart` | Group id Plex Media Server runs as inside the container (PLEX_GID; default 1001). While a library setting uses a shared folder, the Hub sets it to the folder's group. Default: `1001`. |
| **Claim token** | `secret` | instance | `restart` | Plex claim token from https://plex.tv/claim, needed for the initial setup only (it expires a few minutes after it is issued). |

## Access URLs

- **Plex**: `https://{{HOST_PLEX}}`
