#!/usr/bin/env python3
from __future__ import annotations

import bpy


def remove_collection_recursive(col: bpy.types.Collection) -> None:
    """
    Remove a Blender collection and everything inside it:
      - recursively removes child collections
      - deletes all objects in the collection (and unlinks them from all collections)
      - removes the collection datablock itself

    Safe to call even if some objects/collections are already removed.
    Avoids context-dependent bpy.ops where possible.
    """
    if col is None:
        return

    # 1) Recurse into children first (copy list because it mutates during removal)
    for child in list(col.children):
        remove_collection_recursive(child)

    # 2) Remove all objects referenced by this collection
    # Copy list because it mutates as we unlink/remove
    for obj in list(col.objects):
        # Unlink from all collections to avoid lingering references
        for c in list(obj.users_collection):
            try:
                c.objects.unlink(obj)
            except Exception:
                pass

        # Remove the object datablock if it still exists
        if obj.name in bpy.data.objects:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                # If something else still references it, do_unlink handles most cases
                pass

    # 3) Unlink this collection from any parents
    for parent in list(col.users_scene):
        try:
            parent.collection.children.unlink(col)
        except Exception:
            pass

    for parent_col in list(col.users_collection):
        try:
            parent_col.children.unlink(col)
        except Exception:
            pass

    # 4) Finally remove the collection datablock
    if col.name in bpy.data.collections:
        try:
            bpy.data.collections.remove(col)
        except Exception:
            pass


def purge_orphans(recursive: bool = True, passes: int = 5) -> None:
    """
    Optional helper: purge orphan datablocks after deletions.
    Some builds require multiple passes.
    """
    # This operator is the canonical way; it can be context-sensitive,
    # but generally works from scripting context.
    for _ in range(max(1, passes)):
        try:
            bpy.ops.outliner.orphans_purge(do_recursive=recursive)
        except Exception:
            break
