"""Make the demo project: small .blend files that exercise every module (used by `skillblend.py demo` and the tests).

    blender -b --factory-startup --python forge/demo/make_demo.py -- OUT_DIR

Each file imitates how an artist might hand in that module's request. They are
deliberately simple; they exist to prove the analysis and the build work.
"""
import bpy
import bmesh
import math
import os
import sys

out_dir = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "fixtures"
os.makedirs(out_dir, exist_ok=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.unit_settings.system = "METRIC"
    s.unit_settings.scale_length = 1.0


def coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def box(name, size, loc=(0, 0, 0), col=None, bottom=True):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
        if bottom:
            v.co.z += size[2] / 2
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    ob.location = loc
    return ob


def cyl(name, r, h, loc=(0, 0, 0), col=None, segs=24):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=h)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    ob.location = loc
    return ob


def bevel(ob, width, segs=3, angle=30, harden=True):
    m = ob.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segs
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle)
    m.harden_normals = harden
    m.use_clamp_overlap = False
    m.miter_outer = "MITER_ARC"
    return m


def weighted(ob):
    m = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    m.keep_sharp = True
    return m


def smooth(ob, angle=30):
    ob.data.shade_smooth()
    try:
        ob.data.set_sharp_from_angle(angle=math.radians(angle))
    except Exception:
        pass


def unwrap(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.01)
    bpy.ops.object.mode_set(mode="OBJECT")


def set_mat(ob, name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    ob.data.materials.append(m)
    return ob


def save(name):
    path = os.path.join(out_dir, name)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("saved", path)


# 1. setup-and-scale: a 30 x 20 x 25 cm crate, snake_case names, bottom-centre origins
reset()
c = coll("crate")
body = box("crate_body", (0.30, 0.20, 0.25), col=c)
lid = box("crate_lid", (0.31, 0.21, 0.02), loc=(0, 0, 0.25), col=c)
handle = box("crate_handle_left", (0.01, 0.08, 0.03), loc=(-0.155, 0, 0.17), col=c)
for o, m in ((body, "PaintDark"), (lid, "PaintDark"), (handle, "Rubber")):
    bevel(o, 0.003, 3)
    weighted(o)
    smooth(o)
    set_mat(o, m)
save("setup_crate.blend")

# 2. bevels-and-shading: a junction box, bevel width ~1.5% of size, 3 segs, harden normals
reset()
c = coll("junction_box")
jb = box("junction_box_body", (0.20, 0.12, 0.08), col=c)
bevel(jb, 0.003, 3)
weighted(jb)
smooth(jb)
cover = box("junction_box_cover", (0.19, 0.11, 0.008), loc=(0, 0, 0.08), col=c)
bevel(cover, 0.0015, 2)
weighted(cover)
smooth(cover)
save("bevel_junction_box.blend")

# 3. subd-topology: a nozzle with support loops (cylinder with inset rings) + subsurf
reset()
c = coll("nozzle")
me = bpy.data.meshes.new("nozzle_shell")
bm = bmesh.new()
bmesh.ops.create_circle(bm, cap_ends=False, radius=0.05, segments=16)
edges = list(bm.edges)
z = 0.0
for step, (dz, scale) in enumerate([(0.004, 1.0), (0.05, 1.0), (0.004, 1.0), (0.03, 0.8),
                                    (0.004, 0.8), (0.04, 0.6), (0.004, 0.6)]):
    ret = bmesh.ops.extrude_edge_only(bm, edges=edges)
    verts = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=verts, vec=(0, 0, dz))
    for v in verts:
        v.co.x *= scale / (1.0 if step == 0 else 1.0)
        v.co.y *= scale / (1.0 if step == 0 else 1.0)
    edges = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMEdge)]
bm.to_mesh(me)
bm.free()
noz = bpy.data.objects.new("nozzle_shell", me)
c.objects.link(noz)
sol = noz.modifiers.new("Solidify", "SOLIDIFY")
sol.thickness = 0.004
sol.use_even_offset = True
sub = noz.modifiers.new("Subdivision", "SUBSURF")
sub.levels = 2
sub.render_levels = 3
smooth(noz, 180)
save("subd_nozzle.blend")

# 4. booleans-and-cutters: a panel with vent slots and a port, live EXACT booleans, wire cutters
reset()
c = coll("panel")
cut_c = coll("cutters")
panel = box("panel_plate", (0.30, 0.02, 0.20), col=c)
for i in range(4):
    ct = box(f"cutter_vent_{i}", (0.12, 0.05, 0.008), loc=(-0.05, 0, 0.04 + i * 0.02), col=cut_c)
    ct.display_type = "WIRE"
    ct.hide_render = True
    ct.parent = panel
