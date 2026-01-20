#!/usr/bin/env python3

#
# How to run:
# scripts/synth2aa.py  -o /Users/gcr/ingis.Wk/FHIRSDS/aa-bundles/Adam631_Buckridge80_2f3fd555-23e0-adae-ccb8-438dca7e7304.json /Users/gcr/ingis.Wk/FHIRSDS/bundles/Adam631_Buckridge80_2f3fd555-23e0-adae-ccb8-438dca7e7304.json
#

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Set, Optional

print("Start==>")

EMPTY = ""

def res_id(res: Dict[str, Any]) -> Optional[str]:
    rt = res.get("resourceType")
    rid = res.get("id")
    if rt and rid:
        return f"{rt}/{rid}"
    return None


def is_reference_obj(x: Any) -> bool:
    return isinstance(x, dict) and "reference" in x and isinstance(x["reference"], str)


def join_multi(values: List[str]) -> str:
    # deterministic + compact; dbllogi can still “lift”
    uniq = []
    seen = set()
    for v in values:
        if v and v not in seen:
            uniq.append(v)
            seen.add(v)
    return "|".join(uniq)


def walk_for_references(
    obj: Any,
    path: str,
    out: List[Tuple[str, str]],
) -> None:
    """
    Append (path, reference_string) pairs into out.
    Recognizes FHIR Reference objects and nested references.
    """
    if obj is None:
        return

    # Reference object
    if is_reference_obj(obj):
        out.append((path, obj["reference"]))
        return

    # Dict: recurse keys
    if isinstance(obj, dict):
        for k, v in obj.items():
            # Skip Bundle noise if encountered inside (rare)
            if k in ("meta", "text", "contained"):
                # contained can include nested resources; skip for now to avoid exploding
                continue
            new_path = f"{path}.{k}" if path else k
            walk_for_references(v, new_path, out)
        return

    # List: recurse items (keep same path; don’t add indexes)
    if isinstance(obj, list):
        for item in obj:
            walk_for_references(item, path, out)
        return

    # Primitive: ignore
    return


def bundle_to_aa_json(bundle: Dict[str, Any]) -> Dict[str, Any]:
    # 1) collect resources
    resources: List[Dict[str, Any]] = []
    for e in bundle.get("entry", []) or []:
        r = e.get("resource")
        if isinstance(r, dict) and r.get("resourceType"):
            resources.append(r)

    # 2) collect rows
    rows: List[str] = []
    for r in resources:
        rid = res_id(r)
        if rid:
            rows.append(rid)

    # Stable ordering
    rows = sorted(set(rows))

    # 3) collect (row, col, val) triples
    triples: List[Tuple[str, str, str]] = []
    cols_set: Set[str] = set()

    for r in resources:
        row = res_id(r)
        if not row:
            continue

        pairs: List[Tuple[str, str]] = []
        walk_for_references(r, r.get("resourceType", ""), pairs)

        # Turn "ResourceType.field..." into "ResourceType.field..." (already)
        # But we *prefer* cols without the duplicated resourceType prefix in the row?
        # You previously used "Observation.subject" style columns, so we keep that.

        # Aggregate per (row, col)
        by_col: Dict[str, List[str]] = {}
        for col, val in pairs:
            if not col or not val:
                continue
            by_col.setdefault(col, []).append(val)

        for col, vals in by_col.items():
            cols_set.add(col)
            triples.append((row, col, join_multi(vals)))

    cols = sorted(cols_set)

    # 4) build dense row-major vals
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

    return {
        "layout": "row-major",
        "empty": EMPTY,
        "rows": rows,
        "cols": cols,
        "vals": grid,
    }


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Convert FHIR Bundle JSON to AA row-major JSON.")
    ap.add_argument("bundle_json", help="Path to Synthea FHIR Bundle JSON file")
    ap.add_argument("-o", "--out", help="Output AA JSON path (default: <input>.aa.json)")
    args = ap.parse_args()

    in_path = Path(args.bundle_json)
    out_path = Path(args.out) if args.out else in_path.with_suffix(in_path.suffix + ".aa.json")

    bundle = json.loads(in_path.read_text(encoding="utf-8"))
    aa = bundle_to_aa_json(bundle)

    out_path.write_text(json.dumps(aa, indent=2), encoding="utf-8")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
