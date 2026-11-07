"""Car kit for headless Blender: build a car body the way a car modeller does (long quad loops that follow the
character lines, panels split with real gaps, glass inset behind a gasket, lights as recessed buckets, arches
cut and lined), then wheels, a driver rig and an Unreal vehicle export. Studied from a downloaded production-car
.blend (see the vehicles module); only techniques, no meshes. It builds ORIGINAL cars, never a copy of a real one.

Frame: metres, car faces +X (front at +X), Y = left, Z up, ground at z 0, origin on the ground under the
centre of the wheelbase. Material slots (plain names): CarPaint, Glass, Trim, Chrome, Gap, WheelWell,
LampHousing, LampLens, TailLens, Grille, Tire, Rim, Brake, Plate.

Pipeline (see SKILL.md):
  P = proportions(kind, length)          # dimensions from a measured ratio table
  D = design(P, ...)                     # the 2D curves: top line, belt line, floor, plan width
  body = loft_body(D)                    # stations -> quad shell (creased shoulder + rocker) -> subdiv
  wheel_arches(body, P) ; O = dlo(D) ; window(body, poly, ...) ; split_panel(...) ; lamp(...) ; grille(...)
  wheels = [wheel(P, ...) for each corner]
  rig = rig_car(body, wheels, doors)     # custom props steer / travel / door drive empties
  export_unreal_vehicle(...)             # skeletal FBX: root + 4 wheel bones, centimetre scene"""
import math, os, sys
import bpy, bmesh
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:                                 # stackkit sits in the same scripts/ folder
    sys.path.append(HERE)
try:
    import stackkit as S
except ImportError:
    S = None

PREVIEW = {"CarPaint": (0.55, 0.08, 0.06), "Glass": (0.05, 0.07, 0.09), "Trim": (0.03, 0.03, 0.03),
           "Chrome": (0.8, 0.8, 0.82), "Gap": (0.01, 0.01, 0.01), "WheelWell": (0.02, 0.02, 0.02),
           "LampHousing": (0.6, 0.6, 0.62), "LampLens": (0.92, 0.94, 0.95), "TailLens": (0.75, 0.05, 0.04),
           "Grille": (0.04, 0.04, 0.045), "Tire": (0.025, 0.025, 0.025), "Rim": (0.7, 0.71, 0.73),
           "Brake": (0.35, 0.35, 0.36), "Plate": (0.9, 0.9, 0.85), "Interior": (0.05, 0.05, 0.05)}


def mat(name):
    m = bpy.data.materials.get(name)
    if not m:
        m = bpy.data.materials.new(name); m.diffuse_color = (*PREVIEW.get(name, (0.5, 0.5, 0.5)), 1)
    return m


def link(bm, name, slots):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    for s in ([slots] if isinstance(slots, str) else slots):
        me.materials.append(mat(s))
    return ob


def slot(ob, name):
    """index of material slot `name` on ob (added if missing)."""
    for i, m in enumerate(ob.data.materials):
        if m and m.name == name:
            return i
    ob.data.materials.append(mat(name)); return len(ob.data.materials) - 1


def apply(ob):
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
        for md in list(ob.modifiers):
            bpy.ops.object.modifier_apply(modifier=md.name)
    return ob


BOOL_SELF = False   # exact solver self-intersection mode (slow; rarely needed)
BOOL_HOLES = False  # hole-tolerant exact solver: needed while cutting an open skin (hollow(..., thicken_now=False))
SKIN_CUT = False    # cutting an open skin: the solver treats the skin as a closed volume and leaves the cutter's own
                    # walls inside it (a door came out as a box reaching to the cab's centre, 2026-11-07); with this
                    # on, every face the cutter contributes is deleted after the cut, so cuts leave clean holes and
                    # INTERSECT leaves only the skin piece. Use with BOOL_HOLES; thicken() afterwards makes the walls.


