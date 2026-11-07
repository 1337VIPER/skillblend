"""Live modifier-stack kit for headless Blender: the non-destructive hard-surface techniques studied in a
downloaded sci-fi prop .blend (see the modifier-stacks module). A bake-as-you-go kit applies each step as it
goes; here every part keeps its stack live until game_down() + bake() + your exporter.

Techniques (the stack order is the technique; keep it):
  hybrid()       Bevel (angle 30, 3 segs, profile 0.7) -> Subsurf -> [booleans] -> smooth by angle.
                 The bevel's segments are the subsurf's support loops: soft, tight edges with no loop cuts.
  shell()        Mirror (clip) -> Solidify (offset -1, even, rim) -> Bevel: armour plates and covers from an
                 open surface; constant thickness, the rim takes the bevel.
  cutter()       live Boolean DIFFERENCE from a cutter that carries its own (wider) bevel, kept in a hidden
                 "Cutters" collection shown as wire. The boolean sits AFTER the subsurf so the cut stays crisp.
  mirror_about() Mirror around another object's axis (an off-centre part mirrored round the main body's axis).
  skin_cable()   vertex/edge skeleton -> Mirror -> Skin -> Subsurf: pipes and cage rails with clean joints.
  curve_wire()   Bezier through points with a round profile: wire wraps and lashings.
  glass_shell()  thin Solidify on a hybrid form, glass slot, an inner "liquid" copy a little smaller.
  insert()       drop a part from your own kitbash library (inserts.blend); insert_save() adds one.
Sizes come from tiers(D), D = the main body's diameter or width (ratios measured on the studied prop).
Metres; materials by slot name. The insert library path is $BSF_INSERT_LIB, or ~/blender_inserts/inserts.blend."""
import math, os
import bpy, bmesh
from mathutils import Vector, Quaternion

def mat(name):
    return bpy.data.materials.get(name) or bpy.data.materials.new(name)

INSERT_LIB = os.environ.get("BSF_INSERT_LIB") or os.path.join(os.path.expanduser("~"), "blender_inserts", "inserts.blend")
CUTTERS = "Cutters"

# ---------------------------------------------------------------- proportions
def tiers(D):
    """edge and thickness ladder as fractions of the main body's size D (studied prop: D = 2.11 units).
    Only three bevel widths on the whole model: one edge language everywhere."""
    return {
        "fine":   0.0036 * D,   # small parts, lips, caps                   (studied 0.0077)
        "mid":    0.0082 * D,   # plates, rails, covers                     (0.0173)
        "cutter": 0.011 * D,    # bevel ON the cutter = the chamfer of a cut (0.0231)
        "shell":  0.031 * D,    # plate / cover thickness                   (0.065)
        "glass":  0.0056 * D,   # glass wall                                (0.012)
        "gap":    0.008 * D,    # parting gap between plate and body
    }

# ---------------------------------------------------------------- stacks
def _mod(ob, name, kind):
    return ob.modifiers.get(name) or ob.modifiers.new(name, kind)


def bevel(ob, width, segs=3, profile=0.7, angle=30, name="Bevel"):
    b = _mod(ob, name, "BEVEL")
    b.width, b.segments, b.profile = width, segs, profile
    b.limit_method, b.angle_limit = "ANGLE", math.radians(angle)
    b.miter_outer = "MITER_SHARP"
    b.use_clamp_overlap = False          # studied file: off, so every edge gets the same width; keep widths < half the thinnest wall
    return b


def subsurf(ob, levels=2):
    s = _mod(ob, "Subsurf", "SUBSURF")
    s.levels = s.render_levels = levels
    s.use_limit_surface = True
    ob["hs_subd"] = levels               # game_down() reads this
    return s


def smooth(ob, angle=30):
    """shade smooth with sharp edges over `angle` (an 'Auto Smooth' node, last in every stack)."""
    for p in ob.data.polygons if ob.type == "MESH" else []:
        p.use_smooth = True
    try:
        with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                       selected_editable_objects=[ob]):
            bpy.ops.object.modifier_add_node_group(asset_library_type="ESSENTIALS", asset_library_identifier="",
                                                   relative_asset_identifier="geometry_nodes/smooth_by_angle.blend/NodeTree/Smooth by Angle")
        m = ob.modifiers[-1]
        for it in m.node_group.interface.items_tree:
            if getattr(it, "name", "") == "Angle":
                m[it.identifier] = math.radians(angle)
        m.name = "Smooth"
    except Exception:                    # headless --factory-startup has no Essentials library (seen 5.2):
                                         # mark sharp on the base; export re-marks at SHARP_ANGLE + weighted normals
        _mark_sharp(ob, angle)
    return ob


