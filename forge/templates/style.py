"""Apply this skill's modelling style inside Blender (4.2 or newer).

    import sys; sys.path.insert(0, r"<skill>/scripts")
    import style
    style.setup_scene()
    body = style.box("crate_body", (0.3, 0.2, 0.25))
    style.finish(body)            # bevel, weighted normals, smoothing, stack order
    style.cutter(body, hole_obj)  # a live boolean the way the style keeps cutters

Every number comes from ../style.json (measured from the artist's files, or the
generic defaults). Read S to see them; pass explicit values to override.
"""
import json
import math
import os

import bpy
import bmesh

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "..", "style.json"), encoding="utf-8") as _fh:
    _STYLE = json.load(_fh)
S = _STYLE["numbers"]


def get(key, default=None):
    return S.get(key, default)


# ------------------------------------------------------------------ scene and names
def setup_scene(scene=None):
    scene = scene or bpy.context.scene
    scene.unit_settings.system = get("unit_system", "METRIC")
    scene.unit_settings.scale_length = float(get("scale_length", 1.0))
    return scene


def name(base, role=None):
    """Name a part the style's way. role: None, 'high', 'low', 'cutter' or 'lodN'."""
    case = get("naming_case", "snake")
    words = [w for w in base.replace("-", " ").replace("_", " ").split() if w]
    if case in ("pascal", "pascal_underscore"):
        out = ("_" if case == "pascal_underscore" else "").join(w[:1].upper() + w[1:] for w in words)
    elif case == "camel":
        out = words[0].lower() + "".join(w[:1].upper() + w[1:] for w in words[1:]) if words else base
    elif case == "kebab":
        out = "-".join(w.lower() for w in words)
    elif case == "spaces":
        out = " ".join(words)
    else:
        out = "_".join(w.lower() for w in words)
    pref = get("naming_prefix", "") or ""
    if role == "cutter":
        cp = get("cutter_prefix") or "cutter"
        out = (cp if cp.endswith("_") else cp + "_") + out
    elif pref and not out.startswith(pref):
        out = pref + out
    if role == "high":
        out += get("high_suffix", "_high")
    elif role == "low":
        out += get("low_suffix", "_low")
    elif role and role.startswith("lod"):
        out += "_LOD" + role[3:]
    return out


def collection(name_, parent=None):
    c = bpy.data.collections.get(name_)
    if c is None:
        c = bpy.data.collections.new(name_)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def link(obj, col=None):
    (col or bpy.context.scene.collection).objects.link(obj)
    return obj


# ------------------------------------------------------------------ primitives
def _mesh_obj(nm, bm, col=None):
    me = bpy.data.meshes.new(nm)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(nm, me)
    return link(ob, col)


def box(nm, size, loc=(0, 0, 0), col=None):
    """A box of real size (metres) with its origin where the style puts origins."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    ob = _mesh_obj(nm, bm, col)
    ob.location = loc
    set_origin(ob)
    return ob


def cylinder(nm, radius, depth, segments=32, loc=(0, 0, 0), col=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius, depth=depth)
    ob = _mesh_obj(nm, bm, col)
    ob.location = loc
    set_origin(ob)
    return ob


def set_origin(ob, mode=None):
    """Move the origin to 'bottom-center' or 'center' of the mesh without moving it.

    'contact-point' (the generic rule) means where the part touches the world: this sets
    bottom-center, which is right for anything that stands on something. Move it yourself
    for wall props (the wall face), lids and doors (the hinge line) and inserts (the mount).
    """
    mode = mode or get("origin", "bottom-center")
    if mode == "contact-point":
        mode = "bottom-center"
    if ob.type != "MESH" or mode not in ("bottom-center", "center"):
        return ob
    me = ob.data
    xs = [v.co.x for v in me.vertices] or [0]
    ys = [v.co.y for v in me.vertices] or [0]
    zs = [v.co.z for v in me.vertices] or [0]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    cz = min(zs) if mode == "bottom-center" else (min(zs) + max(zs)) / 2
    for v in me.vertices:
        v.co.x -= cx
        v.co.y -= cy
        v.co.z -= cz
    ob.location.x += cx * ob.scale.x
    ob.location.y += cy * ob.scale.y
    ob.location.z += cz * ob.scale.z
    return ob


# ------------------------------------------------------------------ modifiers
def bevel(ob, width=None, segments=None, tier=1.0, name_="Bevel"):
    """A Bevel modifier with the style's settings. tier scales the width (0.5 small edge, 2 big chamfer)."""
    m = ob.modifiers.new(name_, "BEVEL")
    if width is None:
        ratio = get("bevel_width_ratio")
        dims = max(ob.dimensions) if max(ob.dimensions) > 0 else 1.0
        width = ratio * dims if ratio else get("bevel_width_m", 0.002)
    m.width = width * tier
    m.segments = int(segments or get("bevel_segments", 3))
    lim = get("bevel_limit_method", "ANGLE")
    m.limit_method = lim
    if lim == "ANGLE":
        m.angle_limit = math.radians(float(get("bevel_angle_deg", 30)))
    if get("bevel_profile") is not None:
        m.profile = float(get("bevel_profile"))
    m.harden_normals = bool(get("bevel_harden_normals", True))
    m.use_clamp_overlap = bool(get("bevel_clamp", False))
    m.miter_outer = "MITER_ARC"
    return m


