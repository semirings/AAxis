import bpy
import os

TRAJAN_FONT_PATH = "/Users/gcr/Vignettes/BlenderShared/Fonts/Trajan Pro Font Family/TrajanPro-Regular.ttf"
COLLECTION_NAME = "TrajanGlyphs"
TEXT_SIZE = 1.0

UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"
SPECIAL = " " + r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"""
CHARS = UPPER + LOWER + DIGITS + SPECIAL
# CHARS = "ABCDabcd0123"  # DEBUG SET FIRST. Expand later once this works.

def ensure_collection(name: str):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col

def clear_collection(col):
    for o in list(col.objects):
        bpy.data.objects.remove(o, do_unlink=True)

def load_font(font_file: str):
    ap = bpy.path.abspath(font_file)
    if not (os.path.isfile(ap) and ap.lower().endswith((".ttf",".otf"))):
        raise RuntimeError(f"Font file not found: {ap}")
    for f in bpy.data.fonts:
        if bpy.path.abspath(f.filepath) == ap:
            return f
    return bpy.data.fonts.load(ap)

def mesh_from_object(obj, mesh_name: str):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(eval_obj, preserve_all_data_layers=True, depsgraph=depsgraph)
    mesh.name = mesh_name
    mesh.update()  # important
    return mesh

def make_font_obj(ch: str, font, col):
    crv = bpy.data.curves.new(name=f"FONTDATA_{ord(ch)}", type="FONT")
    crv.body = ch
    crv.size = TEXT_SIZE
    crv.extrude = 0.0
    crv.bevel_depth = 0.0
    crv.fill_mode = 'BOTH'
    crv.font = font

    # These matter for evaluated output
    crv.resolution_u = 12
    crv.render_resolution_u = 12

    obj = bpy.data.objects.new(name=f"FONT_{ord(ch)}", object_data=crv)
    obj["char"] = ch
    col.objects.link(obj)
    return obj

def build_debug():
    col = ensure_collection(COLLECTION_NAME)
    clear_collection(col)

    font = load_font(TRAJAN_FONT_PATH)
    print("Loaded font:", bpy.path.abspath(font.filepath))

    for ch in CHARS:
        # Create font object
        font_obj = make_font_obj(ch, font, col)

        # Force depsgraph/view-layer update so evaluated geometry exists
        bpy.context.view_layer.update()

        # Extract mesh without bpy.ops
        mesh = mesh_from_object(font_obj, f"MESH_{ord(ch)}")

        # Diagnostics: counts + first vertex coordinate
        vcount = len(mesh.vertices)
        ecount = len(mesh.edges)
        pcount = len(mesh.polygons)
        if vcount:
            v0 = mesh.vertices[0].co
            print(f"[{ch}] mesh: verts={vcount} edges={ecount} faces={pcount} v0={tuple(v0)}")
        else:
            print(f"[{ch}] mesh: verts=0 edges=0 faces=0  <-- EMPTY (dims will be 0)")

        # Create mesh object (named as the character)
        obj_name = ch if ch != " " else "␠"
        mesh_obj = bpy.data.objects.new(obj_name, mesh)
        mesh_obj["char"] = ch
        col.objects.link(mesh_obj)

        # Clean up intermediate font obj + data
        crv = font_obj.data
        bpy.data.objects.remove(font_obj, do_unlink=True)
        bpy.data.curves.remove(crv, do_unlink=True)

    print("Done.")

build_debug()
