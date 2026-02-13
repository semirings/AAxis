import bpy
import bmesh
from mathutils import Vector

obj = bpy.context.edit_object
me = obj.data
bm = bmesh.from_edit_mesh(me)

# Get selected verts
verts = [v for v in bm.verts if v.select]

if len(verts) % 2 != 0:
    raise ValueError("Selected vertex count must be even")

processed = set()

for v in verts:
    if v in processed:
        continue

    # find nearest unprocessed neighbor
    nearest = None
    min_dist = float("inf")

    for u in verts:
        if u is v or u in processed:
            continue
        d = (v.co - u.co).length
        if d < min_dist:
            min_dist = d
            nearest = u

    if nearest is None:
        continue

    # midpoint
    mid = (v.co + nearest.co) / 2

    # move v to midpoint
    v.co = mid

    # redirect edges from nearest to v
    for e in list(nearest.link_edges):
        other = e.other_vert(nearest)
        if other != v:
            bm.edges.new((v, other))

    # delete nearest
    bm.verts.remove(nearest)

    processed.add(v)
    processed.add(nearest)

bmesh.update_edit_mesh(me)
