"""Tests of generate-app-docs.py's logo copy and credit (run:
python -m unittest discover -s scripts -p 'test_*.py').

A template's logo is copied onto the docs site, so nothing is read through
a symlink or from outside the template directory, only a logo that passes
the templates' own lint is copied, and the REUSE credit's values can't
become markup or a script link.
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

import markdown

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("generate_app_docs", HERE / "generate-app-docs.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

GOOD_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#123456"/></svg>'


def lint(data: bytes):
    """A stand-in for tests/svgsafe.py's check: refuses a script."""
    return "element script refused" if b"<script" in data else None


def site_html(lines: list[str]) -> str:
    """The page lines as the site's Markdown renders them (the extensions
    that pass raw HTML through: md_in_html, attr_list)."""
    return markdown.markdown("\n".join(lines), extensions=["md_in_html", "attr_list"])


class LogoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.tdir = self.root / "src" / "app"
        self.tdir.mkdir(parents=True)
        self.out = self.root / "out"
        self.out.mkdir()
        self.secret = self.root / "secret.svg"
        self.secret.write_bytes(GOOD_SVG)

    def tearDown(self):
        self.tmp.cleanup()

    def app(self, **kw):
        a = {"_id": "app", "name": "App", "logo": "logo.svg", "_dir": self.tdir}
        a.update(kw)
        return a

    def test_copies_a_clean_logo(self):
        (self.tdir / "logo.svg").write_bytes(GOOD_SVG)
        lines = gen.logo_lines(self.app(), self.out, lint)
        self.assertEqual((self.out / "logos" / "app.svg").read_bytes(), GOOD_SVG)
        self.assertIn("![App logo](logos/app.svg)", lines[0])

    def test_refuses_a_symlinked_logo(self):
        (self.tdir / "logo.svg").symlink_to(self.secret)
        with self.assertRaisesRegex(gen.AssetError, "symlink"):
            gen.logo_lines(self.app(), self.out, lint)
        self.assertFalse((self.out / "logos" / "app.svg").exists())

    def test_refuses_a_symlinked_license(self):
        (self.tdir / "logo.svg").write_bytes(GOOD_SVG)
        (self.root / "passwd").write_text("SPDX-FileCopyrightText: root:x:0:0\n")
        (self.tdir / "logo.svg.license").symlink_to(self.root / "passwd")
        with self.assertRaisesRegex(gen.AssetError, "symlink"):
            gen.logo_lines(self.app(), self.out, lint)

    def test_refuses_a_dangling_license_symlink(self):
        (self.tdir / "logo.svg").write_bytes(GOOD_SVG)
        (self.tdir / "logo.svg.license").symlink_to(self.root / "missing")
        with self.assertRaisesRegex(gen.AssetError, "symlink"):
            gen.logo_lines(self.app(), self.out, lint)

    def test_refuses_a_symlinked_template_dir(self):
        real = self.root / "real"
        real.mkdir()
        (real / "logo.svg").write_bytes(GOOD_SVG)
        link = self.root / "src" / "linked"
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(gen.AssetError, "template directory is a symlink"):
            gen.logo_lines(self.app(_dir=link), self.out, lint)

    def test_load_manifests_refuses_a_symlinked_template_dir(self):
        real = self.root / "real"
        real.mkdir()
        (real / "manifest.yaml").write_text("name: X\n")
        (self.root / "src" / "linked").symlink_to(real, target_is_directory=True)
        with self.assertRaises(SystemExit):
            gen.load_manifests(self.root / "src")

    def test_refuses_a_name_with_a_directory(self):
        with self.assertRaises(gen.AssetError):
            gen.read_asset(self.tdir, "../secret.svg", gen.LOGO_MAX)

    def test_refuses_a_logo_that_fails_the_lint(self):
        (self.tdir / "logo.svg").write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
        with self.assertRaisesRegex(gen.AssetError, "fails the logo lint"):
            gen.logo_lines(self.app(), self.out, lint)
        self.assertFalse((self.out / "logos" / "app.svg").exists())

    def test_no_lint_no_copy(self):
        (self.tdir / "logo.svg").write_bytes(GOOD_SVG)
        self.assertEqual(gen.logo_lines(self.app(), self.out, None), [])
        self.assertFalse((self.out / "logos").exists())

    def test_oversized_logo(self):
        (self.tdir / "logo.svg").write_bytes(b" " * (gen.LOGO_MAX + 1))
        with self.assertRaisesRegex(gen.AssetError, "over"):
            gen.logo_lines(self.app(), self.out, lint)

    def test_hostile_credit_is_text(self):
        (self.tdir / "logo.svg").write_bytes(GOOD_SVG)
        (self.tdir / "logo.svg.license").write_text(
            "SPDX-FileCopyrightText: <script>alert(1)</script> [x](javascript:alert(2)) <img src=x onerror=alert(3)>\n"
            "SPDX-License-Identifier: MIT</code><b onclick=alert(4)>\n"
            "Source: javascript:alert(5)\n")
        out = site_html(gen.logo_lines(self.app(), self.out, lint))
        # "javascript:" may stay as text; it is never a link target.
        for bad in ("<script", "<img src=x", "<b onclick", 'href="javascript', "<a "):
            self.assertNotIn(bad, out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", out)
        self.assertIn("[x](", out)  # left as text, never a link
        self.assertNotIn(">source</a>", out)

    def test_source_urls(self):
        for bad in ("javascript:alert(1)", "http://example.org/logo.svg", "https:///nohost",
                    'https://example.org/"onmouseover="alert(1)', "https://example.org/a)b",
                    "https://example.org/a b", "https://example.org/<x>", "https://u:p@example.org/",
                    "data:image/svg+xml,<svg>", ""):
            self.assertEqual(gen.source_url(bad), "", bad)
        ok = "https://github.com/jellyfin/jellyfin-ux/blob/9e27258/branding/SVG/icon-transparent.svg"
        self.assertEqual(gen.source_url(ok), ok)
        html_ = gen.logo_credit({"Source:": ok, "SPDX-FileCopyrightText:": "2019 A & B"})
        self.assertIn('<a href="' + ok + '"', html_)
        self.assertIn("© 2019 A &amp; B", html_)


@unittest.skipUnless(os.environ.get("PORTCULLIS_TEMPLATES"), "PORTCULLIS_TEMPLATES (a templates checkout) not set")
class RealLintTest(unittest.TestCase):
    """The real tests/svgsafe.py loads and refuses a script."""

    def test_real_lint(self):
        check = gen.load_logo_lint(Path(os.environ["PORTCULLIS_TEMPLATES"]))
        self.assertIsNotNone(check)
        self.assertIsNone(check(GOOD_SVG))
        self.assertIsNotNone(check(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><script/></svg>'))


if __name__ == "__main__":
    sys.exit(unittest.main())