def boolean(target, cutter, op="DIFFERENCE", transfer=True, keep=False):
    apply(cutter)
    if SKIN_CUT:
        cutter.data.materials.clear(); cutter.data.materials.append(mat("_cut"))
        for p in cutter.data.polygons:
            p.material_index = 0
        transfer = True
    b = target.modifiers.new("b", "BOOLEAN"); b.operation, b.solver, b.object = op, "EXACT", cutter
    if BOOL_SELF:
        b.use_self = True; b.use_hole_tolerant = True
    if BOOL_HOLES:
        b.use_hole_tolerant = True
    if transfer:
        b.material_mode = "TRANSFER"
    apply(target)
    if SKIN_CUT:
        ci = [i for i, m in enumerate(target.data.materials) if m and m.name == "_cut"]
        if ci:
            bm = bmesh.new(); bm.from_mesh(target.data)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in ci], context="FACES")
            bm.to_mesh(target.data); bm.free()
            target.data.materials.pop(index=ci[0])
    if not keep:
        bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def lerp_keys(keys, t, ease=True):
    """interpolate [(t, v), ...]: ease=True cosine-eases between keys (plan, belt, floor: no kinks);
    ease=False is straight between keys (the top line: windscreen and backlight are near-flat planes; an eased
    top line bows the windscreen into an S). The subdivision rounds the joints either way."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0) if t1 > t0 else 0
            if ease:
                u = 0.5 - 0.5 * math.cos(math.pi * u)
            return v0 + (v1 - v0) * u
    return keys[-1][1]


def top_at(D, t):
    return lerp_keys(D["top"], t, ease=False)

# ------------------------------------------------------------------ proportions
# Ratios of overall length L. "wedge_coupe" is measured from a studied car (side ortho render);
# the others are starting points from typical production cars of each class: check them against your own
# reference drawing before trusting a number.
KINDS = {
    #             wheelbase  wheel_d  width  height  front_oh  ground  belt   cowl   roof_front roof_rear  deck
    "wedge_coupe": (0.58,    0.143,   0.465, 0.267,  0.21,     0.035,  0.150, 0.180, 0.42,      0.66,      0.80),
    "hatchback":   (0.64,    0.155,   0.44,  0.36,   0.20,     0.035,  0.205, 0.230, 0.40,      0.86,      0.98),
    "saloon":      (0.59,    0.140,   0.39,  0.30,   0.20,     0.032,  0.180, 0.200, 0.38,      0.64,      0.80),
    "suv":         (0.60,    0.165,   0.41,  0.37,   0.19,     0.045,  0.235, 0.260, 0.38,      0.90,      0.97),
    # pickup: crew cab + separate bed, 3/4-ton class on 37 in tyres (from a test truck build). L is the body
    # (front fascia to bed tail, bumpers excluded). "ground" is the rocker line (lifted: above the tyre centre),
    # roof_rear_t / deck_t are the roof's rear edge and the cab back; the bed starts at bed_t (PICKUP below).
    "pickup":      (0.675,   0.163,   0.363, 0.384,  0.144,    0.138,  0.145, 0.311, 0.386,     0.657,     0.663),
}
TIRE_W = {"suv": 0.40, "pickup": 0.338}                  # tyre width / wheel diameter (cars 0.37)
PICKUP = {"bed_t": 0.672}                                # where the separate bed starts (t), cab back = deck_t


def proportions(kind="wedge_coupe", L=4.2, **over):
    """dimensions from the class ratio table; any key can be overridden (track=1.97 for a lifted truck whose
    tyres sit out under flares, wheel_r=0.47 to pin the tyre to a real size)."""
    wb, wd, w, h, foh, gc, belt, cowl, rf, rr, deck = KINDS[kind]
    P = {"kind": kind, "L": L, "wheelbase": wb * L, "wheel_r": wd * L / 2, "W": w * L, "H": h * L,
         "front_oh": foh * L, "ground": gc * L, "belt_h": belt * L, "cowl_t": cowl, "roof_front_t": rf,
         "roof_rear_t": rr, "deck_t": deck}
    if kind == "pickup":
        P.update(PICKUP)
    P["rear_oh"] = L - P["wheelbase"] - P["front_oh"]
    # origin under the middle of the wheelbase: front axle at +wb/2, rear at -wb/2, nose at +wb/2 + front_oh
    P["x_front_axle"], P["x_rear_axle"] = P["wheelbase"] / 2, -P["wheelbase"] / 2
    P["x_nose"], P["x_tail"] = P["wheelbase"] / 2 + P["front_oh"], -P["wheelbase"] / 2 - P["rear_oh"]
    P["tire_w"] = TIRE_W.get(kind, 0.37) * P["wheel_r"] * 2
    P["track"] = P["W"] - P["tire_w"] - 0.06          # wheel centre to centre across
    P.update(over)
    return P


def design(P, top=None, belt=None, floor=None, plan=None, tumblehome=0.80, shoulder=0.5, wedge=0.0):
    """the four curves that ARE the car, as [(t, value)] with t = 0 at the nose, 1 at the tail.
    top: roof/hood/deck height; belt: shoulder line; floor: underside; plan: half-width as a fraction of W/2.
    Defaults come from P's ratios; pass your own keys to make a different car. wedge tilts the belt line
    (positive = rising to the tail, the wedge look)."""
    L, H, g = P["L"], P["H"], P["ground"]
    bh = P["belt_h"] + g
    hood = bh + 0.06 * H
    D = dict(P)
    # nose low and the hood BELOW the belt at the front (the hood rises to meet the shoulder at the cowl);
    # crisp plan corners (0.88 -> 0.97 within 3% of the length) read as a car, eased 0.8 corners read as soap
    D["top"] = top or [(0.0, bh - 0.16 * H), (0.06, bh - 0.09 * H), (P["cowl_t"], bh + 0.03 * H), (P["roof_front_t"], H),
                       (P["roof_rear_t"], H * 0.985), (P["deck_t"], bh + 0.10 * H + wedge * H * 0.3), (1.0, bh + 0.05 * H)]
    D["belt"] = belt or [(0.0, bh - 0.19 * H), (0.06, bh - 0.12 * H), (P["cowl_t"], bh - 0.01 * H), (0.5, bh + wedge * 0.06 * H),
                         (0.94, bh + wedge * 0.12 * H), (1.0, bh - 0.02 * H)]
    D["floor"] = floor or [(0.0, g + 0.14 * H), (0.07, g), (0.93, g), (1.0, g + 0.15 * H)]
    D["plan"] = plan or [(0.0, 0.88), (0.03, 0.97), (0.10, 1.0), (0.90, 1.0), (0.97, 0.97), (1.0, 0.90)]
    D["tumblehome"], D["shoulder"] = tumblehome, shoulder
    return D


def x_at(D, t):
    return D["x_nose"] - t * D["L"]


def t_at(D, x):
    return (D["x_nose"] - x) / D["L"]

# ------------------------------------------------------------------ body
def station(D, t):
    """half cross-section at t: bottom centre -> rocker -> side -> shoulder -> greenhouse -> top centre.
    D["profile"] = "slab" switches to the square-body section (station_slab)."""
    if D.get("profile") == "slab":
        return station_slab(D, t)
    if D.get("profile") == "truck":
        return station_truck(D, t)
    w = lerp_keys(D["plan"], t) * D["W"] / 2
    zf, zb, zt = lerp_keys(D["floor"], t), lerp_keys(D["belt"], t), top_at(D, t)
    zb = min(zb, zt - 0.02); zf = min(zf, zb - 0.1)
    gh = zt - zb                                         # greenhouse height (tiny over the hood and deck)
    s = max(0.0, min(1.0, (gh - 0.08) / 0.30))           # 0 = hood/deck, 1 = full cabin
    th = 1 - (1 - D["tumblehome"]) * s                   # cabin sides lean in
    rnd = D["shoulder"]
    side_lo = zf + 0.30 * (zb - zf)
    return [(0.0, zf), (0.78 * w, zf), (0.96 * w, zf + 0.04), (w, side_lo), (w, zb - 0.08 * (zb - zf)),
            (w * (1 - 0.03 * rnd), zb),                                         # shoulder (creased)
            (w * (th - 0.02 - 0.05 * (1 - s)), zb + 0.30 * gh),
            (w * (th - 0.07) * (1 - 0.12 * (1 - s)), zb + 0.82 * gh),
            (w * (th - 0.07) * 0.62, zt - 0.004 * s), (0.0, zt)]


def loft_body(D, stations=40, subd=2, name="Body", t0=0.0, t1=1.0, cap_crease=0.3, cap_fill="ngon"):
    """quad shell lofted through `stations` cross-sections, mirrored, end-capped; shoulder and rocker loops
    creased so the subdivision keeps them crisp. Returns the applied mesh (slot 0 CarPaint).
    t0..t1 lofts only part of the length (a pickup's cab 0..deck_t; its bed with bed_box); D["creases"]
    ({section point index: crease}) replaces the car creases; cap_crease 0.8+ keeps square-body ends crisp.
    cap_fill "tri": constrained triangle fill for the end caps. A concave section (a square body's ledge, a hood
    bump) makes the n-gon cap fold under Catmull-Clark; hollow() then self-intersects and booleans wipe it."""
    bm = bmesh.new(); rings = []
    ts = [t0 + (t1 - t0) * (0.5 - 0.5 * math.cos(math.pi * i / (stations - 1))) for i in range(stations)]
    # D["key_ts"]: stations placed exactly on character lines across the body (cowl, windscreen header), so a
    # coarse LOW and a dense HIGH turn the same corner; D["ring_creases"] {t: crease} creases those rings
    ts = sorted(set([round(t, 6) for t in ts] + [k for k in D.get("key_ts", []) if t0 < k < t1]))
    for t in ts:
        half = station(D, t); x = x_at(D, t)
        ring = [(y, z) for y, z in half] + [(-y, z) for y, z in half[-2:0:-1]]
        rings.append([bm.verts.new((x, y, z)) for y, z in ring])
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for k in range(n):
            bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
    if cap_fill == "tri":
        for ring in (rings[0], rings[-1]):
            bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False,
                                    edges=[bm.edges.get((ring[k], ring[(k + 1) % n])) for k in range(n)])
    else:
        bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    cr = bm.edges.layers.float.get("crease_edge") or bm.edges.layers.float.new("crease_edge")
    half_n = len(station(D, 0.5))
    crease_idx = D.get("creases") or {5: 0.9, 2: 0.6}  # shoulder, rocker turn
    # D["crease_fn"](k, t, c) -> crease (opt-in): vary a section line's crease along the
    # length (t = the edge's mid station), e.g. soft character lines on the cab and bed, the original ones where a
    # separately built part has to match the section. Blender maps crease c to sharpness 10 c^2: at subd 2 a crease
    # of 0.45+ is a knife edge, 0.15-0.3 a soft 15-30 mm roll on a 10-40 mm control spacing.
    cfn = D.get("crease_fn")
    for k, c in crease_idx.items():
        for side in (k, n - k):
            for i, (a, b) in enumerate(zip(rings, rings[1:])):
                e = bm.edges.get((a[side % n], b[side % n]))
                if e:
                    e[cr] = cfn(k, 0.5 * (ts[i] + ts[i + 1]), c) if cfn else c
    for tk, c in D.get("ring_creases", {}).items():
        for i, t in enumerate(ts):
            if abs(t - tk) < 1e-6:
                for k in range(n):
                    e = bm.edges.get((rings[i][k], rings[i][(k + 1) % n]))
                    if e:
                        e[cr] = c
    # cap edges crisp-ish; cap_crease may be (front, rear) to soften one end only (a cab back rolling into the roof)
    ccs = cap_crease if isinstance(cap_crease, (tuple, list)) else (cap_crease, cap_crease)
    for ring, cc in zip((rings[0], rings[-1]), ccs):
        for k in range(n):
            e = bm.edges.get((ring[k], ring[(k + 1) % n]))
            if e:
                e[cr] = cc
    ob = link(bm, name, "CarPaint")
    s = ob.modifiers.new("Subsurf", "SUBSURF"); s.levels = s.render_levels = subd; s.use_creases = True
    apply(ob)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def _poly_prism(pts2d, plane, lo, hi, slot_name, name):
    """extrude a 2D polygon: plane 'XZ' (side view, along Y from lo to hi), 'XY' (plan, along Z) or 'YZ' (end view,
    points (y, z), along X from lo to hi)."""
    bm = bmesh.new()
    def P3(a, b, c):
        if plane == "YZ":
            return (c, a, b)
        return (a, c, b) if plane == "XZ" else (a, b, c)
    A = [bm.verts.new(P3(u, v, lo)) for u, v in pts2d]; B = [bm.verts.new(P3(u, v, hi)) for u, v in pts2d]
    bm.faces.new(A); bm.faces.new(B[::-1])
    for k in range(len(A)):
        bm.faces.new((A[k], B[k], B[(k + 1) % len(B)], A[(k + 1) % len(A)]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(bm, name, slot_name)


def offset_poly(pts, d):
    """grow a counter-clockwise or clockwise 2D polygon outward by d (mitred)."""
    n = len(pts); area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    sgn = 1 if area > 0 else -1
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        e0, e1 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n0, n1 = Vector((e0.y, -e0.x)) * sgn, Vector((e1.y, -e1.x)) * sgn
        m = (n0 + n1); m = m.normalized() if m.length > 1e-6 else n0
        cosh = max(0.3, m.dot(n0))
        out.append(tuple(p1 + m * d / cosh))
    return out


def split_panel(body, pts2d, plane="XZ", side=None, gap=0.004, name="Panel", depth=None):
    """cut a panel (door, hood, boot lid, fuel flap) out of the body with a real gap: the panel is the body inside
    the outline, the body loses the outline grown by `gap` (gap walls get the Gap slot). plane 'XZ' = outline
    drawn in the side view, cut through one side (side=+1 left / -1 right / None both); 'XY' = drawn in plan,
    cut from above down to `depth` below the top; 'YZ' = drawn in the end view (y, z), cut from the rear end
    (side=-1, tailgates) or the front end (side=+1) inward by `depth`. Returns the panel objects.
    On a hollow() shell the panel comes out as a skin with its own edge walls (the return flange)."""
    W = body.dimensions.y
    objs = []
    sides = [side] if side else [1, -1]
    if plane == "YZ":
        sides = [side or -1]
    for sd in sides:
        if plane == "XZ":
            lo, hi = (0.15 * W, W) if sd > 0 else (-W, -0.15 * W)
        elif plane == "YZ":
            xs = [(body.matrix_world @ v.co).x for v in body.data.vertices]
            lo, hi = ((min(xs) - 0.5, min(xs) + (depth or 0.25)) if sd < 0 else
                      (max(xs) - (depth or 0.25), max(xs) + 0.5))
        else:
            top = max((body.matrix_world @ v.co).z for v in body.data.vertices)
            lo, hi = top - (depth or 0.25), top + 0.5
        dup = body.copy(); dup.data = body.data.copy(); bpy.context.collection.objects.link(dup)
        cut_in = _poly_prism(pts2d, plane, lo, hi, "CarPaint", "pin")
        boolean(dup, cut_in, "INTERSECT", transfer=False)
        gap_c = _poly_prism(offset_poly(pts2d, gap), plane, lo - 0.01, hi + 0.01, "Gap", "pgap")
        boolean(body, gap_c, "DIFFERENCE", transfer=True)
        dup.name = dup.data.name = f"{name}_{'L' if sd > 0 else 'R'}" if plane == "XZ" else name
        objs.append(dup)
        if plane != "XZ":
            break
    return objs


def wheel_arches(body, P, clearance=1.12, well=None, lip=0.012, axles=None, outline=None, liner=0.0, z_cut=None,
                 segs=64):
    """cut each arch as a short cylinder from the outside in to the depth of the wheel well (not through the car,
    so you can't see through it), walls in WheelWell; a thin lip ring in Trim round the opening if lip > 0.
    axles: x positions to cut (default both; a pickup cuts the front on the cab and the rear on the bed).
    outline: the arch as an XZ polygon (dx, dz) round the axle centre instead of a circle (box flares want a
    chamfered box arch). liner > 0: a hollow() shell or a bed has nothing behind the cut, so a closed wheel-house
    liner (a strip round the arch plus the inner side plate, `liner` thick, above z_cut) is built per arch.
    Returns lips + liners."""
    R = P["wheel_r"] * clearance; W = P["W"]
    well = well or (P["tire_w"] + 0.10)
    zc = P["wheel_r"]
    out = []
    shape = outline or [(R * math.cos(2 * math.pi * k / segs), R * math.sin(2 * math.pi * k / segs)) for k in range(segs)]
    for x in (axles if axles is not None else (P["x_front_axle"], P["x_rear_axle"])):
        for sd in (1, -1):
            ob = _poly_prism([(x + a, zc + b) for a, b in shape], "XZ", sd * (W / 2 - well), sd * (W / 2 + 0.3),
                             "WheelWell", "arch")
            boolean(body, ob)
            if lip > 0 and outline is None:
                out.append(_arch_lip(x, sd * (W / 2 + 0.002 - lip / 2), zc, R, lip, sd))
            if liner > 0:
                out += _arch_liner(x, zc, shape, sd, W / 2 - 0.006, W / 2 - well, liner,
                                   z_cut if z_cut is not None else zc)
    return out


def _arch_liner(x, zc, shape, sd, y_out, y_in, t, z_cut):
    """wheel-house liner for one arch: the arch outline above z_cut (an open curve), grown t outward, swept from
    y_out to y_in, plus the inner side plate (outline + chord) t thick at y_in. Two closed solids that intersect."""
    n = len(shape)
    pts = [(x + a, zc + b) for a, b in shape]
    # rotate the closed outline so it starts below z_cut, then keep the run above it (clipped at z_cut)
    k0 = min(range(n), key=lambda i: pts[i][1])
    pts = pts[k0:] + pts[:k0]
    run = []
    for i in range(n):                                  # every edge once (n + 1 closed the run back across the
        p, q = Vector(pts[i]), Vector(pts[(i + 1) % n])   # arch bottom, a plate through the tyre, 2026-11-07)
        if p.y >= z_cut:
            run.append(p)
        if (p.y - z_cut) * (q.y - z_cut) < 0:
            run.append(p + (q - p) * ((z_cut - p.y) / (q.y - p.y)))
    if len(run) < 3:
        return []
    cx = sum(p.x for p in run) / len(run)
    if run[0].x < cx:                                   # run from front (+x) over the top to the rear
        run.reverse()
    def grown(i):
        a, b = run[max(i - 1, 0)], run[min(i + 1, len(run) - 1)]
        d = (b - a).normalized(); nrm = Vector((-d.y, d.x))
        if nrm.dot(run[i] - Vector((cx, zc))) < 0:
            nrm = -nrm
        return run[i] + nrm * t
    inner, outer = run, [grown(i) for i in range(len(run))]
    bm = bmesh.new()
    ys = (sd * y_out, sd * y_in)
    V4 = [[[bm.verts.new((p.x, y, p.y)) for y in ys] for p in (inner[i], outer[i])] for i in range(len(run))]
    for i in range(len(run) - 1):
        a, b = V4[i], V4[i + 1]
        for (r0, c0), (r1, c1) in (((0, 0), (0, 1)), ((0, 1), (1, 1)), ((1, 1), (1, 0)), ((1, 0), (0, 0))):
            bm.faces.new((a[r0][c0], a[r1][c1], b[r1][c1], b[r0][c0]))
    for e in (V4[0], V4[-1]):
        bm.faces.new((e[0][0], e[0][1], e[1][1], e[1][0]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    strip = link(bm, "arch_liner", "WheelWell")
    plate = _poly_prism([(p.x, p.y) for p in outer], "XZ", *sorted((sd * y_in, sd * (y_in - t))), "WheelWell",
                        "arch_plate")
    return [strip, plate]


def _arch_lip(x, y, z, R, t, sd, a0=-15, a1=195, segs=48):
    bm = bmesh.new(); rings = []
    prof = [(R, -t / 2), (R + t * 1.6, -t / 2), (R + t * 1.6, t / 2), (R, t / 2)]
    for i in range(segs + 1):
        a = math.radians(a0 + (a1 - a0) * i / segs)
        rings.append([bm.verts.new((x + r * math.cos(a), y + yy, z + r * math.sin(a))) for r, yy in prof])
    for A, B in zip(rings, rings[1:]):
        for k in range(4):
            bm.faces.new((A[k], A[(k + 1) % 4], B[(k + 1) % 4], B[k]))
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(bm, "arch_lip", "Trim")


def dlo(D, rail=0.05, sill=0.025, pillar=0.06, b_pillar_t=None, a_tip=0.05, c_end=0.55, n=14):
    """daylight openings from the design curves: side glass (XZ, split at a B pillar if b_pillar_t), windscreen and
    backlight (XY). rail = roof rail height above the glass, sill = paint above the belt, pillar = A/C pillar width
    in plan, a_tip = how far past the cowl the side glass starts (t), c_end = where between roof_rear and deck the
    side glass ends (0..1). Returns {"side": [poly...], "windscreen": poly, "backlight": poly, "z_min": z}."""
    t0 = D["cowl_t"] + a_tip
    t1 = D["roof_rear_t"] + c_end * (D["deck_t"] - D["roof_rear_t"])
    ts = [t0 + (t1 - t0) * i / (n - 1) for i in range(n)]
    def zb(t): return lerp_keys(D["belt"], t) + sill
    def ztop(t): return max(top_at(D, t) - rail, zb(t) + 0.01)
    def side_poly(ta, tb):
        tt = [ta + (tb - ta) * i / (n - 1) for i in range(n)]
        bottom = [(x_at(D, t), zb(t)) for t in tt]
        top = [(x_at(D, t), ztop(t)) for t in reversed(tt)]
        pts = bottom + top
        return [p for i, p in enumerate(pts) if i == 0 or (Vector(p) - Vector(pts[i - 1])).length > 1e-3]
    if b_pillar_t:
        sides = [side_poly(t0, b_pillar_t - 0.012), side_poly(b_pillar_t + 0.012, t1)]
    else:
        sides = [side_poly(t0, t1)]
    def half_w(t):
        st = station(D, t); return st[D.get("glass_pt", 7)][0] - pillar
    def plan_poly(ta, tb):
        tt = [ta + (tb - ta) * i / (n - 1) for i in range(n)]
        return [(x_at(D, t), half_w(t)) for t in tt] + [(x_at(D, t), -half_w(t)) for t in reversed(tt)]
    ws = plan_poly(D["cowl_t"] + 0.012, D["roof_front_t"] - 0.015)
    bl = plan_poly(D["roof_rear_t"] + 0.015, D["deck_t"] - 0.02)
    zmin = min(lerp_keys(D["belt"], t) for t in ts) - 0.05
    return {"side": sides, "windscreen": ws, "backlight": bl, "z_min": zmin}


def window(body, pts2d, plane="XZ", side=None, depth=0.012, z_min=None, name="Glass", x_lim=None):
    """a window with an exact outline, built the way the studied car's glass is: a separate glass skin that keeps
    the body's curvature, sunk `depth` behind the paint, in a recess whose walls are the gasket (Trim).
    plane 'XZ': outline drawn in the side view (door glass, quarter lights), cut on one side or both;
    plane 'XY': outline drawn in plan (windscreen, rear screen, sunroof), cut from above down to z_min;
    plane 'YZ': outline (y, z) in the end view (a pickup's upright back window), side -1 = rear end, cut from
    behind forward to x_lim (+1 = front end, cut back to x_lim).
    On a hollow() shell the recess opens right through the skin: close the gap to the glass with gasket().
    Returns the glass objects."""
    W = body.dimensions.y; out = []
    sides = [side] if side else ([1, -1] if plane == "XZ" else ([-1] if plane == "YZ" else [0]))
    for sd in sides:
        if plane == "XZ":
            lo, hi = (0.12 * W, W) if sd > 0 else (-W, -0.12 * W); odir = Vector((0, sd, 0))
        elif plane == "YZ":
            lo, hi = (-20.0, x_lim) if sd < 0 else (x_lim, 20.0); odir = Vector((sd, 0, 0))
        else:
            lo, hi = (z_min if z_min is not None else 0.0), 10.0; odir = Vector((0, 0, 1))
        g = body.copy(); g.data = body.data.copy(); bpy.context.collection.objects.link(g)
        boolean(g, _poly_prism(pts2d, plane, lo, hi, "Gap", "wcut"), "INTERSECT", transfer=True)
        bm = bmesh.new(); bm.from_mesh(g.data)
        gi = [i for i, m in enumerate(g.data.materials) if m and m.name == "Gap"]
        kill = [f for f in bm.faces if f.material_index in gi or f.normal.dot(odir) < 0.15]
        bmesh.ops.delete(bm, geom=kill, context="FACES")
        if not bm.faces:
            print("WINDOW empty", name, sd); bm.free(); bpy.data.objects.remove(g); continue
        for v in bm.verts:
            v.co -= v.normal * depth
        far = min(v.co.dot(odir) for v in bm.verts)          # deepest glass point along the outward direction
        for f in bm.faces:
            f.material_index = 0; f.smooth = True
        bm.to_mesh(g.data); bm.free()
        g.data.materials.clear(); g.data.materials.append(mat("Glass"))
        g.name = g.data.name = f"{name}_{'L' if sd > 0 else 'R' if sd < 0 else 'C'}"
        # recess in the body behind the glass: from just behind the glass outward, walls = gasket
        if plane == "XZ":
            plo, phi = (far - 0.02, W) if sd > 0 else (-W, -(far - 0.02))
        elif plane == "YZ":
            plo, phi = sorted((sd * (far - 0.02), sd * 20.0))
        else:
            plo, phi = far - 0.02, 10.0
        boolean(body, _poly_prism(pts2d, plane, plo, phi, "Trim", "wrec"), "DIFFERENCE", transfer=True)
        out.append(g)
    return out


def _surface_hit(body, origin, direction):
    bm = bmesh.new(); bm.from_mesh(body.data); bm.transform(body.matrix_world)
    tree = BVHTree.FromBMesh(bm); bm.free()
    loc, nrm, idx, dist = tree.ray_cast(Vector(origin), Vector(direction).normalized())
    return loc, nrm


def lamp(body, y, z, w, h, end="front", depth=0.05, lens="LampLens", inner=2, mirror=True):
    """a recessed lamp bucket where a ray from the front (or rear) hits the body at (y, z): pocket cut along the
    surface normal (walls LampHousing), `inner` reflector rings inset inside it (the concentric loops the studied
    car's lamps have), a lens slot face. mirror=True makes the pair."""
    made = []
    for yy in ([y, -y] if mirror and abs(y) > 1e-4 else [y]):
        d = Vector((-1, 0, 0)) if end == "front" else Vector((1, 0, 0))
        hit, nrm = _surface_hit(body, (-d.x * 20, yy, z), d)
        if hit is None:
            print("LAMP miss", end, yy, z); continue
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(depth * 2, w, h), verts=bm.verts)
        cut = link(bm, "lampcut", "LampHousing")
        up = Vector((0, 0, 1))
        cut.matrix_world = Matrix.Translation(hit) @ nrm.to_track_quat("X", "Z").to_matrix().to_4x4()
        boolean(body, cut)
        made.append((hit, nrm.copy()))
    # reflector rings + lens: faces at the pocket floor (LampHousing, facing out) get inset rings, centre = lens
    bm = bmesh.new(); bm.from_mesh(body.data)
    hi, li = slot(body, "LampHousing"), slot(body, lens)
    for hpos, n in made:
        floor = [f for f in bm.faces if f.material_index == hi and (f.calc_center_median() - hpos).length < max(w, h)
                 and f.normal.dot(n) > 0.8]
        for i in range(inner):
            if not floor:
                break
            bmesh.ops.inset_region(bm, faces=floor, thickness=min(w, h) * 0.08, depth=-depth * 0.12)
        for f in floor:
            f.material_index = li
    bm.to_mesh(body.data); bm.free()
    return made


def grille(body, y_half, z0, z1, depth=0.03, slats=6, end="front"):
    """a grille opening between the lamps: pocket cut, then horizontal slats inside it."""
    d = -1 if end == "front" else 1
    hit, nrm = _surface_hit(body, (-d * 20, 0, (z0 + z1) / 2), (d, 0, 0))
    if hit is None:
        return []
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(depth * 2, 2 * y_half, z1 - z0), verts=bm.verts)
    cut = link(bm, "grillecut", "Grille"); cut.location = hit
    boolean(body, cut)
    out = []
    for i in range(slats):
        z = z0 + (z1 - z0) * (i + 0.5) / slats
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(depth * 0.5, 2 * y_half - 0.01, (z1 - z0) / slats * 0.35), verts=bm.verts)
        s = link(bm, "slat", "Chrome" if i in (0, slats - 1) else "Grille")
        s.location = (hit.x + d * depth * 0.5, 0, z); out.append(s)
    return out


def plate(body, end="rear", z=None, w=0.52, h=0.11):
    """number-plate recess + plate."""
    z = z if z is not None else body.location.z + 0.45
    d = -1 if end == "rear" else 1                   # rear is -X
    hit, nrm = _surface_hit(body, (d * 20, 0, z), (-d, 0, 0))
    if hit is None:
        return None
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bmesh.ops.scale(bm, vec=(0.02, w + 0.02, h + 0.02), verts=bm.verts)
    c = link(bm, "platecut", "Trim"); c.location = hit; boolean(body, c)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bmesh.ops.scale(bm, vec=(0.004, w, h), verts=bm.verts)
    p = link(bm, "Plate", "Plate"); p.location = hit + Vector((-d * 0.006, 0, 0))
    return p

# ------------------------------------------------------------------ wheels
def _lathe_y(profile, segs, slots_idx, name, slots, rfunc=None, closed=True):
    """lathe round the Y axis: profile [(r, y, slot_index)]."""
    bm = bmesh.new(); rings = []
    prof = list(profile) + ([profile[0]] if closed else [])
    for row, (r, y, si) in enumerate(prof):
        ring = []
        for k in range(segs):
            a = 2 * math.pi * k / segs
            rr = rfunc(r, y, k, row) if rfunc else r
            ring.append(bm.verts.new((rr * math.cos(a), y, rr * math.sin(a))) if rr > 1e-6 else None)
        rings.append((ring, si))
    for (A, si), (B, _) in zip(rings, rings[1:]):
        for k in range(segs):
            k2 = (k + 1) % segs
            vs = [v for v in (A[k], A[k2], B[k2], B[k]) if v is not None]
            if len(set(vs)) >= 3:
                f = bm.faces.new(vs); f.material_index = si
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = True
    return link(bm, name, slots)


def wheel(P, side=1, spokes=5, segs=64, tread=True, name="Wheel", lug=True):
    """tire + rim + brake disc and caliper, built at the origin with the axle along Y, outer face toward +Y*side.
    Rim diameter about 0.66 of the tire; tread blocks from a per-vertex pattern; spokes radial; lug nuts from the
    hard-surface insert library when it exists."""
    R, wt = P["wheel_r"], P["tire_w"]; rr = R * 0.66; h = wt / 2
    so = side
    tire_prof = [(rr * 1.02, -h * 0.92, 0), (R * 0.93, -h, 0), (R - 0.006, -h * 0.86, 0), (R, -h * 0.55, 0),
                 (R, -h * 0.18, 0), (R - 0.008, -h * 0.12, 0), (R - 0.008, h * 0.12, 0), (R, h * 0.18, 0),
                 (R, h * 0.55, 0), (R - 0.006, h * 0.86, 0), (R * 0.93, h, 0), (rr * 1.02, h * 0.92, 0)]
    tread_rows = {3, 4, 7, 8}
    def tread_f(r, y, k, row):
        if not tread or row not in tread_rows:
            return r
        return r - 0.005 if (k + (0 if row in (3, 8) else 2)) % 4 in (0, 1) else r
    tire = _lathe_y(tire_prof, segs, None, name + "_tire", ["Tire"], tread_f)
    # rim: barrel + dish, face at the outer side
    ys = so
    rim_prof = [(rr * 0.98, -h * 0.9 * ys, 0), (rr * 1.04, -h * 0.95 * ys, 0), (rr * 1.04, -h * 0.80 * ys, 0),
                (rr * 0.97, -h * 0.75 * ys, 0), (rr * 0.97, h * 0.70 * ys, 0), (rr * 1.05, h * 0.78 * ys, 0),
                (rr * 1.05, h * 0.92 * ys, 0), (rr * 0.92, h * 0.88 * ys, 0), (rr * 0.88, h * 0.55 * ys, 0),
                (rr * 0.22, h * 0.50 * ys, 0), (rr * 0.18, h * 0.62 * ys, 0), (0.0, h * 0.62 * ys, 0)]
    rim = _lathe_y(rim_prof, segs // 2 if segs >= 48 else segs, None, name + "_rim", ["Rim"], closed=False)
    parts = [tire, rim]
    for i in range(spokes):
        a = 2 * math.pi * i / spokes
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(rr * 0.70, 0.035, rr * 0.18), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(rr * 0.52, 0, 0), verts=bm.verts)
        for v in bm.verts:                               # taper toward the rim, dish toward the face
            u = (v.co.x - rr * 0.17) / (rr * 0.70)
            v.co.z *= 1.0 - 0.35 * u
            v.co.y = v.co.y + ys * (h * 0.62 - 0.02 - 0.06 * u * h)
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(a, 3, "Y"), verts=bm.verts)
        parts.append(link(bm, "spoke", "Rim"))
    disc = _lathe_y([(rr * 0.82, -0.012, 0), (rr * 0.82, 0.012, 0), (rr * 0.30, 0.012, 0), (rr * 0.30, -0.012, 0)],
                    48, None, "disc", ["Brake"])
    disc.location.y = ys * h * 0.15; parts.append(disc)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bmesh.ops.scale(bm, vec=(rr * 0.35, 0.06, rr * 0.22), verts=bm.verts)
    cal = link(bm, "caliper", "Brake"); cal.location = (-rr * 0.62, ys * h * 0.15, rr * 0.25); parts.append(cal)
    if lug and S and os.path.exists(S.INSERT_LIB):
        for i in range(spokes):
            a = 2 * math.pi * (i + 0.5) / spokes
            p = Vector((rr * 0.2 * math.cos(a), ys * (h * 0.62 + 0.001), rr * 0.2 * math.sin(a)))
            parts.append(S.insert("hex_nut_m8", p, normal=(0, ys, 0), scale=1.4))
    for o in parts:
        apply(o) if o.modifiers else None
        if o.data.users > 1:
            o.data = o.data.copy()
        o.data.transform(o.matrix_basis); o.matrix_basis = Matrix.Identity(4)
    with bpy.context.temp_override(active_object=parts[0], selected_editable_objects=parts, selected_objects=parts):
        bpy.ops.object.join()
    w = parts[0]; w.name = w.data.name = name
    return w

