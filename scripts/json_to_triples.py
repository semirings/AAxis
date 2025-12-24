#!/usr/bin/env python3

import json
import argparse
from typing import Any, Dict, List, Tuple


def aa_json_to_d4m_csv_triples(
    aa: Dict[str, Any],
    *,
    layout: str = "row-major",          # for dense only
    drop_empty: bool = True,
    empty_values: Tuple[Any, ...] = ("", None),
) -> Tuple[str, str, str]:
    """
    Return (row_csv, col_csv, val_csv) as comma-separated strings ending with a comma,
    suitable for: D4M.Assoc(row_csv, col_csv, val_csv)
    """

    def keep(v: Any) -> bool:
        return (not drop_empty) or (v not in empty_values)

    rr: List[str] = []
    cc: List[str] = []
    vv: List[str] = []

    # Case: explicit triples list
    if "triples" in aa and isinstance(aa["triples"], list):
        for t in aa["triples"]:
            if not (isinstance(t, (list, tuple)) and len(t) == 3):
                raise ValueError(f"Bad triple entry: {t!r}")
            r, c, v = t
            if keep(v):
                rr.append(str(r)); cc.append(str(c)); vv.append(str(v))
        return ",".join(rr) + ("," if rr else ""), ",".join(cc) + ("," if cc else ""), ",".join(vv) + ("," if vv else "")

    rows = aa.get("rows", [])
    cols = aa.get("cols", [])
    vals = aa.get("vals", [])

    if not (isinstance(rows, list) and isinstance(cols, list) and isinstance(vals, list)):
        raise ValueError("AA_JSON must have lists rows/cols/vals (or triples).")

    R, C, V = len(rows), len(cols), len(vals)
    if R == 0 or C == 0:
        raise ValueError("AA_JSON must have non-empty rows and cols.")

    # Detect dense vs triples-arrays
    is_dense = (V == R * C)
    is_triples_arrays = (R == C == V)

    if is_dense and not is_triples_arrays:
        if layout not in ("row-major", "col-major"):
            raise ValueError("layout must be 'row-major' or 'col-major'")
        for ri in range(R):
            for ci in range(C):
                idx = (ri * C + ci) if layout == "row-major" else (ci * R + ri)
                v = vals[idx]
                if keep(v):
                    rr.append(str(rows[ri]))
                    cc.append(str(cols[ci]))
                    vv.append(str(v))
    else:
        n = min(R, C, V)
        for i in range(n):
            v = vals[i]
            if keep(v):
                rr.append(str(rows[i]))
                cc.append(str(cols[i]))
                vv.append(str(v))

    return ",".join(rr) + ("," if rr else ""), ",".join(cc) + ("," if cc else ""), ",".join(vv) + ("," if vv else "")

def aa_json_to_triple_lists(aa: Dict[str, Any], *, layout="row-major", drop_empty=True, empty_values=("", None)):
    rows = aa["rows"]; cols = aa["cols"]; vals = aa["vals"]
    R, C, V = len(rows), len(cols), len(vals)

    def keep(v): return (not drop_empty) or (v not in empty_values)

    rr, cc, vv = [], [], []
    if V == R * C:
        for r in range(R):
            for c in range(C):
                v = vals[r*C + c] if layout == "row-major" else vals[c*R + r]
                if keep(v):
                    rr.append(rows[r]); cc.append(cols[c]); vv.append(v)
    else:
        n = min(R, C, V)
        for i in range(n):
            if keep(vals[i]):
                rr.append(rows[i]); cc.append(cols[i]); vv.append(vals[i])
    return rr, cc, vv

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--layout", default="row-major")
    ap.add_argument("--keep-empty", action="store_true")
    args = ap.parse_args()

    aa = json.load(open(args.inp))
    out = aa_json_to_triple_lists(aa, layout=args.layout, drop_empty=not args.keep_empty)

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)

if __name__ == "__main__":
    main()