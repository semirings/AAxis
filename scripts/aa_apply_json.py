#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import bpy


# -----------------------------
# Mesh grid builder
# -----------------------------
def ensure_grid_faces(
    mesh: bpy.types.Mesh,
    nrows: int,
    ncols: int,
    cell_size: float = 1.0,
    origin_topleft: bool = False,
) -> None:
    """
    Ensure `mesh` is a quad grid with exactly nrows*ncols faces.

    Faces are row-major: face_index = ri*ncols + ci
    """
    expected_faces = nrows * ncols
    if len(mesh.polygons) == expected_faces and expected_faces > 0:
        return

    mesh.clear_geometry()

    verts: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int, int]] = []

    total_w = ncols * cell_size
    total_h = nrows * cell_size
    x0 = -total_w / 2.0
    y0 = -total_h / 2.0

    def y_for_vertex_row(vr: int) -> float:
        # vr is 0..nrows
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


# -----------------------------
# Attribute helpers
# -----------------------------
def _ensure_face_attr(mesh: bpy.types.Mesh, name: str, type_str: str) -> bpy.types.Attribute:
    """
    Ensure a FACE-domain attribute exists with the desired type.
    Recreates the attribute if type/domain mismatch.
    """
    attr = mesh.attributes.get(name)
    if attr is not None:
        if attr.domain != "FACE" or attr.data_type != type_str:
            mesh.attributes.remove(attr)
            attr = None
    if attr is None:
        attr = mesh.attributes.new(name=name, type=type_str, domain="FACE")
    return attr


def _clear_face_attributes(
    mesh: bpy.types.Mesh,
    aa_present: bpy.types.Attribute,
    aa_val: bpy.types.Attribute,
    aa_row: bpy.types.Attribute,
    aa_col: bpy.types.Attribute,
) -> None:
    """
    Clear defaults across all faces.
    """
    face_count = len(mesh.polygons)
    # If face_count is 0, caller should have ensured faces first.
    for i in range(face_count):
        aa_present.data[i].value = 0.0
        aa_val.data[i].value = 0.0
        aa_row.data[i].value = -1
        aa_col.data[i].value = -1


# -----------------------------
# AA JSON parsing (supports sparse triples and optional dense)
# -----------------------------
def _load_json(path: str | Path) -> dict:
    p = Path(path).expanduser().resolve()
    return json.loads(p.read_text(encoding="utf-8"))


def _build_domain_maps(aa: dict, rows: list, cols: list) -> tuple[Dict[Any, int], Dict[Any, int]]:
    """
    Builds row_index / col_index using optional rowDomain/colDomain if present,
    otherwise infers encounter order from rows/cols triples.
    """
    row_index: Dict[Any, int] = {}
    col_index: Dict[Any, int] = {}

    domain_rows = aa.get("rowDomain", None)
    domain_cols = aa.get("colDomain", None)

    if isinstance(domain_rows, list) and len(domain_rows) > 0:
        row_index = {r: i for i, r in enumerate(domain_rows)}
    else:
        for r in rows:
            if r not in row_index:
                row_index[r] = len(row_index)

    if isinstance(domain_cols, list) and len(domain_cols) > 0:
        col_index = {c: i for i, c in enumerate(domain_cols)}
    else:
        for c in cols:
            if c not in col_index:
                col_index[c] = len(col_index)

    return row_index, col_index


def _iter_cells_from_sparse_triples(rows: list, cols: list, vals: list):
    for r, c, v in zip(rows, cols, vals):
        yield r, c, v


def _iter_cells_from_dense(aa: dict, rows_key: str, cols_key: str, vals_key: str):
    """
    Dense form:
      rows: [...]
      cols: [...]
      vals: [[...], [...], ...] where vals[ri][ci]
    Only yields non-null values.
    """
    rows = aa.get(rows_key, [])
    cols = aa.get(cols_key, [])
    vals = aa.get(vals_key, [])
    if not (isinstance(rows, list) and isinstance(cols, list) and isinstance(vals, list)):
        raise ValueError("Dense AA JSON must contain list fields: rows, cols, vals")

    if len(vals) != len(rows):
        raise ValueError("Dense AA JSON: 'vals' must have length == len(rows)")
    for ri in range(len(rows)):
        rowvals = vals[ri]
        if not (isinstance(rowvals, list) and len(rowvals) == len(cols)):
            raise ValueError(f"Dense AA JSON: vals[{ri}] must have length == len(cols)")
        for ci in range(len(cols)):
            v = rowvals[ci]
            if v is not None:
                yield rows[ri], cols[ci], v


