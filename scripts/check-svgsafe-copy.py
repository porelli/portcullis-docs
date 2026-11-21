#!/usr/bin/env python3
"""Checks that scripts/svgsafe.py is a byte copy of the templates repo's
tests/svgsafe.py below its header marker (CI step "svgsafe copy matches
the templates repo"). Both files are read as bytes only: nothing from the
templates checkout is imported or run.

Usage: python scripts/check-svgsafe-copy.py <portcullis-templates checkout>
"""
import sys
from pathlib import Path

MARKER = b"# --- byte copy of portcullis-templates tests/svgsafe.py below ---\n"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    ours = (Path(__file__).parent / "svgsafe.py").read_bytes()
    theirs_path = Path(sys.argv[1]) / "tests" / "svgsafe.py"
    if theirs_path.is_symlink():
        print(f"check-svgsafe-copy: {theirs_path} is a symlink", file=sys.stderr)
        return 1
    theirs = theirs_path.read_bytes()
    at = ours.find(MARKER)
    if at < 0:
        print("check-svgsafe-copy: scripts/svgsafe.py has no marker line", file=sys.stderr)
        return 1
    if ours[at + len(MARKER):] != theirs:
        print(f"check-svgsafe-copy: scripts/svgsafe.py differs from {theirs_path}: copy it below the marker", file=sys.stderr)
        return 1
    print("check-svgsafe-copy: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
