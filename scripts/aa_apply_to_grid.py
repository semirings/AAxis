#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import bpy


# ------------------------------------------------------------
# Context / safety helpers
# ------------------------------------------------------------
def _force_object_mode(obj: bpy.types.Object) -> None:
    try:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        # In --background, ops can fail; keep going.
        pass


def _detach_gn_modifiers(obj: bpy.types.Object) -> List[Tuple[str, bpy.types.NodeTree | None, bool, bool]]:
    """
    Remove all Geometry Nodes modifiers from obj and return a list of tuples
    describing them so we can restore later.

    This is the most reliable way to avoid Blender segfaults in headless runs
    while you clear/rebuild mesh geometry + attributes.
    """
    saved: List[Tuple[str, bpy.types.NodeTree | None, bool, bool]] = []
    for m in list(obj.modifiers):
        if m.type == "NODES":
            # Store: (modifier_name, node_group, show_viewport, show_render)
            saved.append((m.name, getattr(m, "node_group", None), bool(m.show_viewport), bool(m.show_render)))
            obj.modifiers.remove(m)
    return saved


def _restore_gn_modifiers(obj: bpy.types.Object, saved: List[Tuple[str, bpy.types.NodeTree | None, bool, bool]]) -> None:
    """
    Restore Geometry Nodes modifiers previously removed by _detach_gn_modifiers().
    """
    for name, node_group, show_vp, show_rd in saved:
        try:
            m = obj.modifiers.new(name=name, type="NODES")
            m.node_group = node_group
            m.show_viewport = show_vp
            m.show_render = show_rd
        except Exception:
            pass


# ------------------------------------------------------------
# Mesh grid builder
# ------------------------------------------------------------
def ensure_grid_faces(
    mesh: bpy.types.Mesh,
    nrows: int,
    ncols: int,
    cell_size: float = 1.0,
    origin_topleft: bool = False,
) -> None:
    """
    Ensure `mesh` is a quad grid with exactly nrows*ncols faces.
    Face index is row-major: fi = ri*ncols + ci.
    """
    expected_faces = nrows * ncols
    if expected_faces <= 0:
        raise RuntimeError(f"Invalid grid dims: nrows={nrows}, ncols={ncols}")

    if len(mesh.polygons) == expected_faces:
        return

    mesh.clear_geometry()

    verts: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int, int]] = []

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

    def vid(vr: int, vc: int) -> int:
        return vr * (ncols + 1) + vc

    for ri in range(nrows):
        for ci in range(ncols):
            faces.append((vid(ri, ci), vid(ri, ci + 1), vid(ri + 1, ci + 1), vid(ri + 1, ci)))

    mesh.from_pydata(verts, [], faces)
    mesh.update()


# ------------------------------------------------------------
# Attribute helpers
# ------------------------------------------------------------
def ensure_attribute(mesh: bpy.types.Mesh, name: str, type_str: str, domain: str) -> bpy.types.Attribute:
    if name in mesh.attributes:
        a = mesh.attributes[name]
        if a.data_type != type_str or a.domain != domain:
            mesh.attributes.remove(a)
            a = mesh.attributes.new(name=name, type=type_str, domain=domain)
    else:
        a = mesh.attributes.new(name=name, type=type_str, domain=domain)
    return a


def _ensure_face_attrs(mesh: bpy.types.Mesh):
    aa_val = ensure_attribute(mesh, "aa_val", "FLOAT", "FACE")
    aa_present = ensure_attribute(mesh, "aa_present", "BOOLEAN", "FACE")
    aa_row = ensure_attribute(mesh, "aa_row", "INT", "FACE")
    aa_col = ensure_attribute(mesh, "aa_col", "INT", "FACE")
    return aa_val, aa_present, aa_row, aa_col


def _rebuild_face_attrs(mesh: bpy.types.Mesh):
    for nm in ("aa_val", "aa_present", "aa_row", "aa_col"):
        if nm in mesh.attributes:
            mesh.attributes.remove(mesh.attributes[nm])
    return _ensure_face_attrs(mesh)


# ------------------------------------------------------------
# AA JSON parsing
# ------------------------------------------------------------
def _load_json(path: str | Path) -> dict:
    p = Path(path).expanduser().resolve()
    return json.loads(p.read_text(encoding="utf-8"))


def _iter_cells_dense(rows: list, cols: list, vals: list) -> Iterable[Tuple[int, int, Any]]:
    nrows = len(rows)
    ncols = len(cols)
    if not (isinstance(vals, list) and len(vals) == nrows):
        raise ValueError("Dense AA: 'vals' must have length == len(rows)")
    for ri in range(nrows):
        rowvals = vals[ri]
        if not (isinstance(rowvals, list) and len(rowvals) == ncols):
            raise ValueError(f"Dense AA: vals[{ri}] must be list with length == len(cols)")
        for ci in range(ncols):
            v = rowvals[ci]
            if v is not None:
                yield ri, ci, v


def _build_domain_maps_from_sparse(aa: dict, rows: list, cols: list) -> Tuple[Dict[Any, int], Dict[Any, int]]:
    domain_rows = aa.get("rowDomain", None)
    domain_cols = aa.get("colDomain", None)

    if isinstance(domain_rows, list) and len(domain_rows) > 0:
        row_index = {r: i for i, r in enumerate(domain_rows)}
    else:
        row_index: Dict[Any, int] = {}
        for r in rows:
            if r not in row_index:
                row_index[r] = len(row_index)

    if isinstance(domain_cols, list) and len(domain_cols) > 0:
        col_index = {c: i for i, c in enumerate(domain_cols)}
    else:
        col_index: Dict[Any, int] = {}
        for c in cols:
            if c not in col_index:
                col_index[c] = len(col_index)

    return row_index, col_index


