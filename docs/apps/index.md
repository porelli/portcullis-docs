# App Catalog

All apps available in Portcullis with their authentication capabilities.
Each app is reachable at `<subdomain>.<your-domain>`.

These pages are generated from the `manifest.yaml` and `compose.yml` files in
[porelli/portcullis-templates](https://github.com/porelli/portcullis-templates);
see the [Manifest Reference](../guides/manifest-reference.md) for the fields.

| App | Subdomain | Category | Auth Method | SSO | Group Access | Group Admin |
|-----|-----------|----------|-------------|-----|-------------|-------------|
| 🤖 [LiteLLM](litellm.md) | `llm` | ai | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 💬 [Matrix (Synapse + Element)](matrix.md) | `element`, `matrix` | communication | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 📏 [CADCraft](cadcraft.md) | `cadcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📐 [DesignCraft](designcraft.md) | `designcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🎬 [EffectCraft](effectcraft.md) | `effectcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🧩 [FigCraft](figcraft.md) | `figcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🎞 [FilmCraft](filmcraft.md) | `filmcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🌅 [LightCraft](lightcraft.md) | `lightcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📷 [PhotoCraft](photocraft.md) | `photocraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🎚 [SoundCraft](soundcraft.md) | `soundcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🧱 [TextureCraft](texturecraft.md) | `texturecraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🖋 [VectorCraft](vectorcraft.md) | `vectorcraft` | creative | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🗃 [CloudBeaver](cloudbeaver.md) | `db` | devops | `header-auth` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 🦊 [GitLab](gitlab.md) | `git` | devops | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 🍵 [Gitea](gitea.md) | `gitea` | devops | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: |
| 💰 [Actual Budget](actual-budget.md) | `budget` | finance | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 💸 [Firefly III](firefly-iii.md) | `finance` | finance | `header-auth` | :warning: Partial | :white_check_mark: | :x: |
| 📷 [Immich](immich.md) | `photos` | media | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 📺 [Jellyfin](jellyfin.md) | `media` | media | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: |
| 🎬 [Plex](plex.md) | `plex` | media | `custom` | :x: No | :white_check_mark: | :x: |
| 📊 [Grafana](grafana.md) | `grafana` | monitoring | `header-auth` | :warning: Partial | :white_check_mark: | :x: |
| 💾 [Scrutiny](scrutiny.md) | `disks` | monitoring | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🛡 [AdGuard Home](adguard.md) | `adguard` | networking | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🚫 [Pi-hole](pihole.md) | `pihole` | networking | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🔍 [Craft Anything](craft-anything.md) | `craft-anything` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📽 [DeckCraft](deckcraft.md) | `deckcraft` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📝 [DokuWiki](dokuwiki.md) | `dokuwiki` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: |
| 🧮 [GridCraft](gridcraft.md) | `gridcraft` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📋 [Kanboard](kanboard.md) | `kanboard` | productivity | `header-auth` | :warning: Partial | :white_check_mark: | :x: |
| 🍽 [Mealie](mealie.md) | `recipes` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: |
| ☁ [Nextcloud](nextcloud.md) | `cloud` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: |
| 📄 [Paperless-ngx](paperless.md) | `paperless` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: |
| 📄 [PdfCraft](pdfcraft.md) | `pdfcraft` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📖 [Wiki.js](wiki.md) | `wiki` | productivity | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: |
| 📝 [WordCraft](wordcraft.md) | `wordcraft` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📄 [Docs Site](docs.md) | `docs` | public | `public` | :x: No | :x: | :x: |
| 🖥 [Apache Guacamole](guacamole.md) | `remote` | remote-access | `header-auth` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 🔒 [Vault UI](vault-ui.md) | `vault` | security | `mtls` | :x: No | :x: | :x: |
| 🔐 [Vaultwarden](vaultwarden.md) | `passwords` | security | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 🌐 [Headscale](headscale.md) | `vpn-admin`, `vpn` | vpn | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 🐦 [NetBird](netbird.md) | `netbird` | vpn | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