port = cyl("cutter_port", 0.015, 0.06, loc=(0.09, 0, 0.12), col=cut_c)
port.rotation_euler = (math.radians(90), 0, 0)
port.display_type = "WIRE"
port.hide_render = True
port.parent = panel
b = panel.modifiers.new("Vents", "BOOLEAN")
b.operation = "DIFFERENCE"
b.solver = "EXACT"
b.operand_type = "COLLECTION"
b.collection = cut_c
bevel(panel, 0.002, 2)
weighted(panel)
smooth(panel)
save("boolean_panel.blend")

# 5. modifier-stacks: a mirrored, arrayed sci-fi rail
reset()
c = coll("rail")
rail = box("rail_segment", (0.10, 0.04, 0.03), loc=(0.06, 0, 0), col=c)
mi = rail.modifiers.new("Mirror", "MIRROR")
mi.use_axis = (True, False, False)
mi.use_clip = True
ar = rail.modifiers.new("Array", "ARRAY")
ar.count = 4
sol = rail.modifiers.new("Solidify", "SOLIDIFY")
sol.thickness = 0.002
bevel(rail, 0.0015, 2)
weighted(rail)
smooth(rail)
save("stack_rail.blend")

# 6. kit-library: a library of inserts (asset-marked) and a model using linked duplicates
reset()
lib = coll("kit_inserts")
pieces = []
for name, maker in (("kit_screw_m3", lambda n: cyl(n, 0.003, 0.002, col=lib, segs=12)),
                    ("kit_bolt_m6", lambda n: cyl(n, 0.006, 0.004, col=lib, segs=6)),
                    ("kit_vent_small", lambda n: box(n, (0.04, 0.004, 0.02), col=lib)),
                    ("kit_panel_hatch", lambda n: box(n, (0.08, 0.004, 0.06), col=lib))):
    p = maker(name)
    p.asset_mark()
    pieces.append(p)
use = coll("kit_test_model")
base = box("hull_plate", (0.4, 0.05, 0.3), col=use)
for i in range(6):
    d = bpy.data.objects.new(f"kit_screw_m3.{i + 1:03d}", pieces[0].data)
    use.objects.link(d)
    d.location = (-0.18 + i * 0.07, -0.026, 0.28)
save("kit_library.blend")

# 7. uvs-and-texel-density + game-ready-export: high/low pair with UVs
reset()
c = coll("canister")
hi = cyl("canister_high", 0.06, 0.25, col=c, segs=48)
bevel(hi, 0.004, 4)
sub = hi.modifiers.new("Subdivision", "SUBSURF")
sub.levels = 1
smooth(hi)
lo = cyl("canister_low", 0.06, 0.25, col=c, segs=16)
smooth(lo)
unwrap(lo)
mat = bpy.data.materials.new("canister_mat")
lo.data.materials.append(mat)
save("gameready_canister.blend")

# 8. vehicles: a lofted-ish body block with wheels
reset()
c = coll("car")
body = box("car_body", (4.2, 1.8, 1.0), loc=(0, 0, 0.35), col=c)
sub = body.modifiers.new("Subdivision", "SUBSURF")
sub.levels = 2
for i, (x, y) in enumerate(((1.3, 0.8), (1.3, -0.8), (-1.3, 0.8), (-1.3, -0.8))):
    w = cyl(f"car_wheel_{i}", 0.33, 0.22, loc=(x, y, 0.33), col=c)
    w.rotation_euler = (math.radians(90), 0, 0)
save("vehicle_body.blend")
# 9. blockout-to-detail: a radio as a blockout and as the finished model, with materials
reset()
blk = coll("Blockout")
fin = coll("Final")
box("radio_block_body", (0.08, 0.04, 0.16), col=blk)
box("radio_block_antenna", (0.01, 0.01, 0.12), loc=(0.03, 0, 0.16), col=blk)
parts = [box("radio_body", (0.08, 0.04, 0.16), col=fin), box("radio_front_panel", (0.07, 0.004, 0.10), loc=(0, -0.021, 0.03), col=fin),
         cyl("radio_knob_volume", 0.007, 0.012, loc=(0.025, 0, 0.165), col=fin), cyl("radio_knob_channel", 0.006, 0.01, loc=(-0.02, 0, 0.165), col=fin),
         cyl("radio_antenna", 0.004, 0.12, loc=(0.03, 0, 0.22), col=fin, segs=12), box("radio_belt_clip", (0.03, 0.006, 0.07), loc=(0, 0.023, 0.06), col=fin)]
for o, m in zip(parts, ("PaintDark", "Plastic", "Rubber", "Rubber", "Rubber", "Steel")):
    bevel(o, 0.0015, 3)
    weighted(o)
    smooth(o)
    set_mat(o, m)
save("blockout_radio.blend")
# 10. shaders, geometry nodes and look-dev: a lamp post with node materials, a GN-built cable and a lit scene
reset()
col = coll("lamp_post")


