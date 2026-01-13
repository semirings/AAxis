#!/usr/bin/env bash

set -euo pipefail

BLENDER="/Applications/Blender.app/Contents/MacOS/Blender"
BLEND="/Users/gcr/ingis.Wk/AAxis/scene.blend"
SCRIPTS_DIR="/Users/gcr/ingis.Wk/AAxis/scripts"

# Default script (override by: SCRIPT=scene_clean.py ./traver_setup.sh ...)
SCRIPT="${SCRIPT:-scene_clean.py}"

"$BLENDER" \
  --factory-startup \
  --background \
  "$BLEND" \
  --python "$SCRIPTS_DIR/$SCRIPT" \
  -- "$@"

# /Applications/Blender.app/Contents/MacOS/Blender \
#   /Users/gcr/ingis.Wk/AAxis/scene.blend \
#  --background \
#  --python /Users/gcr/ingis.Wk/AAxis/scripts/aa_cards.py
#  --python /Users/gcr/ingis.Wk/AAxis/scripts/aa_render_grid.py
#  --python /Users/gcr/ingis.Wk/AAxis/scripts/scene_build.py
#  --python /Users/gcr/ingis.Wk/AAxis/scripts/style_apply.py
#  --python /Users/gcr/ingis.Wk/AAxis/scripts/style_theme.py
#  --python /Users/gcr/ingis.Wk/AAxis/scripts/scene_setup.py
#  --python /Users/gcr/ingis.Wk/AAxis/scripts/grid_node_group.py
#  --python /Users/gcr/ingis.Wk/AAxis/scripts/aa_setup_camera.py
#  --python /Users/gcr/ingis.Wk/AAxis/scripts/scene_clean.py
