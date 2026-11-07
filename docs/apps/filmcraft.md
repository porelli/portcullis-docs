# 🎞 FilmCraft

> Non-linear video editor by ArtCraft, running entirely in the browser (Rust/WebAssembly; files stay on your device). In development.

**Category:** creative  
**Tags:** `artcraft`, `wasm`, `video`, `editor`, `nle`  
**Website:** <https://getartcraft.com/apps/filmcraft>  
**Source:** <https://github.com/storytold/filmcraft>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_filmcraft` |
| **Admin Group** | `admin_filmcraft` |
| **Subdomain** | `filmcraft` |

!!! info "Auth Notes"
    In development upstream (https://getartcraft.com/apps): expect missing features and breaking changes between versions. FilmCraft (https://github.com/storytold/filmcraft, Apache-2.0 OR MIT) is a static site: the app runs in the visitor's browser and has no user system, no server-side code and no server-side storage. Open uses the browser's file picker, Save/Export download files; preferences live in the browser's storage for this hostname. Portcullis sign-in (forward-auth + group-gate) is the only login; every member of the access group gets the same app (there are no roles). At every start the filmcraft-fetch init container downloads the release's filmcraft-web-<version>.zip from GitHub, checks its SHA-256 against the pin before unpacking, and swaps the unpacked site into the filmcraft-site volume by rename; on any error it exits non-zero and the web server doesn't start (an unchanged pin skips the download). The host needs outbound HTTPS to github.com. The web server (nginx-unprivileged, read-only, no directory listing) answers only Traefik and itself. Version: the Release version / Release SHA-256 settings default to the pin in compose.yml (bumped with the template); set both together, from the release's SHA256SUMS.txt, to pin another release.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `filmcraft` | `filmcraft.<domain>` | all | `authaware@file` | :white_check_mark: |

## AI support

**No AI support:** Runs entirely in the browser; files stay on the person's device, so there is nothing on the server for an AI to reach.

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `filmcraft` | `nginxinc/nginx-unprivileged:1.31.7-alpine3.24` | `sha256:b5047b9b7684…` |
| `filmcraft-fetch` | `alpine:3.24.3` | `sha256:be2656061b53…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Release version** | `string` | instance | `restart` | FilmCraft release to serve (x.y.z, without the "v"). Empty = the version pinned in compose.yml. Set the release SHA-256 with it. |
| **Release SHA-256** | `string` | instance | `restart` | SHA-256 of filmcraft-web-&lt;version&gt;.zip (lowercase hex, from the release's SHA256SUMS.txt). Empty = the pin in compose.yml. A mismatch stops the start. |

## Access URLs

- **Open FilmCraft**: `https://{{HOST_FILMCRAFT}}`