# -----------------------------
# Main apply function
# -----------------------------
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

    mesh = obj.data
    aa = _load_json(aa_json_path)

    rows = aa.get(rows_key, [])
    cols = aa.get(cols_key, [])
    vals = aa.get(vals_key, [])

    # Decide whether we're sparse-triples or dense-matrix
    is_sparse_triples = (
        isinstance(rows, list) and isinstance(cols, list) and isinstance(vals, list)
        and len(rows) == len(cols) == len(vals)
        and (len(rows) > 0 or aa.get("rowDomain") or aa.get("colDomain"))
    )

    is_dense = (
        isinstance(rows, list) and isinstance(cols, list) and isinstance(vals, list)
        and (len(rows) > 0 and len(cols) > 0 and len(vals) == len(rows))
        and (len(rows) != len(cols) or len(rows) != len(vals))  # heuristic; dense usually isn't equal-length triples
    )

    if not is_sparse_triples and not is_dense:
        raise ValueError(
            "AA JSON must be either:\n"
            "  - Sparse triples: rows/cols/vals lists of equal length, or\n"
            "  - Dense: rows/cols + vals as a matrix vals[ri][ci].\n"
            "If you meant sparse triples, ensure rows/cols/vals lengths match."
        )

    # Build domain maps (uses rowDomain/colDomain if present)
    if is_dense:
        domain_rows = rows
        domain_cols = cols
        row_index = {r: i for i, r in enumerate(domain_rows)}
        col_index = {c: i for i, c in enumerate(domain_cols)}
        cell_iter = _iter_cells_from_dense(aa, rows_key, cols_key, vals_key)
    else:
        row_index, col_index = _build_domain_maps(aa, rows, cols)
        cell_iter = _iter_cells_from_sparse_triples(rows, cols, vals)

    nrows = len(row_index)
    ncols = len(col_index)
    if nrows <= 0 or ncols <= 0:
        raise RuntimeError(f"Computed invalid grid dims: nrows={nrows}, ncols={ncols}")

    # CRITICAL FIX: ensure base mesh has faces before writing FACE attributes
    ensure_grid_faces(mesh, nrows, ncols, cell_size=cell_size, origin_topleft=origin_topleft)

    expected_faces = nrows * ncols
    if len(mesh.polygons) != expected_faces:
        raise RuntimeError(f"Grid mesh has {len(mesh.polygons)} faces, expected {expected_faces}")

    # Ensure attributes
    aa_present = _ensure_face_attr(mesh, "aa_present", "FLOAT")
    aa_val = _ensure_face_attr(mesh, "aa_val", "FLOAT")
    aa_row = _ensure_face_attr(mesh, "aa_row", "INT")
    aa_col = _ensure_face_attr(mesh, "aa_col", "INT")

    # Clear defaults
    _clear_face_attributes(mesh, aa_present, aa_val, aa_row, aa_col)

    # Populate
    for r, c, v in cell_iter:
        if r not in row_index or c not in col_index:
            # Ignore out-of-domain (can happen if rowDomain/colDomain restricts)
            continue
        ri = row_index[r]
        ci = col_index[c]
        face_idx = ri * ncols + ci

        aa_present.data[face_idx].value = 1.0
        try:
            aa_val.data[face_idx].value = float(v)
        except Exception:
            aa_val.data[face_idx].value = 1.0
        aa_row.data[face_idx].value = int(ri)
        aa_col.data[face_idx].value = int(ci)

    # Debug info on the object
    obj["aa_nrows"] = int(nrows)
    obj["aa_ncols"] = int(ncols)
    obj["aa_rowDomain"] = [str(k) for k in sorted(row_index, key=row_index.get)]
    obj["aa_colDomain"] = [str(k) for k in sorted(col_index, key=col_index.get)]


# -----------------------------
# CLI
# -----------------------------
def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Apply AA/JSON to grid mesh face attributes.")
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
