"""A stand-in for an AI in the eval harness's tests. It is NOT evidence about any AI: it only gives the harness
two kinds of model to score, so the tests can check the plumbing without spending anyone's AI usage.

    blender -b --factory-startup --python tests/eval_standin.py -- ARM SKILL_DIR OUT.blend TASK

ARM "with" builds a small prop with the skill's style.py (the way tests/use_built_skill.py does); anything else
builds a careless one (default names, unapplied scale, a huge bevel, a cutter that renders). To act like a runner
that fails, set EVAL_STANDIN_SKIP to "task:arm" pairs (comma-separated): those save nothing.
"""
import math
import os
import sys

import bpy

arm, skill, out, task = (sys.argv[sys.argv.index("--") + 1:] + ["", "", "", ""])[:4]
if f"{task}:{arm}" in [x.strip() for x in os.environ.get("EVAL_STANDIN_SKIP", "").split(",")]:
    print("STANDIN skipped", task, arm)
    sys.exit(0)

# a different size for each task, so the models aren't copies of each other
SIZES = {"supply-crate": (0.8, 0.5, 0.5), "flashlight": (0.16, 0.04, 0.04), "junction-box": (0.2, 0.08, 0.2),
         "field-radio": (0.3, 0.1, 0.22), "vent-panel": (0.6, 0.05, 0.4), "fuel-canister": (0.35, 0.16, 0.45)}
sx, sy, sz = SIZES.get(task, (0.3, 0.2, 0.25))

bpy.ops.wm.read_factory_settings(use_empty=True)
if arm == "with":
    sys.path.insert(0, os.path.join(skill, "scripts"))
    import style  # noqa: E402
    style.setup_scene()
    col = style.collection(style.name(task or "prop"))
    body = style.box(style.name(f"{task} body"), (sx, sy, sz), col=col)
    knob = style.cylinder(style.name(f"{task} knob"), min(sx, sz) * 0.08, sy * 0.25, segments=24,
                          loc=(sx * 0.25, 0, sz), col=col)
    hole = style.cylinder(style.name(f"{task} opening", role="cutter"), min(sx, sz) * 0.15, sy * 3,
                          loc=(0, 0, sz * 0.5))
    hole.rotation_euler = (math.radians(90), 0, 0)
    style.cutter(body, hole)
    for ob in (body, knob):
        style.finish(ob)
        style.material(ob)
else:
    bpy.context.scene.unit_settings.system = "IMPERIAL"
    bpy.ops.mesh.primitive_cube_add(size=1)
    cube = bpy.context.active_object
    cube.scale = (sx, sy, sz)                      # scale left unapplied
    m = cube.modifiers.new("Bevel", "BEVEL")
    m.width = 0.2                                  # far too wide for the part
    m.segments = 12
    bpy.ops.mesh.primitive_cylinder_add(radius=min(sx, sz) * 0.3, depth=1)
    cyl = bpy.context.active_object                # a cutter left visible, with its default name
    b = cube.modifiers.new("Boolean", "BOOLEAN")
    b.object = cyl
bpy.ops.wm.save_as_mainfile(filepath=out)
print("STANDIN saved", out)
