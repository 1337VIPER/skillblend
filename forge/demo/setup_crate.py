"""Crate: 30 x 20 x 25 cm storage crate with lid and handles (demo build script).

    blender -b --factory-startup --python setup_crate.py -- OUT.blend
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demokit as K  # noqa: E402

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
col = bpy.data.collections.new("crate")
bpy.context.scene.collection.children.link(col)
body = K.bevel(K.box("crate_body", (0.30, 0.20, 0.25), col=col), 0.003)
lid = K.bevel(K.box("crate_lid", (0.31, 0.21, 0.02), loc=(0, 0, 0.25), col=col), 0.003)
for side in (-1, 1):
    K.bevel(K.box(f"crate_handle_{'left' if side < 0 else 'right'}", (0.01, 0.08, 0.03),
                  loc=(side * 0.155, 0, 0.17), col=col), 0.0015, 2)
bpy.ops.wm.save_as_mainfile(filepath=out)
