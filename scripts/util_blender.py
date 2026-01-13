#!/usr/bin/env python3
from __future__ import annotations

import bpy
from pathlib import Path

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

def ensure_collection(name: str, parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
    """
    Ensure a Collection with `name` exists and is linked under `parent` (or the scene root).
    Returns the collection.
    """
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)

    # Decide where it should be linked
    if parent is None:
        parent = bpy.context.scene.collection

    # Link if not already linked under parent
    if col.name not in parent.children:
        parent.children.link(col)

    return col

def ensure_object_linked(obj: bpy.types.Object, collection: bpy.types.Collection | None = None) -> None:
    """
    Ensure `obj` is linked to `collection` (or the active scene root collection if None).
    Safe to call repeatedly.
    """
    if obj is None:
        return

    if collection is None:
        collection = bpy.context.scene.collection

    # If already linked to that collection, nothing to do
    if obj.name in collection.objects:
        return

    # Link it
    collection.objects.link(obj)

def ensure_material(
    name: str,
    use_nodes: bool = True,
) -> bpy.types.Material:
    """
    Ensure a Material with `name` exists. Optionally enables nodes.
    Returns the material.
    """
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)

    if use_nodes and not mat.use_nodes:
        mat.use_nodes = True

    return mat

def ensure_font(font_path: str | Path) -> bpy.types.VectorFont:
    """
    Ensure a VectorFont datablock is loaded from `font_path`.
    Returns the loaded font datablock.

    `font_path` should be a .ttf/.otf file on disk.
    """
    p = Path(font_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Font file not found: {p}")

    # If already loaded, reuse it
    for f in bpy.data.fonts:
        try:
            if Path(bpy.path.abspath(f.filepath)).resolve() == p:
                return f
        except Exception:
            pass

    # Load new font datablock
    return bpy.data.fonts.load(str(p))

def frame_range_set(start: int, end: int, *, current: int | None = None) -> None:
    """
    Set scene frame start/end (and optionally current frame).
    """
    scene = bpy.context.scene
    scene.frame_start = int(start)
    scene.frame_end = int(end)
    if current is not None:
        scene.frame_set(int(current))