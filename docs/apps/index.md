# App Catalog

All apps available in Portcullis with their authentication capabilities.
Each app is reachable at `<subdomain>.<your-domain>`.

These pages are generated from the `manifest.yaml` and `compose.yml` files in
[porelli/portcullis-templates](https://github.com/porelli/portcullis-templates);
see the [Manifest Reference](../guides/manifest-reference.md) for the fields.

| App | Subdomain | Category | Auth Method | SSO | Group Access | Group Admin |
|-----|-----------|----------|-------------|-----|-------------|-------------|
| 🤖 [LiteLLM](litellm.md) | `llm` | ai | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 🗃 [CloudBeaver](cloudbeaver.md) | `db` | devops | `header-auth` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 🦊 [GitLab](gitlab.md) | `git` | devops | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 💰 [Actual Budget](actual-budget.md) | `budget` | finance | `native-oidc` | :white_check_mark: Yes | :x: | :x: |
| 💸 [Firefly III](firefly-iii.md) | `finance` | finance | `header-auth` | :warning: Partial | :white_check_mark: | :x: |
| 📷 [Immich](immich.md) | `photos` | media | `native-oidc` | :white_check_mark: Yes | :x: | :x: |
| 📺 [Jellyfin](jellyfin.md) | `media` | media | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :white_check_mark: |
| 🎬 [Plex](plex.md) | `plex` | media | `custom` | :x: No | :white_check_mark: | :x: |
| 📊 [Grafana](grafana.md) | `grafana` | monitoring | `header-auth` | :warning: Partial | :white_check_mark: | :x: |
| 💾 [Scrutiny](scrutiny.md) | `disks` | monitoring | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🛡 [AdGuard Home](adguard.md) | `adguard` | networking | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 🚫 [Pi-hole](pihole.md) | `pihole` | networking | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📝 [DokuWiki](dokuwiki.md) | `dokuwiki` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📋 [Kanboard](kanboard.md) | `kanboard` | productivity | `header-auth` | :warning: Partial | :white_check_mark: | :x: |
| ☁ [Nextcloud](nextcloud.md) | `cloud` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📖 [Wiki.js](wiki.md) | `wiki` | productivity | `forward-auth` | :x: No | :white_check_mark: | :x: |
| 📄 [Docs Site](docs.md) | `docs` | public | `public` | :x: No | :x: | :x: |
| 🖥 [Apache Guacamole](guacamole.md) | `remote` | remote-access | `header-auth` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 🔒 [Vault UI](vault-ui.md) | `vault` | security | `mtls` | :x: No | :x: | :x: |
| 🔐 [Vaultwarden](vaultwarden.md) | `passwords` | security | `native-oidc` | :white_check_mark: Yes | :white_check_mark: | :x: |
| 🌐 [Headscale](headscale.md) | `vpn-admin`, `vpn` | vpn | `native-oidc` | :white_check_mark: Yes | :x: | :x: |
| 🐦 [NetBird](netbird.md) | `netbird` | vpn | `native-oidc` | :white_check_mark: Yes | :x: | :x: |
