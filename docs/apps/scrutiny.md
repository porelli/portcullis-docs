# 💾 Scrutiny

> Hard drive S.M.A.R.T monitoring with web dashboard and alerts

**Category:** monitoring  
**Tags:** `disk`, `smart`, `health`, `monitoring`, `hardware`

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
    No SSO or user system. Access gated by group-gate middleware. All authenticated users have full access. Disks: list the host disks this instance monitors in the Disk 1-8 settings (e.g. /dev/sda, /dev/nvme0); only those are passed into the container, read-only, so several instances can each monitor their own disks. The container is not privileged: it gets SYS_RAWIO for SATA/SAS SMART passthrough, plus SYS_ADMIN only if "NVMe capability" is set to SYS_ADMIN (NVMe SMART logs need it). With no disk listed the dashboard stays empty. A listed path that doesn't exist on the host stops the container from starting.

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `scrutiny` | `disks.<domain>` | all | `authaware@file` | :white_check_mark: |

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `scrutiny` | `ghcr.io/analogj/scrutiny:v0.9.5-omnibus` | `sha256:6ee271ee5314…` |

## Settings

User-configurable options available in the Hub UI:

| Setting | Type | Description |
|---------|------|-------------|
| **Disk 1** | `text` | Device path of a disk to monitor, e.g. /dev/sda or /dev/nvme0 (empty = unused). |
| **Disk 2** | `text` | Another disk to monitor (empty = unused). |
| **Disk 3** | `text` | Another disk to monitor (empty = unused). |
| **Disk 4** | `text` | Another disk to monitor (empty = unused). |
| **Disk 5** | `text` | Another disk to monitor (empty = unused). |
| **Disk 6** | `text` | Another disk to monitor (empty = unused). |
| **Disk 7** | `text` | Another disk to monitor (empty = unused). |
| **Disk 8** | `text` | Another disk to monitor (empty = unused). |
| **NVMe capability** | `select` | SYS_RAWIO (default) is enough for SATA/SAS disks. Choose SYS_ADMIN if a listed disk is NVMe: the kernel only allows NVMe SMART reads with it.  Options: `SYS_RAWIO`, `SYS_ADMIN` (default `SYS_RAWIO`) |

## Access URLs

- **Dashboard**: `https://{{HOST_SCRUTINY}}`
