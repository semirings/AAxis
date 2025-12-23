#!/usr/bin/env bash
set -euo pipefail

# ---- configuration ----
BLENDER_BIN="/Applications/Blender.app/Contents/MacOS/Blender"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BLENDER_SCRIPT="$PROJECT_ROOT/scripts/aa_render_grid.py"

# ---- arguments ----
if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <aa.json> <output.(blend|png|mp4)>"
  exit 1
fi

AA_JSON="$1"
OUT_PATH="$2"

# ---- sanity checks ----
[[ -x "$BLENDER_BIN" ]] || { echo "Blender not found/executable: $BLENDER_BIN"; exit 1; }
[[ -f "$BLENDER_SCRIPT" ]] || { echo "Blender script not found: $BLENDER_SCRIPT"; exit 1; }
[[ -f "$AA_JSON" ]] || { echo "AA JSON not found: $AA_JSON"; exit 1; }

# Ensure output directory exists
OUT_DIR="$(dirname "$OUT_PATH")"
mkdir -p "$OUT_DIR"

echo "Rendering AA:"
echo "  AA_JSON : $AA_JSON"
echo "  Output  : $OUT_PATH"
echo "  Blender : $BLENDER_BIN"
echo "  Script  : $BLENDER_SCRIPT"

# ---- invoke blender ----
# IMPORTANT: args after `--` are passed to the python script
"$BLENDER_BIN" \
  -b \
  -P "$BLENDER_SCRIPT" \
  -- \
  --aa "$AA_JSON" \
  --out "$OUT_PATH"
