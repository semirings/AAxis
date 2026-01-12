#!/usr/bin/env bash

set -euo pipefail

BLENDER_BIN="${BLENDER_BIN:-blender}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/aa_apply_to_grid.py"

if [[ $# -eq 0 ]]; then
  echo "Usage:"
  echo "  aa_render.sh --template T.blend [--list-groups]"
  echo "  aa_render.sh --template T.blend --aa aa.json --group GroupName --out out.blend [other options...]"
  echo
  echo "This forwards all args to aa_apply_to_grid.py inside Blender."
  exit 1
fi

exec "$BLENDER_BIN" -b -P "$PY_SCRIPT" -- "$@"
