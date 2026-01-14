#!/usr/bin/env bash

set -euo pipefail

BLENDER="/Applications/Blender.app/Contents/MacOS/Blender"
BLEND="/Users/gcr/ingis.Wk/AAxis/scene.blend"
SCRIPTS_DIR="/Users/gcr/ingis.Wk/AAxis/scripts"

# Default script (override by: SCRIPT=scene_clean.py ./traver_setup.sh ...)
SCRIPT="${SCRIPT:-aa_cards.py}"

"$BLENDER" \
  --factory-startup \
  --background \
  "$BLEND" \
  --python "$SCRIPTS_DIR/$SCRIPT" \
  -- \
  --traversal-json "/Users/gcr/ingis.Wk/AAxis/data/fixtures/aa/traversal_spec.json"

#  aa_cards.py
#  aa_render_grid.py
#  scene_build.py
#  style_apply.py
#  style_theme.py
#  scene_setup.py
#  grid_node_group.py
#  aa_setup_camera.py
#  scene_clean.py