# ------------------------------------------------------------------ rig
def _empty(name, loc, parent=None, size=0.3):
    """empty at `loc` given in the PARENT's space (no parent inverse, so drivers rotate it in place)."""
    e = bpy.data.objects.new(name, None); e.empty_display_size = size
    bpy.context.collection.objects.link(e)
    e.parent = parent; e.location = loc
    return e


def _drive(ob, path, index, root, prop, expr):
    fc = ob.driver_add(path, index); d = fc.driver; d.type = "SCRIPTED"
    v = d.variables.new(); v.name = "v"; v.type = "SINGLE_PROP"
    v.targets[0].id = root; v.targets[0].data_path = f'["{prop}"]'
    d.expression = expr


def rig_car(body, P, wheels, hinges=()):
    """driver rig on custom properties of CAR_root (the studied car drove its doors and wheel fold from control
    handles through Transform constraints; custom props + drivers do the same and are animator-friendly):
      steer  -1..1 -> front steer empties turn +-0.6 rad
      travel metres rolled -> every spin empty turns travel / wheel radius
      door   0..1  -> each hinge in `hinges` [(panel, pivot, axis 'X'|'Y'|'Z', max_angle_deg)] opens
    wheels: dict corner -> wheel object, corners FL FR RL RR."""
    root = _empty("CAR_root", (0, 0, 0), size=1.0)
    root["steer"] = 0.0; root["travel"] = 0.0; root["door"] = 0.0
    body.parent = root
    R = P["wheel_r"]; tr = P["track"] / 2
    pos = {"FL": (P["x_front_axle"], tr, R), "FR": (P["x_front_axle"], -tr, R),
           "RL": (P["x_rear_axle"], tr, R), "RR": (P["x_rear_axle"], -tr, R)}
    for c, w in wheels.items():
        steer = _empty(f"WHL_{c}_steer", pos[c], root, 0.25)
        spin = _empty(f"WHL_{c}_spin", (0, 0, 0), steer, 0.2)
        w.parent = spin; w.matrix_parent_inverse = Matrix.Identity(4); w.location = (0, 0, 0)
        if c[0] == "F":
            _drive(steer, "rotation_euler", 2, root, "steer", "v*0.6")
        _drive(spin, "rotation_euler", 1, root, "travel", f"-v/{R:.4f}")
    bpy.context.view_layer.update()
    for panel, pivot, axis, ang in hinges:
        hg = _empty(f"HINGE_{panel.name}", pivot, root, 0.15)
        bpy.context.view_layer.update()
        mw = panel.matrix_world.copy(); panel.parent = hg
        panel.matrix_parent_inverse = hg.matrix_world.inverted(); panel.matrix_world = mw
        _drive(hg, "rotation_euler", "XYZ".index(axis), root, "door", f"v*{math.radians(ang):.4f}")
    return root

