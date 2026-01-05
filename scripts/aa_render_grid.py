#!/usr/bin/env python3
"""
aa_render_grid.py  (DROP-IN)

Blender CLI usage:
  blender -b -P scripts/aa_render_grid.py -- --aa path/to/AA_JSON.json --out out.blend
  blender -b -P scripts/aa_render_grid.py -- --aa path/to/AA_JSON.json --out out.png

Input formats supported:
1) Dense "easy" AA_JSON:
   {"rows":[...], "cols":[...], "vals":[R*C]}   (row-major by default)

2) Triples-list AA_JSON (recommended for canonical handoff):
   {"format":"triples","triples":[[row,col,val], ...]}

3) Parallel triples arrays:
   {"rows":[...], "cols":[...], "vals":[...]} where len(rows)==len(cols)==len(vals)
"""

import sys
import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import bpy


# -------------------------
# Scene helpers
# -------------------------

def clear_scene_aggressive() -> None:
    """Nuclear option: clear everything. Good for batch generation."""
    bpy.ops.wm.read_factory_settings(use_empty=True)

def ensure_collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col

def new_empty(name: str, collection: bpy.types.Collection) -> bpy.types.Object:
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.5
    collection.objects.link(empty)
    return empty

def _depsgraph_update():
    bpy.context.evaluated_depsgraph_get().update()
    bpy.context.view_layer.update()


# -------------------------
# Materials (5 requested)
# -------------------------