def pbr(name, base, metallic, roughness, rough_noise=False, emission=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*base, 1)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = roughness
    if rough_noise:  # procedural roughness break-up: Noise > Color Ramp > Roughness
        tc = nt.nodes.new("ShaderNodeTexCoord")
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 24.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (0.25, 0.25, 0.25, 1)
        ramp.color_ramp.elements[1].color = (0.55, 0.55, 0.55, 1)
        nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], p.inputs["Roughness"])
        bev = nt.nodes.new("ShaderNodeBevel")  # shader-only rounded edges
        bev.inputs["Radius"].default_value = 0.002
        nt.links.new(bev.outputs["Normal"], p.inputs["Normal"])
    if emission:
        p.inputs["Emission Color"].default_value = (*emission, 1)
        p.inputs["Emission Strength"].default_value = 8.0
    return m


steel = pbr("SteelDark", (0.08, 0.08, 0.09), 1.0, 0.35, rough_noise=True)
paint = pbr("PaintGreen", (0.05, 0.22, 0.12), 0.0, 0.55, rough_noise=True)
glow = pbr("LampGlow", (1.0, 0.9, 0.7), 0.0, 0.3, emission=(1.0, 0.85, 0.6))
pole = cyl("lamp_pole", 0.06, 4.0, loc=(0, 0, 2.0), col=col, segs=24)
set_mat(pole, "PaintGreen")
bevel(pole, 0.004, 3)
weighted(pole)
smooth(pole)
head = box("lamp_head", (0.5, 0.25, 0.12), loc=(0.2, 0, 4.0), col=col)
set_mat(head, "SteelDark")
sw = head.modifiers.new("Shrinkwrap", "SHRINKWRAP")  # studied-style wrap onto a target
sw.target = pole
sw.wrap_method = "NEAREST_SURFACEPOINT"
sw.offset = 0.001
sw.show_viewport = False
es = head.modifiers.new("EdgeSplit", "EDGE_SPLIT")
es.split_angle = math.radians(30)
lens = box("lamp_lens", (0.4, 0.2, 0.01), loc=(0.2, 0, 3.94), col=col)
set_mat(lens, "LampGlow")
# geometry nodes: a cable made from a curve, with an exposed radius input
ng = bpy.data.node_groups.new("CableFromCurve", "GeometryNodeTree")
ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
rad = ng.interface.new_socket("Radius", in_out="INPUT", socket_type="NodeSocketFloat")
rad.default_value = 0.01
ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
gi = ng.nodes.new("NodeGroupInput")
go = ng.nodes.new("NodeGroupOutput")
c2m = ng.nodes.new("GeometryNodeCurveToMesh")
circ = ng.nodes.new("GeometryNodeCurvePrimitiveCircle")
circ.inputs["Resolution"].default_value = 12
ng.links.new(gi.outputs["Radius"], circ.inputs["Radius"])
ng.links.new(gi.outputs["Geometry"], c2m.inputs["Curve"])
ng.links.new(circ.outputs["Curve"], c2m.inputs["Profile Curve"])
ng.links.new(c2m.outputs["Mesh"], go.inputs["Geometry"])
cd = bpy.data.curves.new("lamp_cable", "CURVE")
cd.dimensions = "3D"
sp = cd.splines.new("POLY")
sp.points.add(3)
for i, pt in enumerate(((0.06, 0, 3.6, 1), (0.3, 0.1, 3.0, 1), (0.4, 0.1, 1.5, 1), (0.5, 0, 0.0, 1))):
    sp.points[i].co = pt
cable = bpy.data.objects.new("lamp_cable", cd)
col.objects.link(cable)
gm = cable.modifiers.new("Cable", "NODES")
gm.node_group = ng
for it in ng.interface.items_tree:
    if getattr(it, "in_out", "") == "INPUT" and it.name == "Radius":
        props = getattr(gm, "properties", None)
        if props is not None and hasattr(props, "inputs"):
            getattr(props.inputs, it.identifier).value = 0.012  # Blender 5
        else:
            gm[it.identifier] = 0.012  # Blender 4
# look-dev: sky world, a sun and an area light, a 50 mm camera, AgX
sc = bpy.context.scene
w = bpy.data.worlds.new("Sky")
w.use_nodes = True
sky = w.node_tree.nodes.new("ShaderNodeTexSky")
w.node_tree.links.new(sky.outputs["Color"], w.node_tree.nodes["Background"].inputs["Color"])
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
sc.world = w
for kind, energy, loc in (("SUN", 3.0, (4, -4, 8)), ("AREA", 400.0, (-3, -3, 4))):
    ld = bpy.data.lights.new(f"{kind.lower()}_key", kind)
    ld.energy = energy
    lo = bpy.data.objects.new(f"{kind.lower()}_key", ld)
    sc.collection.objects.link(lo)
    lo.location = loc
camd = bpy.data.cameras.new("review_cam")
camd.lens = 50
camo = bpy.data.objects.new("review_cam", camd)
sc.collection.objects.link(camo)
camo.location = (6, -6, 3)
sc.camera = camo
try:
    sc.view_settings.view_transform = "AgX"
except TypeError:
    pass
save("lookdev_lamp_post.blend")
print("FIXTURES_OK")
