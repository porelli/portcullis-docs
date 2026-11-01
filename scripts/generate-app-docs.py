#!/usr/bin/env python3
"""Generate app catalog documentation from Portcullis manifest files.

Reads manifest.yaml files from the templates repo and generates:
  - docs/apps/index.md    (overview table)
  - docs/apps/<app>.md    (per-app detail page)
  - docs/apps/.nav.yml    (ordered nav list, consumed by Zensical's awesome-nav support)

Does NOT modify zensical.toml. awesome-nav reads .nav.yml files in each
docs directory to build the site nav, so we generate apps/.nav.yml and let the
plugin handle the rest.

Usage:
  python scripts/generate-app-docs.py [--source /path/to/portcullis-templates]
"""

import html
import os
import re
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
        compose_path = entry / "compose.yml"
        manifest["_compose"] = {}
        if compose_path.is_file():
            with open(compose_path) as f:
                manifest["_compose"] = yaml.safe_load(f) or {}
        apps.append(manifest)
    return apps


# ── compose.yml parsing (routing + images) ─────────────────────────────

HOST_RE = re.compile(r"Host\(\s*`([^`]*)`\s*\)")
PATH_RE = re.compile(r"PathPrefix\(\s*`([^`]*)`\s*\)")
ROUTER_RE = re.compile(r"^traefik\.http\.routers\.([^.]+)\.(.+)$")
DOMAIN_VAR_RE = re.compile(r"\$\{PORTCULLIS_DOMAIN[^}]*\}")


def _labels(svc: dict) -> dict:
    raw = (svc or {}).get("labels") or {}
    if isinstance(raw, list):
        out = {}
        for item in raw:
            k, _, v = str(item).partition("=")
            out[k.strip()] = v.strip()
        return out
    return {str(k): str(v) for k, v in raw.items()}


def compose_routers(compose: dict) -> list[dict]:
    """[{service, name, hosts, paths, tls, middlewares}] for every HTTP router."""
    routers = []
    for sname, svc in sorted((compose.get("services") or {}).items()):
        per = {}
        for k, v in _labels(svc).items():
            m = ROUTER_RE.match(k)
            if m:
                per.setdefault(m.group(1), {})[m.group(2)] = v
        for rname, attrs in sorted(per.items()):
            rule = attrs.get("rule", "")
            hosts = [DOMAIN_VAR_RE.sub("<domain>", h) for h in HOST_RE.findall(rule)]
            mws = [m.strip() for m in attrs.get("middlewares", "").split(",") if m.strip()]
            routers.append({
                "service": sname,
                "name": rname,
                "hosts": hosts,
                "paths": PATH_RE.findall(rule),
                "tls": attrs.get("tls.options", ""),
                "middlewares": mws,
            })
    return routers


def compose_images(compose: dict) -> list[tuple[str, str, str]]:
    """[(service, image name:tag, digest)]."""
    out = []
    for sname, svc in sorted((compose.get("services") or {}).items()):
        image = str((svc or {}).get("image") or "")
        if not image:
            continue
        ref, _, digest = image.partition("@")
        out.append((sname, ref, digest))
    return out


def subdomains(app: dict) -> list[str]:
    subs = []
    for r in compose_routers(app.get("_compose") or {}):
        for h in r["hosts"]:
            sub = h.split(".", 1)[0] if h.endswith(".<domain>") else h
            if sub not in subs:
                subs.append(sub)
    return subs


