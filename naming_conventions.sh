#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# aa_naming.sh
#
# Convenience wrapper for naming_conventions.py
#
# Supports:
#   1) Dry-run
#   2) Apply canonical naming
#   3) Apply explicit traversal step + label mappings
#
# ------------------------------------------------------------

# ---- Configuration ----

BLENDER_BIN="${BLENDER_BIN:-blender}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMING_SCRIPT="${SCRIPT_DIR}/naming_conventions.py"

BLEND_FILE=""
MODE="dry-run"
VERBOSE="--verbose"

# Explicit mappings (optional)
CODE_STEPS=()
LABEL_NODES=()

# ---- Usage ----

usage() {
  cat <<EOF
Usage:
  aa_naming.sh --blend <file.blend> [options]

Modes (choose one):
  --dry-run              Show proposed renames only (default)
  --apply                Apply canonical naming
  --apply-mapped         Apply naming with explicit step/node mappings

Options:
  --code-step "N:Title"  Code card step mapping (repeatable)
  --label-node "N:Title" Label card node mapping (repeatable)
  --with-grid            Rename detected AA grid mesh
  --no-verbose           Disable verbose output
  -h, --help             Show this help

Examples:

1) Dry-run:
  aa_naming.sh --blend scene.blend

2) Apply canonical naming:
  aa_naming.sh --blend scene.blend --apply

3) Apply with explicit traversal mapping:
  aa_naming.sh --blend scene.blend --apply-mapped \\
    --code-step "1:Patient to Encounter" \\
    --code-step "2:Encounter to Observation" \\
    --code-step "3:Observation to Practitioner" \\
    --label-node "1:Patient" \\
    --label-node "2:Encounter" \\
    --label-node "3:Specimen"

Environment:
  BLENDER_BIN   Override Blender executable (default: blender)

EOF
  exit 0
}

# ---- Argument parsing ----

WITH_GRID=""
APPLY_FLAG="--dry-run"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --blend)
      BLEND_FILE="$2"
      shift 2
      ;;
    --dry-run)
      MODE="dry-run"
      APPLY_FLAG="--dry-run"
      shift
      ;;
    --apply)
      MODE="apply"
      APPLY_FLAG="--apply"
      shift
      ;;
    --apply-mapped)
      MODE="apply-mapped"
      APPLY_FLAG="--apply"
      shift
      ;;
    --code-step)
      CODE_STEPS+=("$2")
      shift 2
      ;;
    --label-node)
      LABEL_NODES+=("$2")
      shift 2
      ;;
    --with-grid)
      WITH_GRID="--with-grid"
      shift
      ;;
    --no-verbose)
      VERBOSE=""
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      ;;
  esac
done

# ---- Validation ----

if [[ -z "$BLEND_FILE" ]]; then
  echo "Error: --blend <file.blend> is required"
  usage
fi

if [[ ! -f "$BLEND_FILE" ]]; then
  echo "Error: Blend file not found: $BLEND_FILE"
  exit 1
fi

if [[ ! -f "$NAMING_SCRIPT" ]]; then
  echo "Error: naming_conventions.py not found in $SCRIPT_DIR"
  exit 1
fi

# ---- Build Blender command ----

CMD=(
  "$BLENDER_BIN"
  -b "$BLEND_FILE"
  --python "$NAMING_SCRIPT"
  --
  "$APPLY_FLAG"
  "$VERBOSE"
)

if [[ -n "$WITH_GRID" ]]; then
  CMD+=("$WITH_GRID")
fi

if [[ "$MODE" == "apply-mapped" ]]; then
  for cs in "${CODE_STEPS[@]}"; do
    CMD+=(--code-step "$cs")
  done
  for ln in "${LABEL_NODES[@]}"; do
    CMD+=(--label-node "$ln")
  done
fi

# ---- Run ----

echo "Running naming conventions ($MODE) on:"
echo "  $BLEND_FILE"
echo

"${CMD[@]}"

echo
echo "Done."
