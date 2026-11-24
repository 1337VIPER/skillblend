"""Render one picture of the open .blend. Runs INSIDE Blender; nothing is saved to the file.

    blender -b --factory-startup MODEL.blend --python review_shot.py -- OUT.png [back | top | front | side]

SkillBlend's eval uses it for its report, and every built skill ships it as scripts/review_shot.py so an AI can
look at what it built before calling it done.

Every model is shown the same way, whatever cameras and lights its file has: a view fitted to the model (3/4 from
the front by default; `back` is the opposite 3/4, `front` looks along the model's +X front), the
Workbench engine with studio lighting, cavity and outlines, and each material's own colour. A material whose
viewport colour was never set is shown in its shader's base colour, so a model isn't drawn grey only because its
author set colours in the node tree.
"""
import math
import sys

import bpy
from mathutils import Vector

GREY = 0.8
VIEWS = {"3/4": (1.0, -1.25, 0.75), "back": (-1.0, 1.25, 0.75), "top": (0.001, -0.001, 1.0),
         "front": (1.0, 0.0, 0.12), "side": (0.0, -1.0, 0.12)}


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    out = args[0]
    view = args[1] if len(args) > 1 and args[1] in VIEWS else "3/4"
    sc = bpy.context.scene
    cutters = {m.object.name for o in sc.objects for m in getattr(o, "modifiers", []) if m.type == "BOOLEAN" and m.object}
    parts = [o for o in sc.objects if o.type == "MESH" and not o.hide_render and o.name not in cutters
             and o.display_type not in ("WIRE", "BOUNDS")]
    if not parts:
        print("EVAL_THUMB none")
        return
    for o in sc.objects:  # helpers stay out of the picture
        if o.type == "MESH" and o not in parts:
            o.hide_render = True
    for m in bpy.data.materials:
        if not (m.use_nodes and m.node_tree):
            continue
        p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        default = all(abs(c - GREY) < 0.005 for c in m.diffuse_color[:3])
        if p is not None and default and not p.inputs["Base Color"].is_linked:
            m.diffuse_color = tuple(p.inputs["Base Color"].default_value)
            if not p.inputs["Metallic"].is_linked:
                m.metallic = p.inputs["Metallic"].default_value
            if not p.inputs["Roughness"].is_linked:
                m.roughness = p.inputs["Roughness"].default_value
    pts = [o.matrix_world @ Vector(c) for o in parts for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    centre, radius = (lo + hi) / 2, max((hi - lo).length / 2, 1e-4)
    cam_data = bpy.data.cameras.new("EvalThumb")
    cam = bpy.data.objects.new("EvalThumb", cam_data)
    sc.collection.objects.link(cam)
    cam_data.lens = 60
    w, h = 800, 600
    fov = 2 * math.atan(36 / 2 / cam_data.lens * h / w)
    direction = Vector(VIEWS[view]).normalized()
    cam.location = centre + direction * (radius / math.sin(fov / 2) * 1.04)
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_data.clip_start, cam_data.clip_end = radius / 100, radius * 100
    sc.camera = cam
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light, sh.color_type = "STUDIO", "MATERIAL"
    sh.show_cavity, sh.cavity_type, sh.show_object_outline = True, "BOTH", True
    backdrop = bpy.data.worlds.new("EvalThumb")  # the same backdrop for every model, whatever its file's world is
    backdrop.color = (0.05, 0.05, 0.05)
    sc.world = backdrop
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("EVAL_THUMB ok", len(parts))


main()
