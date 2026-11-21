# 🐝 Zigbee2MQTT

> Zigbee to MQTT bridge with its web frontend and a bundled, password-protected Mosquitto broker

**Category:** home-automation  
**Tags:** `home-automation`, `zigbee`, `mqtt`, `iot`, `smart-home`  
**Website:** <https://www.zigbee2mqtt.io/>  
**Source:** <https://github.com/Koenkk/zigbee2mqtt>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_zigbee2mqtt` |
| **Admin Group** | `admin_zigbee2mqtt` |
| **Subdomain** | `zigbee` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Zigbee2MQTT 2.14 behind Portcullis sign-in (forward-auth + group-gate on the whole host), with a bundled Mosquitto broker. Every member of the access group has full control: pairing, device settings, OTA, the network key in Settings.</p>
<p><strong>No user system:</strong> its frontend's only protection is an optional shared <code>auth_token</code>. It runs without one here: forward-auth + group-gate is the sign-in.</p>
<ul>
<li>The frontend is on the instance's private network only; the gate in front of it (nginx, the only container on <code>portcullis-proxy</code>) answers Traefik's address alone, so no other container reaches it unauthenticated.</li>
<li>The gate never forwards the Portcullis session (<code>Authorization</code>, access-token headers, forward-auth cookies) to the frontend.</li>
<li>Zigbee2MQTT's onboarding wizard and failure page never open (<code>Z2M_ONBOARD_NO_SERVER</code>): they would configure the instance for whoever reaches them first. The instance settings are applied at every start instead (they override edits made in the frontend's Settings for the same keys).</li>
<li>External JavaScript (extensions and converters, arbitrary code) is off unless the instance setting turns it on.</li>
</ul>
<p><strong>Coordinator:</strong> set either</p>
<ul>
<li><strong>Serial device</strong>: the host path of a USB coordinator, best a stable <code>/dev/serial/by-id/...</code> path; only that device is passed into the container, not privileged, so several instances can each drive their own coordinator; a path that doesn't exist on the host stops the container from starting; or</li>
<li><strong>Network coordinator</strong>: <code>tcp://host:port</code> of an Ethernet/Wi-Fi coordinator such as an SLZB-06 or a ser2net bridge, reached outbound, with its <strong>Adapter type</strong>.</li>
</ul>
<p>With neither, Zigbee2MQTT is not started and its log says what to set. No host networking is needed: mDNS discovery of network coordinators isn't available, give their address.</p>
<p><strong>MQTT:</strong> by default the bundled Mosquitto 2.1 on the instance's private network, anonymous clients refused, two accounts with generated passwords (<code>zigbee2mqtt</code> for the bridge, <code>homeassistant</code> for Home Assistant), ACL limited to <code>zigbee2mqtt/#</code> and <code>homeassistant/#</code> (the base topic is fixed to <code>zigbee2mqtt</code>).</p>
<ul>
<li>Passwords are written hashed by <code>mosquitto-init</code> at every start; Zigbee2MQTT stores its own MQTT password in <code>configuration.yaml</code> in its data volume (upstream behaviour).</li>
<li>Or set <strong>MQTT server</strong> (+ user and password) to use an existing broker, e.g. the one Home Assistant uses (the bundled broker then idles).</li>
</ul>
<p><strong>The <code>homeassistant</code> account</strong> has an allowlist only (Zigbee2MQTT matches bridge requests case-insensitively, so writes are never denylisted):</p>
<ul>
<li>allowed: discovery (read <code>homeassistant/#</code>, write <code>homeassistant/status</code>), device and group state, endpoint state, availability and device-trigger actions, the bridge's state, info (its configuration without the network key, MQTT password and frontend token), devices, groups and event topics, <code>&lt;name&gt;[/&lt;endpoint&gt;]/set|get</code> commands and the <code>permit_join</code> request;</li>
<li>never <code>bridge/logging</code> (where Zigbee2MQTT logs every MQTT publish with its payload), the extension / converter JavaScript source, definitions or health; never other bridge requests (extensions, converters, options, backup, restart, OTA updates, ...) nor bridge responses.</li>
</ul>
<p>So in Home Assistant the bridge's log level select and restart button and the firmware update entities (Zigbee2MQTT OTA update requests) are refused, and Home Assistant can't clear retained discovery messages (deleting a device in Home Assistant leaves its discovery config; remove the device in Zigbee2MQTT, which clears it). Use friendly names without <code>/</code> (availability and two-level names aren't covered), or your own broker via <strong>MQTT server</strong>.</p>
<p><strong>Home Assistant:</strong> with <strong>Home Assistant discovery</strong> on, Zigbee2MQTT publishes discovery messages. In Home Assistant add the MQTT integration with the broker address <code>host:&lt;MQTT port&gt;</code>, user <code>homeassistant</code> and the password <code>Z2M_BROKER_HA_PASSWORD</code> from this instance's <code>.env</code> (Hub data <code>env/&lt;instance&gt;.env</code>).</p>
<ul>
<li>The MQTT port (default 1883) is bound to 127.0.0.1 by default; set its bind address to the host's LAN address (or 0.0.0.0) for a Home Assistant on another machine or in a container, or clear the port to keep the broker private.</li>
<li>It is plain MQTT without TLS, protected by the password: use it on a trusted network only.</li>
<li>Each instance needs its own MQTT port (the Hub's port collision check).</li>
<li>The frontend's &quot;Open in Home Assistant&quot; links and device pages link to this instance's hostname.</li>
</ul>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `zigbee2mqtt` | `zigbee.<domain>` | all | `authaware@file` | :white_check_mark: |

## AI support

**No AI support:** No official or vetted community MCP server known (surveyed 2026-11-05).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `mosquitto` | `eclipse-mosquitto:2.1.2-alpine` | `sha256:860aeb5d63ce…` |
| `mosquitto-init` | `eclipse-mosquitto:2.1.2-alpine` | `sha256:860aeb5d63ce…` |
| `zigbee2mqtt` | `ghcr.io/koenkk/zigbee2mqtt:2.14.3` | `sha256:fb4a6b0f6868…` |
| `zigbee2mqtt-gate` | `nginx:1.31.8-alpine` | `sha256:fed7e14be83c…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Serial device** | `string` | instance | `restart` | Host path of a USB Zigbee coordinator, e.g. /dev/serial/by-id/usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_...-if00-port0 or /dev/ttyUSB0 (empty = none). |
| **Network coordinator** | `string` | instance | `restart` | tcp://&lt;host&gt;:&lt;port&gt; of a network (Ethernet/Wi-Fi) coordinator, e.g. tcp://192.168.1.50:6638; used instead of the serial device when set. Needs the Adapter type. |
| **Adapter type** | `enum` | instance | `restart` | Coordinator firmware type: ember (Silicon Labs EFR32, e.g. Sonoff ZBDongle-E, SLZB-06M), zstack (Texas Instruments CC2652/CC1352, e.g. Sonoff ZBDongle-P), deconz (ConBee/RaspBee), zigate, zboss, zoh; auto lets Zigbee2MQTT detect a USB adapter. Choices: `auto`, `ember`, `zstack`, `deconz`, `zigate`, `zboss`, `zoh`. Default: `auto`. |
| **Home Assistant discovery** | `bool` | instance | `restart` | Publish Home Assistant MQTT discovery messages (homeassistant/#). Default: `true`. |
| **External extensions and converters** | `bool` | instance | `restart` | Allow Zigbee2MQTT's external JavaScript (extensions and converters saved from the frontend or over MQTT): arbitrary code that runs in the Zigbee2MQTT container. Off by default. Default: `false`. |
| **MQTT server** | `string` | instance | `restart` | An existing broker instead of the bundled one, e.g. mqtt://192.168.1.10:1883 or mqtts://broker.lan:8883 (empty = the bundled Mosquitto). |
| **MQTT user** | `string` | instance | `restart` | User for the MQTT server above (ignored for the bundled broker). |
| **MQTT password** | `secret` | instance | `restart` | Password for the MQTT server above (ignored for the bundled broker). |

## Host Ports

Ports this app binds on the host. Collisions with other enabled apps block enable; each binding can be rebound or disabled from the Hub UI.

| Port | Protocol | Default | Container | Required | Notes |
|------|----------|---------|-----------|----------|-------|
| **MQTT (bundled broker)** | `tcp` | `1883` | `1883` | :x: | — |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `Z2M_BROKER_PASSWORD` | Bundled Mosquitto password of the zigbee2mqtt user (the bridge) | `random` |
| `Z2M_BROKER_HA_PASSWORD` | Bundled Mosquitto password of the homeassistant user (Home Assistant's MQTT integration) | `random` |

## Access URLs

- **Frontend**: `https://{{HOST_ZIGBEE2MQTT}}`