# ------------------------------------------------------------------ export
def export_unreal_vehicle(path, body_objs, wheels, P):
    """skeletal FBX for a Chaos vehicle: one mesh, bones root + wheel_fl/fr/rl/rr at the wheel centres, body
    weighted to root, each wheel to its bone. Built in centimetres (scene unit scale 0.01, everything x100),
    because a metre scene gives Unreal a 100x root-bone scale (the setup-and-scale gotcha). Destructive: run last."""
    sc = bpy.context.scene
    for o in list(bpy.data.objects):                     # freeze the rig: world transforms into the meshes
        if o.type == "MESH":
            o.data = o.data.copy() if o.data.users > 1 else o.data
    names = {"FL": "wheel_fl", "FR": "wheel_fr", "RL": "wheel_rl", "RR": "wheel_rr"}
    meshes = []
    for o in body_objs:
        mw = o.matrix_world.copy(); o.parent = None; o.data.transform(mw); o.matrix_world = Matrix.Identity(4)
        o.vertex_groups.new(name="root").add(range(len(o.data.vertices)), 1.0, "REPLACE"); meshes.append(o)
    centres = {}
    for c, w in wheels.items():
        mw = w.matrix_world.copy(); centres[c] = mw.translation.copy()
        w.parent = None; w.data.transform(mw); w.matrix_world = Matrix.Identity(4)
        w.vertex_groups.new(name=names[c]).add(range(len(w.data.vertices)), 1.0, "REPLACE"); meshes.append(w)
    for o in list(bpy.data.objects):
        if o.type == "EMPTY":
            bpy.data.objects.remove(o)
    with bpy.context.temp_override(active_object=meshes[0], selected_editable_objects=meshes, selected_objects=meshes):
        bpy.ops.object.join()
    car = meshes[0]; car.name = car.data.name = "SK_Car"
    arm_d = bpy.data.armatures.new("Car_Skel"); arm = bpy.data.objects.new("Car_Skel", arm_d); sc.collection.objects.link(arm)
    with bpy.context.temp_override(active_object=arm, object=arm, selected_objects=[arm], selected_editable_objects=[arm]):
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        rb = arm_d.edit_bones.new("root"); rb.head = (0, 0, 0); rb.tail = (0.5, 0, 0)
        for c, n in names.items():
            b = arm_d.edit_bones.new(n); b.head = centres[c]; b.tail = centres[c] + Vector((0.2, 0, 0)); b.parent = rb
        bpy.ops.object.mode_set(mode="OBJECT")
    car.parent = arm; m = car.modifiers.new("Armature", "ARMATURE"); m.object = arm
    # centimetre scene
    sc.unit_settings.scale_length = 0.01
    for o in (arm, car):
        pass
    arm.scale = (100, 100, 100)
    with bpy.context.temp_override(active_object=arm, selected_editable_objects=[arm, car], selected_objects=[arm, car]):
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with bpy.context.temp_override(active_object=arm, selected_objects=[arm, car], selected_editable_objects=[arm, car]):
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"},
                                 add_leaf_bones=False, bake_anim=False, mesh_smooth_type="FACE",
                                 armature_nodetype="NULL", primary_bone_axis="X", secondary_bone_axis="Y")
    tris = sum(len(p.vertices) - 2 for p in car.data.polygons)
    print("VEHICLE exported", path, "tris", tris, "bones", [b.name for b in arm_d.bones],
          "slots", [m.name for m in car.data.materials])
    return tris

