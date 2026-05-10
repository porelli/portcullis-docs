#!/usr/bin/env python3
"""Generate app catalog documentation from Portcullis manifest files.

Reads manifest.yaml files from the templates repo and generates:
  - docs/apps/index.md    (overview table)
  - docs/apps/<app>.md    (per-app detail page)
  - docs/apps/.pages      (ordered nav list, consumed by mkdocs-awesome-pages-plugin)

Does NOT modify mkdocs.yml. The awesome-pages plugin reads .pages files in each
docs directory to build the site nav, so we generate apps/.pages and let the
plugin handle the rest.

Usage:
  python scripts/generate-app-docs.py [--source /path/to/portcullis-templates]
"""

import os
import sys
import argparse
from pathlib import Path

import yaml


def load_manifests(source_dir: Path) -> list[dict]:
    """Load all manifest.yaml files. Checks templates/ subdir first, then root."""
    templates_dir = source_dir / "templates"
    if not templates_dir.is_dir():
        # Templates repo has apps at root level (no templates/ subdir)
        templates_dir = source_dir
    if not templates_dir.is_dir():
        print(f"ERROR: {templates_dir} not found", file=sys.stderr)
        sys.exit(1)

    apps = []
    for entry in sorted(templates_dir.iterdir()):
        manifest_path = entry / "manifest.yaml"
        if not manifest_path.is_file():
            continue
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)
        manifest["_id"] = entry.name
        apps.append(manifest)
    return apps


def sso_badge(sso_val) -> str:
    if sso_val is True:
        return ":white_check_mark: Yes"
    elif sso_val == "partial":
        return ":warning: Partial"
    return ":x: No"


def bool_badge(val) -> str:
    return ":white_check_mark:" if val else ":x:"


def generate_index(apps: list[dict], output_dir: Path):
    """Generate the app catalog overview table."""
    lines = [
        "# App Catalog",
        "",
        "All apps available in Portcullis with their authentication capabilities.",
        "",
        "| App | Category | Auth Method | SSO | Group Access | Group Admin |",
        "|-----|----------|-------------|-----|-------------|-------------|",
    ]

    for app in sorted(apps, key=lambda a: (a.get("category", ""), a.get("name", ""))):
        app_id = app["_id"]
        name = app.get("name", app_id)
        icon = app.get("icon", "")
        category = app.get("category", "")
        auth = app.get("auth", {})
        method = auth.get("method", "—")
        sso = sso_badge(auth.get("sso", False))
        group = bool_badge(auth.get("group_access", False))
        admin = bool_badge(auth.get("group_admin", False))

        lines.append(
            f"| {icon} [{name}]({app_id}.md) | {category} | `{method}` | {sso} | {group} | {admin} |"
        )

    lines.append("")
    (output_dir / "index.md").write_text("\n".join(lines))
    print(f"  Generated apps/index.md ({len(apps)} apps)")


