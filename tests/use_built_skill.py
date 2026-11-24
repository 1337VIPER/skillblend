"""Use a built skill's style.py to make a small model, the way Claude would.

    blender -b --factory-startup --python tests/use_built_skill.py -- SKILL_DIR OUT_GOOD.blend OUT_BAD.blend
"""
import math
import os
import sys

import bpy

skill, good_path, bad_path = sys.argv[sys.argv.index("--") + 1:][:3]
sys.path.insert(0, os.path.join(skill, "scripts"))
import style  # noqa: E402

bpy.ops.wm.read_factory_settings(use_empty=True)
style.setup_scene()
col = style.collection(style.name("radio"))
body = style.box(style.name("radio body"), (0.08, 0.04, 0.16), col=col)
knob = style.cylinder(style.name("radio knob"), 0.008, 0.01, segments=24, loc=(0.02, 0, 0.16), col=col)
hole = style.cylinder(style.name("speaker hole", role="cutter"), 0.02, 0.1, loc=(0, -0.02, 0.06))
hole.rotation_euler = (math.radians(90), 0, 0)
style.cutter(body, hole)
# a cutter stays where the script put it, also off-centre and on a part that isn't at the origin
side = style.box(style.name("side part"), (0.2, 0.1, 0.1), loc=(0.5, 0.3, 0.0), col=col)
slot = style.box(style.name("side slot", role="cutter"), (0.05, 0.2, 0.02), loc=(0.56, 0.31, 0.04))
tris_before = len(side.data.polygons)
style.cutter(side, slot)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
cut_faces = len(side.evaluated_get(dg).to_mesh().polygons)
print("CUTTER", [round(v, 3) for v in slot.matrix_world.translation], [round(v, 3) for v in hole.matrix_world.translation], tris_before, cut_faces)
if (abs(slot.matrix_world.translation.x - 0.56) < 1e-5 and abs(slot.matrix_world.translation.y - 0.31) < 1e-5
        and abs(hole.matrix_world.translation.y + 0.02) < 1e-5 and cut_faces > tris_before):
    print("CUTTER_OK")
for ob in (body, knob, side):
    style.finish(ob)
    style.material(ob)
print("STACK", [m.type for m in body.modifiers])
print("BEVEL", round(body.modifiers["Bevel"].width, 5), body.modifiers["Bevel"].segments)
# with measured tiers, every width style.bevel picks is one of them, and "small" / "large" are the ends of the ladder
tiers = style.bevel_tiers()
picked = [body.modifiers["Bevel"].width, knob.modifiers["Bevel"].width, style.bevel_width(body, "small"),
          style.bevel_width(body, "medium"), style.bevel_width(body, "large"), style.bevel_width(body, 0.5)]
if tiers:
    on_ladder = all(any(abs(w - t) < 1e-7 for t in tiers) for w in picked)
    ends = abs(picked[2] - tiers[0]) < 1e-7 and abs(picked[4] - tiers[-1]) < 1e-7
else:
    on_ladder, ends = True, picked[2] < picked[3] < picked[4]
print("TIERS", [round(t, 5) for t in tiers], [round(w, 5) for w in picked])
if on_ladder and ends and body.modifiers["Bevel"].miter_outer == (style.get("bevel_miter_outer") or "MITER_ARC"):
    print("TIERS_OK")
bpy.ops.wm.save_as_mainfile(filepath=good_path)

# a careless version: default names, unscaled, a huge bevel, a rendering cutter
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.unit_settings.system = "IMPERIAL"
bpy.ops.mesh.primitive_cube_add(size=1)
cube = bpy.context.active_object
cube.scale = (0.1, 0.1, 0.2)
m = cube.modifiers.new("Bevel", "BEVEL")
m.width = 0.2
m.segments = 12
bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=1)
cyl = bpy.context.active_object
blank = bpy.data.materials.new("Blank")          # a material nobody gave a colour
blank.use_nodes = True
cube.data.materials.append(blank)
b = cube.modifiers.new("Boolean", "BOOLEAN")
b.object = cyl
b.solver = "FLOAT" if "FLOAT" in [i.identifier for i in b.bl_rna.properties["solver"].enum_items] else "FAST"
bpy.ops.mesh.primitive_cube_add(size=0.02)       # a cutter lost in the middle of the part: it cuts nothing you can see
inner = bpy.context.active_object
b2 = cube.modifiers.new("Boolean inner", "BOOLEAN")
b2.object = inner
bpy.ops.wm.save_as_mainfile(filepath=bad_path)
print("USE_OK")

# deeper style helpers: any modifier with the artist's settings, recipe materials, review render setup
bpy.ops.wm.read_factory_settings(use_empty=True)
style.setup_scene()
part = style.box("deep_part", (0.2, 0.1, 0.05))
sw = style.modifier(part, "SOLIDIFY")
print("DEEP solidify", round(sw.thickness, 4))
mat = style.material(part, "SteelDark")
p = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
print("DEEP steel metallic", p.inputs["Metallic"].default_value, "roughness linked", p.inputs["Roughness"].is_linked)
noise = next((n for n in mat.node_tree.nodes if n.type == "TEX_NOISE"), None)
ramp = next((n for n in mat.node_tree.nodes if n.type == "VALTORGB"), None)
if noise and ramp:
    print("DEEP noise", round(noise.inputs["Scale"].default_value, 3),
          round(ramp.color_ramp.elements[0].color[0], 3), round(ramp.color_ramp.elements[1].color[0], 3))
# a name the files never showed gets the standard palette's values, by name or by what the name says; your own colour wins
def base(m):
    n = next(x for x in m.node_tree.nodes if x.type == "BSDF_PRINCIPLED")
    return [round(c, 3) for c in n.inputs["Base Color"].default_value[:3]], round(n.inputs["Metallic"].default_value, 2)
rub, gun, own = style.build_material("RubberGrip"), style.build_material("GunMetalDark"), style.build_material("CrateGreen", color=(0.2, 0.27, 0.19))
print("STANDARD", base(rub), base(gun), base(own), [round(c, 3) for c in own.diffuse_color[:3]])
if (max(base(rub)[0]) < 0.1 and base(gun)[1] == 1.0 and max(base(gun)[0]) < 0.2 and base(own)[0] == [0.2, 0.27, 0.19]
        and [round(c, 3) for c in own.diffuse_color[:3]] == [0.2, 0.27, 0.19]):
    print("STANDARD_OK")
sc = style.setup_render()
print("DEEP render", sc.render.engine, sc.view_settings.view_transform, sc.world is not None)
print("DEEP_OK")