def _mark_sharp(ob, angle):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    lim = math.radians(angle)
    for e in bm.edges:
        e.smooth = not (e.is_manifold and e.calc_face_angle(0.0) > lim)
    bm.to_mesh(ob.data); bm.free()


def _keep_last(ob, name):
    """move modifier `name` to the end of the stack (smooth must stay last)."""
    m = ob.modifiers.get(name)
    if m:
        ob.modifiers.move(list(ob.modifiers).index(m), len(ob.modifiers) - 1)


def hybrid(ob, width, segs=3, profile=0.7, angle=30, levels=2):
    """Bevel -> Subsurf: the main stack for turned hero forms (cylinders, tanks, caps)."""
    bevel(ob, width, segs, profile, angle)
    subsurf(ob, levels)
    return smooth(ob)


def shell(ob, thickness, width, mirror_x=True, angle=30):
    """open surface -> Mirror(clip) -> Solidify(inward, even, rim) -> Bevel: covers, armour, cowlings.
    Model the outer surface only (one side when mirror_x), normals out."""
    if mirror_x:
        m = _mod(ob, "Mirror", "MIRROR"); m.use_axis = (True, False, False); m.use_clip = True
    s = _mod(ob, "Solidify", "SOLIDIFY")
    s.thickness, s.offset, s.use_even_offset, s.use_quality_normals, s.use_rim = thickness, -1, True, True, True
    bevel(ob, width, 3, 0.7, angle)
    return smooth(ob)


def _cutter_coll():
    c = bpy.data.collections.get(CUTTERS)
    if not c:
        c = bpy.data.collections.new(CUTTERS); bpy.context.scene.collection.children.link(c)
    return c


def cutter(cut_ob, targets, width=0.0, slot=None):
    """live boolean: cut_ob (own bevel `width` = the chamfer the cut leaves) subtracted from each target.
    The boolean goes after the target's subsurf; the cutter moves to the hidden Cutters collection as wire.
    slot: material the cut walls wear (the cutter's slot is transferred), e.g. 'Light' for glowing grooves."""
    targets = targets if isinstance(targets, (list, tuple)) else [targets]
    if width > 0:
        bevel(cut_ob, width)
    if slot:
        cut_ob.data.materials.clear(); cut_ob.data.materials.append(mat(slot))
    for c in list(cut_ob.users_collection):
        c.objects.unlink(cut_ob)
    _cutter_coll().objects.link(cut_ob)
    cut_ob.display_type = "WIRE"; cut_ob.hide_render = True; cut_ob.hide_set(True)
    for t in targets:
        b = t.modifiers.new("Cut_" + cut_ob.name, "BOOLEAN")
        b.operation, b.solver, b.object = "DIFFERENCE", "EXACT", cut_ob
        if slot:
            b.material_mode = "TRANSFER"
        _keep_last(t, "Smooth")
    return cut_ob


def mirror_about(ob, pivot, axes=(True, False, False)):
    """mirror an off-centre part round another object's local axes (a tank mirrored round the main cylinder)."""
    m = _mod(ob, "MirrorAbout", "MIRROR"); m.use_axis = axes; m.mirror_object = pivot
    _keep_last(ob, "Smooth")
    return ob


def skin_cable(points, radius, m, edges=None, mirror_x=False, levels=2, name="cable"):
    """pipes / cage rails: a vertex skeleton through `points` (edges default to a chain) -> Skin -> Subsurf.
    Branches are fine (pass edges); every vertex gets `radius` (a float or one per point)."""
    me = bpy.data.meshes.new(name)
    edges = edges or [(i, i + 1) for i in range(len(points) - 1)]
    me.from_pydata([Vector(p) for p in points], edges, [])
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    me.materials.append(mat(m))
    if mirror_x:
        mm = ob.modifiers.new("Mirror", "MIRROR"); mm.use_axis = (True, False, False); mm.use_clip = True
    sk = ob.modifiers.new("Skin", "SKIN"); sk.use_smooth_shade = True; sk.branch_smoothing = 0
    rs = radius if isinstance(radius, (list, tuple)) else [radius] * len(points)
    for sv, r in zip(me.skin_vertices[0].data, rs):
        sv.radius = (r, r)
    me.skin_vertices[0].data[0].use_root = True
    subsurf(ob, levels)
    return ob


