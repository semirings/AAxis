#!/usr/bin/env python3
from __future__ import annotations

import bpy
import argparse
import json
from typing import Dict, List, Tuple, Optional

from util_blender import ensure_collection, ensure_object_linked, ensure_material
from style_theme import DEFAULT_THEME, Theme


def _make_card_plane(name: str, w: float, h: float) -> bpy.types.Object:
    bpy.ops.mesh.primitive_plane_add(size=1.0, enter_editmode=False, align='WORLD')
    obj = bpy.context.active_object
    obj.name = name
    obj.scale[0] = w * 0.5
    obj.scale[1] = h * 0.5
    return obj


def _make_text(name: str, text: str) -> bpy.types.Object:
    bpy.ops.object.text_add(enter_editmode=False, align='WORLD')
    obj = bpy.context.active_object
    obj.name = name
    obj.data.body = text
    obj.data.align_x = 'LEFT'
    obj.data.align_y = 'TOP'
    return obj


def _ensure_alpha_driver(mat: bpy.types.Material) -> bpy.types.NodeSocket:
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    mat.blend_method = "BLEND"
    return bsdf.inputs["Alpha"]


def _key_alpha(mat: bpy.types.Material, frame: int, alpha: float) -> None:
    sock = _ensure_alpha_driver(mat)
    sock.default_value = alpha
    sock.keyframe_insert("default_value", frame=frame)


def create_card(
    parent_collection: str,
    card_collection: str,
    plane_name: str,
    text_name: str,
    text: str,
    location: Tuple[float, float, float],
    size: Tuple[float, float] = (6.0, 1.2),
) -> Tuple[bpy.types.Object, bpy.types.Object]:
    root = ensure_collection(parent_collection)
    col = ensure_collection(card_collection, parent=root)

    plane = _make_card_plane(plane_name, size[0], size[1])
    plane.location = location

    txt = _make_text(text_name, text)
    txt.location = (location[0] - size[0]*0.45, location[1] + size[1]*0.25, location[2] + 0.01)

    ensure_object_linked(plane, col)
    ensure_object_linked(txt, col)

    return plane, txt


def animate_card_alpha(
    plane: bpy.types.Object,
    fade_in_start: int,
    fade_in_end: int,
    hold_end: int,
    fade_out_end: int,
    visible_alpha: float = 0.75,
) -> None:
    mat = plane.data.materials[0] if plane.type == "MESH" and plane.data.materials else None
    if mat is None:
        mat = ensure_material("MAT_CARD_BG")
        plane.data.materials.append(mat)

    # Key alpha: 0 -> visible -> 0
    _key_alpha(mat, fade_in_start, 0.0)
    _key_alpha(mat, fade_in_end, visible_alpha)
    _key_alpha(mat, hold_end, visible_alpha)
    _key_alpha(mat, fade_out_end, 0.0)


def build_cards_from_spec(
    traversal_json_path: str,
    cards_parent: str = "GEN_OVERLAY_CARDS",
    labels_parent: str = "GEN_OVERLAY_LABELS",
    z: float = 0.5,
    start_frame: int = 1,
    frames_per_step: int = 40,
) -> Dict[str, List[bpy.types.Object]]:
    with open(traversal_json_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    steps = spec.get("steps", [])
    node_map = spec.get("nodeMap", {})

    created = {"code": [], "labels": []}

    # 1) One roster card (labels) – shows mapping briefly
    roster_lines = []
    for k in sorted(node_map.keys(), key=lambda x: int(x)):
        roster_lines.append(f"{k} = {node_map[k]}")
    roster_text = "Roster:\n" + "\n".join(roster_lines)

    plane, txt = create_card(
        parent_collection=labels_parent,
        card_collection="GEN_LABEL_ROSTER",
        plane_name="CARD_LABEL_ROSTER__PLANE",
        text_name="CARD_LABEL_ROSTER__TEXT",
        text=roster_text,
        location=(0.0, -4.0, z),
        size=(6.5, 2.5),
    )
    created["labels"].extend([plane, txt])
    animate_card_alpha(plane, start_frame, start_frame+8, start_frame+60, start_frame+70)

    # 2) Code cards per step
    for st in steps:
        step = int(st.get("step", 0))
        code = st.get("code", None)
        if not code:
            # fallback: show generic step title
            nodes = ",".join([str(n) for n in st.get("activateNodes", [])])
            code = f"# step {step}\nactive = {{{nodes}}}"

        f0 = start_frame + (step-1) * frames_per_step
        plane, txt = create_card(
            parent_collection=cards_parent,
            card_collection=f"GEN_CARD_CODE_S{step:02d}",
            plane_name=f"CARD_CODE_S{step:02d}__PLANE",
            text_name=f"CARD_CODE_S{step:02d}__TEXT",
            text=code,
            location=(0.0, -5.2, z),
            size=(7.2, 1.4),
        )
        created["code"].extend([plane, txt])
        animate_card_alpha(plane, f0+4, f0+10, f0+frames_per_step-6, f0+frames_per_step-1)

    return created


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Create + animate code/label cards from traversal spec JSON.")
    ap.add_argument("--traversal-json", required=True)
    ap.add_argument("--start-frame", type=int, default=1)
    ap.add_argument("--frames-per-step", type=int, default=40)
    return ap.parse_args(argv)


def main():
    argv = []
    if "--" in bpy.app.argv:
        argv = bpy.app.argv[bpy.app.argv.index("--")+1:]
    args = _parse_args(argv)
    build_cards_from_spec(args.traversal_json, start_frame=args.start_frame, frames_per_step=args.frames_per_step)


if __name__ == "__main__":
    main()
