import bpy

def ensure_geometry_nodes_modifier(obj, node_group):
    """Add a Geometry Nodes modifier (or reuse one) and assign the node group."""
    mod = None
    for m in obj.modifiers:
        if m.type == 'NODES':
            mod = m
            break
    if mod is None:
        mod = obj.modifiers.new(name="GeometryNodes", type='NODES')
    mod.node_group = node_group
    return mod

def make_grid_node_group(name="AA_Grid_GN"):
    # Reuse if already exists
    ng = bpy.data.node_groups.get(name)
    if ng and ng.bl_idname == "GeometryNodeTree":
        return ng

    ng = bpy.data.node_groups.new(name=name, type="GeometryNodeTree")
    ng.is_modifier = True

    # Clear default nodes (if any)
    ng.nodes.clear()
    nodes = ng.nodes
    links = ng.links

    # --- Nodes: Group Input / Output ---
    n_in = nodes.new("NodeGroupInput")
    n_in.location = (-600, 0)

    n_out = nodes.new("NodeGroupOutput")
    n_out.location = (400, 0)

    # Ensure group interface sockets
    # Output: Geometry
    if "Geometry" not in ng.interface.items_tree:
        pass  # interface API differs a bit across versions; we'll add sockets below

    # Add sockets via interface (Blender 4.x/5.x)
    # Outputs
    try:
        out_geo = ng.interface.new_socket(
            name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry'
        )
    except Exception:
        # If already exists or API variance, ignore
        pass

    # Inputs
    def add_input(name, socket_type, default=None, minv=None, maxv=None):
        try:
            s = ng.interface.new_socket(name=name, in_out='INPUT', socket_type=socket_type)
            if default is not None:
                s.default_value = default
            if minv is not None:
                s.min_value = minv
            if maxv is not None:
                s.max_value = maxv
            return s
        except Exception:
            return None

    add_input("Size X", "NodeSocketFloat", default=2.0, minv=0.0)
    add_input("Size Y", "NodeSocketFloat", default=2.0, minv=0.0)
    add_input("Verts X", "NodeSocketInt",   default=10,  minv=2)
    add_input("Verts Y", "NodeSocketInt",   default=10,  minv=2)

    # --- Grid primitive node ---
    n_grid = nodes.new("GeometryNodeMeshGrid")
    n_grid.location = (-150, 0)

    # Wire group inputs -> Mesh Grid inputs
    # Mesh Grid inputs typically:
    # 0: Size X, 1: Size Y, 2: Vertices X, 3: Vertices Y (varies slightly, but names are stable)
    def sock(node, name):
        return node.inputs.get(name) or node.outputs.get(name)

    # Connect by name (more robust than index)
    links.new(n_in.outputs.get("Size X"), sock(n_grid, "Size X"))
    links.new(n_in.outputs.get("Size Y"), sock(n_grid, "Size Y"))
    links.new(n_in.outputs.get("Verts X"), sock(n_grid, "Vertices X"))
    links.new(n_in.outputs.get("Verts Y"), sock(n_grid, "Vertices Y"))

    # Output grid geometry -> Group Output
    links.new(n_grid.outputs.get("Mesh"), n_out.inputs.get("Geometry"))

    return ng

def main():
    # Create node group
    ng = make_grid_node_group("AA_Grid_GN")

    # Create a new object to hold the modifier
    mesh = bpy.data.meshes.new("AA_Grid_HolderMesh")
    obj = bpy.data.objects.new("AA_Grid_Object", mesh)
    bpy.context.collection.objects.link(obj)

    # Make it active/selected
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Add GN modifier and assign node group
    ensure_geometry_nodes_modifier(obj, ng)

    # Optional: set some defaults on the modifier inputs (the “Group Input” sockets)
    # These keys match the interface socket names
    # Note: Blender stores them as ID-properties on the modifier, by socket identifier;
    # names usually work, but if not, just set them in the modifier UI.
    try:
        mod = next(m for m in obj.modifiers if m.type == 'NODES')
        mod["Size X"] = 4.0
        mod["Size Y"] = 3.0
        mod["Verts X"] = 12
        mod["Verts Y"] = 8
    except Exception:
        pass

    print("Created Geometry Nodes grid node group and attached it to:", obj.name)

main()