# ------------------------------------------------------------------ review
def render_views(out_dir, target=(0, 0, 0.6), dist=7.0, res=(1600, 900), prefix="car"):
    sc = bpy.context.scene; sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading; sh.light = "STUDIO"; sh.color_type = "MATERIAL"; sh.show_cavity = True; sh.cavity_type = "BOTH"
    sc.render.resolution_x, sc.render.resolution_y = res; sc.render.image_settings.file_format = "PNG"
    cam = sc.camera or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    if cam.name not in sc.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam; T = Vector(target); files = []
    for tag, d, ortho in (("34f", (1, 1, 0.45), 0), ("34r", (-1, -1, 0.5), 0), ("side", (0, 1, 0), 6.0),
                          ("front", (1, 0, 0.0), 3.2), ("top", (0, 0, 1), 6.0)):
        d = Vector(d).normalized(); cam.location = T + d * dist
        cam.rotation_euler = (T - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.type = "ORTHO" if ortho else "PERSP"; cam.data.ortho_scale = ortho or 1; cam.data.lens = 45
        f = os.path.join(out_dir, f"{prefix}_{tag}.png"); sc.render.filepath = f
        bpy.ops.render.render(write_still=True); files.append(f)
    return files


# ------------------------------------------------------------------ pickups, trucks, off-road (2026-11-07)
# Added for a crew-cab pickup test build: the square-body section, a sheet-metal
# shell with an interior behind the glass, a separate bed, wheel-house liners, window gaskets, joint gap
# measurement and a mud-terrain tyre on a beadlock steel wheel. Everything takes metres in the car frame.

def station_slab(D, t):
    """square-body half section (12 points, fixed count so the loft stays one quad grid):
    0 bottom centre, 1 floor, 2 rocker tuck, 3-6 the slab side (vertical, flat), 6 the shoulder crease (belt),
    7 the top of the shoulder, 8 the ledge / glass base, 9 the greenhouse top (glass_pt), 10 the roof edge,
    11 roof centre. Over the hood (no greenhouse) 9-11 lie flat, except a raised centre section of height
    D["bump"] (keys over t) and half width D["bump_w"] * w with a ramp. Keys: lean (glass lean-in over its height),
    ledge (glass base inboard of the shoulder), roof_round, side_top, crown. Creases for loft_body: SLAB_CREASES."""
    w = lerp_keys(D["plan"], t) * D["W"] / 2
    zf, zb, zt = lerp_keys(D["floor"], t), lerp_keys(D["belt"], t), top_at(D, t)
    zt = max(zt, zb + 0.012)
    gh = zt - zb
    s = max(0.0, min(1.0, (gh - 0.08) / 0.30))
    bkeys = D.get("bump", [(0.0, 0.0)])
    bmax = max(v for _, v in bkeys)
    bump = lerp_keys(bkeys, t) * (1 - s)
    h = bump / bmax if bmax > 1e-6 else 0.0
    bw = D.get("bump_w", 0.42) * w
    lean, ledge, rr = D.get("lean", 0.06), D.get("ledge", 0.045), D.get("roof_round", 0.035)
    yb = w - ledge

    def mix(a, b, f):
        return a + (b - a) * f
    hood9 = (mix(yb - 0.012, bw + 0.06, h), zt)
    hood10 = (mix(yb - 0.03, bw, h), zt + bump)
    cab9 = (yb - lean, zt - D.get("side_top", 0.06))
    cab10 = (yb - lean - rr, zt - 0.004)
    p9 = (mix(hood9[0], cab9[0], s), mix(hood9[1], cab9[1], s))
    p10 = (mix(hood10[0], cab10[0], s), mix(hood10[1], cab10[1], s))
    return [(0.0, zf), (w - 0.12, zf), (w - 0.022, zf + 0.012), (w, zf + 0.055), (w, 0.5 * (zf + zb)),
            (w, zb - 0.03), (w, zb), (w - 0.028, zb + 0.008), (yb, zb + 0.014), p9, p10,
            (0.0, zt + D.get("crown", 0.012) * s + bump)]


SLAB_CREASES = {2: 0.7, 6: 0.95, 7: 0.85, 8: 0.5, 9: 0.6, 10: 0.9}


def hollow(body, t=0.003, open_below=-0.7, thicken_now=True):
    """turn a closed loft into a sheet-metal shell: the underside faces (normal z < open_below) are removed and
    the skin is solidified inward t (with rims), so windows cut by window() open into an interior and
    split_panel() returns skins instead of solid chunks. Returns the body.
    thicken_now=False keeps it an open skin: cut every window / panel / arch first (set BOOL_HOLES = True for
    those booleans), then thicken() each piece. Solidifying first and cutting after fails on a square body: the
    4 mm inward offset folds at the tiny creased corners of the end caps and the exact solver wipes the shell."""
    bm = bmesh.new(); bm.from_mesh(body.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z < open_below], context="FACES")
    bm.to_mesh(body.data); bm.free()
    if thicken_now:
        thicken(body, t, rim_slot=None)
    return body


def thicken(ob, t=0.003, rim_slot="Gap", offset=-1.0):
    """solidify a skin piece inward with closed rims; rims (panel gap walls, opening edges) get rim_slot"""
    s = ob.modifiers.new("shell", "SOLIDIFY"); s.thickness = t; s.offset = offset
    s.use_rim = True; s.use_even_offset = True; s.use_quality_normals = True
    n = len(ob.data.materials)
    if rim_slot:
        ob.data.materials.append(mat(rim_slot)); s.material_offset_rim = n
    apply(ob)
    if rim_slot:
        for p in ob.data.polygons:
            if p.material_index > n:
                p.material_index = n
    return ob


