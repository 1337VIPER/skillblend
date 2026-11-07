"""subdkit test: an original probe (not a copy of any studied model), built only with subdkit.
  blender -b --factory-startup --python example_subd_probe.py -- OUT_DIR
Prints a TOPO PASS/FAIL line per part and writes shaded and wireframe renders to OUT_DIR."""
import os, sys, math, bpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subdkit as K
from mathutils import Vector
out = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
SEG = 16                                   # one cage count for every lathe: 64 around after SubD 2
R = 0.32
# hull: lathed along Z (nose at +Z), crisp hatch lip at the joint with the dome and at the tail step
hull = K.lathe([(0, -0.95), (0.06, -0.93), (0.16, -0.78), (0.26, -0.50), (0.31, -0.20), (R, 0.10), (R, 0.32),
                (0.30, 0.34), (0.0, 0.34)], "PaintGrey", SEG, crisp=(5, 6, 7), name="hull")
dome = K.lathe([(0.0, 0.30), (0.29, 0.30), (0.29, 0.36), (0.26, 0.52), (0.17, 0.66), (0.0, 0.72)], "Glass", SEG, crisp=(1, 2), name="dome")
ring = K.seam_ring(R, 0.06, 0.018, 0.33, "Steel", SEG)
rib, rc = K.ribs(0.09, 0.19, -1.00, -1.30, 5, 0.012)
nozzle = K.lathe([(0.0, -0.90), (0.07, -0.92), (0.08, -0.98)] + rib + [(0.21, -1.33), (0.20, -1.34), (0.08, -1.0), (0.0, -0.99)],
                 "SteelDark", SEG, crisp=[c + 3 for c in rc] + [len(rib) + 3, len(rib) + 4], name="nozzle")
fins = []
for k in range(3):
    a = 2 * math.pi * k / 3; d = Vector((math.cos(a), math.sin(a), 0))
    root = (d * 0.27 + Vector((0, 0, -0.35)), d * 0.20 + Vector((0, 0, -0.85)))
    tip = (d * 0.62 + Vector((0, 0, -0.80)), d * 0.60 + Vector((0, 0, -1.10)))
    fins.append(K.fin(root, tip, 0.05, "PaintRed", nu=4, nv=6, root_normal=d, embed=0.05, flare=1.5, name=f"fin{k}"))
# scoop frame on the side: rounded rect swept round a rounded triangle, sunk into the hull
c = Vector((0.0, -0.33, -0.05))
tri = [c + Vector((0, 0.02, 0.20)), c + Vector((-0.12, 0.04, -0.18)), c + Vector((0.12, 0.04, -0.18))]
frame = K.sweep(K.rounded_rect(0.035, 0.05, 0.012), K.rounded_polygon(tri, 0.05, 3), "PaintGrey", closed_path=True,
                up_fn=lambda p: (0, -1, 0), name="scoop_frame")
# seam strips: a vertical panel line down the hull, and one around the waist
line = [Vector((R * math.cos(math.radians(60)), R * math.sin(math.radians(60)), z)) for z in (0.30, 0.0, -0.3, -0.6)]
strip1 = K.trim_strip(hull, line, 0.014, 0.008, "Steel", step=0.04, name="seam_v")
waist = [Vector((R * math.cos(t), R * math.sin(t), 0.0)) for t in [2 * math.pi * i / 48 for i in range(48)]]
strip2 = K.trim_strip(hull, waist + waist[:1], 0.016, 0.008, "Steel", name="seam_waist")
# a cable: circle swept along a curve from the ring to the nozzle
path = [Vector((0.28 * math.cos(1.2), 0.28 * math.sin(1.2), 0.25 - 1.05 * t)) * 1 + Vector((0.06 * math.sin(math.pi * t), 0, 0)) for t in [i / 24 for i in range(25)]]
cable = K.sweep(K.circle(0.012, 8), path, "Rubber", name="cable")
bpy.context.view_layer.update()
ok1 = K.qa([hull, dome, ring, nozzle] + fins, "primary")
ok2 = K.qa([frame, strip1, strip2, cable], "detail")
print("QA", ok1, ok2)
# renders: shaded + wire
sc = bpy.context.scene; sc.render.engine = "BLENDER_WORKBENCH"; sh = sc.display.shading
sh.light = "STUDIO"; sh.color_type = "MATERIAL"; sh.show_cavity = True
sc.render.resolution_x, sc.render.resolution_y = 1400, 1000; sc.render.image_settings.file_format = "PNG"
col = {"PaintGrey": (.75, .75, .77), "Glass": (.3, .45, .55), "Steel": (.6, .6, .63), "SteelDark": (.3, .3, .32), "PaintRed": (.6, .1, .08), "Rubber": (.05, .05, .05)}
for m in bpy.data.materials: m.diffuse_color = (*col.get(m.name, (.5, .5, .5)), 1)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
T = Vector((0, 0, -0.25))
def shot(n, d, dist=3.4):
    d = Vector(d).normalized(); cam.location = T + d * dist
    cam.rotation_euler = (T - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = f"{out}/{n}.png"; bpy.ops.render.render(write_still=True)
shot("probe_a", (0.6, -1, 0.35)); shot("probe_b", (-0.5, 0.8, -0.4))
ink = bpy.data.materials.new("ink"); ink.diffuse_color = (0, 0, 0, 1)
for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    dd = o.copy(); dd.data = o.data.copy(); sc.collection.objects.link(dd)
    w = dd.modifiers.new("w", "WIREFRAME"); w.thickness = 0.0012; w.use_replace = True
    dd.data.materials.clear(); dd.data.materials.append(ink)
shot("probe_wire", (0.6, -1, 0.35)); shot("probe_wire_close", (0.7, -1, 0.1), 1.6)