def _iter_cells_sparse(rows: list, cols: list, vals: list, row_index: Dict[Any, int], col_index: Dict[Any, int]) -> Iterable[Tuple[int, int, Any]]:
    for r, c, v in zip(rows, cols, vals):
        if r in row_index and c in col_index:
            yield row_index[r], col_index[c], v


# ------------------------------------------------------------
# Public API used by scene_build.py
# ------------------------------------------------------------
def apply_aa_json_to_grid(
    aa_json_path: str,
    grid_obj_name: str = "AA_GRID__MESH",
    rows_key: str = "rows",
    cols_key: str = "cols",
    vals_key: str = "vals",
    *,
    cell_size: float = 1.0,
    origin_topleft: bool = False,
) -> None:
    obj = bpy.data.objects.get(grid_obj_name)
    if obj is None or obj.type != "MESH":
        raise RuntimeError(f"Grid object '{grid_obj_name}' not found or not a mesh.")

    _force_object_mode(obj)

    # --- CRITICAL: detach GN modifiers to avoid segfault while mutating mesh/attrs ---
    saved_gn = _detach_gn_modifiers(obj)
    try:
        mesh = obj.data
        aa = _load_json(aa_json_path)

        rows = aa.get(rows_key, [])
        cols = aa.get(cols_key, [])
        vals = aa.get(vals_key, [])

        if not (isinstance(rows, list) and isinstance(cols, list) and isinstance(vals, list)):
            raise ValueError("AA JSON must contain list fields: rows, cols, vals")

        # Sparse vs dense
        is_sparse = (len(rows) == len(cols) == len(vals))
        is_dense = (not is_sparse) and (len(rows) > 0 and len(cols) > 0 and len(vals) == len(rows))

        if is_dense:
            nrows = len(rows)
            ncols = len(cols)
            cell_iter = _iter_cells_dense(rows, cols, vals)
            row_domain = [str(x) for x in rows]
            col_domain = [str(x) for x in cols]
        elif is_sparse:
            row_index, col_index = _build_domain_maps_from_sparse(aa, rows, cols)
            nrows = len(row_index)
            ncols = len(col_index)
            cell_iter = _iter_cells_sparse(rows, cols, vals, row_index, col_index)
            row_domain = [str(k) for k in sorted(row_index, key=row_index.get)]
            col_domain = [str(k) for k in sorted(col_index, key=col_index.get)]
        else:
            raise ValueError(
                "AA JSON format not recognized. Expected either:\n"
                "  - Sparse triples: len(rows)==len(cols)==len(vals), or\n"
                "  - Dense: vals is a matrix with len(vals)==len(rows)."
            )

        if nrows <= 0 or ncols <= 0:
            raise RuntimeError(f"Computed invalid grid dimensions: nrows={nrows}, ncols={ncols}")

        # Build/ensure base mesh faces
        ensure_grid_faces(mesh, nrows, ncols, cell_size=cell_size, origin_topleft=origin_topleft)

        expected_faces = nrows * ncols
        if len(mesh.polygons) != expected_faces:
            raise RuntimeError(f"Grid mesh has {len(mesh.polygons)} faces, expected {expected_faces}.")

        # Ensure attrs (rebuild once if Blender returns wrong-sized storage)
        aa_val, aa_present, aa_row, aa_col = _ensure_face_attrs(mesh)
        if len(aa_val.data) != expected_faces or len(aa_present.data) != expected_faces:
            aa_val, aa_present, aa_row, aa_col = _rebuild_face_attrs(mesh)

        if len(aa_val.data) != expected_faces or len(aa_present.data) != expected_faces:
            raise RuntimeError(
                f"FACE attribute storage wrong after rebuild. faces={expected_faces}, "
                f"aa_val.data={len(aa_val.data)}, aa_present.data={len(aa_present.data)}"
            )

        # Clear defaults
        for fi in range(expected_faces):
            aa_present.data[fi].value = False
            aa_val.data[fi].value = 0.0
            aa_row.data[fi].value = -1
            aa_col.data[fi].value = -1

        # Populate
        for ri, ci, v in cell_iter:
            if not (0 <= ri < nrows and 0 <= ci < ncols):
                continue
            fi = ri * ncols + ci
            aa_present.data[fi].value = True
            try:
                aa_val.data[fi].value = float(v)
            except Exception:
                aa_val.data[fi].value = 1.0
            aa_row.data[fi].value = int(ri)
            aa_col.data[fi].value = int(ci)

        # Debug info
        obj["aa_nrows"] = int(nrows)
        obj["aa_ncols"] = int(ncols)
        obj["aa_rowDomain"] = row_domain
        obj["aa_colDomain"] = col_domain

        # Best-effort update
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass

    finally:
        # Restore GN modifiers exactly as they were
        _restore_gn_modifiers(obj, saved_gn)


# ------------------------------------------------------------
# CLI (optional)
# ------------------------------------------------------------
def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Apply AA JSON to grid mesh face attributes.")
    ap.add_argument("--aa-json", required=True)
    ap.add_argument("--grid", default="AA_GRID__MESH")
    ap.add_argument("--cell-size", type=float, default=1.0)
    ap.add_argument("--origin-topleft", action="store_true")
    return ap.parse_args(argv)


def main():
    argv = []
    if "--" in bpy.app.argv:
        argv = bpy.app.argv[bpy.app.argv.index("--") + 1 :]
    args = _parse_args(argv)
    apply_aa_json_to_grid(
        args.aa_json,
        args.grid,
        cell_size=args.cell_size,
        origin_topleft=args.origin_topleft,
    )
    bpy.ops.wm.save_mainfile()
    print("blend saved...")

if __name__ == "__main__":
    main()