def bed_box(D, t0=None, t1=1.0, floor_z=None, wall=0.09, front_wall=0.06, rear_wall=0.05, floor_t=0.03,
            stations=24, subd=2, rail=0.006, name="Bed", cap_crease=0.8):
    """a pickup's separate bed from t0 (default D["bed_t"]) to the tail: the body section lofted with a flat rail
    on top (top = belt + rail), so the shoulder line runs on from the cab; then the load box (floor_z up, `wall`
    in from the sides, front_wall / rear_wall in from the ends) and the underside below the floor plate (between
    the side skirts, so the frame fits under it) are cut out. Leaves double-wall sides with a flat rail cap, a
    floor plate and a rear wall to split off as the tailgate (split_panel plane 'YZ', side -1)."""
    t0 = D.get("bed_t", 0.675) if t0 is None else t0
    Db = dict(D)
    Db["top"] = [(t0 + (t1 - t0) * i / 8, lerp_keys(D["belt"], t0 + (t1 - t0) * i / 8) + rail) for i in range(9)]
    Db["bump"] = [(0.0, 0.0)]
    bed = loft_body(Db, stations, subd, name, t0, t1, cap_crease=cap_crease, cap_fill="tri")
    xf, xr = x_at(D, t0), x_at(D, t1)
    hw = D["W"] / 2 - wall
    fz = floor_z if floor_z is not None else lerp_keys(D["floor"], t0) + 0.2
    box = [(xr + rear_wall, -hw), (xf - front_wall, -hw), (xf - front_wall, hw), (xr + rear_wall, hw)]
    boolean(bed, _poly_prism(box, "XY", fz, 10.0, "CarPaint", "loadbox"), transfer=False)
    under = [(xr - 0.2, -hw), (xf + 0.2, -hw), (xf + 0.2, hw), (xr - 0.2, hw)]
    boolean(bed, _poly_prism(under, "XY", -1.0, fz - floor_t, "CarPaint", "under"), transfer=False)
    return bed


def _loops(bm_edges):
    """order boundary edges into closed vertex loops"""
    adj = {}
    for e in bm_edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    seen, loops = set(), []
    for v0 in adj:
        if v0 in seen:
            continue
        loop, prev, cur = [v0], None, v0
        seen.add(v0)
        while True:
            nxt = [w for w in adj[cur] if w is not prev and (w not in seen or w is v0)]
            if not nxt or nxt[0] is v0:
                break
            prev, cur = cur, nxt[0]
            loop.append(cur); seen.add(cur)
        if len(loop) > 2:
            loops.append(loop)
    return loops


