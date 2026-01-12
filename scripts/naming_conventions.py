#!/usr/bin/env python3
"""
naming_conventions.py

Enforce naming conventions for generated objects/collections in a Blender scene.

Design goals:
- Keep intent readable in the Outliner (semantic names, stable prefixes).
- Make rebuild/cleanup safe (everything generated is under GEN_* collections).
- Avoid collisions (unique naming with numeric suffixes).
- Support dry-run so you can see changes before applying.

Typical usage (headless):
  blender -b /path/to/template.blend --python naming_conventions.py -- \
    --apply --prefix GEN --verbose

Or, dry-run (prints proposed renames):
  blender -b /path/to/template.blend --python naming_conventions.py -- \
    --dry-run --verbose

What it enforces:
- Top-level collections:
    GEN_AA_GRID
    GEN_OVERLAY
      GEN_OVERLAY_CARDS
      GEN_OVERLAY_LABELS
    GEN_DEBUG
- Code cards:
    Collection: GEN_CARD_CODE_S01_<Slug>
    Objects:    CARD_CODE_S01_<Slug>__PLANE
               CARD_CODE_S01_<Slug>__TEXT
- Label cards:
    Collection: GEN_CARD_LABEL_N01_<Slug>
    Objects:    CARD_LABEL_N01_<Slug>__PLANE
               CARD_LABEL_N01_<Slug>__TEXT
- Grid container object (optional if found by heuristic):
    AA_GRID__MESH
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

import bpy


# ----------------------------
# Configuration / Conventions
# ----------------------------

DEFAULT_PREFIX = "GEN"

# Canonical collection names (generated)
COL_AA_GRID = "AA_GRID"
COL_OVERLAY = "OVERLAY"
COL_OVERLAY_CARDS = "OVERLAY_CARDS"
COL_OVERLAY_LABELS = "OVERLAY_LABELS"
COL_DEBUG = "DEBUG"

# Object suffixes
SUF_PLANE = "__PLANE"
SUF_TEXT = "__TEXT"
SUF_MESH = "__MESH"

# Code card object/collection prefixes
CARD_CODE = "CARD_CODE"
CARD_LABEL = "CARD_LABEL"


@dataclass(frozen=True)
class RenameOp:
    kind: str  # "collection" | "object"
    old: str
    new: str


# ----------------------------
# Helpers
# ----------------------------

_slug_re = re.compile(r"[^A-Za-z0-9]+")


def slugify(s: str) -> str:
    s = s.strip()
    s = _slug_re.sub("_", s)
    s = s.strip("_")
    return s or "UNNAMED"


def ensure_unique_name(desired: str, existing: Set[str]) -> str:
    """Return a name not in `existing` by adding _001 style suffix if needed."""
    if desired not in existing:
        existing.add(desired)
        return desired
    i = 1
    while True:
        candidate = f"{desired}_{i:03d}"
        if candidate not in existing:
            existing.add(candidate)
            return candidate
        i += 1


def get_all_collection_names() -> Set[str]:
    return {c.name for c in bpy.data.collections}


def get_all_object_names() -> Set[str]:
    return {o.name for o in bpy.data.objects}


def get_or_create_collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def is_text_object(obj: bpy.types.Object) -> bool:
    return obj.type == "FONT"


def is_plane_like(obj: bpy.types.Object) -> bool:
    # Heuristic: MESH with 4 verts or named plane-ish
    if obj.type != "MESH":
        return False
    if obj.data and hasattr(obj.data, "vertices") and len(obj.data.vertices) == 4:
        return True
    return "plane" in obj.name.lower() or "card" in obj.name.lower()


def iter_collection_objects_recursive(col: bpy.types.Collection) -> Iterable[bpy.types.Object]:
    for obj in col.objects:
        yield obj
    for child in col.children:
        yield from iter_collection_objects_recursive(child)


def safe_link_child(parent: bpy.types.Collection, child: bpy.types.Collection) -> None:
    if child.name not in {c.name for c in parent.children}:
        parent.children.link(child)


def move_collection_under(parent: bpy.types.Collection, child: bpy.types.Collection) -> None:
    # Ensure child is linked under parent; do not forcibly unlink from other parents (can be shared)
    safe_link_child(parent, child)


def canonical_col_name(prefix: str, base: str) -> str:
    return f"{prefix}_{base}"


def code_card_collection_name(prefix: str, step: int, title: str) -> str:
    return f"{prefix}_CARD_CODE_S{step:02d}_{slugify(title)}"


def code_card_object_base(step: int, title: str) -> str:
    return f"{CARD_CODE}_S{step:02d}_{slugify(title)}"


def label_card_collection_name(prefix: str, node_num: int, title: str) -> str:
    return f"{prefix}_CARD_LABEL_N{node_num:02d}_{slugify(title)}"


def label_card_object_base(node_num: int, title: str) -> str:
    return f"{CARD_LABEL}_N{node_num:02d}_{slugify(title)}"


# ----------------------------
# Discovery (heuristics)
# ----------------------------

def find_generated_collections(prefix: str) -> List[bpy.types.Collection]:
    return [c for c in bpy.data.collections if c.name.startswith(prefix + "_")]


def find_overlay_like_collections() -> List[bpy.types.Collection]:
    # Loose heuristic: any collection containing "overlay" or "card"
    hits = []
    for c in bpy.data.collections:
        nm = c.name.lower()
        if "overlay" in nm or "card" in nm:
            hits.append(c)
    return hits


def find_code_card_candidates() -> List[Tuple[bpy.types.Collection, Optional[bpy.types.Object], Optional[bpy.types.Object]]]:
    """
    Identify card-ish collections (plane + text). This is heuristic.
    Returns list of (collection, plane_obj, text_obj).
    """
    out: List[Tuple[bpy.types.Collection, Optional[bpy.types.Object], Optional[bpy.types.Object]]] = []
    for col in bpy.data.collections:
        # candidates: collections with 1+ TEXT + 1+ plane-like mesh
        objs = list(iter_collection_objects_recursive(col))
        texts = [o for o in objs if is_text_object(o)]
        planes = [o for o in objs if is_plane_like(o)]
        if texts and planes:
            # Prefer direct objects in the collection (not from children), but fall back
            text = texts[0]
            plane = planes[0]
            out.append((col, plane, text))
    return out


def find_grid_mesh_candidates() -> List[bpy.types.Object]:
    """
    Heuristic for grid mesh: large mesh with many faces/verts or name contains 'grid'.
    """
    candidates = []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        name_l = o.name.lower()
        if "grid" in name_l or "aa" in name_l:
            candidates.append(o)
            continue
        if o.data and hasattr(o.data, "vertices") and len(o.data.vertices) >= 100:
            candidates.append(o)
    return candidates


# ----------------------------
# Core renaming logic
# ----------------------------

def plan_canonical_structure(prefix: str) -> List[RenameOp]:
    """
    Ensure canonical top-level collections exist and are named properly.
    If similarly named collections exist (e.g. 'AA_Grid' or 'Overlay Cards'),
    we won't try to be too clever: we create canonicals and (optionally) link
    existing ones under them later in apply step.
    """
    ops: List[RenameOp] = []

    # No renames for canonicals here; creation happens in apply.
    # This function focuses on renaming obvious near-misses.
    # Near-miss patterns:
    near_miss = [
        (re.compile(r"^(AA[_\s-]*GRID)$", re.I), canonical_col_name(prefix, COL_AA_GRID)),
        (re.compile(r"^(OVERLAY)$", re.I), canonical_col_name(prefix, COL_OVERLAY)),
        (re.compile(r"^(OVERLAY[_\s-]*CARDS)$", re.I), canonical_col_name(prefix, COL_OVERLAY_CARDS)),
        (re.compile(r"^(OVERLAY[_\s-]*LABELS)$", re.I), canonical_col_name(prefix, COL_OVERLAY_LABELS)),
        (re.compile(r"^(DEBUG)$", re.I), canonical_col_name(prefix, COL_DEBUG)),
    ]

    existing_cols = get_all_collection_names()
    # Plan renames for exact near misses only (avoid surprising renames)
    for col in bpy.data.collections:
        for rx, target in near_miss:
            if rx.match(col.name) and col.name != target:
                ops.append(RenameOp("collection", col.name, target))
                # update local set to avoid double targeting
                existing_cols.discard(col.name)
                existing_cols.add(target)
                break

    return ops


def plan_card_renames(prefix: str,
                      code_steps: Optional[Dict[str, int]] = None,
                      label_nodes: Optional[Dict[str, int]] = None) -> List[RenameOp]:
    """
    Plan renames for card collections and their plane/text objects.

    You can pass explicit mappings:
      code_steps: {"Patient to Encounter": 1, "Encounter to Observation": 2}
      label_nodes: {"Patient": 1, "Encounter": 2}

    If not provided, we will NOT guess step numbers; we will only normalize
    object suffixes within already well-named card collections.
    """
    ops: List[RenameOp] = []
    existing_cols = get_all_collection_names()
    existing_objs = get_all_object_names()

    # If explicit mappings provided, enforce full names
    if code_steps:
        for title, step in code_steps.items():
            # Find a candidate collection containing the title substring (loose)
            slug = slugify(title).lower()
            candidates = [c for c in bpy.data.collections if slug in slugify(c.name).lower()]
            if not candidates:
                continue
            col = candidates[0]
            new_col = ensure_unique_name(code_card_collection_name(prefix, step, title), existing_cols)
            if col.name != new_col:
                ops.append(RenameOp("collection", col.name, new_col))

            # Rename contained plane/text objects (first plane-like, first text)
            objs = list(iter_collection_objects_recursive(col))
            plane = next((o for o in objs if is_plane_like(o)), None)
            text = next((o for o in objs if is_text_object(o)), None)

            base = code_card_object_base(step, title)
            if plane:
                desired = ensure_unique_name(base + SUF_PLANE, existing_objs)
                if plane.name != desired:
                    ops.append(RenameOp("object", plane.name, desired))
            if text:
                desired = ensure_unique_name(base + SUF_TEXT, existing_objs)
                if text.name != desired:
                    ops.append(RenameOp("object", text.name, desired))

    if label_nodes:
        for title, node_num in label_nodes.items():
            slug = slugify(title).lower()
            candidates = [c for c in bpy.data.collections if slug in slugify(c.name).lower()]
            if not candidates:
                continue
            col = candidates[0]
            new_col = ensure_unique_name(label_card_collection_name(prefix, node_num, title), existing_cols)
            if col.name != new_col:
                ops.append(RenameOp("collection", col.name, new_col))

            objs = list(iter_collection_objects_recursive(col))
            plane = next((o for o in objs if is_plane_like(o)), None)
            text = next((o for o in objs if is_text_object(o)), None)

            base = label_card_object_base(node_num, title)
            if plane:
                desired = ensure_unique_name(base + SUF_PLANE, existing_objs)
                if plane.name != desired:
                    ops.append(RenameOp("object", plane.name, desired))
            if text:
                desired = ensure_unique_name(base + SUF_TEXT, existing_objs)
                if text.name != desired:
                    ops.append(RenameOp("object", text.name, desired))

    # If no explicit mapping, do a conservative pass:
    # - For any card-ish collection already starting with GEN_CARD_CODE_ or GEN_CARD_LABEL_
    #   ensure its objects end with __PLANE and __TEXT if we can identify them.
    if not code_steps and not label_nodes:
        for col, plane, text in find_code_card_candidates():
            if not (col.name.startswith(prefix + "_CARD_CODE_") or col.name.startswith(prefix + "_CARD_LABEL_")):
                continue

            # derive base from collection name by stripping prefix collection part
            # Example: GEN_CARD_CODE_S01_PatientToEncounter -> CARD_CODE_S01_PatientToEncounter
            base = col.name
            base = base.replace(prefix + "_", "", 1)  # CARD_CODE_S01_...
            # Convert to object prefix
            if base.startswith("CARD_CODE_"):
                obj_base = base
            elif base.startswith("CARD_LABEL_"):
                obj_base = base
            else:
                # fallback, don't rename
                continue

            # Objects: obj_base__PLANE / __TEXT
            if plane:
                desired = ensure_unique_name(obj_base + SUF_PLANE, existing_objs)
                if plane.name != desired:
                    ops.append(RenameOp("object", plane.name, desired))
            if text:
                desired = ensure_unique_name(obj_base + SUF_TEXT, existing_objs)
                if text.name != desired:
                    ops.append(RenameOp("object", text.name, desired))

    return ops


def plan_grid_mesh_rename() -> List[RenameOp]:
    ops: List[RenameOp] = []
    existing_objs = get_all_object_names()
    candidates = find_grid_mesh_candidates()
    if not candidates:
        return ops

    # Choose the best candidate: prefer name containing 'aa' and 'grid'
    def score(o: bpy.types.Object) -> int:
        n = o.name.lower()
        s = 0
        if "aa" in n:
            s += 2
        if "grid" in n:
            s += 3
        if o.data and hasattr(o.data, "vertices"):
            s += min(5, len(o.data.vertices) // 200)
        return s

    grid = sorted(candidates, key=score, reverse=True)[0]
    desired = ensure_unique_name("AA_GRID" + SUF_MESH, existing_objs)
    if grid.name != desired:
        ops.append(RenameOp("object", grid.name, desired))
    return ops


# ----------------------------
# Apply changes
# ----------------------------

def apply_ops(ops: List[RenameOp], verbose: bool = False) -> None:
    # Apply collections first to keep object renames stable (objects don't care, but humans do)
    for op in [o for o in ops if o.kind == "collection"]:
        col = bpy.data.collections.get(op.old)
        if col is None:
            continue
        if verbose:
            print(f"[rename collection] {op.old} -> {op.new}")
        col.name = op.new

    for op in [o for o in ops if o.kind == "object"]:
        obj = bpy.data.objects.get(op.old)
        if obj is None:
            continue
        if verbose:
            print(f"[rename object] {op.old} -> {op.new}")
        obj.name = op.new


def ensure_canonical_collections(prefix: str, verbose: bool = False) -> None:
    """
    Ensure canonical collection hierarchy exists:
      PREFIX_OVERLAY
        PREFIX_OVERLAY_CARDS
        PREFIX_OVERLAY_LABELS
      PREFIX_AA_GRID
      PREFIX_DEBUG
    """
    col_overlay = get_or_create_collection(canonical_col_name(prefix, COL_OVERLAY))
    col_cards = get_or_create_collection(canonical_col_name(prefix, COL_OVERLAY_CARDS))
    col_labels = get_or_create_collection(canonical_col_name(prefix, COL_OVERLAY_LABELS))
    col_grid = get_or_create_collection(canonical_col_name(prefix, COL_AA_GRID))
    col_debug = get_or_create_collection(canonical_col_name(prefix, COL_DEBUG))

    move_collection_under(col_overlay, col_cards)
    move_collection_under(col_overlay, col_labels)

    if verbose:
        print(f"[ensure] {col_overlay.name} contains {col_cards.name} and {col_labels.name}")
        print(f"[ensure] {col_grid.name} exists")
        print(f"[ensure] {col_debug.name} exists")


# ----------------------------
# CLI
# ----------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Enforce Blender naming conventions for AA grid + cards.")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX, help="Generated prefix, default: GEN")
    ap.add_argument("--apply", action="store_true", help="Apply renames (default is dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="Dry-run (default if --apply not set)")
    ap.add_argument("--verbose", action="store_true", help="Verbose output")
    ap.add_argument("--with-grid", action="store_true", help="Also rename best-guess grid mesh to AA_GRID__MESH")

    # Optional explicit mappings (repeatable)
    ap.add_argument("--code-step", action="append", default=[],
                    help='Code card mapping "step:title", e.g. 1:Patient to Encounter')
    ap.add_argument("--label-node", action="append", default=[],
                    help='Label card mapping "node:title", e.g. 1:Patient')

    return ap.parse_args(argv)


def parse_mapping(items: List[str]) -> Dict[str, int]:
    """
    Parse list of strings like ["1:Patient to Encounter", "2:Encounter to Observation"]
    into {"Patient to Encounter": 1, ...}
    """
    out: Dict[str, int] = {}
    for it in items:
        if ":" not in it:
            continue
        left, right = it.split(":", 1)
        left = left.strip()
        right = right.strip()
        if not left or not right:
            continue
        try:
            n = int(left)
        except ValueError:
            continue
        out[right] = n
    return out


def main() -> None:
    # Blender passes its own args; after `--` belong to us.
    argv = []
    if "--" in bpy.app.argv:
        argv = bpy.app.argv[bpy.app.argv.index("--") + 1 :]

    args = parse_args(argv)

    prefix = args.prefix.strip()
    if not prefix:
        prefix = DEFAULT_PREFIX

    code_steps = parse_mapping(args.code_step)
    label_nodes = parse_mapping(args.label_node)

    ops: List[RenameOp] = []
    ops.extend(plan_canonical_structure(prefix))
    ops.extend(plan_card_renames(prefix, code_steps if code_steps else None, label_nodes if label_nodes else None))
    if args.with_grid:
        ops.extend(plan_grid_mesh_rename())

    # De-dup exact ops (keep first)
    seen = set()
    uniq_ops = []
    for op in ops:
        key = (op.kind, op.old, op.new)
        if key in seen:
            continue
        seen.add(key)
        uniq_ops.append(op)

    if args.verbose or (not args.apply):
        if uniq_ops:
            print("Proposed renames:")
            for op in uniq_ops:
                print(f"  - {op.kind}: {op.old} -> {op.new}")
        else:
            print("No renames proposed.")

    if args.apply:
        ensure_canonical_collections(prefix, verbose=args.verbose)
        apply_ops(uniq_ops, verbose=args.verbose)
        if args.verbose:
            print("Done.")
    else:
        if args.verbose:
            print("Dry-run only (no changes applied). Use --apply to apply renames.")


if __name__ == "__main__":
    main()
