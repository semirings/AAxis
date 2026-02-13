import bpy
import bmesh

def merge_selected_two_rails_keep_z(z_tol=1e-6):
    obj = bpy.context.edit_object
    if not obj or obj.type != "MESH":
        raise RuntimeError("Must be in Edit Mode on a mesh object.")

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()

    sel = [v for v in bm.verts if v.select]
    if len(sel) < 2 or len(sel) % 2 != 0:
        raise RuntimeError(f"Select an even number of verts (got {len(sel)}).")

    # Check uniform Z (your stated constraint)
    z0 = sel[0].co.z
    if any(abs(v.co.z - z0) > z_tol for v in sel):
        raise RuntimeError("Selected verts do not share the same Z (or tolerance too small).")

    # Split into two rails by X
    sel_by_x = sorted(sel, key=lambda v: v.co.x)
    half = len(sel_by_x) // 2
    left = sel_by_x[:half]
    right = sel_by_x[half:]

    # Sort each rail top->bottom by Y
    left.sort(key=lambda v: -v.co.y)
    right.sort(key=lambda v: -v.co.y)

    if len(left) != len(right):
        raise RuntimeError("Rails do not match in count after split.")

    # Merge
    for vL, vR in zip(left, right):
        midx = (vL.co.x + vR.co.x) * 0.5
        midy = (vL.co.y + vR.co.y) * 0.5
        merge_co = vL.co.copy()
        merge_co.x = midx
        merge_co.y = midy
        merge_co.z = z0  # unchanged

        vL.co = merge_co
        bmesh.ops.pointmerge(bm, verts=[vR], merge_co=merge_co)

    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=True)

# Run it
merge_selected_two_rails_keep_z()
