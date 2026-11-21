#!/usr/bin/env python3
"""Generate app catalog documentation from Portcullis manifest files.

Reads manifest.yaml files from the templates repo and generates:
  - docs/apps/index.md    (overview table)
  - docs/apps/<app>.md    (per-app detail page)
  - docs/apps/.nav.yml    (ordered nav list, consumed by Zensical's awesome-nav support)
  - docs/apps/logos/<app>.svg (a copy of the template's logo, if it has one)

Does NOT modify zensical.toml. awesome-nav reads .nav.yml files in each
docs directory to build the site nav, so we generate apps/.nav.yml and let the
plugin handle the rest.

Usage:
  python scripts/generate-app-docs.py [--source /path/to/portcullis-templates]
"""

import html
import importlib.util
import os
import re
import stat
import sys
import argparse
import urllib.parse
from pathlib import Path

import yaml
from markdown_it import MarkdownIt

# auth.notes renderer: CommonMark + tables, raw HTML escaped, no images;
# markdown-it-py's link validation drops javascript:, vbscript:, file: and
# data: URLs.
NOTES_MD = MarkdownIt("commonmark", {"html": False}).enable("table").disable("image")


def notes_html(notes: str) -> str:
    """auth.notes as an HTML fragment with no blank line (one raw HTML
    block for Python-Markdown); links open in a new tab, like the Hub's."""
    out = NOTES_MD.render(notes).strip()
    out = out.replace("<a href=", '<a target="_blank" rel="noopener noreferrer nofollow" href=')
    # A blank line would end Python-Markdown's raw HTML block (code blocks).
    while re.search(r"\n[ \t]*\n", out):
        out = re.sub(r"\n[ \t]*\n", "\n&#10;", out)
    return out


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
        if entry.is_symlink() or manifest_path.is_symlink():
            # Nothing is read through a symlink (a logo would be copied
            # onto the docs site from wherever it points).
            print(f"ERROR: {entry}: a template directory or manifest that is a symlink is refused", file=sys.stderr)
            sys.exit(1)
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)
        settings = manifest.get("settings")
        if settings is not None and not isinstance(settings, dict):
            # A v2 settings list would silently publish pages without
            # their settings: refuse it before writing anything.
            kind = "a list (template contract v2)" if isinstance(settings, list) else type(settings).__name__
            print(f"ERROR: {manifest_path}: settings is {kind}; the docs need contract v3 "
                  "(settings: {options: [...]}). Point --source at a v3 templates checkout.", file=sys.stderr)
            sys.exit(1)
        manifest["_id"] = entry.name
        manifest["_dir"] = entry
        compose_path = entry / "compose.yml"
        manifest["_compose"] = {}
        if compose_path.is_file():
            with open(compose_path) as f:
                manifest["_compose"] = yaml.safe_load(f) or {}
        apps.append(manifest)
    return apps


# ── compose.yml parsing (routing + images) ─────────────────────────────

