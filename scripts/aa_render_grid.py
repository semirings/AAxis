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

import bpy
import math

def _depsgraph_update():
    # In background mode, this is usually enough.
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()

def measure_text_dimensions(
    body: str,
    size: float,
    *,
    rotation_z_rad: float = 0.0,
    font: bpy.types.VectorFont | None = None,
    extrude: float = 0.0,
) -> tuple[float, float]:
    """
    Returns (width, height) in Blender world units for a Text object.

    We create a temporary text object, update depsgraph, read obj.dimensions,
    then delete it. This is robust in -b mode.
    """
    scene = bpy.context.scene
    root = scene.collection

    bpy.ops.object.text_add(location=(0.0, 0.0, 0.0))
    obj = bpy.context.object
    obj.hide_render = True
    obj.hide_viewport = True

    obj.data.body = "" if body is None else str(body)
    obj.data.size = float(size)
    obj.data.extrude = float(extrude)
    obj.rotation_euler = (0.0, 0.0, float(rotation_z_rad))

    if font is not None:
        obj.data.font = font

    # Link explicitly (background-safe) and update
    if obj.name not in root.objects:
        root.objects.link(obj)

    _depsgraph_update()

    # dimensions includes rotation effect (bounding box in world axes)
    w = float(obj.dimensions.x)
    h = float(obj.dimensions.y)

    # Cleanup
    bpy.data.objects.remove(obj, do_unlink=True)

    # Guard: empty strings can sometimes measure ~0
    return max(w, 0.001), max(h, 0.001)

def default_cell_style():
    """
    Returns a dict of layout style knobs.
    Tune these without touching layout logic.
    """
    return {
        "pad_x": 0.20,      # horizontal padding added to measured text width
        "pad_y": 0.20,      # vertical padding added to measured text height
        "min_w": 0.60,      # minimum cell width
        "min_h": 0.45,      # minimum cell height
        "gap_x": 0.00,      # optional gap between columns
        "gap_y": 0.00,      # optional gap between rows
    }

def compute_table_layout(
    *,
    row_headers: list[str],                 # length R
    col_headers: list[str],                 # length C
    cell_text: dict[tuple[int, int], str],  # keys (r,c) where r in [0..R-1], c in [0..C-1]
    sizes: dict,
    style: dict,
    col_header_rot_z: float = math.radians(45.0),
    font: bpy.types.VectorFont | None = None,
) -> tuple[list[float], list[float]]:
    """
    Returns (col_widths, row_heights) for a table with:
      - header row (col_headers) and header col (row_headers)
      - value region cell_text

    We compute:
      col_widths[0] for the row-header column
      col_widths[c+1] for value columns
      row_heights[0] for the col-header row
      row_heights[r+1] for value rows

    sizes = {
      "row_header": 0.25,
      "col_header": 0.25,
      "value": 0.22
    }
    """
    R = len(row_headers)
    C = len(col_headers)

    pad_x = style["pad_x"]
    pad_y = style["pad_y"]
    min_w = style["min_w"]
    min_h = style["min_h"]

    # 0th col is row headers; cols 1..C are value columns
    col_widths = [min_w] * (C + 1)
    # 0th row is col headers; rows 1..R are value rows
    row_heights = [min_h] * (R + 1)

    # --- measure column headers (affects row 0 height and each value column width) ---
    for c, label in enumerate(col_headers):
        w, h = measure_text_dimensions(
            label,
            sizes["col_header"],
            rotation_z_rad=col_header_rot_z,
            font=font,
        )
        col_widths[c + 1] = max(col_widths[c + 1], w + pad_x * 2, min_w)
        row_heights[0] = max(row_heights[0], h + pad_y * 2, min_h)

    # --- measure row headers (affects col 0 width and each value row height) ---
    for r, label in enumerate(row_headers):
        w, h = measure_text_dimensions(
            label,
            sizes["row_header"],
            rotation_z_rad=0.0,
            font=font,
        )
        col_widths[0] = max(col_widths[0], w + pad_x * 2, min_w)
        row_heights[r + 1] = max(row_heights[r + 1], h + pad_y * 2, min_h)

    # --- measure value cells (affects both their row height and column width) ---
    for (r, c), body in cell_text.items():
        w, h = measure_text_dimensions(
            body,
            sizes["value"],
            rotation_z_rad=0.0,
            font=font,
        )
        col_widths[c + 1] = max(col_widths[c + 1], w + pad_x * 2, min_w)
        row_heights[r + 1] = max(row_heights[r + 1], h + pad_y * 2, min_h)

    return col_widths, row_heights

def cumulative_edges(lengths: list[float], gap: float = 0.0) -> list[float]:
    """
    For lengths [L0, L1, ...], returns edges [0, e1, e2, ...] where
    each step adds length + gap.

    edges[i] is the start edge of cell i.
    edges[i+1] is the end edge of cell i.
    """
    edges = [0.0]
    cur = 0.0
    for L in lengths:
        cur += float(L)
        edges.append(cur)
        cur += float(gap)
    return edges

def cell_center(edges: list[float], i: int) -> float:
    return (edges[i] + edges[i + 1]) * 0.5

def total_span(edges: list[float]) -> float:
    return edges[-1]

