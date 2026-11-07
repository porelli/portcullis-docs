# App Catalog

All apps available in Portcullis with their authentication capabilities.
Each app is reachable at `<subdomain>.<your-domain>`.

These pages are generated from the `manifest.yaml` and `compose.yml` files in
[porelli/portcullis-templates](https://github.com/porelli/portcullis-templates);
see the [Manifest Reference](../guides/manifest-reference.md) for the fields.

| App | Subdomain | Category | Auth Method | SSO | Group Access | Group Admin | AI support |
|-----|-----------|----------|-------------|-----|-------------|-------------|------------|
| 💬 [AI Chat](ai-chat.md) | `ai` | ai | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: | AI page |
| 🤖 [LiteLLM](litellm.md) | `llm` | ai | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
| 💬 [Matrix (Synapse + Element)](matrix.md) | `element`, `matrix` | communication | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
| 📏 [CADCraft](cadcraft.md) | `cadcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 📐 [DesignCraft](designcraft.md) | `designcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🎬 [EffectCraft](effectcraft.md) | `effectcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🧩 [FigCraft](figcraft.md) | `figcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🎞 [FilmCraft](filmcraft.md) | `filmcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🌅 [LightCraft](lightcraft.md) | `lightcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 📷 [PhotoCraft](photocraft.md) | `photocraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🎚 [SoundCraft](soundcraft.md) | `soundcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🧱 [TextureCraft](texturecraft.md) | `texturecraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🖋 [VectorCraft](vectorcraft.md) | `vectorcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🗃 [CloudBeaver](cloudbeaver.md) | `db` | devops | `header-auth` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
| 🦊 [GitLab](gitlab.md) | `git` | devops | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
| 🍵 [Gitea](gitea.md) | `gitea` | devops | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| 💰 [Actual Budget](actual-budget.md) | `budget` | finance | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
| 💸 [Firefly III](firefly-iii.md) | `finance` | finance | `header-auth` | :warning: Partial | :white_check_mark: | :x: | :x: |
| 📟 [ESPHome](esphome.md) | `esphome` | home-automation | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🏠 [Home Assistant](homeassistant.md) | `home` | home-automation | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| 🐝 [Zigbee2MQTT](zigbee2mqtt.md) | `zigbee` | home-automation | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 📹 [motionEye](motioneye.md) | `cameras` | home-automation | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 📷 [Immich](immich.md) | `photos` | media | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
| 📺 [Jellyfin](jellyfin.md) | `media` | media | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: | :x: |
| 🎬 [Plex](plex.md) | `plex` | media | `custom` | :x: No | :white_check_mark: | :x: | :x: |
| 📊 [Grafana](grafana.md) | `grafana` | monitoring | `header-auth` | :warning: Partial | :white_check_mark: | :x: | :white_check_mark: |
| 💾 [Scrutiny](scrutiny.md) | `disks` | monitoring | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🛡 [AdGuard Home](adguard.md) | `adguard` | networking | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🚫 [Pi-hole](pihole.md) | `pihole` | networking | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🔍 [Craft Anything](craft-anything.md) | `craft-anything` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 📽 [DeckCraft](deckcraft.md) | `deckcraft` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 📝 [DokuWiki](dokuwiki.md) | `dokuwiki` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: | :x: |
| 🦊 [Firefox Sync](firefox-sync.md) | `firefox-sync` | productivity | `custom` | :x: No | :x: | :x: | :x: |
| 🧮 [GridCraft](gridcraft.md) | `gridcraft` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 📋 [Kanboard](kanboard.md) | `kanboard` | productivity | `header-auth` | :warning: Partial | :white_check_mark: | :x: | :x: |
| 💬 [Mattermost](mattermost.md) | `chat` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 🍽 [Mealie](mealie.md) | `recipes` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: | :x: |
| ☁️ [Nextcloud](nextcloud.md) | `cloud` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| 🗂 [OxiCloud](oxicloud.md) | `drive` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: | :x: |
| 📄 [Paperless-ngx](paperless.md) | `paperless` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: | :x: |
| 📄 [PdfCraft](pdfcraft.md) | `pdfcraft` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| ✅ [Vikunja](vikunja.md) | `tasks` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
| 📖 [Wiki.js](wiki.md) | `wiki` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: | :x: |
| 📝 [WordCraft](wordcraft.md) | `wordcraft` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: | :x: |
| 📄 [Docs Site](docs.md) | `docs` | public | `public` | :x: No | :x: | :x: | :x: |
| 🖥 [Apache Guacamole](guacamole.md) | `remote` | remote-access | `header-auth` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
| 🔐 [Vaultwarden](vaultwarden.md) | `passwords` | security | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
| 📂 [Samba](samba.md) | — | storage | `custom` | :x: No | :white_check_mark: | :x: | :x: |
| 🕰 [Time Machine](timemachine.md) | — | storage | `custom` | :x: No | :white_check_mark: | :x: | :x: |
| 🌐 [Headscale](headscale.md) | `vpn-admin`, `vpn` | vpn | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
| 🐦 [NetBird](netbird.md) | `netbird` | vpn | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: | :x: |