HOST_RE = re.compile(r"Host\(\s*`([^`]*)`\s*\)")
PATH_RE = re.compile(r"(PathPrefix|Path)\(\s*`([^`]*)`\s*\)")
ROUTER_RE = re.compile(r"^traefik\.http\.routers\.([^.]+)\.(.+)$")
DOMAIN_VAR_RE = re.compile(r"\$\{PORTCULLIS_DOMAIN[^}]*\}")
# Contract v2: ${PORTCULLIS_HOST_<ROUTER>:-<sub>.portcullis.local} is the
# instance's hostname; the default instance's is <sub>.<domain>.
HOST_VAR_RE = re.compile(r"\$\{PORTCULLIS_HOST_[A-Z0-9_]+:-([a-z0-9-]+)\.portcullis\.local\}")


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
            hosts = [HOST_VAR_RE.sub(r"\1.<domain>", DOMAIN_VAR_RE.sub("<domain>", h)) for h in HOST_RE.findall(rule)]
            mws = [m.strip() for m in attrs.get("middlewares", "").split(",") if m.strip()]
            routers.append({
                "service": sname,
                "name": rname,
                "hosts": hosts,
                # Path(`/x`) is that path only, PathPrefix(`/x`) the prefix.
                "paths": [p if kind == "PathPrefix" else f"{p} (exact)" for kind, p in PATH_RE.findall(rule)],
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



# ── settings (template contract v3) ─────────────────────────────────────

SCOPE_LABEL = {
    "instance": "instance",
    "person": "per person",
    "group": "per group",
    "person_entered": "entered by each person",
}

def effective_scope(o: dict) -> str:
    """The option's effective scope (contracts §13.2, §13.3).

    person_secret and person_id have effective scope 'person' even though
    they refuse the scope field in their declaration.
    """
    typ = o.get("type", "")
    if typ in ("person_secret", "person_id"):
        return "person"
    return o.get("scope") or "instance"


def effective_applies(o: dict) -> str:
    """The option's applies, or the Hub's default (contracts §13.9): the
    same rule for every type, person_secret included (no applies and no
    claim or header delivery = restart)."""
    if o.get("applies"):
        return o["applies"]
    for d in o.get("delivery") or []:
        if isinstance(d, dict) and "claim" in d:
            return "next_sign_in"
        if isinstance(d, dict) and "header" in d:
            return "next_request"
    return "restart"


def setting_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ", ".join(setting_value(x) for x in v)
    return md_cell(str(v))


def effective_mode(o: dict) -> str:
    """How the Hub mounts a path option (contracts §13.15): a folder block's
    access decides (read is always read-only), else mode, default rw."""
    folder = o.get("folder")
    if isinstance(folder, dict):
        return "rw" if folder.get("access") == "write" else "ro"
    return "ro" if o.get("mode") == "ro" else "rw"


def _run_id(runs_as: dict, which: str) -> str:
    """One id of a folder block's runs_as (contracts §13.15), "" if it has
    no source."""
    if runs_as.get(which) is not None:
        return str(runs_as[which])
    if runs_as.get(f"{which}_env"):
        return f"`{runs_as[f'{which}_env']}`"
    return ""


JOIN_TEXT = {
    "group_add": "the Hub adds the folder's group (`group_add`)",
    "gid_env": "joins the folder's group as its primary group: the Hub writes the folder's gid to `{var}`",
    "template": "joins the folder's group itself, from `PORTCULLIS_FOLDER_GID_{key}`",
}


def _runs_as_text(runs_as: dict) -> str:
    """Who the app writes or reads as on the mount (contracts §13.15)."""
    if runs_as.get("uid_from"):
        who = f"each person's own uid (`{runs_as['uid_from']}`)"
        if runs_as.get("gid_from"):
            return who + f" and private group (`{runs_as['gid_from']}`)"
        gid = _run_id(runs_as, "gid")
        return who + (f", gid {gid}" if gid else " with the folder's group")
    uid, gid = _run_id(runs_as, "uid"), _run_id(runs_as, "gid")
    if uid == "0" and gid == "0":
        return "root"
    return f"uid {uid}, gid {gid}"


def folder_text(folder: dict, key: str = "") -> str:
    """One line for a folder block: what the app does on the mount."""
    runs_as = folder.get("runs_as") or {}
    access = "writes" if folder.get("access") == "write" else "reads (read-only)"
    who = _runs_as_text(runs_as)
    if runs_as.get("gid_from"):
        # A per-person tree (contracts §13.15): one top-level folder per
        # person; it can't take a shared folder.
        return (f"Per-person folders: {access} as {who}; one `<username>` folder per person, "
                f"mode `0700` (it can't be a [shared folder](../operations/hub.md#shared-folders))")
    # Every other folder block is shared-folder ready; joins_group
    # defaults to group_add.
    join = folder.get("joins_group") or "group_add"
    jt = JOIN_TEXT.get(join, f"joins through `{join}`").format(
        var=runs_as.get("gid_env", ""), key=key.upper())
    text = f"[Shared folder](../operations/hub.md#shared-folders) ready: {access} as {who}; {jt}"
    if folder.get("must_own"):
        text += "; owns what it writes (the Hub also sets the owner)"
    return text


def check_text(c: dict) -> str:
    """One line for a doctor check (contracts §13.15 `checks`)."""
    kind = c.get("kind", "")
    if kind == "filesystem":
        parts = []
        if c.get("needs"):
            parts.append("needs " + ", ".join(f"`{x}`" for x in c["needs"]))
        if c.get("not"):
            parts.append("not on " + ", ".join(f"`{x}`" for x in c["not"]))
        what = "the filesystem " + " and ".join(parts)
    elif kind == "exclusive":
        what = "no other app may write the same folder"
    elif kind == "free_space":
        what = f"at least `{c.get('min', '')}` free"
    elif kind == "requires_group_value":
        what = "a group row should set it"
    else:
        what = f"`{kind}`"
    reason = " ".join(str(c.get("reason") or "").split())
    return f"[Doctor](../operations/hub.md#doctor) check: {what}" + (f" ({html.escape(reason, quote=False)})" if reason else "")


def setting_type(o: dict) -> str:
    typ = o.get("type", "")
    if typ == "list":
        item = (o.get("items") or {}).get("type", "")
        return f"`list` of `{item}`" if item else "`list`"
    if typ == "int" and o.get("unit"):
        return f"`int` ({md_cell(o['unit'])})"
    return f"`{md_cell(typ)}`"


def links_line(app: dict) -> str:
    """Website / source links (manifest links:), one line."""
    links = app.get("links") or {}
    parts = []
    if links.get("website"):
        parts.append(f"**Website:** <{links['website']}>")
    if links.get("source"):
        parts.append(f"**Source:** <{links['source']}>")
    elif links.get("source_note"):
        parts.append(f"**Source:** none ({md_cell(links['source_note'])})")
    return "  \n".join(parts)


def _size(mib: int) -> str:
    """MiB as 'N GiB' when it is a whole number of GiB, else 'N MiB'."""
    return f"{mib // 1024} GiB" if mib % 1024 == 0 else f"{mib} MiB"


def resources_line(app: dict) -> str:
    """resources: (contract §3, the project's documented minimum), one
    line; empty when the template states none."""
    res = app.get("resources") or {}
    parts = []
    if isinstance(res.get("min_memory_mib"), int):
        parts.append(f"{_size(res['min_memory_mib'])} RAM")
    if isinstance(res.get("min_disk_gib"), int):
        parts.append(f"{res['min_disk_gib']} GiB disk")
    return f"**Minimum resources:** {', '.join(parts)}" if parts else ""


# Logos (manifest logo:, contract §3) are copied next to the app pages and
# shown with <img> only, never inlined. The site sets no Content Security
# Policy (zensical.toml, GitHub Pages), so a same-origin image loads. A
# logo opened directly would run as an SVG document on the site's origin,
# so a copy is only ever one that passes the templates' own logo lint
# (tests/svgsafe.py of the --source checkout), read without following a
# symlink, from the template's own directory.
LOGO_DIR = "logos"
LOGO_MAX = 64 << 10
LICENSE_MAX = 4 << 10
LICENSE_KEYS = ("SPDX-FileCopyrightText:", "SPDX-License-Identifier:", "Source:")
# A credit's source link: https, a host, nothing that could leave the
# attribute or the URL (whitespace, quotes, brackets).
SOURCE_BAD = re.compile(r"[\s)<>\"'`\\]")


class AssetError(Exception):
    """A template asset the generator refuses (the message names it)."""


def load_logo_lint(source_dir: Path):
    """The templates repo's logo lint, tests/svgsafe.py: check(bytes) ->
    None or the reason. None when the checkout has none (then no logo is
    copied)."""
    path = source_dir / "tests" / "svgsafe.py"
    if path.is_symlink() or not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("portcullis_templates_svgsafe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.check


def read_asset(tdir: Path, name: str, limit: int) -> bytes:
    """name's bytes from the template directory tdir: a regular file in
    tdir itself (no directory part), never through a symlink (the file or
    the directory), at most limit bytes."""
    if tdir.is_symlink():
        raise AssetError(f"{tdir.name}: the template directory is a symlink")
    if "/" in name or "\\" in name or name in (".", ".."):
        raise AssetError(f"{tdir.name}: {name!r} is not a file name")
    path = tdir / name
    if path.is_symlink():
        raise AssetError(f"{tdir.name}/{name} is a symlink")
    if path.resolve().parent != tdir.resolve():
        raise AssetError(f"{tdir.name}/{name} resolves outside the template directory")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise AssetError(f"{tdir.name}/{name} is not a regular file")
        if st.st_size > limit:
            raise AssetError(f"{tdir.name}/{name} is over {limit} bytes")
        with os.fdopen(fd, "rb") as f:
            fd = -1
            data = f.read(limit + 1)
    finally:
        if fd >= 0:
            os.close(fd)
    if len(data) > limit:
        raise AssetError(f"{tdir.name}/{name} is over {limit} bytes")
    return data


def source_url(value: str) -> str:
    """The credit's Source: as a link target, or "" (no link)."""
    if not value or SOURCE_BAD.search(value):
        return ""
    u = urllib.parse.urlsplit(value)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        return ""
    return value


def logo_credit(meta: dict) -> str:
    """The REUSE attribution as one raw HTML block: Python-Markdown leaves
    its content alone, so a value can't become Markdown (a link, an
    image), and every value is HTML-escaped. "" without anything to say."""
    def text(v) -> str:
        # md_cell flattens newlines; its "\\|" is undone (this is HTML, not
        # a table cell, where the backslash would show).
        return html.escape(md_cell(v).replace("\\|", "|"), quote=False)
    parts = []
    if meta.get("SPDX-FileCopyrightText:"):
        parts.append("© " + text(meta["SPDX-FileCopyrightText:"]))
    if meta.get("SPDX-License-Identifier:"):
        parts.append("<code>" + text(meta["SPDX-License-Identifier:"]) + "</code>")
    url = source_url(meta.get("Source:", ""))
    if url:
        parts.append('<a href="' + html.escape(url, quote=True) + '" target="_blank" rel="noopener noreferrer nofollow">source</a>')
    if not parts:
        return ""
    return ('<p class="app-logo-credit"><small>Logo: ' + ", ".join(parts) +
            ". Shown only to identify the app; any trademark stays its owner's.</small></p>")


def logo_lines(app: dict, output_dir: Path, lint) -> list[str]:
    """Copy the template's logo to apps/logos/<id>.svg and return the page
    lines: the image and its REUSE attribution (copyright, licence,
    source), as the logo's licence asks. Nothing without a logo, or
    without the templates' lint to check it with."""
    logo = app.get("logo")
    tdir = app.get("_dir")
    if not isinstance(logo, str) or tdir is None:
        return []
    if lint is None:
        print(f"WARNING: {app['_id']}: no tests/svgsafe.py in the templates checkout: its logo is not copied", file=sys.stderr)
        return []
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}\.svg", logo):
        raise AssetError(f"{app['_id']}: logo {logo!r} is not a logo file name")
    data = read_asset(tdir, logo, LOGO_MAX)
    why = lint(data)
    if why is not None:
        raise AssetError(f"{app['_id']}: logo {logo} fails the logo lint: {why}")
    meta = {}
    if (tdir / f"{logo}.license").exists() or (tdir / f"{logo}.license").is_symlink():
        lic = read_asset(tdir, f"{logo}.license", LICENSE_MAX).decode("utf-8", "replace")
        for line in lic.splitlines():
            for key in LICENSE_KEYS:
                if line.startswith(key):
                    meta[key] = line[len(key):].strip()
    dest = output_dir / LOGO_DIR / f"{app['_id']}.svg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    alt = re.sub(r"[^\w .+&()-]", "", str(app.get("name", app["_id"]))).strip() or app["_id"]
    lines = [f'![{alt} logo]({LOGO_DIR}/{app["_id"]}.svg){{ width="64" height="64" }}', ""]
    credit = logo_credit(meta)
    if credit:
        lines += [credit, ""]
    return lines


def sso_badge(sso_val) -> str:
    if sso_val is True:
        return ":white_check_mark: Yes"
    elif sso_val == "partial":
        return ":warning: Partial"
    return ":x: No"


def bool_badge(val) -> str:
    return ":white_check_mark:" if val else ":x:"



# ── AI support (the ai: block, contract §3.2) ───────────────────────────

AI_GUIDE = Path(__file__).parent.parent / "docs" / "operations" / "ai.md"

IDENTITY_TEXT = {
    "app_token": "per-person app credential (`app_token`): the Hub mints one for each person in the app; mcp-gate sends it with every call",
    "identity_headers": "identity headers (`identity_headers`): mcp-gate tells the companion who the person is, with a caller secret only it holds",
    "app_oauth": "the app's own sign-in (`app_oauth`): the app is its own OAuth server and signs people in through Portcullis; mcp-gate is not in the path",
}

MODE_TEXT = {"read_only": "read only", "read_write": "read and write"}

KIND_TEXT = {
    "litellm": "LiteLLM", "openai_compatible": "OpenAI-compatible", "anthropic": "Anthropic",
    "openai": "OpenAI", "google": "Google", "bedrock": "AWS Bedrock", "azure_openai": "Azure OpenAI",
}


def ai_note_anchor(app_id: str) -> str:
    """The anchor of the app's note in the AI admin guide, if it has one."""
    try:
        text = AI_GUIDE.read_text()
    except OSError:
        return ""
    anchor = f"ai-{app_id}"
    return anchor if "{#" + anchor + "}" in text else ""


def ai_lines(app: dict) -> list[str]:
    ai = app.get("ai")
    if not isinstance(ai, dict):
        return []
    app_id = app["_id"]
    lines = ["## AI support", ""]
    anchor = ai_note_anchor(app_id)
    mcp = ai.get("mcp") or []
    if mcp:
        routers = {r["name"]: r for r in compose_routers(app.get("_compose") or {})}
        lines.append("People's AI assistants can use this app as themselves through these MCP servers, "
                     "once an admin switches AI support on in the app's **AI support** tab "
                     "(see [AI support](../operations/ai.md)).")
        lines.append("")
        for c in mcp:
            ident = c.get("identity") or {}
            mode = ident.get("mode", "")
            r = routers.get(c.get("router", ""))
            host = (r["hosts"][0] if r and r["hosts"] else "<host>")
            path = c.get("path") or "/mcp" if mode == "app_oauth" else (c.get("public_path") or "/mcp")
            upstream = c.get("upstream", "")
            up_text = ("official (the app's own MCP server)" if c.get("kind") == "builtin"
                       else "official companion (the app project's own MCP server)" if upstream == "official"
                       else "community companion, vetted by the template's reviewers")
            modes = c.get("modes") or []
            mode_text = ", ".join(MODE_TEXT.get(m, m) for m in modes)
            if c.get("default_mode"):
                mode_text += f" (default {MODE_TEXT.get(c['default_mode'], c['default_mode'])})"
            aggregate = c.get("aggregate", mode != "app_oauth")
            lines.append(f"**{md_cell(c.get('label', c.get('name', '')))}** (`{c.get('name', '')}`)")
            lines.append("")
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")
            lines.append(f"| **Endpoint** | `https://{host}{path}` |")
            lines.append(f"| **Server** | {'built into the app' if c.get('kind') == 'builtin' else 'a companion container (`' + str(c.get('service', '')) + '`), scaled to 0 while AI support is off'} |")
            lines.append(f"| **Upstream** | {up_text} |")
            lines.append(f"| **Source** | <{c.get('source', '')}> |")
            lines.append(f"| **Identity mode** | {IDENTITY_TEXT.get(mode, f'`{mode}`')} |")
            lines.append(f"| **Modes** | {mode_text} |")
            lines.append(f"| **In \"All my apps\"** | {bool_badge(aggregate)} |")
            lines.append(f"| **MCP versions** | {', '.join(f'`{v}`' for v in c.get('protocol') or [])} |")
            tools = c.get("tools") or {}
            if tools.get("confirm"):
                lines.append(f"| **Needs the person's confirmation** | {', '.join(f'`{md_cell(t)}`' for t in tools['confirm'])} |")
            if tools.get("never"):
                lines.append(f"| **Never offered** | {', '.join(f'`{md_cell(t)}`' for t in tools['never'])} |")
            if tools.get("writes"):
                lines.append(f"| **Hidden in read-only mode** | {', '.join(f'`{md_cell(t)}`' for t in tools['writes'])} |")
            lines.append("")
        if mode_of_any(mcp, "app_oauth"):
            lines.append("!!! warning \"The app applies its own rules\"")
            lines.append("    This app signs AI clients in itself. Portcullis doesn't log, confirm, rate-limit or filter "
                         "its AI actions; leaving the app's access group revokes the person's AI tokens through the "
                         "template's revoke hook.")
            lines.append("")
    elif ai.get("chat"):
        chat = ai["chat"]
        kinds = chat.get("provider_kinds") or {}
        lines.append("This template is an **AI page**: an MCP client people chat in, connected to "
                     "\"All my apps\" as each person. Its models come from the model providers in "
                     "Hub Settings → AI (see [The AI page](../operations/ai.md#the-ai-page)).")
        lines.append("")
        lines.append("| Provider kind | Per instance |")
        lines.append("|---------------|--------------|")
        for k, v in kinds.items():
            lines.append(f"| {KIND_TEXT.get(k, k)} (`{k}`) | {'one' if v == 'one' else 'several'} |")
        lines.append("")
        if ai.get("unsupported"):
            lines.append(f"Not an app the AI acts in: {md_cell(html.escape(str(ai['unsupported']), quote=False))}.")
            lines.append("")
    else:
        lines.append(f"**No AI support:** {md_cell(html.escape(str(ai.get('unsupported', '')), quote=False))}.")
        lines.append("")
        alt = ai.get("alternative")
        if isinstance(alt, dict):
            lines.append(f"An alternative **not vetted by Portcullis**, for an admin to evaluate on their own: "
                         f"{md_cell(html.escape(str(alt.get('name', '')), quote=False))} (<{alt.get('source', '')}>) — "
                         f"{md_cell(html.escape(str(alt.get('note', '')), quote=False))}. Portcullis never installs it.")
            lines.append("")
    if anchor:
        lines.append(f"Why this choice, and what to know: [AI support → {app.get('name', app_id)}](../operations/ai.md#{anchor}).")
        lines.append("")
    return lines


# Hand-written provider notes (contract §19: a mail provider's app page is
# normative for that template): scripts/app-notes/<id>.md is appended
# verbatim to the generated mail section. Not under docs/, so it is never a
# page of its own.
APP_NOTES = Path(__file__).parent / "app-notes"


def _endpoint(e) -> str:
    if not isinstance(e, dict):
        return "—"
    return f"`{e.get('service', '?')}` port `{e.get('port', '?')}`"


def mail_lines(app: dict) -> list[str]:
    """The ## Mail provider section for a template with a mail: block."""
    m = app.get("mail")
    if not isinstance(m, dict):
        return []
    app_id = app["_id"]
    lines = ["## Mail provider", ""]
    lines.append("This template is a **mail provider** "
                 "([contracts §3.5](../guides/integration-contracts.md#35-mail-providers-the-mail-block-new-mail-provider)): "
                 "installing it grants nothing. A full administrator wires one instance into the server's mail slot "
                 "([Mail operations → Wiring a provider](../operations/mail.md#wiring-a-provider)), and only that "
                 "instance gets the slot's powers: the public ports, the provider API network, the mail certificate, "
                 "the slot files and the well-known router.")
    lines.append("")
    lines.append("| `mail:` field | Value |")
    lines.append("|---------------|-------|")
    lines.append(f"| `label` | {md_cell(str(m.get('label', '')))} |")
    lines.append(f"| `api_version` | `{m.get('api_version', '?')}` |")
    lines.append(f"| `api` | {_endpoint(m.get('api'))}: the provider API the Hub dials on `portcullis-mail-api` |")
    li = m.get("listeners") or {}
    if isinstance(li, dict):
        ports = ", ".join(f"{host} → `{li.get(k, '?')}`" for host, k in
                          (("25", "smtp"), ("465", "submissions"), ("587", "submission"), ("993", "imaps")))
        lines.append(f"| `listeners` | `{li.get('service', '?')}`: host port {ports} (published by the Hub, IPv4 only) |")
    lines.append(f"| `wellknown` | {_endpoint(m.get('wellknown'))}: MTA-STS, autoconfig and autodiscover |")
    lines.append(f"| `metrics` | {_endpoint(m.get('metrics'))} |")
    sm = m.get("server_metrics")
    if isinstance(sm, dict):
        lines.append(f"| `server_metrics` | {_endpoint(sm)}, path `{sm.get('path', '?')}` |")
    for k in ("tls", "gated"):
        lines.append(f"| `{k}` | {', '.join(f'`{x}`' for x in m.get(k) or []) or '—'} |")
    lines.append(f"| `sessions.restart` | `{(m.get('sessions') or {}).get('restart', '?')}`: restarted after every removal and every revoked mail password |")
    ex = m.get("export")
    if isinstance(ex, dict):
        argv = " ".join(str(a) for a in ex.get("argv") or [])
        lines.append(f"| `export` | `{ex.get('service', '?')}`: `{md_cell(argv)}` (`./portcullis mail export`) |")
    else:
        lines.append("| `export` | none: `./portcullis mail export` says the provider has none |")
    lines.append("")
    notes = APP_NOTES / f"{app_id}.md"
    if notes.is_file():
        lines.extend(notes.read_text().rstrip("\n").splitlines())
        lines.append("")
    return lines


def ai_badge(app: dict) -> str:
    ai = app.get("ai") if isinstance(app.get("ai"), dict) else {}
    if ai.get("mcp"):
        return ":white_check_mark:"
    if ai.get("chat"):
        return "AI page"
    return ":x:"


def mode_of_any(mcp: list, mode: str) -> bool:
    return any(((c.get("identity") or {}).get("mode")) == mode for c in mcp)


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
        "| App | Subdomain | Category | Auth Method | SSO | Group Access | Group Admin | AI support |",
        "|-----|-----------|----------|-------------|-----|-------------|-------------|------------|",
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
            f"| {icon} [{name}]({app_id}.md) | {subs} | {category} | `{method}` | {sso} | {group} | {admin} | {ai_badge(app)} |"
        )

    lines.append("")
    (output_dir / "index.md").write_text("\n".join(lines))
    print(f"  Generated apps/index.md ({len(apps)} apps)")


def generate_app_page(app: dict, output_dir: Path, lint=None):
    """Generate a per-app detail page."""
    app_id = app["_id"]
    name = app.get("name", app_id)
    icon = app.get("icon", "")
    desc = app.get("description", "")
    category = app.get("category", "")
    tags = app.get("tags", [])
    auth = app.get("auth", {})
    settings = app.get("settings") or {}
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
    links = links_line(app)
    if links:
        # Below the tags, as part of the same block (Markdown line breaks).
        lines[-2] += "  "
        lines.insert(len(lines) - 1, links)
    res = resources_line(app)
    if res:
        lines[-2] += "  "
        lines.insert(len(lines) - 1, res)
    # The logo goes under the title, before the description.
    lines[2:2] = logo_lines(app, output_dir, lint)

    long_desc = app.get("long_description", "")
    if long_desc:
        # long_description is Markdown (contract §3 "Catalog fields") with
        # the auth.notes rules: the same renderer, into a raw HTML block,
        # above the sign-in notes.
        lines.append("## About")
        lines.append("")
        lines.append('<div class="app-long-description">')
        lines.append(notes_html(str(long_desc)))
        lines.append("</div>")
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
    admin_paths = auth.get("admin_paths") or []
    if admin_paths:
        paths = ", ".join(f"`{p}`" for p in admin_paths)
        lines.append(f"| **Admin Paths** | {paths} (require `{admin_group}` in addition to access) |")
    subs = subdomains(app)
    if subs:
        lines.append(f"| **Subdomain** | {', '.join(f'`{x}`' for x in subs)} |")
    lines.append("")

    if notes:
        # auth.notes is Markdown (contract §3) from a template source: render
        # it here with markdown-it-py (CommonMark + tables, raw HTML off,
        # images off) into a raw HTML block, so the site's own Markdown
        # (raw HTML passed through, attr_list, md_in_html) never sees it.
        lines.append('<div class="admonition info">')
        lines.append('<p class="admonition-title">Auth Notes</p>')
        lines.append(notes_html(str(notes)))
        lines.append("</div>")
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
        if (app.get("auth") or {}).get("method") == "native-oidc":
            # No forward-auth on the host anyway: the exception only lifts a
            # client-certificate requirement of the host's policy.
            lines.append("The app signs users in itself (native OIDC), so these paths are reachable without "
                         "Portcullis sign-in anyway. When an admin turns them on in the Hub, they are also served "
                         "without a client certificate on hosts whose policy requires one "
                         "(see [Public exceptions](../operations/auth-policies.md#public-exceptions)).")
        else:
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

    lines.extend(mail_lines(app))
    lines.extend(ai_lines(app))

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

    # Settings section (template contract v3: settings.options)
    options = settings.get("options") or [] if isinstance(settings, dict) else []
    if options:
        lines.append("## Settings")
        lines.append("")
        lines.append("Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) "
                     "(person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). "
                     "**Scope** and **Applies** are explained in the "
                     "[Manifest Reference](../guides/manifest-reference.md#settings).")
        lines.append("")
        lines.append("| Setting | Type | Scope | Applies | Description |")
        lines.append("|---------|------|-------|---------|-------------|")
        for o in options:
            label = o.get("label") or o.get("key", "")
            desc = " ".join(str(o.get("description") or "").split())
            extra = []
            choices = o.get("options") or []
            if choices:
                extra.append("Choices: " + ", ".join(f"`{c.get('value')}`" for c in choices))
            if o.get("default") not in (None, "", []):
                extra.append(f"Default: `{setting_value(o['default'])}`")
            gv = o.get("group_values") or {}
            for g, v in gv.items():
                who = {"{{ADMIN_GROUP}}": "the admin group", "{{ACCESS_GROUP}}": "the access group"}.get(g, g)
                extra.append(f"Preset for {who}: `{setting_value(v)}`")
            if o.get("privileged"):
                extra.append("Privileged: per-group values only from [groups delegates can't steer](../operations/groups.md#guarding-groups)")
            if (o.get("scope") or "instance") == "person_entered":
                if o.get("unique"):
                    extra.append("No two people may enter the same value")
                if o.get("admin_override"):
                    extra.append("Admins may set it for someone")
            target = o.get("target") or {}
            if target.get("mount"):
                extra.append(f"Mounted at `{target['mount']}` ({effective_mode(o)})")
            folder = o.get("folder")
            if isinstance(folder, dict):
                extra.append(folder_text(folder, o.get("key", "")))
            for c in o.get("checks") or []:
                if isinstance(c, dict):
                    extra.append(check_text(c))
            if desc and desc[-1] not in ".!?)":
                desc += "."
            elif desc.endswith(")") and not desc.endswith(".)"):
                desc += "."
            text = " ".join(x for x in [md_cell(html.escape(desc, quote=False))] + [md_cell(e) + "." for e in extra] if x)
            scope = effective_scope(o)
            lines.append(f"| **{md_cell(label)}** | {setting_type(o)} | {SCOPE_LABEL.get(scope, md_cell(scope))} "
                         f"| `{effective_applies(o)}` | {text} |")
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
            if p.get("lan_only"):
                notes.append("[LAN only](../operations/hub.md#local-networks): the doctor warns when it is reachable from outside the local networks")
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
                lines.append("")  # Python-Markdown starts a list only after a blank line
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
    # Logos are rewritten from the templates on every run: drop the old
    # copies so a removed logo doesn't linger.
    for old in (docs_dir / LOGO_DIR).glob("*.svg"):
        old.unlink()

    apps = load_manifests(source_dir)
    print(f"Found {len(apps)} app manifests")

    lint = load_logo_lint(source_dir)
    generate_index(apps, docs_dir)
    for app in apps:
        try:
            generate_app_page(app, docs_dir, lint)
        except AssetError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"  Generated apps/{app['_id']}.md")

    generate_apps_pages(apps, docs_dir)
    print("Done!")


if __name__ == "__main__":
    main()
