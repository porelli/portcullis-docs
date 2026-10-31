# Portcullis Docs — Claude Code Instructions

## Project Overview

Documentation website for the Portcullis project, built with [Zensical](https://zensical.org) (the successor of MkDocs + Material for MkDocs) and deployed to GitHub Pages.

## Critical Rules

### Keep Docs In Sync

When making changes to any Portcullis repo, update the corresponding docs here:

| Change | Docs to update |
|--------|----------------|
| New/modified app template (in `porelli/portcullis-templates`) | Run `python3 scripts/generate-app-docs.py --source /Volumes/workspace/portcullis/portcullis-templates` to regenerate the catalog |
| Manifest schema change | `docs/guides/manifest-reference.md` |
| Auth method change | `docs/architecture.md` (flow diagrams), affected app page in `docs/apps/` |
| Hub UI change | `docs/operations/hub.md` |
| CI/test change | `docs/operations/testing.md` |
| Group model change | `docs/operations/groups.md` |
| TLS/mTLS change | `docs/setup/certificates.md` |
| New setup step | `docs/setup/quickstart.md` |

### Nav Structure

Nav is driven by Zensical's built-in **awesome-nav** support: it reads a `.nav.yml` file
in each directory under `docs/`. To change the top-level nav, edit
`docs/.nav.yml` (and the per-section `.nav.yml` files). `zensical.toml` deliberately
contains no `nav` key — don't add one, or it overrides the `.nav.yml` files.

Why not MkDocs 2: as of 2026-10 it only exists as `2.0.devN` pre-releases (a
minimal rewrite with no config file, plugins, admonitions, Mermaid or search), and
Material for MkDocs requires `mkdocs<2`. Zensical is the Material team's successor
and reads this project's config/features unchanged.

### App Catalog Pages

Pages under `docs/apps/` are **auto-generated** from manifest files. Do NOT edit them manually — they will be overwritten. Instead:

1. Edit the app's `manifest.yaml` in `porelli/portcullis-templates`
2. Run: `python3 scripts/generate-app-docs.py --source /Volumes/workspace/portcullis/portcullis-templates`
3. Commit the regenerated `docs/apps/*.md` and `docs/apps/.nav.yml`

The generator writes `docs/apps/.nav.yml` (the nav for that directory) but does **not** modify `zensical.toml`.

### Preview

```bash
# Python >= 3.10; Zensical is pre-1.0, so use the version pinned in deploy.yml
pip install 'zensical==0.0.74' pyyaml
zensical serve            # http://localhost:8000
zensical build --strict   # what CI runs
```

### Deployment

Push to `main` (or the daily schedule, which picks up template changes) → GitHub Actions runs `zensical build --strict` and force-pushes `site/` to the `gh-pages` branch with `ghp-import` (same mechanism `mkdocs gh-deploy` used).

## Key Files

| File | Purpose |
|------|---------|
| `zensical.toml` | Site config, theme, plugins, Markdown extensions (no `nav` key) |
| `docs/.nav.yml` | Top-level nav order |
| `docs/<section>/.nav.yml` | Per-section nav order (setup, guides, operations) |
| `docs/apps/.nav.yml` | Auto-generated (by `generate-app-docs.py`) |
| `scripts/generate-app-docs.py` | Reads templates repo manifests → writes `docs/apps/*.md` + `docs/apps/.nav.yml` |
| `docs/apps/index.md` | Auto-generated app catalog table |
| `docs/apps/*.md` | Auto-generated per-app pages |
| `docs/architecture.md` | Mermaid diagrams (edit manually) |
| `docs/setup/` | Setup guides (edit manually) |
| `docs/guides/` | Developer guides (edit manually) |
| `docs/operations/` | Operations guides (edit manually) |
| `.github/workflows/deploy.yml` | GitHub Pages deployment |

