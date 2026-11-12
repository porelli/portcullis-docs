#!/usr/bin/env python3
"""Fail when the built site has a literal list marker inside a paragraph.

Python-Markdown only starts a list after a blank line: a "- item" line right
under a paragraph line (or a continuation paragraph inside a list item) is
folded into that paragraph, and the page shows "- " as text. This scans every
built page (default: site/) and reports each <p> with a line that starts with
"- ", "* ", "+ " or "1. ", and each tight list item (an <li> without a
<p>) or table cell with a later line that starts with "- ", "* " or "+ ". Text inside <code> /
<pre> is ignored.

Usage: python3 scripts/check-lists.py [site-dir]
"""
import html.parser
import pathlib
import re
import sys

BULLET = re.compile(r"^\s*[-*+]\s+\S")
MARKER = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\S")


BLOCKS = {"p", "li", "td", "th", "dd", "dt", "blockquote"}
SKIP = {"code", "pre", "script", "style"}


class Scan(html.parser.HTMLParser):
    """Collects each block's own text (not its nested blocks') line by line."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []  # [tag, [text parts]] per open block
        self.skip = 0
        self.hits = []

    def handle_starttag(self, tag, attrs):
        if tag in BLOCKS:
            self.stack.append([tag, []])
        elif tag in SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in BLOCKS:
            # Pop up to and including the matching block (tolerates <li>/<p>
            # left open by the HTML).
            while self.stack:
                t, parts = self.stack.pop()
                self.check(t, parts)
                if t == tag:
                    break
        elif tag in SKIP and self.skip:
            self.skip -= 1

    def check(self, tag, parts):
        lines = "".join(parts).split("\n")
        # A paragraph may not start with or contain a list marker line, nor a
        # table cell a bullet line. A tight <li> or the rest may not contain a
        # bullet line after their first: the nav's "1. Versions" entries and
        # a list item reading "+ Add an app" are fine.
        marker = MARKER if tag == "p" else BULLET
        for line in lines if tag in ("p", "td", "th") else lines[1:]:
            if marker.match(line):
                self.hits.append(line.strip()[:100])

    def handle_data(self, data):
        if self.stack:
            self.stack[-1][1].append("`…`" if self.skip else data)


def main():
    site = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    if not site.is_dir():
        print(f"check-lists: {site} is not a directory (build first)", file=sys.stderr)
        return 1
    total = 0
    for page in sorted(site.rglob("*.html")):
        scan = Scan()
        scan.feed(page.read_text(encoding="utf-8"))
        for hit in scan.hits:
            print(f"check-lists: {page.relative_to(site)}: literal list marker in a paragraph: {hit}", file=sys.stderr)
        total += len(scan.hits)
    if total:
        print(f"check-lists: {total} literal list markers (add a blank line before the list)", file=sys.stderr)
        return 1
    print("check-lists: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
