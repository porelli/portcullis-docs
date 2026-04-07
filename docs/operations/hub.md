# Hub Management

The Hub is Portcullis's web-based dashboard for managing apps. It provides a visual interface for enabling apps, configuring settings, viewing logs, and performing administrative tasks. The Hub image is published at `ghcr.io/porelli/portcullis-hub` and pulled automatically by the core `docker-compose.yml` -- no manual build is required.

Access the Hub at `https://hub.<your-domain>`.

## App Catalog

The Hub's main view is the app catalog, showing all available app templates as cards.

### App Cards

Each card displays:

- **App icon and name**
- **Description** -- One-line summary of the app
- **Auth badges** -- Visual indicators of the app's authentication features:

| Badge | Meaning |
|-------|---------|
| **SSO** | The app supports single sign-on via Keycloak |
| **Group Access** | Access is restricted to members of the `users_<app>` group |
| **Group Admin** | The app maps the `admin_<app>` group to admin privileges |
| **Method** | The auth method: forward-auth, native-oidc, header-auth, or public |

- **Status indicator** -- Whether the app is currently enabled and running

### Enabling an App

1. Click on an app card
2. Review the app details
3. Click **Enable**
4. Configure any required settings (see below)
5. The Hub starts the app's Docker containers and registers any Keycloak clients

### Disabling an App

1. Click on an enabled app card
2. Click **Disable**
3. The Hub stops the app's containers and optionally removes its Keycloak clients

## App Detail Panel

Clicking on an enabled app opens the detail panel with four tabs: **Settings**, **Status**, **Logs**, and **Expert**.

### Settings Tab

Configure user-facing settings defined in the app's `manifest.yaml`:

- **Path settings** -- Host directory paths for media libraries and data. For example, Jellyfin has settings for Movies, TV Shows, and Music folders. Enter the absolute path on the host (e.g., `/mnt/media/movies`) and the Hub binds it to the correct container mount point.
- **Text settings** -- Free-form text inputs for API keys, custom names, etc.
- **Boolean settings** -- On/off toggles for feature flags
- **Select settings** -- Dropdowns with predefined options

After changing settings, the Hub restarts the affected containers to apply the changes.

### Status Tab

Shows the health of each container in the app's compose stack:

| Indicator | Meaning |
|-----------|---------|
| Green dot | Container is running and healthy |
| Amber dot | Container is running but unhealthy or starting up |
| Red dot | Container is stopped, crashed, or missing |

Click on a container row to see details: image name, uptime, restart count, and port mappings.

### Logs Tab

A live log viewer for the app's containers. Select a specific container from the dropdown or view combined logs from all containers in the stack.

Logs are streamed in real time and can be paused. Use the search bar to filter log lines.

### Expert Tab

The Expert tab provides advanced tools for power users. These tools give direct access to the underlying Docker Compose configuration and containers.

#### Compose Editor

View and edit the app's `compose.yml` directly. Changes are saved and applied on the next container restart.

!!! warning
    Editing compose.yml directly can break the app or its Traefik routing. Only modify this if you understand Docker Compose and Traefik labels.

#### Environment Variables

View all environment variables for the app. You can:

- **Edit existing variables** -- Click on a value to modify it
- **Add new variables** -- Click "Add Variable" to define a new env var
- **View generated secrets** -- Secrets generated during setup are shown (masked by default, click to reveal)

#### Compose Override

Create or edit a `compose.override.yml` for the app. Overrides are merged with the base compose.yml and take precedence. Use this for custom volume mounts, extra environment variables, or resource limits without modifying the template.

Example override to add a custom volume:

```yaml
services:
  jellyfin:
    volumes:
      - /mnt/external-drive/anime:/data/anime
```

#### Container Shell

Open an interactive shell session inside a running container. Select a container and a shell (`/bin/sh` or `/bin/bash`) to get a terminal directly in the browser.

Useful for debugging configuration issues, checking file permissions, or running app-specific CLI commands.

#### Restart

Restart all containers in the app's compose stack. This is a full `down` + `up` cycle, not just a container restart, so compose changes and env var updates take effect.

## Per-App Isolation

The Hub runs each app as an isolated Docker Compose project with its own network namespace and environment.

### How It Works

- **Separate compose project** -- Each app runs under the project name `portcullis-<app-id>` (e.g., `portcullis-jellyfin`). This means each app has its own set of containers and default network, fully isolated from other apps.
- **Separate network** -- App frontend services join the `portcullis-proxy` external network (shared with Traefik for routing) and the app's own default network (for internal services like databases). Apps cannot communicate with each other or with core services directly.
- **Separate .env** -- The Hub generates a per-app `.env` file containing the app's settings, secrets, and core variables (like `PORTCULLIS_DOMAIN`). These are stored in the Hub data directory and passed to Docker Compose at deploy time.

### Migration from Shared to Isolated

When the Hub starts, it automatically detects apps that were previously running under the shared `portcullis` project and migrates them to the new isolated architecture. This involves:

1. Stopping the app's containers in the old shared project
2. Creating a per-app `.env` file with the app's existing settings
3. Restarting the app under its own `portcullis-<app-id>` project

No manual intervention is required. Volumes with explicit `name:` fields are preserved across the migration.

### Expert Tab and Per-App .env

The Expert tab's Environment Variables section now edits the per-app `.env` file (not the root `.env`). Changes made here only affect the selected app. Core variables like `PORTCULLIS_DOMAIN` are inherited from the root configuration and shown as read-only.

## Template Sources

The Hub manages app templates through configurable template sources. Each source is a Git repository containing app directories with a `manifest.yaml` and `compose.yml`.

### Default Source

On first startup, the Hub automatically clones the [porelli/portcullis-templates](https://github.com/porelli/portcullis-templates) repository and registers it as the default template source named "portcullis". This provides 22 built-in templates covering common self-hosted applications across categories like media, productivity, monitoring, security, and networking.

To update the built-in templates, click **Sync** on the "portcullis" source in the Hub UI to pull the latest changes from the repository.

### Community Templates

You can add additional template sources by registering Git repositories in the Hub. Each repository should contain app directories with:

- `manifest.yaml` -- App metadata and configuration (see [Manifest Reference](../guides/manifest-reference.md))
- `compose.yml` -- Docker Compose services

The Hub clones and merges templates from all configured sources into the catalog.

## Common Tasks

### Changing an app's subdomain

Edit the Traefik `Host()` rule in the app's `compose.yml` via the Expert tab. Update the `urls` in `manifest.yaml` to match.

### Adding custom middleware

Add Traefik middleware labels in the app's `compose.yml` or via a compose override. For example, to add rate limiting:

```yaml
labels:
  traefik.http.middlewares.myapp-ratelimit.ratelimit.average: "100"
  traefik.http.routers.myapp.middlewares: "portcullis-auth@docker,portcullis-groups@docker,myapp-ratelimit,security-headers@file"
```

### Viewing resource usage

Container status in the Status tab shows basic health. For detailed resource monitoring (CPU, memory, network), enable the Grafana app and connect it to a metrics source.

### Backing up app data

App data lives in Docker volumes. Use standard Docker volume backup methods:

```bash
# List volumes for an app
docker volume ls | grep portcullis

# Backup a volume
docker run --rm -v portcullis_jellyfin_config:/data -v $(pwd):/backup \
  alpine tar czf /backup/jellyfin-config.tar.gz -C /data .
```
