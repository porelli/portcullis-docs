# 📹 motionEye

> Video surveillance for network and USB cameras — motion detection, recording, live view

**Category:** home-automation  
**Tags:** `home-automation`, `cameras`, `surveillance`, `cctv`, `motion-detection`  
**Website:** <https://github.com/motioneye-project/motioneye>  
**Source:** <https://github.com/motioneye-project/motioneye>

## About

<div class="app-long-description">
<p>motionEye is a web interface for the motion video surveillance software. It shows live views of network and USB cameras, detects motion, and records movies and still images with schedules.</p>
<p>Portcullis sign-in and the access group protect the whole web interface, and motionEye's own login stays as a second step.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_motioneye` |
| **Admin Group** | `admin_motioneye` |
| **Subdomain** | `cameras` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>motionEye 0.44 (motioneye-project, maintained: 0.44.0 in June 2026) has no SSO. Access is gated by forward-auth + group-gate on the whole host, and motionEye's own login (accounts <code>admin</code> and <code>user</code>) stays as a second step.</p>
<p><strong>Its two local accounts:</strong> <code>admin</code> (full configuration) and <code>user</code> (view only), whose passwords are empty after a fresh install.</p>
<ul>
<li><code>motioneye-init</code> sets each account with an empty password to a generated one before every start (<code>MOTIONEYE_ADMIN_PASSWORD</code> / <code>MOTIONEYE_USER_PASSWORD</code> in this instance's <code>.env</code>, Hub data <code>env/&lt;instance&gt;.env</code>; hashed by motionEye, argon2), so motionEye never runs with its well-known empty default, and the healthcheck fails while either is empty.</li>
<li>Share the admin password with your camera administrators and the user password with viewers; a password changed in motionEye's settings is kept (clearing one sets the generated value again at the next start).</li>
<li>motionEye doesn't read any identity header, so no LLDAP user name maps to these accounts.</li>
<li>The admin account can do everything motionEye can, including commands run on motion events inside the container.</li>
</ul>
<p><strong>The gate:</strong> the UI is on the instance's private network only; the gate in front of it (nginx, the only container on <code>portcullis-proxy</code>) answers Traefik's address alone, never forwards the Portcullis session (<code>Authorization</code>, access-token headers, forward-auth cookies), and is healthy (= routed) only while motionEye refuses an empty password for the <code>admin</code> and <code>user</code> account names.</p>
<p><strong>Cameras:</strong> network cameras by URL (RTSP, HTTP/MJPEG; added in motionEye, reached outbound from the container) and up to four local V4L2 cameras listed in the <strong>Local cameras</strong> setting (e.g. <code>/dev/video0</code>; only those are passed in, not privileged, so several instances can each use their own; a path that doesn't exist on the host stops the container from starting). Live view goes through motionEye's own UI; motion's direct streaming ports (8081+, &quot;Video Streaming&quot; in the camera settings) are not published, so direct stream URLs only work inside the instance.</p>
<p><strong>Storage:</strong> set <strong>Storage folder</strong> to a host path (e.g. <code>/srv/cctv</code>) to record there instead of the instance's media volume; keep an eye on its size (motionEye's own &quot;Preserve&quot; settings delete old media).</p>
<p>Not available in a container: shutdown/reboot, and SMB share mounts.</p>
<p><strong>Shared folders:</strong> motionEye runs as root (uid 0 / gid 0, the image's <code>motion</code> user; no compose <code>user:</code>) and writes the Storage folder, so it declares access <code>write</code> with <code>runs_as</code> uid 0 / gid 0. Root is what lets it write a shared folder: the entrypoint starts motionEye with <code>su -g</code>, which drops supplementary groups, so the folder group the Hub adds through <code>group_add</code> never reaches the process.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `motioneye` | `cameras.<domain>` | all | `default` | :white_check_mark: |

## AI support

**No AI support:** No official or vetted community MCP server known (surveyed 2026-11-05).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `motioneye` | `ghcr.io/motioneye-project/motioneye:0.44.0` | `sha256:7da31d62e6c4…` |
| `motioneye-gate` | `nginx:1.31.8-alpine` | `sha256:fed7e14be83c…` |
| `motioneye-init` | `ghcr.io/motioneye-project/motioneye:0.44.0` | `sha256:7da31d62e6c4…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Storage folder** | `path` | instance | `restart` | Host folder for recordings and pictures (empty = the instance's own volume). Mounted at `/var/lib/motioneye` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as root; the Hub adds the folder's group (`group_add`). |
| **Time zone** | `string` | instance | `restart` | IANA time zone for timestamps and schedules, e.g. Europe/Rome (default UTC). |
| **Local cameras** | `list` of `string` | instance | `restart` | Device paths of local (USB/V4L2) cameras, e.g. /dev/video0 (up to 4; empty = none). |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `MOTIONEYE_ADMIN_PASSWORD` | Initial password of motionEye's admin account | `random` |
| `MOTIONEYE_USER_PASSWORD` | Initial password of motionEye's view-only user account | `random` |

## Access URLs

- **Cameras**: `https://{{HOST_MOTIONEYE}}`