def ensure_material(name: str, rgba: Tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)

    # Render color (nodes)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links

    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    out.location = (300, 0)
    bsdf.location = (0, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = 0.85

    # Viewport color (Solid mode often uses diffuse_color)
    mat.diffuse_color = rgba
    return mat

def ensure_aa_materials() -> Dict[str, bpy.types.Material]:
    return {
        "head_bg": ensure_material("head_bg", (0.18, 0.18, 0.18, 1.0)),
        "cell_bg": ensure_material("cell_bg", (0.72, 0.72, 0.72, 1.0)),
        "row_fg":  ensure_material("row_fg",  (1.00, 0.35, 0.65, 1.0)),
        "col_fg":  ensure_material("col_fg",  (0.25, 0.95, 0.95, 1.0)),
        "val_fg":  ensure_material("val_fg",  (1.00, 0.95, 0.20, 1.0)),
    }

def hex_to_rgba(hex_color: str) -> tuple[float, float, float, float]:
    """
    Convert #RRGGBB or #RRGGBBAA to Blender RGBA floats.
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        a = "FF"
    elif len(hex_color) == 8:
        r, g, b, a = (
            hex_color[0:2],
            hex_color[2:4],
            hex_color[4:6],
            hex_color[6:8],
        )
    else:
        raise ValueError(f"Invalid hex color: #{hex_color}")

    return (
        int(r, 16) / 255.0,
        int(g, 16) / 255.0,
        int(b, 16) / 255.0,
        int(a, 16) / 255.0,
    )


# -------------------------
# Text measure + creation
# -------------------------

def add_text_object(
    collection: bpy.types.Collection,
    parent: Optional[bpy.types.Object],
    *,
    name: str,
    body: str,
    location: Tuple[float, float, float],
    size: float,
    material: Optional[bpy.types.Material],
    rot_z: float = 0.0,
    align_x: str = "CENTER",
    align_y: str = "CENTER",
) -> bpy.types.Object:
    curve = bpy.data.curves.new(name=f"{name}_curve", type="FONT")
    curve.body = "" if body is None else str(body)
    curve.size = float(size)
    curve.align_x = align_x
    curve.align_y = align_y

    obj = bpy.data.objects.new(name, curve)
    obj.location = location
    obj.rotation_euler = (0.0, 0.0, float(rot_z))

    if material:
        if obj.data.materials:
            obj.data.materials[0] = material
        else:
            obj.data.materials.append(material)

    collection.objects.link(obj)
    if parent:
        obj.parent = parent
    return obj

def measure_text_dimensions(body: str, size: float, rot_z: float = 0.0) -> Tuple[float, float]:
    """
    Measure text bounds in world units by instantiating a temp FONT object.
    Safe in -b mode.
    """
    tmp_col = ensure_collection("_AA_TMP_MEASURE")
    t = add_text_object(
        tmp_col, None,
        name="_tmp",
        body=body,
        location=(0.0, 0.0, 0.0),
        size=size,
        material=None,
        rot_z=rot_z,
        align_x="LEFT",
        align_y="BOTTOM",
    )
    _depsgraph_update()
    w = max(float(t.dimensions.x), 0.001)
    h = max(float(t.dimensions.y), 0.001)
    bpy.data.objects.remove(t, do_unlink=True)
    return w, h


# -------------------------
# Geometry helpers
# -------------------------

def add_cell_plane(
    collection: bpy.types.Collection,
    parent: Optional[bpy.types.Object],
    *,
    name: str,
    cx: float,
    cy: float,
    z: float,
    w: float,
    h: float,
    material: Optional[bpy.types.Material],
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(cx, cy, z))
    obj = bpy.context.object
    obj.name = name

    _depsgraph_update()
    dx, dy, _ = obj.dimensions
    if dx <= 0.0: dx = 2.0
    if dy <= 0.0: dy = 2.0
    obj.scale.x *= (w / dx)
    obj.scale.y *= (h / dy)

    if material:
        if obj.data.materials:
            obj.data.materials[0] = material
        else:
            obj.data.materials.append(material)

    if parent:
        obj.parent = parent

    # Ensure it lives in our collection
    if obj.name not in collection.objects:
        collection.objects.link(obj)

    return obj


# -------------------------
# AA parsing -> cell_text
# -------------------------

def _stable_unique(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def aa_to_triples(aa: Dict[str, Any], *, layout: str = "row-major", keep_empty: bool = False) -> List[Tuple[str, str, str]]:
    """
    Returns triples list (row_label, col_label, value_str).
    Supports:
      - {"format":"triples","triples":[[r,c,v],...]}
      - dense rows/cols/vals where len(vals)=R*C
      - parallel triples arrays where len(rows)=len(cols)=len(vals)
    """
    empties = ("", None)

    def keep(v: Any) -> bool:
        return keep_empty or (v not in empties)

    # format=triples
    if aa.get("format") == "triples" and isinstance(aa.get("triples"), list):
        out = []
        for t in aa["triples"]:
            if not (isinstance(t, (list, tuple)) and len(t) == 3):
                continue
            r, c, v = t
            if keep(v):
                out.append((str(r), str(c), str(v)))
        return out

    rows = [str(x) for x in aa.get("rows", [])]
    cols = [str(x) for x in aa.get("cols", [])]
    vals = aa.get("vals", [])

    if not rows or not cols:
        raise ValueError("AA JSON must contain non-empty 'rows' and 'cols' (or format=triples).")

    if not isinstance(vals, list):
        raise ValueError("'vals' must be a list (dense or parallel triples arrays).")

    R, C, V = len(rows), len(cols), len(vals)
    out: List[Tuple[str, str, str]] = []

    # dense
    if V == R * C and not (R == C == V):
        if layout not in ("row-major", "col-major"):
            raise ValueError("layout must be 'row-major' or 'col-major'")
        for ri in range(R):
            for ci in range(C):
                idx = (ri * C + ci) if layout == "row-major" else (ci * R + ri)
                v = vals[idx]
                if keep(v):
                    out.append((rows[ri], cols[ci], str(v)))
        return out

    # parallel triples arrays
    n = min(R, C, V)
    for i in range(n):
        v = vals[i]
        if keep(v):
            out.append((rows[i], cols[i], str(v)))
    return out

def triples_to_headers_and_cells(
    triples: List[Tuple[str, str, str]],
    *,
    aggregate: str = "last",
) -> Tuple[List[str], List[str], Dict[Tuple[int, int], str]]:
    """
    Returns:
      row_headers: unique rows in first-seen order
      col_headers: unique cols in first-seen order
      cell_text: dict[(r_idx,c_idx)] = text
    """
    rows = _stable_unique([r for r, _, _ in triples])
    cols = _stable_unique([c for _, c, _ in triples])

    r_index = {r: i for i, r in enumerate(rows)}
    c_index = {c: i for i, c in enumerate(cols)}

    cell_text: Dict[Tuple[int, int], str] = {}

    def agg(old: Optional[str], new: str) -> str:
        if old is None:
            return new
        if aggregate == "first":
            return old
        if aggregate == "stack":
            return old + "\n" + new
        # "last" default
        return new

    for r, c, v in triples:
        key = (r_index[r], c_index[c])
        cell_text[key] = agg(cell_text.get(key), v)

    return rows, cols, cell_text


# -------------------------
# Variable layout
# -------------------------

def cumulative_edges(lengths: List[float], gap: float = 0.0) -> List[float]:
    edges = [0.0]
    cur = 0.0
    for L in lengths:
        cur += float(L)
        edges.append(cur)
        cur += float(gap)
    return edges

def cell_center(edges: List[float], i: int) -> float:
    return (edges[i] + edges[i + 1]) * 0.5

def compute_table_layout(
    *,
    row_headers: List[str],
    col_headers: List[str],
    cell_text: Dict[Tuple[int, int], str],
    size_row: float,
    size_col: float,
    size_val: float,
    pad_x: float,
    pad_y: float,
    min_w: float,
    min_h: float,
    col_header_rot_z: float,
) -> Tuple[List[float], List[float]]:
    """
    Returns col_widths (C+1) and row_heights (R+1), including header row/col.
    """
    R = len(row_headers)
    C = len(col_headers)

    col_widths = [min_w] * (C + 1)
    row_heights = [min_h] * (R + 1)

    # Column headers (rotated)
    for c, label in enumerate(col_headers):
        w, h = measure_text_dimensions(label, size_col, rot_z=col_header_rot_z)
        col_widths[c + 1] = max(col_widths[c + 1], w + 2 * pad_x, min_w)
        row_heights[0] = max(row_heights[0], h + 2 * pad_y, min_h)

    # Row headers
    for r, label in enumerate(row_headers):
        w, h = measure_text_dimensions(label, size_row, rot_z=0.0)
        col_widths[0] = max(col_widths[0], w + 2 * pad_x, min_w)
        row_heights[r + 1] = max(row_heights[r + 1], h + 2 * pad_y, min_h)

    # Values
    for (r, c), body in cell_text.items():
        w, h = measure_text_dimensions(body, size_val, rot_z=0.0)
        col_widths[c + 1] = max(col_widths[c + 1], w + 2 * pad_x, min_w)
        row_heights[r + 1] = max(row_heights[r + 1], h + 2 * pad_y, min_h)

    return col_widths, row_heights


def build_variable_cell_table(
    *,
    collection: bpy.types.Collection,
    parent: bpy.types.Object,
    row_headers: List[str],
    col_headers: List[str],
    cell_text: Dict[Tuple[int, int], str],
    mats: Dict[str, bpy.types.Material],

    palette: Optional[Dict[str, str]] = None,
    caption: Optional[str] = None,

    origin_xy: Tuple[float, float] = (0.0, 0.0),
    text_z: float = 0.02,
    plane_z: float = 0.0,
    # font sizes
    size_row: float = 0.35,
    size_col: float = 0.35,
    size_val: float = 0.32,
    # padding + minima
    pad_x: float = 0.20,
    pad_y: float = 0.16,
    min_w: float = 0.90,
    min_h: float = 0.60,
    gap_x: float = 0.00,
    gap_y: float = 0.00,
    col_header_rot_z: float = math.radians(45.0),
) -> Dict[str, Any]:
    
    if palette:
        mats = {
            k: ensure_material(k, hex_to_rgba(v))
            for k, v in palette.items()
        }


    """
    Builds:
      - header row (rotated column headings)
      - header col (row headings)
      - value cells
      - skips upper-left cell entirely
    Returns layout info including total_w/total_h.
    """
    col_widths, row_heights = compute_table_layout(
        row_headers=row_headers,
        col_headers=col_headers,
        cell_text=cell_text,
        size_row=size_row,
        size_col=size_col,
        size_val=size_val,
        pad_x=pad_x,
        pad_y=pad_y,
        min_w=min_w,
        min_h=min_h,
        col_header_rot_z=col_header_rot_z,
    )

    x_edges = cumulative_edges(col_widths, gap=gap_x)
    y_edges = cumulative_edges(row_heights, gap=gap_y)

    total_w = x_edges[-1]
    total_h = y_edges[-1]

    if caption:
        cap_x = origin_xy[0] + pad_x
        cap_gap = max(0.25, row_heights[0] * 0.25)   # scales with header row

        cap_y = origin_xy[1] + row_heights[0] + gap_y + cap_gap

        add_text_object(
            collection,
            parent,
            name="grid_caption",
            body=caption,
            location=(cap_x, cap_y, text_z),
            size=size_row * 1.1,
            material=mats["row_fg"],
            rot_z=0.0,
            align_x="LEFT",
            align_y="BOTTOM_BASELINE",
        )


    # Place top-left at origin, grow right and down
    ox, oy = origin_xy

    def world_center(r: int, c: int) -> Tuple[float, float]:
        cx = ox + cell_center(x_edges, c)
        cy = oy - cell_center(y_edges, r)
        return cx, cy

    R = len(row_headers)
    C = len(col_headers)

    # Planes (skip r=0,c=0)
    for r in range(R + 1):
        for c in range(C + 1):
            if r == 0 and c == 0:
                continue

            w = col_widths[c]
            h = row_heights[r]
            cx, cy = world_center(r, c)

            is_header = (r == 0 or c == 0)
            mat = mats["head_bg"] if is_header else mats["cell_bg"]

            add_cell_plane(
                collection, parent,
                name=f"cell_r{r}_c{c}",
                cx=cx, cy=cy, z=plane_z,
                w=w, h=h,
                material=mat,
            )

    # Column header text (r=0,c=1..C)
    for c in range(1, C + 1):
        cx, cy = world_center(0, c)
        add_text_object(
            collection, parent,
            name=f"col_{c}",
            body=col_headers[c - 1],
            location=(cx, cy, text_z),
            size=size_col,
            material=mats["col_fg"],
            rot_z=col_header_rot_z,
            align_x="LEFT",
            align_y="BOTTOM",
        )

    # Row header text (c=0,r=1..R)
    for r in range(1, R + 1):
        cx, cy = world_center(r, 0)
        add_text_object(
            collection, parent,
            name=f"row_{r}",
            body=row_headers[r - 1],
            location=(cx, cy, text_z),
            size=size_row,
            material=mats["row_fg"],
            rot_z=0.0,
            align_x="RIGHT",
            align_y="CENTER",
        )

    # Value text (r=1..R,c=1..C)
    for (vr, vc), body in cell_text.items():
        r = vr + 1
        c = vc + 1
        cx, cy = world_center(r, c)
        add_text_object(
            collection, parent,
            name=f"val_{r}_{c}",
            body=body,
            location=(cx, cy, text_z),
            size=size_val,
            material=mats["val_fg"],
            rot_z=0.0,
            align_x="LEFT",
            align_y="CENTER",
        )

    _depsgraph_update()

    return {
        "col_widths": col_widths,
        "row_heights": row_heights,
        "total_w": total_w,
        "total_h": total_h,
        "x_edges": x_edges,
        "y_edges": y_edges,
    }


# -------------------------
# Camera + output
# -------------------------

def ensure_camera_ortho(span_w: float, span_h: float, *, margin: float = 0.8) -> bpy.types.Object:
    scene = bpy.context.scene
    cam = next((o for o in scene.objects if o.type == "CAMERA"), None)

    if cam is None:
        cam_data = bpy.data.cameras.new("Camera")
        cam = bpy.data.objects.new("Camera", cam_data)
        scene.collection.objects.link(cam)

    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(span_w, span_h) + margin

    # Place camera looking down -Z
    cam.location = (span_w * 0.5, -span_h * 0.5, 15.0)
    cam.rotation_euler = (0.0, 0.0, 0.0)

    scene.camera = cam
    return cam

def write_output(out_path: str) -> None:
    scene = bpy.context.scene
    p = Path(out_path)
    ext = p.suffix.lower()

    if ext == ".blend":
        bpy.ops.wm.save_as_mainfile(filepath=str(p))
        return

    if ext in (".png", ".jpg", ".jpeg"):
        scene.render.filepath = str(p)
        scene.render.image_settings.file_format = "PNG" if ext == ".png" else "JPEG"
        bpy.ops.render.render(write_still=True)
        return

    # Default: save .blend if unknown
    bpy.ops.wm.save_as_mainfile(filepath=str(p.with_suffix(".blend")))

def load_caption(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    data = json.loads(Path(path).read_text())
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return data.get("caption")
    raise ValueError("caption JSON must be a string or an object with a 'caption' field.")

def load_palette(path: Optional[str]) -> Optional[Dict[str, str]]:
    if not path:
        return None
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError("palette JSON must be an object mapping material keys to hex strings.")
    return data

# -------------------------
# Main
# -------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aa", required=True, help="Path to AA JSON (dense or triples).")
    ap.add_argument("--caption-json", default=None, help="Path to caption JSON file")
    ap.add_argument("--palette-json", default=None, help="Path to palette JSON file")
    ap.add_argument("--out", required=True, help="Output .blend or .png/.jpg")

    ap.add_argument("--layout", default="row-major", choices=["row-major", "col-major"],
                    help="Dense vals flattening order.")
    ap.add_argument("--keep-empty", action="store_true", help="Keep empty cells as triples.")
    ap.add_argument("--aggregate", default="last", choices=["last", "first", "stack"],
                    help="If duplicate (row,col) pairs exist, how to combine.")
    ap.add_argument("--no-clear", action="store_true", help="Do not factory-reset the scene.")
    return ap.parse_args(argv)

def main():
    argv = None
    # Blender passes args after "--"
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]

    args = parse_args(argv)
    
    caption = load_caption(args.caption_json)
    print("caption=", caption)
    palette = load_palette(args.palette_json)
    print("palette=", palette)
   
    if not args.no_clear:
        clear_scene_aggressive()

    aa = json.loads(Path(args.aa).read_text())

    triples = aa_to_triples(aa, layout=args.layout, keep_empty=args.keep_empty)
    row_headers, col_headers, cell_text = triples_to_headers_and_cells(triples, aggregate=args.aggregate)

    mats = ensure_aa_materials()
    col = ensure_collection("AA_TABLE")
    parent = new_empty("AA_table", col)

    # Build the grid. origin_xy is top-left corner of the table
    layout_info = build_variable_cell_table(
        collection=col,
        parent=parent,
        row_headers=row_headers,
        col_headers=col_headers,
        cell_text=cell_text,
        mats=mats,
        caption=caption,
        palette=palette,
        origin_xy=(0.0, 0.0),
        col_header_rot_z=math.radians(45.0),
        gap_x=0.05,
        gap_y=0.05,
    )

    # Camera framing
    ensure_camera_ortho(layout_info["total_w"], layout_info["total_h"])

    write_output(args.out)


if __name__ == "__main__":
    main()
