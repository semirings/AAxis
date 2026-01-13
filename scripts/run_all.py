import sys
from pathlib import Path

# Ensure this script's directory is on sys.path so imports like `import scene_build` work.
SCRIPTS_DIR = Path("/Users/gcr/ingis.Wk/AAxis/scripts")  # or your existing logic
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# --- ensure AA_Grid_GN exists BEFORE scene_build ---
from grid_node_group import ensure_aa_grid_gn
ng = ensure_aa_grid_gn("AA_Grid_GN")
print("Ensured GN group:", ng.name)

import scene_build
import os, sys

def ensure_aa_json(path: str | Path, rows, cols, vals):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return

    aa = {
        "rows": rows,
        "cols": cols,
        "vals": vals,
        "meta": {
            "format": "AA_JSON",
            "note": "Auto-generated placeholder for pipeline bring-up"
        }
    }
    p.write_text(json.dumps(aa, indent=2), encoding="utf-8")
    print("Wrote placeholder AA_JSON:", str(p))

AA_JSON = str(Path("/Users/gcr/ingis.Wk/AAxis/data/fixtures/aa/aa_edges.json"))

scene_build.run_from_blender_ui(
    aa_json=AA_JSON,
    traversal_json="/Users/gcr/ingis.Wk/AAxis/data/traversal_spec.json",
    out_blend="/Users/gcr/ingis.Wk/AAxis/scene.blend",
    gn_group="AA_Grid_GN",
    grid_size_x=8.0,
    grid_size_y=5.0,
    start_frame=1,
    frames_per_step=40,
)
