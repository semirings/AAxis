import sys

def checkpoint(tag: str):
    print(f"CHECKPOINT: {tag}")
    sys.stdout.flush()
    stop = os.environ.get("AA_STOP_AFTER", "").strip()
    if stop and stop == tag:
        print(f"Stopping after checkpoint '{tag}' (AA_STOP_AFTER).")
        sys.stdout.flush()
        raise SystemExit(0)
    
def run_from_blender_ui(
    aa_json: str,
    traversal_json: str,
    out_blend: str,
    grid_size_x: float = 8.0,
    grid_size_y: float = 5.0,
    gn_group: str = "AA_Grid_GN",
    start_frame: int = 1,
    frames_per_step: int = 40,
):
    class Args:
        pass

    args = Args()
    args.aa_json = aa_json
    args.traversal_json = traversal_json
    args.out_blend = out_blend
    args.grid_size_x = grid_size_x
    args.grid_size_y = grid_size_y
    args.gn_group = gn_group
    args.start_frame = start_frame
    args.frames_per_step = frames_per_step

    # --- inline what main() does ---
    from scene_clean import clean_generated
    from scene_setup import setup_collections
    from aa_build_grid import build_grid_plane
    from aa_apply_json import apply_aa_json_to_grid
    from aa_traversal import apply_traversal_steps
    from aa_cards import build_cards_from_spec
    from style_apply import apply_theme
    from util_blender import frame_range_set
    
    checkpoint("clean")
    clean_generated()
    setup_collections()

    checkpoint("grid")
    build_grid_plane(
        name="AA_GRID__MESH",
        collection="GEN_AA_GRID",
        size_x=args.grid_size_x,
        size_y=args.grid_size_y,
        gn_group_name=args.gn_group,
    )

    checkpoint("apply_json")
    apply_aa_json_to_grid(args.aa_json, "AA_GRID__MESH")
    max_step = apply_traversal_steps(args.traversal_json, "AA_GRID__MESH")

    checkpoint("cards")
    build_cards_from_spec(
        args.traversal_json,
        start_frame=args.start_frame,
        frames_per_step=args.frames_per_step,
        z=0.5,
    )

    frame_range_set(
        args.start_frame,
        args.start_frame + max_step * args.frames_per_step
    )

    checkpoint("theme")
    apply_theme()

    import bpy
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend)

def run_from_blender_ui(
    aa_json: str,
    traversal_json: str,
    out_blend: str,
    grid_size_x: float = 8.0,
    grid_size_y: float = 5.0,
    gn_group: str = "AA_Grid_GN",
    start_frame: int = 1,
    frames_per_step: int = 40,
):
    class Args:
        pass

    args = Args()
    args.aa_json = aa_json
    args.traversal_json = traversal_json
    args.out_blend = out_blend
    args.grid_size_x = grid_size_x
    args.grid_size_y = grid_size_y
    args.gn_group = gn_group
    args.start_frame = start_frame
    args.frames_per_step = frames_per_step

    # --- inline what main() does ---
    from scene_clean import clean_generated
    from scene_setup import setup_collections
    from aa_build_grid import build_grid_plane
    from aa_apply_json import apply_aa_json_to_grid
    from aa_traversal import apply_traversal_steps
    from aa_cards import build_cards_from_spec
    from style_apply import apply_theme
    from util_blender import frame_range_set

    clean_generated()
    setup_collections()

    build_grid_plane(
        name="AA_GRID__MESH",
        collection="GEN_AA_GRID",
        size_x=args.grid_size_x,
        size_y=args.grid_size_y,
        gn_group_name=args.gn_group,
    )

    apply_aa_json_to_grid(args.aa_json, "AA_GRID__MESH")

    checkpoint("traversal")
    max_step = apply_traversal_steps(args.traversal_json, "AA_GRID__MESH")

    build_cards_from_spec(
        args.traversal_json,
        start_frame=args.start_frame,
        frames_per_step=args.frames_per_step,
        z=0.5,
    )

    frame_range_set(
        args.start_frame,
        args.start_frame + max_step * args.frames_per_step
    )

    apply_theme()

    import bpy
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend)
