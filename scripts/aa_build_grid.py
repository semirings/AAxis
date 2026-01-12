#!/usr/bin/env python3
from __future__ import annotations

import bpy
import argparse

from util_blender import ensure_object_linked, ensure_collection


def build_grid_plane(
    name: str = "AA_GRID__MESH",
    collection: str = "GEN_AA_GRID",
    size_x: float = 8.0,
    size_y: float = 5.0,
    gn_group_name: str = "AA_Grid_GN",
    gn_modifier_name: str = "AA_Grid_GN_Mod",
    params: dict | None = None,
) -> bpy.types.Object:
    params = params or {}

    # Create plane mesh
    mesh = bpy.data.meshes.new(name + "_MESH")
    obj = bpy.data.objects.new(name, mesh)

    # Create a simple plane
    bm = bpy.ops.mesh.primitive_plane_add(size=1.0, enter_editmode=False, align='WORLD')
    # primitive_plane_add created an object; reuse its mesh to avoid bmesh boilerplate
    plane_obj = bpy.context.active_object
    obj.data = plane_obj.data.copy()
    bpy.data.objects.remove(plane_obj, do_unlink=True)

    # Scale plane to desired size
    obj.scale[0] = size_x * 0.5
    obj.scale[1] = size_y * 0.5

    # Link to collection
    col = ensure_collection(collection)
    ensure_object_linked(obj, col)

    # Add geometry nodes modifier
    gn = obj.modifiers.new(name=gn_modifier_name, type='NODES')
    ng = bpy.data.node_groups.get(gn_group_name)
    if ng is None:
        raise RuntimeError(f"Geometry Node group '{gn_group_name}' not found in this .blend")
    gn.node_group = ng

    # Set GN inputs if present
    # Blender names group inputs exactly; we attempt common ones.
    for k, v in params.items():
        try:
            gn[k] = v
        except Exception:
            # some versions use different access; ignore
            pass

    return obj


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Build AA grid plane + attach GN group.")
    ap.add_argument("--size-x", type=float, default=8.0)
    ap.add_argument("--size-y", type=float, default=5.0)
    ap.add_argument("--gn-group", type=str, default="AA_Grid_GN")
    return ap.parse_args(argv)


def main():
    argv = []
    if "--" in bpy.app.argv:
        argv = bpy.app.argv[bpy.app.argv.index("--")+1:]
    args = _parse_args(argv)
    build_grid_plane(size_x=args.size_x, size_y=args.size_y, gn_group_name=args.gn_group)


if __name__ == "__main__":
    main()
