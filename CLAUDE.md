# Portcullis Docs — Claude Code Instructions

## Project Overview

Documentation website for the Portcullis project, built with [Zensical](https://zensical.org) (the successor of MkDocs + Material for MkDocs) and deployed to GitHub Pages at <https://porelli.github.io/portcullis-docs/>.

**This site is the single home for Portcullis documentation.** The other repos keep only their `README.md` (and templates' `CONTRIBUTING.md`), each linking here; core's `docs/*.md` are one-line pointers to the pages below. Never add documentation to `docs/` in core, the Hub or templates — write it here.

| Former core file | Page here |
|------------------|-----------|
| `docs/backups.md` | `docs/operations/backups.md` |
| `docs/monitoring.md` | `docs/operations/monitoring.md` |
| `docs/hardening.md` | `docs/operations/hardening.md` |
| `docs/certificates.md` | `docs/setup/certificates.md` |
| `docs/adding-a-domain.md` | `docs/setup/dns.md` |
| `docs/saml-app-nextcloud.md` | `docs/guides/saml-app.md` |
| `docs/non-saml-app-kanboard.md` | `docs/guides/header-auth-app.md` |

Don't rename or move these pages (or their main headings) without updating the pointer files in core, which link to the published URLs.

## Critical Rules

### Keep Docs In Sync

When making changes to any Portcullis repo, update the corresponding docs here:

| Change | Docs to update |
|--------|----------------|
| New/modified app template (in `porelli/portcullis-templates`) | Run `python3 scripts/generate-app-docs.py --source /Volumes/workspace/portcullis/portcullis-templates` to regenerate the catalog |
| Manifest schema change (`schema/manifest.schema.json` in templates) | `docs/guides/manifest-reference.md` (keep it field-for-field aligned with the schema), and the generator if a new field should show on app pages |
| Auth method change | `docs/architecture.md` (flow diagrams), affected app page in `docs/apps/` |
| Hub UI change | `docs/operations/hub.md` |
| CI/test change | `docs/operations/testing.md` |
| Group model change | `docs/operations/groups.md` |
| TLS/mTLS change | `docs/setup/certificates.md` |
| New setup step / `portcullis init` change | `docs/setup/quickstart.md` |
| New or changed `./portcullis` command or option (core) | `docs/operations/cli.md` — restate the real `./portcullis <cmd> --help` output |
| `portcullis upgrade`, versioning, release tags, `release.yml`, CHANGELOG | `docs/operations/upgrading.md`, `docs/operations/testing.md`, `docs/guides/integration-contracts.md` §1 |
| Backups (`portcullis backup/restore`, restic) / monitoring profile (core) | `docs/operations/backups.md`, `docs/operations/monitoring.md` |
| Identity headers (`X-Forwarded-User` = username, `X-Forwarded-Email`) | contracts §5, `docs/guides/header-auth-app.md`, `docs/operations/hardening.md` — email is never an identity key |
| Socket proxies, container hardening, secrets ownership, networks, header trust (core) | `docs/operations/hardening.md` (authoritative per-service table), `docs/architecture.md` |
| DNS providers, `dns setup`, one-domain rule (core) | `docs/setup/dns.md` |
| group-gate checks, `path_groups`, deny group (core) | `docs/operations/groups.md`, `docs/operations/auth-policies.md` |
| Cross-repo interface (policy file, env vars, proxy secret, Docker access) | `docs/guides/integration-contracts.md` **first**, then the pages above |
| Templates CONTRIBUTING / validator / CI | `docs/guides/adding-an-app.md`, `docs/guides/manifest-reference.md`, `docs/operations/testing.md` |

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

Pages under `docs/apps/` are **auto-generated** from each template's `manifest.yaml` **and** `compose.yml` (routers, subdomains, pinned images). Do NOT edit them manually — they will be overwritten. Instead:

1. Edit the app's `manifest.yaml` in `porelli/portcullis-templates`
2. Run: `python3 scripts/generate-app-docs.py --source /Volumes/workspace/portcullis/portcullis-templates`
3. Commit the regenerated `docs/apps/*.md` and `docs/apps/.nav.yml`

The generator writes `docs/apps/.nav.yml` (the nav for that directory) but does **not** modify `zensical.toml`.

### Preview

```bash
# Python >= 3.10 (macOS's /usr/bin/python3 3.9 only sees zensical 0.0.0-0.0.2 on PyPI;
# use e.g. python3.13 -m venv). requirements.txt pins what CI installs (Zensical is pre-1.0)
pip install -r requirements.txt
zensical serve            # http://localhost:8000
zensical build --strict   # what CI runs
```

### Writing rules

- The project has **no legacy installs**: document the current behaviour only — no migration guides, no "older releases did X".
- Every operator action goes through `./portcullis <command>`; never document `docker compose` invocations where a CLI command exists, and never reference the removed `scripts/*.sh`.
- Verify statements against the code in the other three repos (they are the source of truth); report inconsistencies instead of papering over them.
- This site is authoritative for all documentation (backups, monitoring, hardening, certificates included). Core's `docs/*.md` only point here; verify against core's code, not its docs.
- One base domain per installation; core subdomains are `auth`, `traefik`, `hub`, `directory`, `enroll`, `people`, `metrics`.

### Verify before committing

```bash
zensical build --strict --clean && rm -rf site      # no broken links/anchors
grep -rnE 'bootstrap\.sh|apply-config|configure-keycloak|register-oidc|setup-vault-pki|vault-init\.sh|enroll-yubikey|renew-yubikey|revoke-cert|status\.sh|upgrade\.sh|restore\.sh|setup-dns|init-config|scripts/group-gate' docs   # must be empty
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
| `scripts/generate-app-docs.py` | Reads templates repo `manifest.yaml` + `compose.yml` → writes `docs/apps/*.md` + `docs/apps/.nav.yml` |
| `docs/apps/index.md` | Auto-generated app catalog table |
| `docs/apps/*.md` | Auto-generated per-app pages |
| `docs/architecture.md` | Mermaid diagrams (edit manually) |
| `docs/setup/` | Setup guides (edit manually) |
| `docs/guides/` | Developer guides (edit manually) |
| `docs/operations/` | Operations guides (edit manually): CLI reference, upgrading & releases, backups, monitoring, security & hardening, groups, auth policies, Hub, testing |
| `docs/guides/integration-contracts.md` | Single source of truth for the interfaces between the four repos |
| `.github/workflows/deploy.yml` | GitHub Pages deployment |
| `requirements.txt` | Pinned build deps (zensical, ghp-import, PyYAML); CI's pip cache keys on it, Dependabot bumps it |