def generate_app_page(app: dict, output_dir: Path):
    """Generate a per-app detail page."""
    app_id = app["_id"]
    name = app.get("name", app_id)
    icon = app.get("icon", "")
    desc = app.get("description", "")
    category = app.get("category", "")
    tags = app.get("tags", [])
    conflicts = app.get("conflicts", [])
    auth = app.get("auth", {})
    settings = app.get("settings", [])
    env_vars = app.get("env", [])
    clients = app.get("keycloak_clients", [])
    urls = app.get("urls", [])

    lines = [
        f"# {icon} {name}",
        "",
        f"> {desc}",
        "",
        f"**Category:** {category}  ",
        f"**Tags:** {', '.join(f'`{t}`' for t in tags)}",
        "",
    ]

    if conflicts:
        lines.append(f"!!! warning \"Conflicts with: {', '.join(conflicts)}\"")
        lines.append("")

    # Auth section
    lines.append("## Authentication")
    lines.append("")

    method = auth.get("method", "unknown")
    sso = auth.get("sso", False)
    group_access = auth.get("group_access", False)
    group_admin = auth.get("group_admin", False)
    access_group = auth.get("access_group", "")
    admin_group = auth.get("admin_group", "")
    notes = auth.get("notes", "")

    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| **Method** | `{method}` |")
    lines.append(f"| **SSO** | {sso_badge(sso)} |")
    lines.append(f"| **Group Access** | {bool_badge(group_access)} |")
    lines.append(f"| **Group Admin** | {bool_badge(group_admin)} |")
    if access_group:
        lines.append(f"| **Access Group** | `{access_group}` |")
    if admin_group:
        lines.append(f"| **Admin Group** | `{admin_group}` |")
    lines.append("")

    if notes:
        lines.append(f"!!! info \"Auth Notes\"")
        lines.append(f"    {notes}")
        lines.append("")

    # Settings section
    if settings:
        lines.append("## Settings")
        lines.append("")
        lines.append("User-configurable options available in the Hub UI:")
        lines.append("")
        lines.append("| Setting | Type | Description |")
        lines.append("|---------|------|-------------|")
        for s in settings:
            label = s.get("label", s.get("key", ""))
            stype = s.get("type", "text")
            sdesc = s.get("description", "")
            target = s.get("target", {})
            mount = target.get("mount", "") if target else ""
            extra = f" → `{mount}`" if mount else ""
            lines.append(f"| **{label}** | `{stype}` | {sdesc}{extra} |")
        lines.append("")

    # Environment variables
    if env_vars:
        lines.append("## Environment Variables")
        lines.append("")
        lines.append("Auto-generated by the Hub on first enable:")
        lines.append("")
        lines.append("| Variable | Description | Generation |")
        lines.append("|----------|-------------|------------|")
        for e in env_vars:
            key = e.get("key", "")
            edesc = e.get("description", "")
            gen = e.get("generate", "manual")
            lines.append(f"| `{key}` | {edesc} | `{gen}` |")
        lines.append("")

    # Keycloak clients
    if clients:
        lines.append("## Keycloak Clients")
        lines.append("")
        for c in clients:
            client_id = c.get("client_id", "")
            cname = c.get("name", client_id)
            redirect = c.get("redirect_uri", "")
            redirects = c.get("redirect_uris", [])
            lines.append(f"**{cname}** (`{client_id}`)")
            lines.append("")
            if redirects:
                lines.append("Redirect URIs:")
                for r in redirects:
                    lines.append(f"- `{r}`")
            elif redirect:
                lines.append(f"Redirect URI: `{redirect}`")
            lines.append("")

    # URLs
    if urls:
        lines.append("## Access URLs")
        lines.append("")
        for u in urls:
            label = u.get("label", "")
            url = u.get("url", "")
            lines.append(f"- **{label}**: `{url}`")
        lines.append("")

    (output_dir / f"{app_id}.md").write_text("\n".join(lines))


def generate_apps_pages(apps: list[dict], output_dir: Path):
    """Write docs/apps/.pages for the awesome-pages plugin.

    Lists the overview page first, then each app page in (category, name) order
    with the icon prepended to the display title.
    """
    lines = ["nav:", "  - Overview: index.md"]
    for app in sorted(apps, key=lambda a: (a.get("category", ""), a.get("name", ""))):
        app_id = app["_id"]
        name = app.get("name", app_id)
        icon = app.get("icon", "")
        title = f"{icon} {name}".strip()
        lines.append(f"  - {title}: {app_id}.md")
    (output_dir / ".pages").write_text("\n".join(lines) + "\n")
    print(f"  Generated apps/.pages ({len(apps)} entries)")


def main():
    parser = argparse.ArgumentParser(description="Generate Portcullis app catalog docs")
    parser.add_argument(
        "--source",
        default=os.environ.get(
            "PORTCULLIS_TEMPLATES",
            str(Path(__file__).parent.parent.parent / "portcullis-templates"),
        ),
        help="Path to the portcullis-templates repo (default: ../portcullis-templates)",
    )
    args = parser.parse_args()

    source_dir = Path(args.source)
    docs_dir = Path(__file__).parent.parent / "docs" / "apps"

    print(f"Source: {source_dir}")
    print(f"Output: {docs_dir}")

    docs_dir.mkdir(parents=True, exist_ok=True)

    apps = load_manifests(source_dir)
    print(f"Found {len(apps)} app manifests")

    generate_index(apps, docs_dir)
    for app in apps:
        generate_app_page(app, docs_dir)
        print(f"  Generated apps/{app['_id']}.md")

    generate_apps_pages(apps, docs_dir)
    print("Done!")


if __name__ == "__main__":
    main()
