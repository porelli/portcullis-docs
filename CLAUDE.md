# Portcullis Docs — Claude Code Instructions

## Project Overview

Documentation website for the Portcullis project, built with MkDocs Material and deployed to GitHub Pages.

## Critical Rules

### Keep Docs In Sync

This repo documents the main Portcullis repo (`porelli/portcullis`, locally at `/Volumes/workspace/midway/`). When making changes to the main repo, ALWAYS update the corresponding docs here:

| Main repo change | Docs to update |
|-----------------|----------------|
| New/modified app template | Run `python3 scripts/generate-app-docs.py --source /Volumes/workspace/midway` to regenerate app catalog |
| Manifest schema change | `docs/guides/manifest-reference.md` |
| Auth method change | `docs/architecture.md` (flow diagrams), affected app page in `docs/apps/` |
| Hub UI change | `docs/operations/hub.md` |
| CI/test change | `docs/operations/testing.md` |
| Group model change | `docs/operations/groups.md` |
| TLS/mTLS change | `docs/setup/certificates.md` |
| New setup step | `docs/setup/quickstart.md` |

### App Catalog Pages

Pages under `docs/apps/` are **auto-generated** from manifest files. Do NOT edit them manually — they will be overwritten. Instead:

1. Edit the app's `manifest.yaml` in the main repo
2. Run: `python3 scripts/generate-app-docs.py --source /Volumes/workspace/midway`
3. Commit the regenerated files

The generator also updates `mkdocs.yml` nav with all app pages.

### Preview

```bash
python3 -m mkdocs serve -a 127.0.0.1:8000
# Open http://127.0.0.1:8000/portcullis-docs/
```

### Deployment

Push to `main` → GitHub Actions builds and deploys to `gh-pages` branch automatically.

## Key Files

| File | Purpose |
|------|---------|
| `mkdocs.yml` | Site config, theme, nav structure |
| `scripts/generate-app-docs.py` | Reads manifests → generates `docs/apps/*.md` + updates nav |
| `docs/apps/index.md` | Auto-generated app catalog table |
| `docs/apps/*.md` | Auto-generated per-app pages |
| `docs/architecture.md` | Mermaid diagrams (edit manually) |
| `docs/setup/` | Setup guides (edit manually) |
| `docs/guides/` | Developer guides (edit manually) |
| `docs/operations/` | Operations guides (edit manually) |
| `.github/workflows/deploy.yml` | GitHub Pages deployment |
