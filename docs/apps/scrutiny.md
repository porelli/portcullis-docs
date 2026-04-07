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

!!! info "Auth Notes"
    No SSO or user system. Access gated by group-gate middleware. All authenticated users have full access.

## Access URLs

- **Dashboard**: `https://disks.{{DOMAIN}}`