def curve_wire(points, r, m, res=4, cyclic=False, name="wire"):
    """wire wrap / lashing: a smooth Bezier through points with a round profile of radius r."""
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "3D"
    cu.bevel_depth, cu.bevel_resolution, cu.resolution_u, cu.use_fill_caps = r, res, 12, True
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(points) - 1); sp.use_cyclic_u = cyclic
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p; bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new(name, cu); bpy.context.collection.objects.link(ob)
    cu.materials.append(mat(m))
    return ob


def helix(center, radius, pitch, turns, axis="Z", steps_per_turn=16):
    """points for curve_wire: a coil (springs, wire wrapped round a nozzle)."""
    pts = []
    for i in range(int(turns * steps_per_turn) + 1):
        a = 2 * math.pi * i / steps_per_turn
        x, y, z = radius * math.cos(a), radius * math.sin(a), pitch * i / steps_per_turn
        p = {"Z": (x, y, z), "Y": (x, z, y), "X": (z, x, y)}[axis]
        pts.append(Vector(center) + Vector(p))
    return pts


def glass_shell(ob, wall, width, liquid=0.0, liquid_slot="Liquid"):
    """glass vessel: hybrid form + thin inward Solidify, glass slot; liquid > 0 adds an inner copy filled to
    that fraction of the height (parented, so it moves with the vessel)."""
    hybrid(ob, width)
    s = _mod(ob, "Solidify", "SOLIDIFY"); s.thickness, s.offset, s.use_rim = wall, -1, True
    _keep_last(ob, "Smooth")
    ob.data.materials.clear(); ob.data.materials.append(mat("Glass"))
    if liquid > 0:
        lq = ob.copy(); lq.data = ob.data.copy(); lq.name = ob.name + "_liquid"
        bpy.context.collection.objects.link(lq)
        for md in list(lq.modifiers):
            if md.type in ("SOLIDIFY", "BEVEL"):
                lq.modifiers.remove(md)
        bm = bmesh.new(); bm.from_mesh(lq.data)
        zs = [v.co.z for v in bm.verts]; z0, z1 = min(zs), max(zs); top = z0 + (z1 - z0) * liquid
        c = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
        for v in bm.verts:
            v.co = c + (v.co - c) * 0.97            # sits inside the wall
            v.co.z = min(v.co.z, top)
        bm.to_mesh(lq.data); bm.free()
        lq.data.materials.clear(); lq.data.materials.append(mat(liquid_slot))
        lq.parent = ob; lq.matrix_parent_inverse = ob.matrix_world.inverted()
    return ob

# ---------------------------------------------------------------- your own kitbash library
def insert_save(ob, name):
    """add one of YOUR parts (applied, origin at its mounting point, +Z out of the mount) to the insert library."""
    os.makedirs(os.path.dirname(INSERT_LIB), exist_ok=True)
    ob.name = name
    blocks = {ob, ob.data, *[m for m in ob.data.materials if m]}
    loaded, aside = [], []
    if os.path.exists(INSERT_LIB):
        with bpy.data.libraries.load(INSERT_LIB) as (src, _):
            keep = [n for n in src.objects if n != name]
        if len(keep) < len(src.objects):
            print("INSERT replaced", name)
        for n in keep:                                # session objects with a library name step aside,
            o = bpy.data.objects.get(n)               # so the loaded parts keep their exact names
            if o:
                o.name = n + "__hs_aside"; aside.append((o, n))
        with bpy.data.libraries.load(INSERT_LIB) as (src, dst):
            dst.objects = keep
        loaded = [o for o in dst.objects if o]
        blocks |= set(loaded) | {o.data for o in loaded} | {m for o in loaded for m in o.data.materials if m}
    bpy.data.libraries.write(INSERT_LIB, blocks, fake_user=True)
    for o in loaded:
        bpy.data.objects.remove(o)
    for o, n in aside:
        o.name = n
    return INSERT_LIB


_lib_cache = {}


