# Portcullis Docs — Claude Code Instructions

## Project Overview

Documentation website for the Portcullis project, built with MkDocs Material and deployed to GitHub Pages.

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

Nav is driven by the **mkdocs-awesome-pages-plugin**: it reads a `.pages` file
in each directory under `docs/`. To change the top-level nav, edit
`docs/.pages` (and the per-section `.pages` files). `mkdocs.yml` no longer
contains a `nav:` block.

### App Catalog Pages

Pages under `docs/apps/` are **auto-generated** from manifest files. Do NOT edit them manually — they will be overwritten. Instead:

1. Edit the app's `manifest.yaml` in `porelli/portcullis-templates`
2. Run: `python3 scripts/generate-app-docs.py --source /Volumes/workspace/portcullis/portcullis-templates`
3. Commit the regenerated `docs/apps/*.md` and `docs/apps/.pages`

The generator writes `docs/apps/.pages` (the nav for that directory) but does **not** modify `mkdocs.yml`.

### Preview

```bash
pip install mkdocs-material mkdocs-awesome-pages-plugin pyyaml
python3 -m mkdocs serve -a 127.0.0.1:8000
# Open http://127.0.0.1:8000/portcullis-docs/
```

### Deployment

Push to `main` → GitHub Actions builds and deploys to `gh-pages` branch automatically.

## Key Files

| File | Purpose |
|------|---------|
| `mkdocs.yml` | Site config, theme, plugins (no `nav:` block) |
| `docs/.pages` | Top-level nav order |
| `docs/<section>/.pages` | Per-section nav order (setup, guides, operations) |
| `docs/apps/.pages` | Auto-generated (by `generate-app-docs.py`) |
| `scripts/generate-app-docs.py` | Reads templates repo manifests → writes `docs/apps/*.md` + `docs/apps/.pages` |
| `docs/apps/index.md` | Auto-generated app catalog table |
| `docs/apps/*.md` | Auto-generated per-app pages |
| `docs/architecture.md` | Mermaid diagrams (edit manually) |
| `docs/setup/` | Setup guides (edit manually) |
| `docs/guides/` | Developer guides (edit manually) |
| `docs/operations/` | Operations guides (edit manually) |
| `.github/workflows/deploy.yml` | GitHub Pages deployment |