def md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


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
        "Each app is reachable at `<subdomain>.<your-domain>`.",
        "",
        "These pages are generated from the `manifest.yaml` and `compose.yml` files in",
        "[porelli/portcullis-templates](https://github.com/porelli/portcullis-templates);",
        "see the [Manifest Reference](../guides/manifest-reference.md) for the fields.",
        "",
        "| App | Subdomain | Category | Auth Method | SSO | Group Access | Group Admin |",
        "|-----|-----------|----------|-------------|-----|-------------|-------------|",
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

        subs = ", ".join(f"`{x}`" for x in subdomains(app)) or "—"
        lines.append(
            f"| {icon} [{name}]({app_id}.md) | {subs} | {category} | `{method}` | {sso} | {group} | {admin} |"
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
    auth = app.get("auth", {})
    settings = app.get("settings", [])
    ports = app.get("ports", [])
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
    admin_paths = auth.get("admin_paths") or []
    if admin_paths:
        paths = ", ".join(f"`{p}`" for p in admin_paths)
        lines.append(f"| **Admin Paths** | {paths} (require `{admin_group}` in addition to access) |")
    subs = subdomains(app)
    if subs:
        lines.append(f"| **Subdomain** | {', '.join(f'`{x}`' for x in subs)} |")
    lines.append("")

    if notes:
        lines.append('!!! info "Auth Notes"')
        for line in str(notes).strip().splitlines():
            lines.append(f"    {line}" if line.strip() else "")
        lines.append("")

    # App's own login (auth.native_login)
    nl = auth.get("native_login")
    if isinstance(nl, dict) and nl.get("supported"):
        lines.append("## Sign-in")
        lines.append("")
        lines.append("The app has its own login. The Hub's per-app **Sign-in** setting chooses who signs users in "
                     "([Apps with their own login](../operations/auth-policies.md#apps-with-their-own-login)):")
        lines.append("")
        gate = f"members of `{access_group}`" if group_access and access_group else "any signed-in user"
        lines.append(f"- **Portcullis sign-in, then the app's own login** (default): forward-auth and group-gate in front, {gate}.")
        if nl.get("allow_without_gateway"):
            lines.append("- **App's own login only (no Portcullis)**: allowed by this template. No forward-auth, TLS tier "
                         "`public@file`: anyone on the internet reaches the app's login page.")
        else:
            lines.append("- **App's own login only**: not allowed by this template.")
        if nl.get("note"):
            lines.append("")
            lines.append(f"> {str(nl['note']).strip()}")
        lines.append("")

    # Public exceptions (auth.public_access)
    pa = auth.get("public_access")
    if isinstance(pa, dict):
        has_token = any("{token}" in str(p.get("prefix", "")) for p in pa.get("paths") or [])
        mode = pa.get("default_mode") or ("listed" if has_token else "all")
        lines.append("## Public Exceptions")
        lines.append("")
        if pa.get("description"):
            lines.append(md_cell(html.escape(str(pa["description"]).strip(), quote=False)))
            lines.append("")
        lines.append("When an admin turns them on in the Hub, these paths skip forward-auth and group-gate "
                     "(see [Public exceptions](../operations/auth-policies.md#public-exceptions)).")
        lines.append("")
        lines.append(f"**Default:** {'on' if pa.get('enabled_by_default') else 'off'}, mode `{mode}`  ")
        if pa.get("token_pattern"):
            lines.append(f"**Share token:** `{pa['token_pattern']}`  ")
        creds = ["header `Authorization`", "header `Proxy-Authorization`"] + [f"header `{h}`" for h in pa.get("credential_headers") or []]
        creds += [f"cookie `{c}`" for c in pa.get("credential_cookies") or []] + [f"query `{q}`" for q in pa.get("credential_query") or []]
        lines.append(f"**Refused by the public guard (login credentials):** {', '.join(creds)}  ")
        if auth.get("identity_headers"):
            lines.append(f"**Identity headers stripped:** {', '.join(f'`{h}`' for h in auth['identity_headers'])} (plus the core ones)  ")
        lines.append("")
        lines.append("| Prefix | Opened | Description |")
        lines.append("|--------|--------|-------------|")
        for p in pa.get("paths") or []:
            prefix = str(p.get("prefix", ""))
            if "{token}" in prefix:
                kind = "per listed share; mode `all`: every share"
            elif p.get("supporting"):
                kind = "always (supporting)"
            else:
                kind = "mode `all` only"
            if p.get("exact"):
                kind += f"; this exact path only: {md_cell(html.escape(str(p.get('justification', '')), quote=False))}"
            elif p.get("supporting"):
                kind += "; static files only"
            if p.get("broad"):
                kind += f"; broad: {md_cell(html.escape(str(p.get('justification', '')), quote=False))}"
            lines.append(f"| `{md_cell(prefix)}` | {kind} | {md_cell(html.escape(str(p.get('description', '')), quote=False))} |")
        lines.append("")

    # Routing (from compose.yml)
    routers = compose_routers(app.get("_compose") or {})
    if routers:
        lines.append("## Routing")
        lines.append("")
        lines.append("Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).")
        lines.append("")
        lines.append("| Router | Host | Paths | TLS tier | Forward-auth + group-gate |")
        lines.append("|--------|------|-------|----------|---------------------------|")
        for r in routers:
            hosts = ", ".join(f"`{h}`" for h in r["hosts"]) or "—"
            paths = ", ".join(f"`{p}`" for p in r["paths"]) or "all"
            gated = "portcullis-auth@docker" in r["middlewares"] and "portcullis-groups@docker" in r["middlewares"]
            tls = f"`{r['tls']}`" if r["tls"] else "—"
            lines.append(f"| `{md_cell(r['name'])}` | {hosts} | {paths} | {tls} | {bool_badge(gated)} |")
        lines.append("")
        if isinstance(nl, dict) and nl.get("supported"):
            lines.append("As written in `compose.yml`. With the default [Sign-in](#sign-in) the Hub's override adds "
                         "`portcullis-auth@docker,portcullis-groups@docker` to every router.")
            lines.append("")

    images = compose_images(app.get("_compose") or {})
    if images:
        lines.append("## Images")
        lines.append("")
        lines.append("Pinned by version tag and digest; Dependabot proposes updates.")
        lines.append("")
        lines.append("| Service | Image | Digest |")
        lines.append("|---------|-------|--------|")
        for svc, ref, digest in images:
            short = f"`{digest[:19]}…`" if digest else ":warning: not pinned"
            lines.append(f"| `{svc}` | `{ref}` | {short} |")
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
            opts = s.get("options") or []
            if opts:
                extra += " Options: " + ", ".join(f"`{o}`" for o in opts)
            if s.get("default") not in (None, ""):
                extra += f" (default `{s['default']}`)"
            lines.append(f"| **{label}** | `{stype}` | {md_cell(sdesc)}{extra} |")
        lines.append("")

    # Ports
    if ports:
        lines.append("## Host Ports")
        lines.append("")
        lines.append("Ports this app binds on the host. Collisions with other enabled apps block enable; each binding can be rebound or disabled from the Hub UI.")
        lines.append("")
        lines.append("| Port | Protocol | Default | Container | Required | Notes |")
        lines.append("|------|----------|---------|-----------|----------|-------|")
        for p in ports:
            label = p.get("label", p.get("key", ""))
            proto = (p.get("protocol") or "tcp").lower()
            default = p.get("range") or p.get("default", "")
            container = p.get("container", "—")
            required = ":white_check_mark:" if p.get("required") else ":x:"
            notes = []
            if p.get("network_mode_host"):
                notes.append("host network")
            if p.get("range"):
                notes.append(f"range `{p['range']}`")
            lines.append(f"| **{label}** | `{proto}` | `{default}` | `{container}` | {required} | {', '.join(notes) or '—'} |")
        lines.append("")

    # Environment variables
    if env_vars:
        lines.append("## Environment Variables")
        lines.append("")
        lines.append("Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:")
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
    """Write docs/apps/.nav.yml for awesome-nav.

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
    (output_dir / ".nav.yml").write_text("\n".join(lines) + "\n")
    print(f"  Generated apps/.nav.yml ({len(apps)} entries)")


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
