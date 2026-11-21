# 🎚 SoundCraft

> Digital audio workstation by ArtCraft, running entirely in the browser (Rust/WebAssembly; files stay on your device). In development.

**Category:** creative  
**Tags:** `artcraft`, `wasm`, `audio`, `daw`, `music`  
**Website:** <https://getartcraft.com/apps/soundcraft>  
**Source:** <https://github.com/storytold/soundcraft>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_soundcraft` |
| **Admin Group** | `admin_soundcraft` |
| **Subdomain** | `soundcraft` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p><a target="_blank" rel="noopener noreferrer nofollow" href="https://github.com/storytold/soundcraft">SoundCraft</a> (Apache-2.0 OR MIT) is a static site: the app runs in the visitor's browser and has no user system, no server-side code and no server-side storage. Portcullis sign-in (forward-auth + group-gate) is the only login.</p>
<p><strong>In development upstream</strong> (<a target="_blank" rel="noopener noreferrer nofollow" href="https://getartcraft.com/apps">https://getartcraft.com/apps</a>): expect missing features and breaking changes between versions.</p>
<ul>
<li>Every member of the access group gets the same app (there are no roles).</li>
<li>Open uses the browser's file picker, Save/Export download files; preferences live in the browser's storage for this hostname.</li>
</ul>
<p><strong>How it is served:</strong> at every start the <code>soundcraft-fetch</code> init container downloads the release's <code>soundcraft-web-&lt;version&gt;.zip</code> from GitHub, checks its SHA-256 against the pin before unpacking, and swaps the unpacked site into the <code>soundcraft-site</code> volume by rename. On any error it exits non-zero and the web server doesn't start (an unchanged pin skips the download).</p>
<ul>
<li>The host needs outbound HTTPS to github.com.</li>
<li>The web server (nginx-unprivileged, read-only, no directory listing) answers only Traefik and itself.</li>
</ul>
<p><strong>Version:</strong> the <strong>Release version</strong> / <strong>Release SHA-256</strong> settings default to the pin in <code>compose.yml</code> (bumped with the template); set both together, from the release's <code>SHA256SUMS.txt</code>, to pin another release.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `soundcraft` | `soundcraft.<domain>` | all | `authaware@file` | :white_check_mark: |

## AI support

**No AI support:** Runs entirely in the browser; files stay on the person's device, so there is nothing on the server for an AI to reach.

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `soundcraft` | `nginxinc/nginx-unprivileged:1.31.7-alpine3.24` | `sha256:b5047b9b7684…` |
| `soundcraft-fetch` | `alpine:3.24.4` | `sha256:f59abe656b69…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Release version** | `string` | instance | `restart` | SoundCraft release to serve (x.y.z, without the "v"). Empty = the version pinned in compose.yml. Set the release SHA-256 with it. |
| **Release SHA-256** | `string` | instance | `restart` | SHA-256 of soundcraft-web-&lt;version&gt;.zip (lowercase hex, from the release's SHA256SUMS.txt). Empty = the pin in compose.yml. A mismatch stops the start. |

## Access URLs

- **Open SoundCraft**: `https://{{HOST_SOUNDCRAFT}}`
