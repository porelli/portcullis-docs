# 🎬 Plex

> Media server for movies, TV, music with transcoding and client apps

**Category:** media  
**Tags:** `media`, `movies`, `tv`, `music`, `streaming`  
**Website:** <https://www.plex.tv/personal-media-server/>  
**Source:** none (Plex Media Server is proprietary; Plex publishes no source code for it)

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `custom` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_plex` |
| **Subdomain** | `plex` |

!!! info "Auth Notes"
    Plex uses its own plex.tv account system; no SSO is possible. By default the Hub puts Portcullis sign-in (users_plex) in front of Plex's own login; the Hub's Sign-in setting can switch to Plex's own login only (no Portcullis, TLS tier public), which Plex's native apps need. Claim token required for initial setup.

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

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `plex` | `plexinc/pms-docker:1.43.5.11079-b3b13e506` | `sha256:6d778d41daae…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Movies folder** | `path` | instance | `restart` | Host path to your movies library. Mounted at `/data/movies` (ro). |
| **TV Shows folder** | `path` | instance | `restart` | Host path to your TV shows library. Mounted at `/data/tv` (ro). |
| **Music folder** | `path` | instance | `restart` | Host path to your music library. Mounted at `/data/music` (ro). |
| **Plex user id** | `int` | instance | `restart` | User id Plex Media Server runs as inside the container (PLEX_UID; default 1001, the image's own plex user); it needs read access to the library folders. Default: `1001`. |
| **Plex group id** | `int` | instance | `restart` | Group id Plex Media Server runs as inside the container (PLEX_GID; default 1001). Default: `1001`. |
| **Claim token** | `secret` | instance | `restart` | Plex claim token from https://plex.tv/claim, needed for the initial setup only (it expires a few minutes after it is issued). |

## Access URLs

- **Plex**: `https://{{HOST_PLEX}}`
