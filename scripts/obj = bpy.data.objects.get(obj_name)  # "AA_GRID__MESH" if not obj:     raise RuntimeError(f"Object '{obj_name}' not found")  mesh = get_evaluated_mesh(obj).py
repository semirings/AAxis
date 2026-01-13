import bpy
import json
import sys
import argparse
from pathlib import Path

# -----------------------------
# CLI parsing (everything after --)
# -----------------------------
def parse_args(argv):
    argv = argv[argv.index("--") + 1:] if "--" in argv else []

    p = argparse.ArgumentParser(
        prog="aa_apply_to_grid.py",
        description=(
            "Open a template .blend that contains a Geometry Nodes node group, "
            "create a grid mesh sized to an AA JSON, write per-cell attributes, "
            "attach the node group to the object, and save a new .blend."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Modes / utilities
    p.add_argument("--template", required=True, help="Template .blend containing the node group (and any materials, etc.)")
    p.add_argument("--list-groups", action="store_true",
                   help="List Geometry Nodes group names found in the template and exit")

    # Apply mode args
    p.add_argument("--aa", help="AA JSON input path (required unless --list-groups)")
    p.add_argument("--group", help="Geometry Nodes node group name to attach (required unless --list-groups)")

    # Output behavior
    p.add_argument("--out", default=None,
                   help="Output .blend path. If omitted, saves back to --template ONLY if --overwrite is set.")
    p.add_argument("--overwrite", action="store_true",
                   help="Allow overwriting the template when --out is omitted or equals --template")

    # Object naming
    p.add_argument("--object", default="AA_Grid_Host", help="Name for created host object")
    p.add_argument("--mesh", default="AA_Grid_Mesh", help="Name for created mesh datablock")

    # Geometry sizing
    p.add_argument("--cell-size", type=float, default=1.0, help="Cell size in Blender units")
    p.add_argument("--origin-topleft", action="store_true",
                   help="If set, treat row 0 as top row (table-like). Default origin is bottom-left.")

    return p.parse_args(argv)

# -----------------------------
# AA JSON parsing
# -----------------------------
def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def parse_aa(data: dict):
    """
    Supported forms:

    A) Dense:
       {"rows":[...], "cols":[...], "vals":[ [..], [..], ... ]}  # vals[r][c]

    B) Sparse indices:
       {"rows":[...], "cols":[...], "entries":[{"r":0,"c":2,"v":7}, ...]}

    C) Triples by label:
       {"rows":[...], "cols":[...], "triples":[{"row":"r1","col":"c2","val":5}, ...]}
    """
    rows = data.get("rows")
    cols = data.get("cols")
    if not isinstance(rows, list) or not isinstance(cols, list):
        raise ValueError("AA JSON must include 'rows' and 'cols' arrays.")

    nrows, ncols = len(rows), len(cols)
    cell = {}  # (ri, ci) -> value

    if "vals" in data:
        vals = data["vals"]
        if not (isinstance(vals, list) and len(vals) == nrows):
            raise ValueError("'vals' must have length == len(rows).")
        for ri in range(nrows):
            rowvals = vals[ri]
            if not (isinstance(rowvals, list) and len(rowvals) == ncols):
                raise ValueError(f"'vals[{ri}]' must have length == len(cols).")
            for ci in range(ncols):
                v = rowvals[ci]
                if v is not None:
                    cell[(ri, ci)] = v

    elif "entries" in data:
        for e in data["entries"]:
            ri = int(e.get("r"))
            ci = int(e.get("c"))
            v = e.get("v")
            if 0 <= ri < nrows and 0 <= ci < ncols:
                cell[(ri, ci)] = v

    elif "triples" in data:
        r_index = {lab: i for i, lab in enumerate(rows)}
        c_index = {lab: i for i, lab in enumerate(cols)}
        for t in data["triples"]:
            rlab = t.get("row")
            clab = t.get("col")
            v = t.get("val")
            if rlab in r_index and clab in c_index:
                cell[(r_index[rlab], c_index[clab])] = v

    else:
        raise ValueError("AA JSON must include one of: 'vals', 'entries', or 'triples'.")

    return rows, cols, cell

# -----------------------------
# Scene/object helpers
# -----------------------------
def remove_if_exists_object(name: str):
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

def remove_if_exists_mesh(name: str):
    if name in bpy.data.meshes:
        bpy.data.meshes.remove(bpy.data.meshes[name], do_unlink=True)

def create_object_and_mesh(obj_name: str, mesh_name: str):
    remove_if_exists_object(obj_name)
    remove_if_exists_mesh(mesh_name)

    mesh = bpy.data.meshes.new(mesh_name)
    obj = bpy.data.objects.new(obj_name, mesh)

    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj, mesh

def build_grid_mesh(mesh, nrows: int, ncols: int, cell_size: float, origin_topleft: bool):
    """
    Quad grid with nrows*ncols faces.
    Faces are row-major: face_index = ri*ncols + ci
    """
    verts = []
    faces = []

    total_w = ncols * cell_size
    total_h = nrows * cell_size
    x0 = -total_w / 2.0
    y0 = -total_h / 2.0

    def y_for_vertex_row(vr: int) -> float:
        return y0 + (nrows - vr) * cell_size if origin_topleft else y0 + vr * cell_size

    for vr in range(nrows + 1):
        y = y_for_vertex_row(vr)
        for vc in range(ncols + 1):
            x = x0 + vc * cell_size
            verts.append((x, y, 0.0))

    def vid(vr, vc):
        return vr * (ncols + 1) + vc

    for ri in range(nrows):
        for ci in range(ncols):
            faces.append((
                vid(ri,     ci),
                vid(ri,     ci + 1),
                vid(ri + 1, ci + 1),
                vid(ri + 1, ci),
            ))

    mesh.from_pydata(verts, [], faces)
    mesh.update()

# -----------------------------
# Attributes
# -----------------------------
def ensure_attribute(mesh, name: str, type_str: str, domain: str):
    if name in mesh.attributes:
        a = mesh.attributes[name]
        if a.data_type != type_str or a.domain != domain:
            mesh.attributes.remove(a)
            a = mesh.attributes.new(name=name, type=type_str, domain=domain)
    else:
        a = mesh.attributes.new(name=name, type=type_str, domain=domain)
    return a

def populate_face_attributes(mesh, nrows, ncols, cell_map):
    aa_val     = ensure_attribute(mesh, "aa_val", "FLOAT", "FACE")
    aa_present = ensure_attribute(mesh, "aa_present", "BOOLEAN", "FACE")
    aa_row     = ensure_attribute(mesh, "aa_row", "INT", "FACE")
    aa_col     = ensure_attribute(mesh, "aa_col", "INT", "FACE")

    expected = nrows * ncols
    if len(mesh.polygons) != expected:
        raise RuntimeError(f"Mesh face count {len(mesh.polygons)} != expected {expected}.")

    for ri in range(nrows):
        for ci in range(ncols):
            fi = ri * ncols + ci
            aa_row.data[fi].value = ri
            aa_col.data[fi].value = ci

            if (ri, ci) in cell_map:
                v = cell_map[(ri, ci)]
                try:
                    aa_val.data[fi].value = float(v)
                except Exception:
                    aa_val.data[fi].value = 1.0
                aa_present.data[fi].value = True
            else:
                aa_val.data[fi].value = 0.0
                aa_present.data[fi].value = False

# -----------------------------
# Geometry Nodes attachment
# -----------------------------
def list_geometry_node_groups():
    return [ng.name for ng in bpy.data.node_groups if ng.bl_idname == "GeometryNodeTree"]

def attach_geometry_nodes(obj, group_name: str):
    if group_name not in bpy.data.node_groups:
        available = list_geometry_node_groups()
        raise ValueError(
            f"Geometry Nodes group '{group_name}' not found.\n"
            f"Available GeometryNodeTree groups: {available}"
        )

    ng = bpy.data.node_groups[group_name]

    # Remove existing GN modifiers to avoid stacking
    for m in list(obj.modifiers):
        if m.type == "NODES":
            obj.modifiers.remove(m)

    mod = obj.modifiers.new(name="GeometryNodes", type="NODES")
    mod.node_group = ng
    return mod

# -----------------------------
# MAIN
# -----------------------------
def main():
    args = parse_args(sys.argv)

    template = Path(args.template).expanduser().resolve()
    if not template.exists():
        raise FileNotFoundError(f"Template .blend not found: {template}")

    # Open template (replaces current file)
    bpy.ops.wm.open_mainfile(filepath=str(template))

    if args.list_groups:
        groups = list_geometry_node_groups()
        print("Geometry Nodes groups in template:")
        for g in groups:
            print(f"  - {g}")
        return

    # Apply mode requires these
    if not args.aa or not args.group:
        raise SystemExit("ERROR: --aa and --group are required unless --list-groups is used.")

    aa_path = Path(args.aa).expanduser().resolve()
    if not aa_path.exists():
        raise FileNotFoundError(f"AA JSON not found: {aa_path}")

    out_path = Path(args.out).expanduser().resolve() if_
