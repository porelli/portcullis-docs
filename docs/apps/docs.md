# 📄 Docs Site

> Public documentation — no authentication

**Category:** public  
**Tags:** `docs`, `static`, `nginx`  
**Website:** <https://squidfunk.github.io/mkdocs-material/>  
**Source:** <https://github.com/squidfunk/mkdocs-material>

## About

<div class="app-long-description">
<p>A static documentation site built with Material for MkDocs: Markdown pages turned into a searchable website with navigation.</p>
<p>It is public: anyone can read it, with no sign-in.</p>
</div>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `public` |
| **SSO** | :x: No |
| **Group Access** | :x: |
| **Group Admin** | :x: |
| **Subdomain** | `docs` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>Public documentation site — no authentication required.</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `docs` | `docs.<domain>` | all | `public@file` | :x: |

## AI support

**No AI support:** A public site with no signed-in person to act as.

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `docs` | `squidfunk/mkdocs-material:9.8.0` | `sha256:dc3b5de76c6e…` |

## Access URLs

- **Docs**: `https://{{HOST_DOCS}}`
