"""Worked example: an original wedge coupe, start to Unreal FBX. Copy it as the start of a new car script.
  blender.exe -b --factory-startup --python example_wedge_coupe.py -- OUT_DIR [--door 0.7] [--no-export]
Writes review renders (car_34f/34r/side/front/top.png), the .blend, and SK_WedgeCoupe.fbx."""
import os, sys
import bpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carkit as C

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out = args[0] if args and not args[0].startswith("--") else os.path.join(os.getcwd(), "WedgeCoupe")
door = float(args[args.index("--door") + 1]) if "--door" in args else 0.0
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)

# 1. proportions and the four design curves
P = C.proportions("wedge_coupe", 4.2)
D = C.design(P, wedge=0.6, tumblehome=0.74)
g = P["ground"]

# 2. primary: the lofted body shell, arches
body = C.loft_body(D)
C.wheel_arches(body, P)

# 3. secondary: glass (exact outlines, sunk behind a gasket), lamps, grille, plate, the door split
O = C.dlo(D)
glass = []
for poly in O["side"]:
    glass += C.window(body, poly, "XZ", name="SideGlass")
glass += C.window(body, O["windscreen"], "XY", z_min=O["z_min"], name="Windscreen")
glass += C.window(body, O["backlight"], "XY", z_min=O["z_min"], name="Backlight")
C.lamp(body, 0.58, g + 0.40, 0.30, 0.09, "front")
C.lamp(body, 0.60, g + 0.52, 0.34, 0.08, "rear", lens="TailLens")
C.grille(body, 0.30, g + 0.18, g + 0.32)
C.plate(body, "rear", g + 0.40)
xf = P["x_front_axle"]; zb = C.lerp_keys(D["belt"], 0.4)
door_outline = [(xf - 0.42, g + 0.10), (xf - 1.40, g + 0.10), (xf - 1.40, zb + 0.02), (xf - 0.55, zb + 0.02)]
doors = C.split_panel(body, door_outline, "XZ", gap=0.005, name="Door")

# 4. wheels and the rig (front-hinged doors opening 60 degrees)
wheels = {c: C.wheel(P, side=1 if c[1] == "L" else -1, name="Wheel_" + c) for c in ("FL", "FR", "RL", "RR")}
hinges = [(d, (xf - 0.45, (1 if d.name.endswith("L") else -1) * P["W"] / 2, g + 0.5), "Z",
           60 if d.name.endswith("L") else -60) for d in doors]
root = C.rig_car(body, P, wheels, hinges)
for o in glass:
    o.parent = body
root["door"] = door
bpy.context.view_layer.update()

# 5. review, save, export
print("TRIS", sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in bpy.data.objects if o.type == "MESH"))
C.render_views(out, target=(0, 0, 0.55))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "wedge_coupe.blend"))
if "--no-export" not in args:
    root["door"] = 0.0; bpy.context.view_layer.update()
    parts = [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("Wheel_")]
    C.export_unreal_vehicle(os.path.join(out, "SK_WedgeCoupe.fbx"), parts, wheels, P)
