"""Builds your own kitbash insert library from code (every part modelled here, nothing downloaded):
  blender.exe -b --factory-startup --python build_inserts.py -- [library.blend] [--sheet out_dir]
Default library: stackkit.INSERT_LIB ($BSF_INSERT_LIB, or ~/blender_inserts/inserts.blend). Re-running rebuilds it.

Conventions (stackkit.insert relies on them): real size in metres, origin on the MOUNTING point, +Z out of the
mount (a nut's +Z points away from the face it sits on), modifiers applied, shade smooth with sharp edges over
30 deg. Material slots are plain slot names (Steel, SteelDark, PaintDark, Rubber, Brass). Sizes are ISO metric
where a real part exists (M8 nut 13 mm across flats); scale an insert to get other sizes.
Every part is built twice: full detail, and NAME_lo for games (stackkit.game_down swaps to it).
Catalogue (name, size, tris, mount) is written next to the library as inserts.json."""
import json, math, os, sys
import bpy, bmesh
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stackkit as S

MM = 0.001
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SHEET = args[args.index("--sheet") + 1] if "--sheet" in args else ""
LIB = next((a for a in args if a.endswith(".blend")), S.INSERT_LIB)
CAT = {}
LO = False      # set by main(): the "_lo" game pass (half the round segments, no knurl, 1-segment bevels)

# ------------------------------------------------------------------ helpers
def mat(name):
    return S.mat(name)


def link(bm, name, m):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    me.materials.append(mat(m))
    return ob


def lathe(profile, m, segs=48, name="lathe", rfunc=None, closed=False):
    """solid of revolution round Z from (r, z) points (start/end on the axis for a closed solid; or closed=True
    for a ring/tube whose profile loops back to its first point: washers, collars, flanges with a bore).
    rfunc(r, z, k, row) -> r lets a ring be displaced per vertex (knurl)."""
    if LO:
        segs, rfunc = max(8, segs // 2), None
    if closed:
        profile = list(profile) + [profile[0]]
    bm = bmesh.new(); rings = []
    for row, (r, z) in enumerate(profile):
        if r <= 1e-9:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            ring = []
            for k in range(segs):
                a = 2 * math.pi * k / segs
                rr = rfunc(r, z, k, row) if rfunc else r
                ring.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), z)))
            rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(a) == 1:
                bm.faces.new((a[0], b[k], b[k2]))
            elif len(b) == 1:
                bm.faces.new((a[k], b[0], a[k2]))
            else:
                bm.faces.new((a[k], b[k], b[k2], a[k2]))
    if closed:                                    # the repeated first ring: weld it onto the first
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-9)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(bm, name, m)


