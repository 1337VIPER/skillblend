"""demokit: a tiny helper kit, standing in for an artist's own (the demo's build script imports it)."""
import bmesh
import bpy


def box(name, size, loc=(0, 0, 0), col=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z = v.co.z * size[2] + size[2] / 2
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    ob.location = loc
    return ob


def bevel(ob, width, segments=3):
    m = ob.modifiers.new("Bevel", "BEVEL")
    m.width, m.segments, m.limit_method = width, segments, "ANGLE"
    m.harden_normals = True
    ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL").keep_sharp = True
    ob.data.shade_smooth()
    return ob
