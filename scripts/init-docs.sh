#!/usr/bin/env bash
# docs-pattern v2 init — creates docs/{state,issues,documentation,history,_inbox} + first pages, then builds.
# Usage: bash init-docs.sh [DOCS_DIR]   (default: docs)
# Existing files are never overwritten.
set -euo pipefail
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS="${1:-docs}"
TODAY="$(date +%F)"
mkdir -p "$DOCS"/{state,issues,documentation,history/issues,_inbox}
cd "$SKILL/templates"
for f in state/S001.md documentation/overview.md history/state/S001.md history/documentation/overview.md; do
  dest="$OLDPWD/$DOCS/$f"
  if [ -e "$dest" ]; then echo "skip  $f"; continue; fi
  mkdir -p "$(dirname "$dest")"
  sed "s/@DATE@/$TODAY/" "$f" > "$dest"
  echo "made  $f"
done
cd "$OLDPWD"
python3 "$SKILL/scripts/docs_build.py" "$DOCS"