def add_cell_plane(
    parent,
    *,
    cx: float,
    cy: float,
    w: float,
    h: float,
    mat,
    name: str,
):
    """
    Adds a plane of width w and height h centered at (cx,cy).
    Blender's primitive plane uses a square "size" (half-dimension scaling),
    so we create unit plane and scale it.
    """
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(cx, cy, 0.0))
    obj = bpy.context.object
    obj.name = name
    obj.parent = parent

    # unit plane is 2x2 when size=1.0? Actually size is radius, so plane ends up 2x2.
    # scaling by (w/2, h/2) yields final w x h.
    obj.scale = (w / 2.0, h / 2.0, 1.0)

    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return obj

def add_text_object(
    parent,
    *,
    body: str,
    cx: float,
    cy: float,
    z: float,
    size: float,
    mat,
    rot_z: float = 0.0,
    font: bpy.types.VectorFont | None = None,
):
    bpy.ops.object.text_add(location=(cx, cy, z))
    obj = bpy.context.object
    obj.parent = parent

    obj.data.body = "" if body is None else str(body)
    obj.data.size = float(size)
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.rotation_euler = (0.0, 0.0, float(rot_z))

    if font is not None:
        obj.data.font = font

    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return obj

def build_variable_cell_table(
    *,
    parent,
    row_headers: list[str],
    col_headers: list[str],
    cell_text: dict[tuple[int, int], str],
    mats: dict,
    sizes: dict,
    style: dict | None = None,
    col_header_rot_z: float = math.radians(45.0),
    font: bpy.types.VectorFont | None = None,
    text_z: float = 0.01,
):
    if style is None:
        style = default_cell_style()

    # 1) compute per-row/per-col sizes
    col_widths, row_heights = compute_table_layout(
        row_headers=row_headers,
        col_headers=col_headers,
        cell_text=cell_text,
        sizes=sizes,
        style=style,
        col_header_rot_z=col_header_rot_z,
        font=font,
    )

    # 2) compute edges
    x_edges = cumulative_edges(col_widths, gap=style["gap_x"])
    y_edges = cumulative_edges(row_heights, gap=style["gap_y"])

    # We want y increasing upward, but our table rows go downward.
    # We'll build with y=0 at top edge, then subtract.
    total_w = total_span(x_edges)
    total_h = total_span(y_edges)

    # Center table around origin
    x0 = -total_w / 2.0
    y0 = +total_h / 2.0

    # 3) planes (skip upper-left)
    R = len(row_headers)
    C = len(col_headers)

    for r in range(R + 1):       # includes header row 0
        for c in range(C + 1):   # includes header col 0
            if r == 0 and c == 0:
                continue

            w = col_widths[c]
            h = row_heights[r]
            cx = x0 + cell_center(x_edges, c)
            cy = y0 - cell_center(y_edges, r)

            is_header = (r == 0 or c == 0)
            mat = mats["head_bg"] if is_header else mats["cell_bg"]
            add_cell_plane(
                parent,
                cx=cx, cy=cy,
                w=w, h=h,
                mat=mat,
                name=f"cell_r{r}_c{c}",
            )

    # 4) header text
    # Column headers: row 0, col 1..C
    for c in range(1, C + 1):
        cx = x0 + cell_center(x_edges, c)
        cy = y0 - cell_center(y_edges, 0)
        add_text_object(
            parent,
            body=col_headers[c - 1],
            cx=cx, cy=cy, z=text_z,
            size=sizes["col_header"],
            mat=mats["col_fg"],
            rot_z=col_header_rot_z,
            font=font,
        )

    # Row headers: col 0, row 1..R
    for r in range(1, R + 1):
        cx = x0 + cell_center(x_edges, 0)
        cy = y0 - cell_center(y_edges, r)
        add_text_object(
            parent,
            body=row_headers[r - 1],
            cx=cx, cy=cy, z=text_z,
            size=sizes["row_header"],
            mat=mats["row_fg"],
            rot_z=0.0,
            font=font,
        )

    # 5) value text: (r,c) in value region maps to (r+1,c+1) in full grid
    for (vr, vc), body in cell_text.items():
        r = vr + 1
        c = vc + 1
        cx = x0 + cell_center(x_edges, c)
        cy = y0 - cell_center(y_edges, r)
        add_text_object(
            parent,
            body=body,
            cx=cx, cy=cy, z=text_z,
            size=sizes["value"],
            mat=mats["val_fg"],
            rot_z=0.0,
            font=font,
        )

    return {
        "col_widths": col_widths,
        "row_heights": row_heights,
        "total_w": total_w,
        "total_h": total_h,
        "x_edges": x_edges,
        "y_edges": y_edges,
    }



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
    sizes = {
    "row_header": 0.25,
    "col_header": 0.25,
    "value": 0.22,
    }

    aa = load_aa(aa_path)
    
    layout_info = build_variable_cell_table(
        parent=parent_empty,
        row_headers=row_headers,
        col_headers=col_headers,
        cell_text=cell_text,
        mats=mats,
        sizes=sizes,
    )
    span = build_table_from_triples(aa, mats)
    setup_camera(span)
    save_blend(out_path)

    log("[AA_RENDER] done")


if __name__ == "__main__":
    main()
