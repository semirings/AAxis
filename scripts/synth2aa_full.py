#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# ---------------------------------------------------------------------
# Hard-coded roots (as requested)
# ---------------------------------------------------------------------
INPUT_ROOT = Path("/Users/gcr/ingis.Wk/FHIRSDS/bundles")
OUTPUT_ROOT = Path("/Users/gcr/ingis.Wk/FHIRSDS/aa-bundles")

EMPTY = ""


def res_id(resource: Dict[str, Any]) -> str:
    rt = resource.get("resourceType", "")
    rid = resource.get("id", "")
    return f"{rt}/{rid}" if rt and rid else ""


def build_fullurl_map(bundle: Dict[str, Any]) -> Dict[str, str]:
    """Map Bundle.entry[].fullUrl -> ResourceType/id"""
    m: Dict[str, str] = {}
    for e in bundle.get("entry", []) or []:
        if not isinstance(e, dict):
            continue
        fu = e.get("fullUrl")
        r = e.get("resource")
        if isinstance(fu, str) and isinstance(r, dict):
            rid = res_id(r)
            if rid:
                m[fu] = rid
    return m


def normalize_ref(ref: str, fullurl_to_rid: Dict[str, str]) -> str:
    return fullurl_to_rid.get(ref, ref)


def is_primitive(x: Any) -> bool:
    return x is None or isinstance(x, (str, int, float, bool))


def flatten_resource(
    obj: Any,
    path: str,
    out: Dict[str, str],
    *,
    fullurl_to_rid: Dict[str, str],
) -> None:
    """
    Flatten FHIR JSON into dotted paths.

    Arrays become field[0], field[1], ...
    Special: if a dict has "reference", store the normalized reference at the dict's own path
            (e.g., Observation.subject -> "Patient/...", not Observation.subject.reference).
    Also flattens other keys alongside reference (display/type/identifier/etc).
    """
    if is_primitive(obj):
        if obj is None:
            return
        out[path] = str(obj)
        return

    if isinstance(obj, list):
        for i, item in enumerate(obj):
            flatten_resource(item, f"{path}[{i}]", out, fullurl_to_rid=fullurl_to_rid)
        return

    if isinstance(obj, dict):
        # FHIR Reference object
        if "reference" in obj and isinstance(obj.get("reference"), str):
            out[path] = normalize_ref(obj["reference"], fullurl_to_rid)
            for k, v in obj.items():
                if k == "reference":
                    continue
                flatten_resource(v, f"{path}.{k}", out, fullurl_to_rid=fullurl_to_rid)
            return

        for k, v in obj.items():
            if k == "resourceType":
                continue
            next_path = f"{path}.{k}" if path else k
            flatten_resource(v, next_path, out, fullurl_to_rid=fullurl_to_rid)
        return

    out[path] = str(obj)


def bundle_to_aa_dense(bundle: Dict[str, Any]) -> Dict[str, Any]:
    fullurl_to_rid = build_fullurl_map(bundle)

    resources: List[Dict[str, Any]] = []
    for e in bundle.get("entry", []) or []:
        r = e.get("resource") if isinstance(e, dict) else None
        if isinstance(r, dict) and r.get("resourceType"):
            resources.append(r)

    rows = sorted({res_id(r) for r in resources if res_id(r)})

    triples: List[Tuple[str, str, str]] = []
    cols_set: Set[str] = set()

    for r in resources:
        row = res_id(r)
        rt = r.get("resourceType", "")
        if not row or not rt:
            continue

        flat: Dict[str, str] = {}
        flatten_resource(r, rt, flat, fullurl_to_rid=fullurl_to_rid)

        # Guarantee at least one non-empty cell per resource (avoids “Patient missing” in sparse views)
        cols_set.add(f"{rt}.id")
        triples.append((row, f"{rt}.id", row))

        for col, val in flat.items():
            if col and val != "":
                cols_set.add(col)
                triples.append((row, col, val))

    cols = sorted(cols_set)

    nrows, ncols = len(rows), len(cols)
    idx_row = {r: i for i, r in enumerate(rows)}
    idx_col = {c: j for j, c in enumerate(cols)}
    grid: List[str] = [EMPTY] * (nrows * ncols)

    for r, c, v in triples:
        i = idx_row.get(r)
        j = idx_col.get(c)
        if i is None or j is None:
            continue
        grid[i * ncols + j] = v

    return {"layout": "row-major", "empty": EMPTY, "rows": rows, "cols": cols, "vals": grid}


def bundle_to_aa_triples(bundle: Dict[str, Any]) -> Dict[str, Any]:
    fullurl_to_rid = build_fullurl_map(bundle)

    resources: List[Dict[str, Any]] = []
    for e in bundle.get("entry", []) or []:
        r = e.get("resource") if isinstance(e, dict) else None
        if isinstance(r, dict) and r.get("resourceType"):
            resources.append(r)

    triples: List[Dict[str, str]] = []

    for r in resources:
        row = res_id(r)
        rt = r.get("resourceType", "")
        if not row or not rt:
            continue

        flat: Dict[str, str] = {}
        flatten_resource(r, rt, flat, fullurl_to_rid=fullurl_to_rid)

        triples.append({"row": row, "col": f"{rt}.id", "val": row})
        for col, val in flat.items():
            if col and val != "":
                triples.append({"row": row, "col": col, "val": val})

    return {"layout": "triples", "empty": EMPTY, "triples": triples}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert a Synthea FHIR Bundle JSON to AA JSON (full attributes + references)."
    )
    ap.add_argument(
        "filename",
        help="Input bundle filename (must exist under INPUT_ROOT). Output will be written under OUTPUT_ROOT with the same filename.",
    )
    ap.add_argument(
        "--format",
        choices=["dense", "triples"],
        default="dense",
        help="dense = row-major rows/cols/vals; triples = explicit triples (smaller).",
    )
    args = ap.parse_args()

    in_path = INPUT_ROOT / args.filename
    out_path = OUTPUT_ROOT / args.filename

    if not in_path.exists():
        raise FileNotFoundError(f"Input not found: {in_path}")

    with in_path.open("r", encoding="utf-8") as f:
        bundle = json.load(f)

    aa = bundle_to_aa_dense(bundle) if args.format == "dense" else bundle_to_aa_triples(bundle)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(
            aa,
            f,
            ensure_ascii=False,
            indent=2,
        )


    print(f"Wrote: {out_path}")
    if aa.get("layout") == "row-major":
        print(f"rows={len(aa['rows'])} cols={len(aa['cols'])} vals={len(aa['vals'])}")
    else:
        print(f"triples={len(aa['triples'])}")


if __name__ == "__main__":
    main()
