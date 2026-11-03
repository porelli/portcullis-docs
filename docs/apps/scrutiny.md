# 💾 Scrutiny

> Hard drive S.M.A.R.T monitoring with web dashboard and alerts

**Category:** monitoring  
**Tags:** `disk`, `smart`, `health`, `monitoring`, `hardware`  
**Website:** <https://github.com/AnalogJ/scrutiny>  
**Source:** <https://github.com/AnalogJ/scrutiny>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `forward-auth` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_scrutiny` |
| **Admin Group** | `admin_scrutiny` |
| **Subdomain** | `disks` |

!!! info "Auth Notes"
    No SSO or user system. Access gated by group-gate middleware. All authenticated users have full access. Disks: list the host disks this instance monitors in the Disks setting (up to 8, e.g. /dev/sda, /dev/nvme0); only those are passed into the container, read-only, so several instances can each monitor their own disks. The container is not privileged: it gets SYS_RAWIO for SATA/SAS SMART passthrough, plus SYS_ADMIN only if "NVMe capability" is set to SYS_ADMIN (NVMe SMART logs need it). With no disk listed the dashboard stays empty. A listed path that doesn't exist on the host stops the container from starting.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `scrutiny` | `disks.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `scrutiny` | `ghcr.io/analogj/scrutiny:v0.10.0-omnibus` | `sha256:90062edac57a…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Disks** | `list` of `string` | instance | `restart` | Device paths of the disks to monitor, e.g. /dev/sda or /dev/nvme0 (up to 8). |
| **NVMe capability** | `enum` | instance | `restart` | SYS_RAWIO (default) is enough for SATA/SAS disks. Choose SYS_ADMIN if a listed disk is NVMe: the kernel only allows NVMe SMART reads with it. Choices: `SYS_RAWIO`, `SYS_ADMIN`. Default: `SYS_RAWIO`. |

## Access URLs

- **Dashboard**: `https://{{HOST_SCRUTINY}}`
