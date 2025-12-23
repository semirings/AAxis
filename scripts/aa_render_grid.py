#!/usr/bin/env python3
from __future__ import annotations

import sys
import json
import os
import argparse
import math
import bpy


# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

def log(msg: str):
    print(msg)
    try:
        sys.stdout.flush()
    except Exception:
        pass


# ------------------------------------------------------------
# Args (matches render_aa.sh)
# ------------------------------------------------------------

def parse_args() -> tuple[str, str]:
    argv = sys.argv
    user_argv = []
    if "--" in argv:
        user_argv = argv[argv.index("--") + 1 :]

    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--aa")
    p.add_argument("--out")
    ns, extras = p.parse_known_args(user_argv)

    if ns.aa and ns.out:
        return ns.aa, ns.out
    if len(extras) >= 2:
        return extras[0], extras[1]

    raise RuntimeError("Expected: --aa <aa.json> --out <output.blend>")


# ------------------------------------------------------------
# Scene utilities
# ------------------------------------------------------------

def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    for block in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.objects,
        bpy.data.collections,
        bpy.data.curves,
        bpy.data.fonts,
    ):
        for b in list(block):
            try:
                block.remove(b)
            except Exception:
                pass


def load_aa(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


# ------------------------------------------------------------
# Materials (exactly 5)
# ------------------------------------------------------------

def _make_material(name: str, rgba: tuple[float, float, float, float]):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = 0.85
    return mat


def ensure_five_materials():
    # 1 head_bg dark grey
    head_bg = bpy.data.materials.get("head_bg") or _make_material("head_bg", (0.20, 0.20, 0.20, 1.0))
    # 2 cell_bg light grey
    cell_bg = bpy.data.materials.get("cell_bg") or _make_material("cell_bg", (0.75, 0.75, 0.75, 1.0))
    # 3 row_fg pink
    row_fg = bpy.data.materials.get("row_fg") or _make_material("row_fg", (1.00, 0.35, 0.70, 1.0))
    # 4 col_fg cyan
    col_fg = bpy.data.materials.get("col_fg") or _make_material("col_fg", (0.25, 0.95, 1.00, 1.0))
    # 5 val_fg yellow
    val_fg = bpy.data.materials.get("val_fg") or _make_material("val_fg", (1.00, 0.95, 0.20, 1.0))

    return {
        "head_bg": head_bg,
        "cell_bg": cell_bg,
        "row_fg": row_fg,
        "col_fg": col_fg,
        "val_fg": val_fg,
    }


# ------------------------------------------------------------
# Text helpers
# ------------------------------------------------------------

def add_text(
    parent,
    body: str,
    x: float,
    y: float,
    z: float,
    size: float,
    max_width: float,
    mat,
    rot_z: float = 0.0,
):
    bpy.ops.object.text_add(location=(x, y, z))
    obj = bpy.context.object
    obj.parent = parent

    obj.data.body = str(body)
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.rotation_euler = (0.0, 0.0, rot_z)

    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    # crude width fit
    est = max(1, len(obj.data.body)) * size * 0.6
    if est > max_width:
        s = max_width / est
        obj.scale = (s, s, s)

    return obj


def stringify_val(v) -> str:
    # D4M Assoc assumes no explicit nulls and deletes them, but
    # your JSON may contain them; show them rather than dropping.
    if v is None:
        return "null"
    if isinstance(v, str):
        return v
    try:
        return str(v)
    except Exception:
        return "null"


# ------------------------------------------------------------
# Triple aggregation (D4M-like, but simple)
# ------------------------------------------------------------

def aggregate_cell(existing: str, new: str, mode: str) -> str:
    """
    If multiple triples land in the same (row,col), decide what to show.
    - 'last': keep last
    - 'first': keep first
    - 'stack': show all, one per line
    - 'min'/'max': try numeric compare, fallback to lexical
    """
    if existing is None:
        return new

    if mode == "first":
        return existing
    if mode == "last":
        return new
    if mode == "stack":
        return existing + "\n" + new

    if mode in ("min", "max"):
        # try numeric
        try:
            a = float(existing)
            b = float(new)
            return str(min(a, b) if mode == "min" else max(a, b))
        except Exception:
            return min(existing, new) if mode == "min" else max(existing, new)

    # default
    return new


# ------------------------------------------------------------
# Build table with headers + vals (from triples)
# ------------------------------------------------------------

def build_table_from_triples(aa: dict, mats) -> float:
    rows = aa.get("rows", [])
    cols = aa.get("cols", [])
    vals = aa.get("vals", [])

    # Most JSON produced from triples should satisfy equal lengths.
    # But we still guard and use the common prefix.
    n = min(len(rows), len(cols), len(vals))
    rows = rows[:n]
    cols = cols[:n]
    vals = vals[:n]

    if n == 0:
        raise ValueError("AA has no triples to render (rows/cols/vals empty).")

    # Preserve first-seen order for headers
    unique_rows = list(dict.fromkeys(rows))
    unique_cols = list(dict.fromkeys(cols))

    row_index = {r: i for i, r in enumerate(unique_rows)}
    col_index = {c: i for i, c in enumerate(unique_cols)}

    scene = bpy.context.scene
    root = scene.collection  # background-safe

    parent = bpy.data.objects.new("AA_Table", None)
    root.objects.link(parent)

    # Layout params
    cell_size = 1.0
    text_z = 0.01
    header_text_size = 0.25
    value_text_size = 0.22
    max_text_width = cell_size * 0.9

    # Header band
    n_rows = len(unique_rows) + 1
    n_cols = len(unique_cols) + 1

    # Create planes
    for r in range(n_rows):
        for c in range(n_cols):
            if r == 0 and c == 0:
                continue  # omit upper-left
            bpy.ops.mesh.primitive_plane_add(size=cell_size)
            cell = bpy.context.object
            cell.parent = parent
            cell.location = (c * cell_size, -r * cell_size, 0.0)
            if r == 0 or c == 0:
                cell.data.materials.append(mats["head_bg"])
            else:
                cell.data.materials.append(mats["cell_bg"])

    # Headers
    rot45 = math.radians(45.0)

    for c_idx, c_lab in enumerate(unique_cols, start=1):
        add_text(
            parent,
            c_lab,
            x=c_idx * cell_size,
            y=0.0,
            z=text_z,
            size=header_text_size,
            max_width=max_text_width,
            mat=mats["col_fg"],
            rot_z=rot45,
        )

    for r_idx, r_lab in enumerate(unique_rows, start=1):
        add_text(
            parent,
            r_lab,
            x=0.0,
            y=-r_idx * cell_size,
            z=text_z,
            size=header_text_size,
            max_width=max_text_width,
            mat=mats["row_fg"],
            rot_z=0.0,
        )

    # Values: render every triple; aggregate collisions
    # D4M default aggregate is min, but for visualization "last" is often nicer.
    AGG_MODE = "last"  # change to: 'min', 'max', 'first', 'stack', 'last'

    cell_text: dict[tuple[int, int], str] = {}

    for i in range(n):
        r_lab = rows[i]
        c_lab = cols[i]
        v_str = stringify_val(vals[i])

        # +1 for header band offsets
        r_cell = row_index[r_lab] + 1
        c_cell = col_index[c_lab] + 1

        key = (r_cell, c_cell)
        prev = cell_text.get(key)
        cell_text[key] = aggregate_cell(prev, v_str, AGG_MODE)

    for (r_cell, c_cell), body in cell_text.items():
        add_text(
            parent,
            body,
            x=c_cell * cell_size,
            y=-r_cell * cell_size,
            z=text_z,
            size=value_text_size,
            max_width=max_text_width,
            mat=mats["val_fg"],
            rot_z=0.0,
        )

    # Center around origin
    width = (n_cols - 1) * cell_size
    height = (n_rows - 1) * cell_size
    parent.location = (-width / 2.0, height / 2.0, 0.0)

    return max(width, height, 1.0)


# ------------------------------------------------------------
# World / Camera / Output
# ------------------------------------------------------------

def setup_world():
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (1, 1, 1, 1)
        bg.inputs["Strength"].default_value = 1.0


def setup_camera(span: float):
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.location = (0.0, 0.0, span * 1.5)
    cam.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.scene.camera = cam


def save_blend(path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not path.lower().endswith(".blend"):
        path += ".blend"
    bpy.ops.wm.save_as_mainfile(filepath=path)
    log(f"[AA_RENDER] Saved {path}")


def main():
    log("[AA_RENDER] starting")

    aa_path, out_path = parse_args()

    clear_scene()
    setup_world()

    mats = ensure_five_materials()
    aa = load_aa(aa_path)

    span = build_table_from_triples(aa, mats)
    setup_camera(span)
    save_blend(out_path)

    log("[AA_RENDER] done")


if __name__ == "__main__":
    main()