def insert(name, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0, normal=None, spin=0.0):
    """drop a library part (catalogue: inserts.json next to the library, or build_inserts.py). Its origin is the
    mounting point and +Z points out of the mount, so pass the surface point as loc and the surface normal as
    `normal` (spin = turn about that normal, radians); or a plain Euler `rot`. scale 1 = real size (an M8 nut);
    scale 0.75 makes it an M6. Each call returns a new object sharing the part's mesh."""
    if name not in _lib_cache:
        with bpy.data.libraries.load(INSERT_LIB) as (src, dst):
            if name not in src.objects:
                raise KeyError(f"no insert '{name}' in {INSERT_LIB}: {sorted(src.objects)}")
            dst.objects = [name]
        proto = dst.objects[0]; proto.name = "INS_" + name
        me = proto.data                                  # library slots arrive as "Steel.001" when the scene
        for i, m in enumerate(me.materials):             # already has "Steel": use the scene's, slot names are
            base = m.name.split(".")[0] if m and "." in m.name else None      # the Unreal material mapping
            if base:
                me.materials[i] = mat(base)
                if m.users == 0:
                    bpy.data.materials.remove(m)
        _lib_cache[name] = proto                         # not linked to the scene: a template
    ob = bpy.data.objects.new(name, _lib_cache[name].data)
    ob["hs_insert"] = name
    bpy.context.collection.objects.link(ob)
    ob.location, ob.scale = loc, (scale,) * 3
    if normal is not None:
        q = Vector((0, 0, 1)).rotation_difference(Vector(normal).normalized())
        ob.rotation_euler = (q @ Quaternion((0, 0, 1), spin)).to_euler()
    else:
        ob.rotation_euler = rot
    return ob

# ---------------------------------------------------------------- game bake-down
def tri_count(ob):
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg)
    me = ev.to_mesh(); n = sum(len(p.vertices) - 2 for p in me.polygons); ev.to_mesh_clear()
    return n


def game_down(objs=None, subd=0, curve_res=4, insert_lo=True, report=True):
    """turn the render stacks into game stacks before export: Subsurf -> `subd` (0: the bevel's
    3 segments + weighted normals carry the edge; 1 only on big curved hero forms, set ob['hs_game_subd']),
    curves -> meshes at `curve_res`, cutters stay as booleans (export applies them), and every insert swaps to
    its "_lo" library version (half the segments, knurl and fine grooves left to the normal map) unless the
    object has ob['hs_keep_hi'] (a hero part the camera gets close to). Prints tris before/after."""
    objs = objs or [o for o in bpy.context.scene.objects if o.type in ("MESH", "CURVE") and o.visible_get()]
    rows = []
    for o in objs:
        before = tri_count(o)
        nm = o.get("hs_insert")
        if nm and insert_lo and not o.get("hs_keep_hi") and not nm.endswith("_lo"):
            try:
                lo = insert(nm + "_lo"); o.data = lo.data; o["hs_insert"] = nm + "_lo"
                bpy.data.objects.remove(lo)
            except KeyError:
                print("GAMEDOWN no _lo version of", nm)
        if o.type == "CURVE":
            o.data.resolution_u = min(o.data.resolution_u, curve_res)
            o.data.bevel_resolution = min(o.data.bevel_resolution, 2)
        for md in list(o.modifiers):
            if md.type == "SUBSURF":
                lv = int(o.get("hs_game_subd", subd))
                if lv == 0:
                    o.modifiers.remove(md)            # level 0 counts as disabled and can't be applied
                else:
                    md.levels = md.render_levels = lv
        rows.append((o.name, before, tri_count(o)))
    if report:
        for n, a, b in sorted(rows, key=lambda r: -r[2]):
            print(f"GAMEDOWN {n:28s} {a:>9d} -> {b:>8d}")
        print("GAMEDOWN total", sum(r[1] for r in rows), "->", sum(r[2] for r in rows))
    return rows


def curves_to_mesh(objs=None):
    """an exporter that joins meshes only takes meshes: convert curve wires after game_down()."""
    for o in objs or [o for o in bpy.context.scene.objects if o.type == "CURVE" and o.visible_get()]:
        with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
            bpy.ops.object.convert(target="MESH")


def bake(objs=None):
    """apply every stack (booleans included, in stack order), convert curves to meshes, delete the cutters.
    Run after game_down() and before an export that joins EVERY mesh in the scene (cutters too)."""
    cut = set(bpy.data.collections[CUTTERS].objects) if CUTTERS in bpy.data.collections else set()
    curves_to_mesh()
    objs = objs or [o for o in bpy.context.scene.objects if o.type == "MESH" and o not in cut and o.visible_get()]
    for o in objs:
        if o.data.users > 1:                          # inserts share their part's mesh: export applies transforms
            o.data = o.data.copy()
        with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
            for md in list(o.modifiers):
                try:
                    bpy.ops.object.modifier_apply(modifier=md.name)
                except RuntimeError as e:             # a disabled modifier (boolean without a cutter...)
                    print("BAKE WARNING", o.name, md.name, e); o.modifiers.remove(md)
    for o in objs:                                    # parented children (liquid) keep their world place
        if o.parent:
            mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
    drop_cutters()
    return objs


def drop_cutters():
    """remove the cutter collection (after bake() applied the booleans)."""
    c = bpy.data.collections.get(CUTTERS)
    if c:
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(c)
