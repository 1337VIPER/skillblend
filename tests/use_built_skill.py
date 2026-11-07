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
for ob in (body, knob):
    style.finish(ob)
    style.material(ob)
print("STACK", [m.type for m in body.modifiers])
print("BEVEL", round(body.modifiers["Bevel"].width, 5), body.modifiers["Bevel"].segments)
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
b = cube.modifiers.new("Boolean", "BOOLEAN")
b.object = cyl
b.solver = "FLOAT" if "FLOAT" in [i.identifier for i in b.bl_rna.properties["solver"].enum_items] else "FAST"
bpy.ops.wm.save_as_mainfile(filepath=bad_path)
print("USE_OK")
