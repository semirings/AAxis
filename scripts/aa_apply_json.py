#!/usr/bin/env python3
from __future__ import annotations

import bpy
import json
import argparse
from typing import Dict, Tuple, Any

def _ensure_face_float_attr(mesh: bpy.types.Mesh, name: str) -> bpy.types.Attribute:
    attr = mesh.attributes.get(name)
    if attr is None:
        attr = mesh.attributes.new(name=name, type='FLOAT', domain='FACE')
    return attr

def _ensure_face_int_attr(mesh: bpy.types.Mesh, name: str) -> bpy.types.Attribute:
    attr = mesh.attributes.get(name)
    if attr is None:
        attr = mesh.attributes.new(name=name, type='INT', domain='FACE')
    return attr

def apply_aa_json_to_grid(
    aa_json_path: str,
    grid_obj_name: str = "AA_GRID__MESH",
    rows_key: str = "rows",
    cols_key: str = "cols",
    vals_key: str = "vals",
) -> None:
    obj = bpy.data.objects.get(grid_obj_name)
    if obj is None or obj.type != "MESH":
        raise RuntimeError(f"Grid object '{grid_obj_name}' not found or not a mesh.")

    mesh = obj.data

    with open(aa_json_path, "r", encoding="utf-8") as f:
        aa = json.load(f)

    rows = aa.get(rows_key, [])
    cols = aa.get(cols_key, [])
    vals = aa.get(vals_key, [])

    if not (isinstance(rows, list) and isinstance(cols, list) and isinstance(vals, list)):
        raise ValueError("AA JSON must contain list fields: rows, cols, vals")

    if len(rows) != len(cols) or len(rows) != len(vals):
        raise ValueError("Sparse AA triples require rows, cols, vals lists to be the same length.")

    # Create attributes
    a_present = _ensure_face_float_attr(mesh, "aa_present")
    a_val = _ensure_face_float_attr(mesh, "aa_val")
    a_row = _ensure_face_int_attr(mesh, "aa_row")
    a_col = _ensure_face_int_attr(mesh, "aa_col")

    # Clear defaults
    for i in range(len(mesh.polygons)):
        a_present.data[i].value = 0.0
        a_val.data[i].value = 0.0
        a_row.data[i].value = -1
        a_col.data[i].value = -1

    # Build index maps
    row_index: Dict[Any, int] = {}
    col_index: Dict[Any, int] = {}
    # If AA JSON includes row/col domain lists, use them; else infer order
    domain_rows = aa.get("rowDomain", None)
    domain_cols = aa.get("colDomain", None)
    if isinstance(domain_rows, list):
        row_index = {r: i for i, r in enumerate(domain_rows)}
    else:
        # infer as encountered
        for r in rows:
            if r not in row_index:
                row_index[r] = len(row_index)

    if isinstance(domain_cols, list):
        col_index = {c: i for i, c in enumerate(domain_cols)}
    else:
        for c in cols:
            if c not in col_index:
                col_index[c] = len(col_index)

    # Map (ri,ci) -> face index
    # Assumption: grid faces are row-major: face = ri * ncols + ci
    nrows = len(row_index)
    ncols = len(col_index)
    expected_faces = nrows * ncols
    if len(mesh.polygons) < expected_faces:
        raise RuntimeError(
            f"Grid mesh has {len(mesh.polygons)} faces but needs at least {expected_faces} "
            f"for {nrows}x{ncols}. If your GN generates faces procedurally, we need a different strategy."
        )

    for r, c, v in zip(rows, cols, vals):
        ri = row_index[r]
        ci = col_index[c]
        face_idx = ri * ncols + ci
        a_present.data[face_idx].value = 1.0
        try:
            a_val.data[face_idx].value = float(v)
        except Exception:
            a_val.data[face_idx].value = 1.0
        a_row.data[face_idx].value = int(ri)
        a_col.data[face_idx].value = int(ci)

    # Store domains on object for debugging
    obj["aa_nrows"] = nrows
    obj["aa_ncols"] = ncols
    obj["aa_rowDomain"] = [str(k) for k in sorted(row_index, key=row_index.get)]
    obj["aa_colDomain"] = [str(k) for k in sorted(col_index, key=col_index.get)]


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Apply AA/JSON sparse triples to grid mesh face attributes.")
    ap.add_argument("--aa-json", required=True)
    ap.add_argument("--grid", default="AA_GRID__MESH")
    return ap.parse_args(argv)


def main():
    argv = []
    if "--" in bpy.app.argv:
        argv = bpy.app.argv[bpy.app.argv.index("--")+1:]
    args = _parse_args(argv)
    apply_aa_json_to_grid(args.aa_json, args.grid)


if __name__ == "__main__":
    main()