def prism(n, r, z0, z1, m, name="prism", rot=0.0):
    """n-sided prism (r = circumradius) from z0 to z1; a hex nut is prism(6, AF / sqrt(3)...)."""
    bm = bmesh.new()
    lo = [bm.verts.new((r * math.cos(rot + 2 * math.pi * k / n), r * math.sin(rot + 2 * math.pi * k / n), z0)) for k in range(n)]
    hi = [bm.verts.new((v.co.x, v.co.y, z1)) for v in lo]
    bm.faces.new(lo[::-1]); bm.faces.new(hi)
    for k in range(n):
        bm.faces.new((lo[k], lo[(k + 1) % n], hi[(k + 1) % n], hi[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(bm, name, m)


def box(sx, sy, sz, loc, m, name="box"):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx + loc[0], v.co.y * sy + loc[1], v.co.z * sz + loc[2]))
    return link(bm, name, m)


def extrude_profile(pts2d, y0, y1, m, name="profile"):
    """closed polygon in XZ (list of (x, z)), extruded along Y from y0 to y1."""
    bm = bmesh.new()
    a = [bm.verts.new((x, y0, z)) for x, z in pts2d]
    b = [bm.verts.new((x, y1, z)) for x, z in pts2d]
    bm.faces.new(a); bm.faces.new(b[::-1]); n = len(a)
    for k in range(n):
        bm.faces.new((a[k], b[k], b[(k + 1) % n], a[(k + 1) % n]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(bm, name, m)


def apply(ob):
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
        for md in list(ob.modifiers):
            bpy.ops.object.modifier_apply(modifier=md.name)
    return ob


def boolean(target, other, op="DIFFERENCE", keep_slot=False):
    """apply a boolean now and delete `other`. keep_slot=True: the cut walls wear other's slot."""
    apply(other)
    b = target.modifiers.new("b", "BOOLEAN"); b.operation, b.solver, b.object = op, "EXACT", other
    if keep_slot:
        b.material_mode = "TRANSFER"
    apply(target)
    bpy.data.objects.remove(other, do_unlink=True)
    return target


def bevel(ob, w, segs=2, angle=40):
    S.bevel(ob, w, 1 if LO else segs, 0.6, angle); return apply(ob)


def join(objs, name):
    objs = [o for o in objs if o]
    for o in objs:
        apply(o)
    with bpy.context.temp_override(active_object=objs[0], selected_editable_objects=objs, selected_objects=objs):
        bpy.ops.object.join()
    ob = objs[0]; ob.name = name; ob.data.name = name
    return ob


def finish(ob, name, size_note, mount):
    """weld, smooth by angle 30 (sharp marks), merge duplicate slots, catalogue."""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    for f in bm.faces:
        f.smooth = True
    lim = math.radians(30)
    for e in bm.edges:
        e.smooth = not (e.is_manifold and e.calc_face_angle(0.0) > lim) and e.is_manifold
    bm.to_mesh(ob.data); bm.free()
    me = ob.data; first, remap = {}, []
    for i, m in enumerate(me.materials):
        first.setdefault(m.name, i); remap.append(first[m.name])
    for p in me.polygons:
        p.material_index = remap[p.material_index]
    used = sorted(set(p.material_index for p in me.polygons))
    keep = [me.materials[i] for i in used]; idx = {u: n for n, u in enumerate(used)}
    for p in me.polygons:
        p.material_index = idx[p.material_index]
    me.materials.clear()
    for m in keep:
        me.materials.append(m)
    name = name + ("_lo" if LO else "")
    ob.name = me.name = name
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    dims = [round(d / MM, 1) for d in ob.dimensions]
    CAT[name] = {"size": size_note, "mount": mount, "tris": tris, "dims_mm": dims, "slots": [m.name for m in keep]}
    print(f"INSERT {name:20s} tris {tris:6d} dims_mm {dims} slots {[m.name for m in keep]}")
    return ob

# ------------------------------------------------------------------ parts (millimetre maths, metre output)
def hex_body(af, h, z0, m, chamfer_top=True, chamfer_bottom=True, name="hex"):
    """hex prism across-flats af, with the 30 deg corner chamfer real nuts have (intersect with a chamfered round)."""
    rc = af / math.sqrt(3)
    hx = prism(6, rc * MM, z0 * MM, (z0 + h) * MM, m, name, rot=math.radians(30))
    # a cone at 30 deg to the face, starting on the face at 0.95 x AF/2 (ISO nut chamfer); extended 0.2 mm
    # past each face so the intersect never meets coplanar faces
    t30, rf, ro, e = math.tan(math.radians(30)), af * 0.475, rc + 0.6, 0.2
    z1 = z0 + h
    prof = [(0, z0 - e)]
    prof += [(rf - e / t30, z0 - e), (ro, z0 + (ro - rf) * t30)] if chamfer_bottom else [(ro, z0 - e)]
    prof += [(ro, z1 - (ro - rf) * t30), (rf - e / t30, z1 + e)] if chamfer_top else [(ro, z1 + e)]
    prof += [(0, z1 + e)]
    cone = lathe([(r * MM, z * MM) for r, z in prof], m, 48, "chamf")
    return boolean(hx, cone, "INTERSECT")


def p_hex_nut_m8():
    nut = hex_body(13, 6.5, 0, "Steel", name="hex_nut_m8")
    hole = lathe([(0, -1 * MM), (5.0 * MM, -1 * MM), (4.0 * MM, 0.4 * MM), (4.0 * MM, 6.1 * MM), (5.0 * MM, 7.5 * MM), (0, 7.5 * MM)], "SteelDark", 32, "hole")
    boolean(nut, hole, keep_slot=True)
    bevel(nut, 0.2 * MM, 1, 35)
    return finish(nut, "hex_nut_m8", "ISO 4032 M8, 13 AF x 6.5", "bearing face, +Z away from the surface")


def p_washer_m8():
    w = lathe([(r * MM, z * MM) for r, z in [(4.2, 0), (8.0, 0), (8.0, 1.6), (4.2, 1.6)]], "Steel", 32, "washer", closed=True)
    bevel(w, 0.25 * MM, 1, 40)
    return finish(w, "washer_m8", "ISO 7089 M8, 16 x 8.4 x 1.6", "bottom face, +Z up")


def p_bolt_head_m8():
    face = lathe([(r * MM, z * MM) for r, z in [(0, 0), (6.2, 0), (6.2, 0.5), (0, 0.5)]], "Steel", 40, "wface")
    head = hex_body(13, 5.3, 0.4, "Steel", chamfer_bottom=False, name="head")
    b = join([face, head], "bolt_head_m8"); bevel(b, 0.15 * MM, 1, 35)
    # head marking: two shallow dimples on top for scale read (8.8 grade dots)
    for x in (-2.2, 2.2):
        d = lathe([(0, 5.45 * MM), (0.7 * MM, 5.45 * MM), (0.7 * MM, 6.0 * MM), (0, 6.0 * MM)], "SteelDark", 12, "dot")
        d.location.x = x * MM; boolean(b, d, keep_slot=True)
    return finish(b, "bolt_head_m8", "ISO 4017 M8 head with washer face", "bearing face, +Z out")


def p_socket_cap_m6():
    def knurl(r, z, k, row):
        return r - (0.18 * MM if (k % 2 and row in (2, 3)) else 0)
    c = lathe([(r * MM, z * MM) for r, z in [(0, 0), (5.0, 0), (5.0, 0.4), (5.0, 5.0), (4.5, 6.0), (0, 6.0)]], "SteelDark", 60, "cap", knurl)
    sock = prism(6, 5 / math.sqrt(3) * MM, 2.6 * MM, 7 * MM, "Plastic", "sock")
    boolean(c, sock, keep_slot=True)
    cone = lathe([(0, 2.0 * MM), (1.6 * MM, 2.6 * MM), (0, 2.6 * MM)], "Plastic", 12, "tip")
    boolean(c, cone, keep_slot=True)
    bevel(c, 0.15 * MM, 1, 35)
    return finish(c, "socket_cap_m6", "ISO 4762 M6 head, d10 x 6, 5 mm hex", "bearing face, +Z out")


def p_pan_screw_m4():
    prof = [(0, 0), (3.5, 0)] + [(3.5 * math.cos(a), 0.6 + 2.2 * math.sin(a)) for a in [math.radians(t) for t in (0, 25, 50, 70, 85)]] + [(0, 2.8)]
    s = lathe([(r * MM, z * MM) for r, z in prof], "Steel", 40, "pan")
    slot = box(9 * MM, 1.1 * MM, 2.4 * MM, (0, 0, 2.95 * MM), "SteelDark", "slot")
    boolean(s, slot, keep_slot=True)
    return finish(s, "pan_screw_m4", "ISO 1580 M4 slotted pan, d7 x 2.8", "bearing face, +Z out")


def p_rivet_dome_5():
    prof = [(0, 0), (4.0, 0)] + [(4.0 * math.cos(a), 2.5 * math.sin(a)) for a in [math.radians(t) for t in (10, 30, 50, 70, 85)]] + [(0, 2.5)]
    r = lathe([(a * MM, b * MM) for a, b in prof], "Steel", 32, "rivet")
    return finish(r, "rivet_dome_5", "5 mm dome rivet, head d8 x 2.5", "bearing face, +Z out")


def p_knurled_collar_30():
    R, H, d = 15.0, 20.0, 0.45
    rows = [(R - 0.6, 0), (R, 0.6), (R, 3.5), (R - 0.6, 4.0), (R - 0.6, 4.6)]
    nk = 2 if LO else 14
    rows += [(R, 4.6 + 10.8 * j / (nk - 1)) for j in range(nk)]
    rows += [(R - 0.6, 15.4), (R - 0.6, 16.0), (R, 16.5), (R, 19.4), (R - 0.6, 20.0)]
    prof = [(11.0, 0)] + rows + [(11.0, 20.0)]
    knurl_rows = range(6, 6 + nk)

    def knurl(r, z, k, row):
        return r - d * MM if (row in knurl_rows and (k + row) % 2) else r
    c = lathe([(r * MM, z * MM) for r, z in prof], "SteelDark", 96, "collar", knurl, closed=True)
    ss =lathe([(0, -1 * MM), (2.0 * MM, -1 * MM), (2.0 * MM, 6 * MM), (0, 6 * MM)], "Plastic", 16, "setscrew")
    ss.rotation_euler = (0, math.radians(90), 0); ss.location = (R * MM - 2 * MM, 0, 2.0 * MM)
    boolean(c, ss, keep_slot=True)
    return finish(c, "knurled_collar_30", "d30 x 20 collar, bore 22, diamond knurl band, M4 set screw", "bottom face, +Z along the shaft")


def p_coil_spring_12():
    R, wr, turns = 5.2, 0.8, 7
    pts, steps = [], 12 if LO else 24
    for i in range(turns * steps + 1):
        t = i / steps
        if t < 1:
            z = wr + t * 1.7                                   # closed (squared) end turns
        elif t > turns - 1:
            z = wr + 1.7 + (turns - 2) * 4.0 + (t - (turns - 1)) * 1.7
        else:
            z = wr + 1.7 + (t - 1) * 4.0
        a = 2 * math.pi * t
        pts.append(Vector((R * math.cos(a) * MM, R * math.sin(a) * MM, z * MM)))
    cu = bpy.data.curves.new("spring", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = wr * MM; cu.bevel_resolution = 1 if LO else 2
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for p, v in zip(sp.points, pts):
        p.co = (*v, 1)
    ob = bpy.data.objects.new("spring", cu); bpy.context.collection.objects.link(ob); cu.materials.append(mat("Steel"))
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
        bpy.ops.object.convert(target="MESH")
    ob = bpy.data.objects["spring"]
    return finish(ob, "coil_spring_12", f"d{2*(R+wr):.0f} x {ob.dimensions.z/MM:.0f} compression spring, 1.6 wire, squared ends", "bottom end, +Z along the axis")


def p_pipe_flange_25():
    prof = [(12.5, 0), (30, 0), (30, 8), (21, 8), (20, 9.5), (16, 9.5), (14.5, 12), (13.5, 28), (12.5, 28)]
    f = lathe([(r * MM, z * MM) for r, z in prof], "PaintDark", 64, "flange", closed=True)
    bevel(f, 0.4 * MM, 2, 35)
    parts = [f]
    for k in range(4):
        ang = math.radians(45 + 90 * k); x, y = 23 * MM * math.cos(ang), 23 * MM * math.sin(ang)
        h = lathe([(0, -1 * MM), (3.3 * MM, -1 * MM), (3.3 * MM, 9 * MM), (0, 9 * MM)], "SteelDark", 20, "bh")
        h.location = (x, y, 0); boolean(f, h, keep_slot=True)
        nut = hex_body(10, 5, 8, "Steel", chamfer_bottom=False, name="fnut"); nut.location = (x, y, 0)
        stud = lathe([(0, 8 * MM), (2.5 * MM, 8 * MM), (2.5 * MM, 15 * MM), (2.0 * MM, 15.5 * MM), (0, 15.5 * MM)], "Steel", 16, "stud")
        stud.location = (x, y, 0); parts += [nut, stud]
    j = join(parts, "pipe_flange_25")
    return finish(j, "pipe_flange_25", "d60 x 8 flange, 25 mm pipe socket, 4 x M5 studs + nuts on PCD 46", "flange back face, +Z along the pipe")


def p_clevis_bracket_40():
    base = box(40 * MM, 30 * MM, 5 * MM, (0, 0, 2.5 * MM), "PaintDark", "base")
    bevel(base, 2.5 * MM, 3, 40)
    lug_pts = [(-9.0, 4.0), (9.0, 4.0), (9.0, 22.0)] + [(9 * math.cos(math.radians(a)), 22 + 9 * math.sin(math.radians(a))) for a in range(15, 180, 15)] + [(-9.0, 22.0)]
    lugs = []
    for y in (-9.5, 4.5):
        lg = extrude_profile([(x * MM, z * MM) for x, z in lug_pts], y * MM, (y + 5) * MM, "PaintDark", "lug")
        lugs.append(lg)
    b = join([base] + lugs, "clevis")
    u = b.modifiers.new("w", "WELD"); apply(b)
    pin = lathe([(0, -17 * MM), (4 * MM, -17 * MM), (4 * MM, 17 * MM), (0, 17 * MM)], "SteelDark", 24, "pinhole")
    pin.rotation_euler = (math.radians(90), 0, 0); pin.location.z = 22 * MM; boolean(b, pin, keep_slot=True)
    for x in (-14, 14):
        cs = lathe([(0, -1 * MM), (2.2 * MM, -1 * MM), (2.2 * MM, 3.2 * MM), (4.2 * MM, 5.2 * MM), (0, 5.2 * MM)], "SteelDark", 20, "cs")
        cs.location.x = x * MM; boolean(b, cs, keep_slot=True)
    bevel(b, 0.5 * MM, 2, 35)
    pinb = lathe([(r * MM, z * MM) for r, z in [(0, -13), (6, -13), (6, -11), (3.9, -11), (3.9, 12), (3.4, 12.6), (0, 12.6)]], "Steel", 24, "pin")
    pinb.rotation_euler = (math.radians(-90), 0, 0); pinb.location.z = 22 * MM
    clip = lathe([(r * MM, z * MM) for r, z in [(3.0, 10.6), (5.5, 10.6), (5.5, 11.6), (3.0, 11.6)]], "SteelDark", 24, "eclip")
    clip.rotation_euler = (math.radians(-90), 0, 0); clip.location.z = 22 * MM
    screws = []
    for x in (-14, 14):
        sc = lathe([(0, 2.9 * MM), (4.1 * MM, 4.9 * MM), (4.1 * MM, 5.1 * MM), (0, 5.1 * MM)], "Steel", 20, "fh"); sc.location.x = x * MM
        hx = prism(6, 1.5 * MM, 4.4 * MM, 5.5 * MM, "Plastic", "fhs"); hx.location.x = x * MM
        boolean(sc, hx, keep_slot=True); screws.append(sc)
    j = join([b, pinb, clip] + screws, "clevis_bracket_40")
    return finish(j, "clevis_bracket_40", "40 x 30 base, twin lugs, d8 pin with e-clip, 2 x M4 countersunk", "base bottom, +Z up; pin axis along Y at z 22")


def p_pipe_clamp_20():
    R, t, wdt = 10.25, 1.5, 12.0
    cl = []                                                     # strap centreline in XZ
    cl += [(-21.0, t / 2), (-R - t / 2 - 1.5, t / 2)]
    cl += [(-(R + t / 2), t / 2 + 1.5)]
    cl += [((R + t / 2) * math.cos(math.radians(a)), R + (R + t / 2) * math.sin(math.radians(a))) for a in range(180, -1, -10)]
    cl += [(R + t / 2, t / 2 + 1.5), (R + t / 2 + 1.5, t / 2), (21.0, t / 2)]
    cl = [p for i, p in enumerate(cl) if i == 0 or (Vector(p) - Vector(cl[i - 1])).length > 0.05]
    def off(i, s):
        p = Vector(cl[i]); a = Vector(cl[max(i - 1, 0)]); b = Vector(cl[min(i + 1, len(cl) - 1)])
        tng = (b - a).normalized(); n = Vector((-tng.y, tng.x))
        return tuple(p + n * s)
    outer = [off(i, t / 2) for i in range(len(cl))]; inner = [off(i, -t / 2) for i in range(len(cl))]
    poly = outer + inner[::-1]
    poly = [(x, max(z, 0.0)) for x, z in poly]
    st = extrude_profile([(x * MM, z * MM) for x, z in poly], -wdt / 2 * MM, wdt / 2 * MM, "Galvanized", "strap")
    bevel(st, 0.3 * MM, 2, 40)
    for x in (-16.5, 16.5):
        h = lathe([(0, -1 * MM), (2.3 * MM, -1 * MM), (2.3 * MM, 4 * MM), (0, 4 * MM)], "SteelDark", 16, "h"); h.location.x = x * MM
        boolean(st, h, keep_slot=True)
    parts = [st]
    for x in (-16.5, 16.5):
        prof = [(0, t), (3.5, t)] + [(3.5 * math.cos(math.radians(a)), t + 0.6 + 2.2 * math.sin(math.radians(a))) for a in (0, 30, 60, 85)] + [(0, t + 2.8)]
        sc = lathe([(r * MM, z * MM) for r, z in prof], "Steel", 24, "ps"); sc.location.x = x * MM
        sl = prism(4, 1.0 * MM, (t + 2.0) * MM, (t + 3.5) * MM, "SteelDark", "x1", rot=math.radians(45)); sl.scale = (4.5, 0.5, 1); sl.location.x = x * MM
        boolean(sc, sl, keep_slot=True); parts.append(sc)
    j = join(parts, "pipe_clamp_20")
    return finish(j, "pipe_clamp_20", "saddle clamp for a 20 mm pipe, 12 wide, 2 x M4 pan screws", "mount face, +Z up; pipe axis along Y at z 10.25")


def p_hose_coupler_12():
    hx = hex_body(14, 8, 0, "Brass", name="hx")
    prof = [(0, 7.9), (7.6, 7.9), (8.0, 8.4), (8.0, 11), (7.4, 11), (7.4, 11.8), (8.0, 11.8), (8.0, 17.5), (7.6, 18), (5.0, 18),
            (5.0, 19), (6.2, 20), (5.0, 23), (6.2, 24), (5.0, 27), (6.2, 28), (4.6, 31), (0, 31)]
    body = lathe([(r * MM, z * MM) for r, z in prof], "Brass", 40, "cpl")
    j = join([hx, body], "hose_coupler_12")
    bore = lathe([(0, -1 * MM), (3.2 * MM, -1 * MM), (3.2 * MM, 32 * MM), (0, 32 * MM)], "SteelDark", 20, "bore")
    boolean(j, bore, keep_slot=True)
    bevel(j, 0.15 * MM, 1, 35)
    return finish(j, "hose_coupler_12", "brass quick coupler, 14 AF hex, barbed tail for 10 mm hose", "hex bottom face, +Z along the hose")


def p_cable_gland_m16():
    lock = hex_body(22, 3, 0, "Plastic", name="lock")
    body = hex_body(20, 6, 3, "Plastic", chamfer_bottom=False, name="body")
    cap = lathe([(r * MM, z * MM) for r, z in [(0, 9), (9.5, 9), (9.5, 11), (8.6, 13.5), (6.5, 15.5), (4.6, 16.2), (0, 16.2)]], "Plastic", 40, "cap")
    grip = lathe([(r * MM, z * MM) for r, z in [(0, 15.8), (4.4, 15.8), (4.4, 16.8), (0, 16.8)]], "Rubber", 24, "seal")
    cable = lathe([(r * MM, z * MM) for r, z in [(0, 15), (4.0, 15), (4.0, 40), (0, 40)]], "WireBlack", 20, "cable")
    j = join([lock, body, cap, grip, cable], "cable_gland_m16")
    return finish(j, "cable_gland_m16", "M16 cable gland, 22 AF locknut, 8 mm cable stub 25 long", "panel face, +Z out along the cable")


PARTS = [p_hex_nut_m8, p_washer_m8, p_bolt_head_m8, p_socket_cap_m6, p_pan_screw_m4, p_rivet_dome_5, p_knurled_collar_30,
         p_coil_spring_12, p_pipe_flange_25, p_clevis_bracket_40, p_pipe_clamp_20, p_hose_coupler_12, p_cable_gland_m16]


def contact_sheet(objs, out, fname="inserts_sheet.png"):
    sc = bpy.context.scene; sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading; sh.light = "STUDIO"; sh.color_type = "MATERIAL"; sh.show_cavity = True; sh.cavity_type = "BOTH"
    sc.render.resolution_x, sc.render.resolution_y = 1800, 1200
    sheet = {"Steel": (0.62, 0.63, 0.65), "SteelDark": (0.3, 0.3, 0.32), "PaintDark": (0.2, 0.21, 0.23),
             "Plastic": (0.17, 0.17, 0.18), "Rubber": (0.12, 0.12, 0.12), "WireBlack": (0.14, 0.14, 0.14),
             "Galvanized": (0.7, 0.71, 0.72), "Brass": (0.78, 0.58, 0.22), "Label": (0.9, 0.9, 0.88)}
    for m in bpy.data.materials:
        m.diffuse_color = (*sheet.get(m.name, (0.5, 0.5, 0.5)), 1)
    cols, cell = 5, 1.0
    shown = []
    for i, o in enumerate(objs):
        d = o.copy(); d.data = o.data; sc.collection.objects.link(d); shown.append(d)
        s = 0.7 / max(o.dimensions); d.scale = (s, s, s)
        r, c = divmod(i, cols)
        d.location = (c * cell, -r * cell * 1.35, 0)
        d.rotation_euler = (0, 0, math.radians(20))
        t = bpy.data.curves.new("t", "FONT"); t.body = o.name; t.size = 0.075; t.align_x = "CENTER"
        to = bpy.data.objects.new("t", t); sc.collection.objects.link(to); to.location = (c * cell, -r * cell * 1.35 - 0.5, 0)
        t.materials.append(mat("Label"))
    for o in objs:
        o.hide_render = True
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    rows = (len(objs) - 1) // cols + 1
    ctr = Vector(((cols - 1) * cell / 2, -(rows - 1) * cell * 1.35 / 2, 0.1))
    cam.data.type = "ORTHO"; cam.data.ortho_scale = cols * cell * 1.05
    cam.location = ctr + Vector((0, -6, 6)); cam.rotation_euler = (math.radians(45), 0, 0)
    sc.render.filepath = os.path.join(out, fname); bpy.ops.render.render(write_still=True)
    for d in shown:
        bpy.data.objects.remove(d)
    for o in [o for o in sc.objects if o.type in ("FONT", "CAMERA")]:
        bpy.data.objects.remove(o)
    for o in objs:
        o.hide_render = False


def main():
    global LO
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objs = []
    for LO in (False, True):
        for fn in PARTS:
            before = set(bpy.data.objects)
            ob = fn(); objs.append(ob)
            for o in set(bpy.data.objects) - before - {ob}:     # helpers a part forgot to delete
                print("LEFTOVER", fn.__name__, o.name); bpy.data.objects.remove(o)
    os.makedirs(os.path.dirname(LIB), exist_ok=True)
    blocks = set(objs) | {o.data for o in objs} | {m for o in objs for m in o.data.materials if m}
    bpy.data.libraries.write(LIB, blocks, fake_user=True)
    json.dump(CAT, open(os.path.splitext(LIB)[0] + ".json", "w"), indent=1)
    print("LIBRARY", LIB, len(objs), "parts", sum(c["tris"] for c in CAT.values()), "tris total")
    if SHEET:
        contact_sheet([o for o in objs if not o.name.endswith("_lo")], SHEET)
        contact_sheet([o for o in objs if o.name.endswith("_lo")], SHEET, "inserts_sheet_lo.png")


main()