def weighted_normals(ob):
    m = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    m.keep_sharp = bool(get("weighted_normal_keep_sharp", True))
    return m


def smooth(ob, angle_deg=None):
    """Shade smooth and mark sharp edges by angle (the mesh-data way, no operator needed)."""
    angle = math.radians(float(angle_deg or get("smooth_angle_deg", 30)))
    ob.data.shade_smooth()
    try:
        ob.data.set_sharp_from_angle(angle=angle)
    except Exception:
        pass
    return ob


def subd(ob, levels=None, render=None):
    m = ob.modifiers.new("Subdivision", "SUBSURF")
    m.levels = int(levels if levels is not None else get("subd_levels_viewport", 2))
    m.render_levels = int(render if render is not None else get("subd_levels_render", 3))
    m.use_creases = bool(get("subd_use_creases", True))
    return m


def cutter(target, cut, operation="DIFFERENCE", stack=True):
    """Cut `cut` out of `target` with a live Boolean, keeping the cutter the style's way."""
    cut.display_type = get("cutter_display", "WIRE")
    cut.hide_render = True
    cname = get("cutter_collection")
    if cname:
        col = collection(cname)
        for c in list(cut.users_collection):
            c.objects.unlink(cut)
        col.objects.link(cut)
    if cut.parent is None:
        mw = cut.matrix_world.copy()
        cut.parent = target
        cut.matrix_world = mw
    m = target.modifiers.new("Boolean", "BOOLEAN")
    m.operation = operation
    m.object = cut
    try:
        m.solver = get("boolean_solver", "EXACT")
    except TypeError:
        pass
    if stack:
        order_stack(target)
    return m


def order_stack(ob, order=None):
    """Reorder modifiers to the style's stack order (types not listed keep their place at the end)."""
    order = order or get("stack_order") or []
    rank = {t: i for i, t in enumerate(order)}
    def key(m):
        t = m.type
        if t == "NODES" and m.node_group and "smooth by angle" in m.node_group.name.lower():
            t = "SMOOTH_BY_ANGLE"
        return rank.get(t, len(rank))
    wanted = sorted(ob.modifiers, key=key)
    for i, m in enumerate(wanted):
        cur = list(ob.modifiers).index(m)
        if cur != i:
            ob.modifiers.move(cur, i)
    return ob


def finish(ob, bevel_part=True, tier=1.0):
    """The style's standard finish for a hard-surface part."""
    if bevel_part and not any(m.type == "BEVEL" for m in ob.modifiers):
        bevel(ob, tier=tier)
    if get("weighted_normal", True) and not any(m.type == "WEIGHTED_NORMAL" for m in ob.modifiers):
        weighted_normals(ob)
    smooth(ob)
    order_stack(ob)
    return ob


# ------------------------------------------------------------------ materials
def material(ob, name=None):
    """Assign a material by name (default: the first in the style's palette), reusing an existing one."""
    name = name or (get("material_palette") or ["Material"])[0]
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if ob.data.materials:
        ob.data.materials[0] = m
    else:
        ob.data.materials.append(m)
    return m


def palette():
    return list(get("material_palette") or [])


# ------------------------------------------------------------------ kit
def kit_files():
    d = os.path.join(HERE, "..", "kit")
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".blend")]


def kit_piece(piece_name, col=None, linked_data=True):
    """Append a kit piece by name (see references/kit-catalogue.md) and return the new object."""
    for path in kit_files():
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            hits = [n for n in src.objects if n == piece_name or n.split(".")[0] == piece_name]
            dst.objects = hits[:1]
        if dst.objects:
            ob = dst.objects[0]
            return link(ob, col)
    raise KeyError(f"kit piece {piece_name!r} not found in {kit_files()}")


# ------------------------------------------------------------------ uv
def texel_density(ob, texture=None):
    """Pixels per metre of the active UV map at the given (or style) texture size."""
    texture = texture or get("texture_size", 2048)
    me = ob.data
    if not me.uv_layers:
        return None
    uv = me.uv_layers.active.data
    a3 = auv = 0.0
    for p in me.polygons:
        a3 += p.area
        idx = list(p.loop_indices)
        pts = [uv[i].uv for i in idx]
        for k in range(1, len(pts) - 1):
            a, b, c = pts[0], pts[k], pts[k + 1]
            auv += abs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) / 2
    if a3 <= 0:
        return None
    sx = max(abs(s) for s in ob.scale)
    return math.sqrt(auv / a3) / sx * texture