def tube_mesh(points, r, sides=8, closed=False, ups=None, bm=None):
    """bmesh tube along a polyline (closed for loops). ups: optional per-point reference vectors (keeps the
    section from twisting on a flat loop). Returns the bmesh (caps on open ends)."""
    bm = bm or bmesh.new()
    P = [Vector(p) for p in points]; n = len(P); rings = []
    tgs = []
    for i in range(n):
        a = P[(i - 1) % n] if (closed or i > 0) else P[i]
        b = P[(i + 1) % n] if (closed or i < n - 1) else P[i]
        tgs.append((b - a).normalized())
    # no ups: rotation-minimising frames (parallel transport). A fixed up vector that switches when the path turns
    # vertical twists the section and kinks bent tubes (the bull-bar hoop, 2026-11-07)
    pt = []
    if not ups:
        r0 = Vector((0, 0, 1)) if abs(tgs[0].z) < 0.9 else Vector((1, 0, 0))
        u = (r0 - tgs[0] * r0.dot(tgs[0])).normalized(); pt.append(u)
        for i in range(1, n):
            q = tgs[i - 1].rotation_difference(tgs[i])
            u = q @ pt[-1]; u = (u - tgs[i] * u.dot(tgs[i])).normalized(); pt.append(u)
    for i, p in enumerate(P):
        tg = tgs[i]
        up = Vector(ups[i]) if ups else pt[i]
        u = (up - tg * up.dot(tg)).normalized(); s = tg.cross(u)
        rings.append([bm.verts.new(p + (u * math.cos(2 * math.pi * k / sides) + s * math.sin(2 * math.pi * k / sides)) * r)
                      for k in range(sides)])
    new_faces = []
    for i in range(n if closed else n - 1):
        A, B = rings[i], rings[(i + 1) % n]
        for k in range(sides):
            new_faces.append(bm.faces.new((A[k], A[(k + 1) % sides], B[(k + 1) % sides], B[k])))
    if not closed:
        new_faces.append(bm.faces.new(rings[0][::-1])); new_faces.append(bm.faces.new(rings[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=new_faces)
    return bm


def gasket(glass, r=0.006, out=None, sides=8, slot="Trim", name="Gasket"):
    """rubber bead round a sunk glass panel: follows the glass's own boundary loop, centred `out` (default 0.8 r)
    outward along the glass normal, so it fills the step between the glass and the opening edge of a hollow()
    shell (the opening and the glass share one outline, so the bead also tucks into the cut edge)."""
    out = r * 0.8 if out is None else out
    bm = bmesh.new(); bm.from_mesh(glass.data); bm.transform(glass.matrix_world); bm.normal_update()
    res = bmesh.new()
    for loop in _loops([e for e in bm.edges if e.is_boundary]):
        nrm = [v.normal.copy() for v in loop]
        tube_mesh([v.co + nv * out for v, nv in zip(loop, nrm)], r, sides, closed=True, ups=nrm, bm=res)
    bm.free()
    for f in res.faces:
        f.smooth = True
    return link(res, name, slot)


def _bvh(objs):
    bm = bmesh.new()
    for o in objs:
        me = o.data.copy(); me.transform(o.matrix_world); bm.from_mesh(me); bpy.data.meshes.remove(me)
    bm.normal_update()
    tree = BVHTree.FromBMesh(bm); bm.free()
    return tree


def contact_gap(mounted, support, reach=0.012, facing=-0.3, samples=None):
    """measure how a mounted part sits on its support (the hard-surface rule: anything over ~1 mm open or buried
    fails). Samples = the mounted part's face centres and corners whose face points at the support (normal dot
    the support normal < facing) and lie within `reach` of it; or pass samples=[point, ...]. Signed distance to
    the support surface: + open gap, - buried. Returns dict(n, min, median, max, ok) in millimetres, ok = share of
    samples within +-1 mm."""
    mounted = mounted if isinstance(mounted, (list, tuple)) else [mounted]
    support = support if isinstance(support, (list, tuple)) else [support]
    tree = _bvh(support)
    d, pts = [], []
    if samples is None:
        for o in mounted:
            M = o.matrix_world; R3 = M.to_3x3()
            for p in o.data.polygons:
                nrm = (R3 @ p.normal).normalized()
                cs = [M @ o.data.vertices[i].co for i in p.vertices]
                c = M @ p.center
                pts += [(q, nrm) for q in [c] + [v.lerp(c, 0.1) for v in cs]]
    else:
        pts = [(Vector(p), None) for p in samples]
    for p, nrm in pts:
        co, nn, i, dist = tree.find_nearest(p)
        if co is None or dist > reach:
            continue
        if nrm is not None and nrm.dot(nn) > facing:
            continue
        d.append((p - co).dot(nn) * 1000.0)
    if not d:
        return {"n": 0}
    d.sort()
    return {"n": len(d), "min": round(d[0], 2), "median": round(d[len(d) // 2], 2), "max": round(d[-1], 2),
            "ok": round(sum(1 for x in d if abs(x) <= 1.0) / len(d), 3)}


def min_clearance(a_objs, b_objs, step=1):
    """smallest distance (m) from any vertex of a_objs to b_objs' surfaces, and how many vertices sit inside
    (tyre in arch, flare over tyre). Returns (distance, inside_count)."""
    tree = _bvh(b_objs if isinstance(b_objs, (list, tuple)) else [b_objs])
    best, inside = 1e9, 0
    for o in (a_objs if isinstance(a_objs, (list, tuple)) else [a_objs]):
        M = o.matrix_world
        for v in o.data.vertices[::step]:
            p = M @ v.co
            co, nn, i, dist = tree.find_nearest(p)
            if co is None:
                continue
            if (p - co).dot(nn) < 0 and dist < 0.05:
                inside += 1
            best = min(best, dist)
    return best, inside


# ---- mud-terrain tyre on a beadlock steel wheel (built at the origin, axle along Y, outer face +Y)

def _catmull(keys, per=10):
    P = [Vector(p) for p in keys]; out = []
    for i in range(len(P) - 1):
        p0 = P[i - 1] if i > 0 else P[i] * 2 - P[i + 1]
        p1, p2 = P[i], P[i + 1]
        p3 = P[i + 2] if i + 2 < len(P) else P[i + 1] * 2 - P[i]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1])
    return out


def _resample(pts, n):
    P = [Vector(p) for p in pts]
    L = [0.0]
    for a, b in zip(P, P[1:]):
        L.append(L[-1] + (b - a).length)
    out, k = [], 0
    for i in range(n):
        s = L[-1] * i / (n - 1)
        while k < len(L) - 2 and L[k + 1] < s:
            k += 1
        u = (s - L[k]) / max(1e-9, L[k + 1] - L[k])
        out.append(P[k].lerp(P[k + 1], min(1.0, max(0.0, u))))
    return out


class TyreSurface:
    """the carcass as a lathe round Y: profile points (y, r) resampled evenly by arc length. S(p, a, d) is the
    point at signed arc length p from the crown centre, angle a, lifted d along the outward normal.
    pS = arc length to the shoulder (y = 0.9 h), pL = to the widest point of the sidewall."""

    def __init__(self, R, width, rim_r, depth, n=96):
        h = width / 2; rc = R - depth; self.rc = rc
        half = [(0.0, rc), (0.45, rc - 0.002), (0.76, rc - 0.008), (0.90, rc - 0.024), (0.975, rc - 0.052),
                (1.0, rc - 0.092), (0.985, rc - 0.150), (0.93, rim_r + 0.055), (0.85, rim_r + 0.022),
                (0.80, rim_r + 0.008)]
        keys = [(-yy * h, r) for yy, r in reversed(half)] + [(yy * h, r) for yy, r in half[1:]]
        self.prof = _resample(_catmull(keys, 12), n)
        self.n = n
        cum = [0.0]
        for a, b in zip(self.prof, self.prof[1:]):
            cum.append(cum[-1] + (b - a).length)
        self.cum, self.L, self.p0 = cum, cum[-1], cum[-1] / 2
        mid = n // 2
        iS = next(i for i in range(mid, n) if self.prof[i].x >= 0.9 * h)
        iL = max(range(mid, n), key=lambda i: self.prof[i].x)
        self.pS, self.pL = cum[iS] - self.p0, cum[iL] - self.p0

    def yr(self, p):
        s = max(0.0, min(self.L, p + self.p0))
        k = 0
        lo, hi = 0, self.n - 2
        while lo < hi:                                   # binary search the arc-length table
            m = (lo + hi) // 2
            if self.cum[m + 1] < s:
                lo = m + 1
            else:
                hi = m
        k = lo
        u = (s - self.cum[k]) / max(1e-9, self.cum[k + 1] - self.cum[k])
        q = self.prof[k].lerp(self.prof[k + 1], u)
        d = (self.prof[k + 1] - self.prof[k]).normalized()
        return q.x, q.y, Vector((-d.y, d.x))             # outward normal in (y, r) for a profile running -y -> +y

    def S(self, p, a, d=0.0):
        y, r, nrm = self.yr(p)
        r2, y2 = r + nrm.y * d, y + nrm.x * d
        return Vector((r2 * math.cos(a), y2, r2 * math.sin(a)))


def _block(bm, T, p0, p1, a0, a1, height, nu, nv, skew=0.0, draft=0.06, sink=0.003, rim=None):
    """one tread block: the patch p0..p1 x a0..a1 (angle shifted by skew * u across it) lifted along the carcass
    normal from -sink to height(p), the top shrunk by `draft` toward its centre. Top rim edges go into `rim`."""
    def F(i, j, top):
        u, v = i / nu, j / nv
        if top:
            u = 0.5 + (u - 0.5) * (1 - draft); v = 0.5 + (v - 0.5) * (1 - draft * 1.6)
        p = p0 + (p1 - p0) * u
        return T.S(p, a0 + (a1 - a0) * v + skew * u, height(p) if top else -sink)
    Tv = [[bm.verts.new(F(i, j, True)) for j in range(nv + 1)] for i in range(nu + 1)]
    Bv = [[bm.verts.new(F(i, j, False)) for j in range(nv + 1)] for i in range(nu + 1)]
    fs = []
    for i in range(nu):
        for j in range(nv):
            fs.append(bm.faces.new((Tv[i][j], Tv[i + 1][j], Tv[i + 1][j + 1], Tv[i][j + 1])))
            fs.append(bm.faces.new((Bv[i][j], Bv[i][j + 1], Bv[i + 1][j + 1], Bv[i + 1][j])))
    ring = [(i, 0) for i in range(nu)] + [(nu, j) for j in range(nv)] + [(i, nv) for i in range(nu, 0, -1)] + \
           [(0, j) for j in range(nv, 0, -1)]
    for k in range(len(ring)):
        (i0, j0), (i1, j1) = ring[k], ring[(k + 1) % len(ring)]
        fs.append(bm.faces.new((Tv[i0][j0], Bv[i0][j0], Bv[i1][j1], Tv[i1][j1])))
        if rim is not None:
            rim.append((Tv[i0][j0], Tv[i1][j1]))
    bmesh.ops.recalc_face_normals(bm, faces=fs)


def offroad_tyre(R=0.47, width=0.318, rim_r=0.216, depth=0.019, pitches=20, segs=160, prof_n=72,
                 block=(4, 3), bevel=0.0018, bevel_segs=2, lugs=True, name="Tyre"):
    """a mud-terrain tyre: a smooth carcass (lathe) with separate tread blocks sunk 3 mm into it (intersect,
    never merge): staggered shoulder blocks that wrap over the shoulder and run down the sidewall as lugs
    (alternate long / short), and an angled zig-zag pair of centre blocks per pitch; blocks have draft and
    bevelled top edges. LOW: fewer segs / prof_n, block=(1, 1), bevel=0. Returns [carcass, tread]."""
    T = TyreSurface(R, width, rim_r, depth, n=prof_n)
    bm = bmesh.new(); rings = []
    for k in range(segs):
        a = 2 * math.pi * k / segs
        rings.append([bm.verts.new(T.S(c - T.p0, a)) for c in T.cum])
    for k in range(segs):
        A, B = rings[k], rings[(k + 1) % segs]
        for i in range(prof_n - 1):
            f = bm.faces.new((A[i], A[i + 1], B[i + 1], B[i]))
    bm.normal_update()
    crown = rings[0][prof_n // 2]
    f0 = crown.link_faces[0]
    if f0.normal.dot(crown.co) < 0:                      # outward: away from the axle at the crown
        for f in bm.faces:
            f.normal_flip()
    for f in bm.faces:
        f.smooth = True
    carcass = link(bm, name + "_carcass", "Tire")
    tb = bmesh.new(); rim = []
    dA = 2 * math.pi / pitches; pS, pL = T.pS, T.pL
    nu, nv = block
    full = lambda p: depth
    def wrap_h(p_end):
        def f(p):
            q = abs(p)
            if q <= pS * 1.02:
                return depth
            return depth * (1 - 0.55 * (q - pS * 1.02) / max(1e-6, abs(p_end) - pS * 1.02))
        return f
    for k in range(pitches):
        a = k * dA
        long = (k % 2 == 0) and lugs
        for sd, off in ((1, 0.0), (-1, 0.5)):
            pe = pL + (0.05 if long else 0.008) if lugs else pS
            p0, p1 = (0.40 * pS, pe) if sd > 0 else (-pe, -0.40 * pS)
            a0 = a + off * dA
            _block(tb, T, p0, p1, a0, a0 + 0.50 * dA, wrap_h(pe), nu + 2, nv, skew=sd * 0.10 * dA, rim=rim)
            q0, q1 = (-0.06 * pS, 0.33 * pS) if sd > 0 else (-0.33 * pS, 0.06 * pS)
            c0 = a + (0.06 + off) * dA
            _block(tb, T, q0, q1, c0, c0 + 0.34 * dA, full, max(1, nu - 1), nv, skew=sd * 0.12 * dA, rim=rim)
    if bevel > 0 and rim:
        edges = [tb.edges.get(pair) for pair in rim]
        bmesh.ops.bevel(tb, geom=[e for e in edges if e], offset=bevel, segments=bevel_segs, profile=0.5,
                        affect="EDGES", clamp_overlap=True)
    for f in tb.faces:
        f.smooth = True
    tread = link(tb, name + "_tread", "Tire")
    return [carcass, tread]


def lathe_y(profile, m, name, segs=64, closed=False):
    """solid of revolution round Y from (r, y) points (r = 0 closes to the axis); closed=True joins the last
    point back to the first (a ring section)."""
    bm = bmesh.new(); rings = []
    for r, y in profile:
        rings.append([bm.verts.new((r * math.cos(2 * math.pi * k / segs), y, r * math.sin(2 * math.pi * k / segs)))
                      for k in range(segs)] if r > 1e-6 else [bm.verts.new((0, y, 0))])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for A, B in pairs:
        for k in range(segs):
            if len(A) == 1:
                bm.faces.new((A[0], B[(k + 1) % segs], B[k]))
            elif len(B) == 1:
                bm.faces.new((A[k], A[(k + 1) % segs], B[0]))
            else:
                bm.faces.new((A[k], A[(k + 1) % segs], B[(k + 1) % segs], B[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = True
    return link(bm, name, m)


def steel_wheel(rim_r=0.216, width=0.229, offset=-0.05, lugs=8, pcd=0.1651, vents=8, segs=96, beadlock=True,
                name="Wheel"):
    """a plain steel wheel: rolled barrel with flanges and drop centre, a dished face disc welded in at `offset`
    (< 0 = face inboard, deep dish) with `lugs` stud holes on pcd and `vents` round holes, and a beadlock ring on
    the outer flange (bolt it with your own hardware on a 0.5 * (rim flange + ring outer) circle). Built at the
    origin, axle along Y, outer face +Y. Returns [barrel, face, ring]."""
    h = width / 2; fl = rim_r + 0.017
    barrel = lathe_y([(fl, -h - 0.006), (fl + 0.004, -h + 0.002), (rim_r + 0.002, -h + 0.012), (rim_r, -h + 0.03),
                      (rim_r - 0.024, -h + 0.06), (rim_r - 0.026, h - 0.07), (rim_r, h - 0.035),
                      (rim_r + 0.002, h - 0.012), (fl + 0.004, h - 0.002), (fl, h + 0.006),
                      (fl - 0.006, h + 0.004), (rim_r - 0.004, h - 0.012), (rim_r - 0.006, h - 0.035),
                      (rim_r - 0.032, h - 0.072), (rim_r - 0.030, -h + 0.06), (rim_r - 0.006, -h + 0.028),
                      (rim_r - 0.004, -h + 0.008), (fl - 0.006, -h - 0.004)], "Rim", name + "_barrel", segs, True)
    f0 = offset
    # (the section must not cross itself: an earlier profile did at its welded rim and every hole boolean then
    # left the cutter walls standing, 2026-11-07)
    face = lathe_y([(rim_r - 0.027, f0 + 0.032), (rim_r - 0.046, f0 + 0.016), (rim_r - 0.088, f0 + 0.003),
                    (0.115, f0 + 0.0), (0.068, f0 + 0.0), (0.066, f0 - 0.004), (0.066, f0 - 0.010),
                    (0.11, f0 - 0.010), (rim_r - 0.090, f0 - 0.007), (rim_r - 0.050, f0 + 0.006),
                    (rim_r - 0.033, f0 + 0.021), (rim_r - 0.025, f0 + 0.026)], "Rim", name + "_face", segs, True)
    hs = max(8, segs // 6)
    for k in range(lugs):
        a = 2 * math.pi * (k + 0.5) / lugs
        boolean(face, _poly_prism([(pcd / 2 * math.cos(a) + 0.0105 * math.cos(2 * math.pi * j / hs),
                                    pcd / 2 * math.sin(a) + 0.0105 * math.sin(2 * math.pi * j / hs)) for j in range(hs)],
                                  "XZ", f0 - 0.05, f0 + 0.05, "Rim", "lughole"), transfer=False)
    for k in range(vents):
        a = 2 * math.pi * k / vents
        boolean(face, _poly_prism([(0.152 * math.cos(a) + 0.026 * math.cos(2 * math.pi * j / (hs * 2)),
                                    0.152 * math.sin(a) + 0.026 * math.sin(2 * math.pi * j / (hs * 2))) for j in range(hs * 2)],
                                  "XZ", f0 - 0.05, f0 + 0.06, "Rim", "vent"), transfer=False)
    out = [barrel, face]
    if beadlock:
        out.append(lathe_y([(rim_r - 0.012, h + 0.004), (fl + 0.026, h + 0.004), (fl + 0.028, h + 0.008),
                            (fl + 0.028, h + 0.016), (fl + 0.024, h + 0.019), (rim_r - 0.008, h + 0.019),
                            (rim_r - 0.012, h + 0.015)], "Rim", name + "_beadlock", segs, True))
    return out


def station_truck(D, t):
    """the "truck" section (27 points, fixed count; D["profile"] = "truck", glass_pt 21, creases TRUCK_CREASES):
    a stamped square-body side instead of a dead-flat slab. Bottom up:
      0-4   floor, rocker tuck-under (creased) rising to the side
      5-8   recessed moulding channel (channel_z, channel_h tall, channel_d deep, creased both edges)
      9-11  convex bow of the side (bow) with an optional stamped rib on its peak (side_rib keys over t; a bed)
      12-15 swage: a crisp fold standing swage_out proud, swage_drop below the belt, with a short return under it
            so it casts a shadow line (swage_fn(x) adds height, e.g. an eyebrow over the front arch)
      16-19 shoulder rolled over the top (~22 mm radius, no knife crease)
      20    fender top / glass ledge (ledge in from the side)
      21-22 hood: valley + hood edge stepping hood_step_h above the fender top (hood_step keys 0..1 over t, the
            hood panel sits IN the fenders), edge at w - fender_top; cabin: greenhouse top (glass_pt) + roof edge
      23-25 a stamped rib (ribs keys = height over t; hood_rib_y keys / roof_rib_y place it), 26 centre line
    The hood is crowned from its edge to the centre (the top line is the centre line); the roof crowns roof_crown.
    D["hood_levels"] = {...} makes an old multi-level pressed hood instead (one extra
    point, 28, creases TRUCK_CREASES_LEVELS): from the hood's side edge a large shoulder roll (up to roll_w wide;
    its height is the room left between the top line and the belt, at least roll_min) over to a lower side flat,
    a soft radiused ledge stepping bulge_h up to a wide raised centre bulge (bulge_w of the hood half width,
    crowned crown), the bulge fading out over fade_t behind ledge_t (the nose ledge); frise lifts the valley.
    D["cab_s0"] (default 0.10): the top-above-belt height where the greenhouse section starts to blend in (raise
    it when the hood stands high).
    side_fn(x, z) -> outward offset of the side points (an arch swell). Bed stations (no greenhouse, no hood
    step) come out flat-topped at the top line, so bed_box() works on it unchanged."""
    x = x_at(D, t)
    w = lerp_keys(D["plan"], t) * D["W"] / 2
    zf, zb, zt = lerp_keys(D["floor"], t), lerp_keys(D["belt"], t), top_at(D, t)
    zt = max(zt, zb + 0.012)
    s = max(0.0, min(1.0, (zt - zb - D.get("cab_s0", 0.10)) / 0.30))
    # D["round_ends"] (opt-in): [(t_end, dir, ax, by, az, bz)] rounds a part's end as a
    # quarter ellipse: within ax (metres along x) of t_end (dir +1 = the end lies at larger t, -1 = at smaller t)
    # the half width pulls in up to by and the top line drops up to bz over az, so the vertical corners and the
    # back-to-roof edge are real radii tangent to the end face instead of a crease. Point count is unchanged.
    for te, dr, ax, by, az, bz in D.get("round_ends", ()):
        d = dr * (te - t) * D["L"]
        if -1e-9 <= d < ax:
            u = max(0.0, (ax - d) / ax)
            w -= by * (1 - math.sqrt(max(0.0, 1 - u * u)))
        if -1e-9 <= d < az:
            u = max(0.0, (az - d) / az)
            zt -= bz * (1 - math.sqrt(max(0.0, 1 - u * u)))
    k = lambda key, default=0.0: lerp_keys(D[key], t) if key in D else default
    stp, sh, rib, srib = k("hood_step"), k("hood_step_h", 0.02), k("ribs"), k("side_rib")
    ry = k("hood_rib_y", 0.5) * (1 - s) + D.get("roof_rib_y", 0.42) * s
    rw = D.get("rib_w", 0.0175)
    zc, hc, dc = D.get("channel_z", zf + 0.25), D.get("channel_h", 0.04), D.get("channel_d", 0.01)
    bow, zr = D.get("bow", 0.008), D.get("rib_z", 0.5 * (zc + zb))
    zs = zb - D.get("swage_drop", 0.09) + (D["swage_fn"](x) if "swage_fn" in D else 0.0)
    sp = D.get("swage_out", 0.013)
    yb = w - D.get("ledge", 0.06)
    off = (lambda z: D["side_fn"](x, z)) if "side_fn" in D else (lambda z: 0.0)
    def S(y, z):
        return (y + off(z), z)
    pts = [(0.0, zf), (w - 0.12, zf), (w - 0.025, zf + 0.010), S(w - 0.007, zf + 0.040), S(w, zf + 0.070),
           S(w, zc - hc / 2 - 0.003), S(w - dc, zc - hc / 2 + 0.004), S(w - dc, zc + hc / 2 - 0.004), S(w, zc + hc / 2 + 0.003),
           S(w + bow * 0.7, zr - 0.024), S(w + bow + srib, zr), S(w + bow * 0.7, zr + 0.024),
           S(w + 0.001, zs - 0.016), S(w + sp, zs - 0.009), S(w + sp, zs), S(w + 0.003, zs + 0.022),
           S(w, zb - 0.030), (w - 0.007, zb - 0.010), (w - 0.020, zb + 0.002), (w - 0.038, zb + 0.008)]
    def mix(a, b, f):
        return [(p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f) for p, q in zip(a, b)]
    ch = D.get("hood_levels")
    ye = w - D.get("fender_top", 0.10); he = zb + sh
    y22 = yb - D.get("lean", 0.05) - D.get("roof_round", 0.035); ze = zt - 0.004
    rc = lambda y: ze + D.get("roof_crown", 0.022) * (1 - (y / y22) ** 2)
    if not ch:
        bed = [(yb, zt), (yb - 0.012, zt), (yb - 0.025, zt), (ry + rw, zt), (ry, zt + rib), (ry - rw, zt), (0.0, zt)]
        cr = lambda y: he + (zt - he) * (1 - (y / ye) ** 2)
        hood = [(yb, zb + 0.012), (ye + 0.012, zb + 0.004), (ye - 0.008, he), (ry + rw, cr(ry + rw)), (ry, cr(ry) + rib),
                (ry - rw, cr(ry - rw)), (0.0, zt)]
        cab = [(yb, zb + 0.014), (yb - D.get("lean", 0.05), zt - D.get("side_top", 0.06)), (y22, ze), (ry + rw, rc(ry + rw)),
               (ry, rc(ry) + rib), (ry - rw, rc(ry - rw)), (0.0, rc(0.0))]
        return pts + mix(mix(bed, hood, stp), cab, s)
    # multi-level pressed hood: shoulder roll, side flat, soft ledge, raised centre bulge (fades into the nose ledge)
    zv = zb + 0.012 + ch.get("frise", 0.006)
    he = zv + sh
    ramp = max(0.0, min(1.0, (t - ch.get("ledge_t", 0.026)) / ch.get("fade_t", 0.04)))
    ramp = ramp * ramp * (3 - 2 * ramp)
    crown = ch.get("crown", 0.010)
    bh = ch.get("bulge_h", 0.03) * ramp
    zsf = zt - crown * ramp - bh
    room = zsf - 0.006 - he
    if room < ch.get("roll_min", 0.03):                      # not enough height: the bulge gives way first
        bh = max(0.0, bh - (ch.get("roll_min", 0.03) - room)); zsf = zt - crown * ramp - bh
        room = max(0.012, zsf - 0.006 - he)
    rwid = max(0.045, min(ch.get("roll_w", 0.085), 1.35 * room))
    yl = ch.get("bulge_w", 0.58) * ye
    bed = [(yb, zt), (yb - 0.012, zt), (yb - 0.025, zt), (yb - 0.040, zt), (ry + rw, zt), (ry, zt + rib), (ry - rw, zt), (0.0, zt)]
    hood = [(yb, zb + 0.012), (ye + 0.012, zv), (ye - 0.008, he), (ye - 0.016, he + 0.62 * room),
            (ye - 0.008 - rwid, he + room), (yl + 0.026, zsf), (yl - 0.018, zsf + bh), (0.0, zt)]
    y23 = 0.5 * (y22 + ry + rw)
    cab = [(yb, zb + 0.014), (yb - D.get("lean", 0.05), zt - D.get("side_top", 0.06)), (y22, ze), (y23, rc(y23)),
           (ry + rw, rc(ry + rw)), (ry, rc(ry) + rib), (ry - rw, rc(ry - rw)), (0.0, rc(0.0))]
    return pts + mix(mix(bed, hood, stp), cab, s)


TRUCK_CREASES = {2: 0.8, 4: 0.5, 5: 0.85, 6: 0.85, 7: 0.85, 8: 0.85, 10: 0.3, 12: 0.6, 13: 0.95, 14: 0.95,
                 19: 0.4, 20: 0.5, 21: 0.6, 22: 0.85, 24: 0.9}
TRUCK_CREASES_LEVELS = {k: v for k, v in TRUCK_CREASES.items() if k < 23}
TRUCK_CREASES_LEVELS.update({20: 0.3, 21: 0.6, 22: 0.85, 25: 0.35, 26: 0.4})       # soft ledges, rounded fender top
