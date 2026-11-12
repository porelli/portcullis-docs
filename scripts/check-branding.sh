#!/usr/bin/env bash
# The docs site's logo and favicon are verbatim copies of the branding source
# (concept 1 "Raised gate"). The sha256 values are pinned here, not read from
# outside the repo; a mismatch names the file and fails.
set -euo pipefail

cd "$(dirname "$0")/.."

if command -v sha256sum >/dev/null 2>&1; then
  sha() { sha256sum "$1" | cut -d' ' -f1; }
else
  sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
fi

check() {
  local file=$1 want=$2 got
  if [[ ! -f $file ]]; then
    echo "check-branding: $file is missing" >&2
    exit 1
  fi
  got=$(sha "$file")
  if [[ $got != "$want" ]]; then
    echo "check-branding: $file sha256 $got, want $want" >&2
    exit 1
  fi
}

# favicon.svg
check docs/assets/favicon.svg 8c07f90ac5371f5742ca1837b45ff450f56674c8773ddbcd0b4b03fa17fd2352
# concept-1-mark-dark.svg
check docs/assets/logo.svg a63ddab1ce0eac394cdbc7547f9fcbc9bf6947060601dd5202527222cef97bfa

echo "check-branding: ok"
