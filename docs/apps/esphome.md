# 📟 ESPHome

> ESPHome Device Builder — write, compile and flash ESP32/ESP8266 firmware from YAML

**Category:** home-automation  
**Tags:** `home-automation`, `esphome`, `iot`, `firmware`, `esp32`, `smart-home`  
**Website:** <https://esphome.io/>  
**Source:** <https://github.com/esphome/esphome>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_esphome` |
| **Admin Group** | `admin_esphome` |
| **Subdomain** | `esphome` |

!!! info "Auth Notes"
    ESPHome 2026.10's dashboard is ESPHome Device Builder (esphome-device-builder 1.25.0 in the image; ESPHome removed its legacy dashboard in 2026.7). It has no user system: its only login is an optional single username/password (ESPHOME_USERNAME / ESPHOME_PASSWORD), and without one every peer that reaches port 6052 is fully trusted. Here it runs without that password: forward-auth + group-gate on the whole host is the sign-in, and every member of the access group can do everything (edit device YAML and secrets.yaml, which hold Wi-Fi passwords and API keys, compile, flash). The dashboard is on the instance's private network only; the gate in front of it (nginx, the only container on portcullis-proxy) answers Traefik's address alone, so no other container can reach the dashboard unauthenticated. The gate never forwards the Portcullis session to the dashboard (Authorization, access-token headers and the forward-auth cookies are removed), since members can run code there (compiles). ESPHOME_TRUSTED_DOMAINS is the instance hostname (upstream's websocket Host/Origin check). Networking: bridge networks only, never host networking (the dashboard would then listen on every host address past the gateway, and instances would collide on port 6052), which is why several instances can run side by side. Without host networking there is no mDNS: the dashboard can't discover new devices or resolve <name>.local, so give every device a fixed address it can reach (wifi use_address or manual_ip, or a DNS name your router serves). Online status then comes from the dashboard's ICMP ping sweep, and OTA updates and logs connect to that address from the container (outbound, routed through the host). Flashing over USB: the browser's Web Serial install (Chrome/Edge, HTTPS) works as-is; to flash from the server instead, set "Serial port" to the host device (e.g. /dev/serial/by-id/usb-...), passed into the container (only that one, not privileged; a path that doesn't exist on the host stops the container from starting). The Home Assistant ESPHome integration's dashboard link (firmware updates from Home Assistant) needs direct, unauthenticated access to the dashboard API and doesn't work behind the gateway; the devices' own native API (port 6053 on each device) is unaffected. Compiling downloads toolchains from the internet on first use (kept in the cache volume) and needs a few GB of memory and disk. The optional remote-build listener (Settings, off by default) is reachable only inside the instance's private network.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `esphome` | `esphome.<domain>` | all | `authaware@file` | :white_check_mark: |

## AI support

**No AI support:** No official or vetted community MCP server known (surveyed 2026-11-05).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `esphome` | `ghcr.io/esphome/esphome:2026.10.2` | `sha256:4a918585150e…` |
| `esphome-gate` | `nginx:1.31.8-alpine` | `sha256:785835ea65db…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Serial port** | `string` | instance | `restart` | Optional host USB serial device for flashing from the server, e.g. /dev/serial/by-id/usb-Silicon_Labs_CP2102-if00-port0 or /dev/ttyUSB0 (empty = none; flashing from the browser works without it). |

## Access URLs

- **Device Builder**: `https://{{HOST_ESPHOME}}`
