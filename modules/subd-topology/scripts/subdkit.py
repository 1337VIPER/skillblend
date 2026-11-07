"""SubD-cage kit: hard surface the way a studied hand-built SubD model (a retro rocket, "the ship" below) is
built; see the subd-topology module. All-quad cages, crisp edges from HOLDING LOOPS (never sharp marks or bevel
modifiers), Subdivision on top, and parts that are never merged: fins, frames, seam strips and rings are separate
meshes pushed into the body. Round parts are lathes that share one segment count so their loops line up.

  lathe(profile, segs=16, crisp=..., hold=0.12)  profile [(r, z)] around Z; crisp point indices get two holding
                                                 loops at hold x the neighbouring segment length
  fin(root, tip, thickness, ...)                 a thin slab from root chord to tip chord, quad grid, rim holding
                                                 loops, root flared and sunk into the body (the ship's swept fins)
  sweep(profile, path, closed_path, ...)         a 2D section along a 3D path (frames, rails, cables, handles)
  rounded_rect(w, h, r, n)                       a section for sweep()
  trim_strip(target, pts, w, h, embed)           a raised seam strip that follows a surface (panel lines)
  seam_ring(r, width, proud, x0)                 a band over a joint between two lathed parts
  subd(ob, levels, apply)                        Subdivision (smooth shading, no sharps)
  topology_report(ob) / qa(obj, kind)            the numbers the ship was measured with, and a pass/fail gate
Units metres; the part's local frame is the caller's (lathes run along +Z, then rotate)."""
import math
import bpy, bmesh
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

def mat(name):
    return bpy.data.materials.get(name) or bpy.data.materials.new(name)


def _link(bm, name, m):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    me.materials.append(mat(m))
    for p in me.polygons:
        p.use_smooth = True
    return ob


def subd(ob, levels=2, apply=False, render_levels=None):
    """Subdivision with smooth shading and NO sharp edges: crispness must come from the cage's holding loops."""
    s = ob.modifiers.new("Subsurf", "SUBSURF"); s.levels = levels; s.render_levels = render_levels or levels
    s.use_limit_surface = True; s.boundary_smooth = "PRESERVE_CORNERS"
    for p in ob.data.polygons:
        p.use_smooth = True
    for e in ob.data.edges:
        e.use_edge_sharp = False
    if apply:
        with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
            bpy.ops.object.modifier_apply(modifier=s.name)
    return ob

# ------------------------------------------------------------------ lathe with holding loops
def hold_profile(profile, crisp, hold=0.12):
    """insert two holding points around every crisp profile point, at `hold` x the shorter neighbouring segment.
    That is what makes a crisp lip or step on a SubD surface (the ship's seam ring, nozzle ribs, hull hatch)."""
    out = []
    n = len(profile)
    for i, p in enumerate(profile):
        p = Vector(p)
        if i in crisp and 0 < i < n - 1:
            a, b = Vector(profile[i - 1]), Vector(profile[i + 1])
            d = hold * min((p - a).length, (b - p).length)
            out += [tuple(p + (a - p).normalized() * d), tuple(p), tuple(p + (b - p).normalized() * d)]
        else:
            out.append(tuple(p))
    return out


def square_profile(profile, segs, crisp=(), k=1.0):
    """resample a lathe profile so each span along it is about as long as the cage spacing around it
    (2 pi r / segs, times k): square quads, like the ship (hull quads ~30 mm both ways). Original points are kept,
    so crisp indices are remapped and returned."""
    out, cmap = [], {}
    for i, p in enumerate(profile):
        if i:
            a, b = Vector(profile[i - 1]), Vector(p)
            r = max((a.x + b.x) / 2, 0.25 * max(a.x, b.x), 1e-4)
            n = max(1, round((b - a).length / (k * 2 * math.pi * r / segs)))
            out += [tuple(a.lerp(b, t / n)) for t in range(1, n)]
        cmap[i] = len(out); out.append(tuple(p))
    return out, tuple(cmap[c] for c in crisp if c in cmap)


def lathe(profile, m, segs=16, crisp=(), hold=0.12, name="lathe", closed=False, levels=2, apply=False, square=True):
    """SubD lathe around +Z. profile [(r, z)] from bottom to top; start/end at r = 0 for a closed solid (the
    poles then sit on the axis, where the ship's lathes put them too), or closed=True for a ring section.
    segs is the CAGE count: 16 cage segs x Subsurf 2 = 64 around, the ship's count for every round part.
    Keep one segs value for every lathed part of an assembly so the loops line up at joints.
    square=True resamples long profile spans so the quads come out square (square_profile)."""
    if square:
        profile, crisp = square_profile(profile, segs, crisp)
    prof = hold_profile(profile, set(crisp), hold)
    if closed:
        prof = prof + [prof[0]]
    bm = bmesh.new(); rings = []
    for r, z in prof:
        if r <= 1e-9:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * k / segs), r * math.sin(2 * math.pi * k / segs), z))
                          for k in range(segs)])
    for A, B in zip(rings, rings[1:]):
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(A) == 1:
                bm.faces.new((A[0], B[k], B[k2]))
            elif len(B) == 1:
                bm.faces.new((A[k], B[0], A[k2]))
            else:
                bm.faces.new((A[k], B[k], B[k2], A[k2]))
    if closed:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-9)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _link(bm, name, m)
    return subd(ob, levels, apply) if levels else ob


def ribs(r0, r1, z0, z1, n, depth, crisp=True):
    """profile segment for a ribbed bell (the ship's nozzles): n ribs from (r0, z0) to (r1, z1), each a step
    out by `depth`. Returns (points, crisp_indices) to splice into a lathe profile."""
    pts, cr = [], []
    for i in range(n):
        t0, t1 = i / n, (i + 0.6) / n
        ra, za = r0 + (r1 - r0) * t0, z0 + (z1 - z0) * t0
        rb, zb = r0 + (r1 - r0) * t1, z0 + (z1 - z0) * t1
        pts += [(ra, za), (ra + depth, za + 0.15 * (zb - za)), (rb + depth, zb), (rb, zb + 0.1 * (zb - za))]
        if crisp:
            cr += [len(pts) - 3, len(pts) - 2]
    return pts, cr

# ------------------------------------------------------------------ fins (thin slabs with flared, sunk roots)
def fin(root, tip, thickness, m, nu=4, nv=6, taper=0.4, sweep_curve=0.0, flare=1.6, embed=0.06,
        root_normal=(0, 0, 1), hold=0.12, levels=2, name="fin", apply=False):
    """a swept fin as a quad-grid slab. root, tip = ((x_lead, y, z), (x_trail, y, z)) chords; the slab spans
    root -> tip in nu cage rows and lead -> trail in nv columns. thickness at the root, tapering by `taper` to
    the tip. The root row is pushed `embed` into the body along -root_normal and widened by `flare`, so after
    SubD the fin rolls onto the body like a fillet (the ship's fins sit ~88 mm into a 1 m hull). Holding loops
    run round the whole rim at `hold` of the local cage spacing: thin edges stay crisp, faces stay soft."""
    (rl, rt), (tl, tt) = [Vector(p) for p in root], [Vector(p) for p in tip]
    rn = Vector(root_normal).normalized()
    us = [-embed / max(1e-6, (tl - rl).length)] + [i / nu for i in range(nu + 1)]
    vs = [j / nv for j in range(nv + 1)]
    def H(seq):                                          # holding values just inside both ends
        a, b = seq[0], seq[-1]; d = hold * (seq[1] - seq[0])
        return sorted(set(seq + [a + d, b - (seq[-1] - seq[-2]) * hold]))
    us_h, vs_h = H(us[1:]), H(vs)
    us_h = [us[0]] + us_h
    thick_dir = (rt - rl).cross(tl - rl).normalized()
    bm = bmesh.new(); grid = {}
    for s in (1, -1):
        for i, u in enumerate(us_h):
            uu = max(0.0, u)
            a = rl.lerp(tl, uu); b = rt.lerp(tt, uu)
            if u < 0:                                    # sunk root row, flared
                c = (a + b) / 2; a = c + (a - c) * flare; b = c + (b - c) * flare
                a = a - rn * embed; b = b - rn * embed
            t_here = thickness * (1 - taper * uu) * (flare if u < 0 else 1.0)
            for j, v in enumerate(vs_h):
                p = a.lerp(b, v)
                p += thick_dir * sweep_curve * math.sin(math.pi * v) * uu
                edge_fade = math.sin(math.pi * v) ** 0.35 if 0 < v < 1 else 0.0
                grid[(s, i, j)] = bm.verts.new(p + thick_dir * s * 0.5 * t_here * max(edge_fade, 0.0))
    ni, nj = len(us_h), len(vs_h)
    for s in (1, -1):
        for i in range(ni - 1):
            for j in range(nj - 1):
                q = [grid[(s, i, j)], grid[(s, i + 1, j)], grid[(s, i + 1, j + 1)], grid[(s, i, j + 1)]]
                bm.faces.new(q if s > 0 else q[::-1])
    for j in range(nj - 1):
        bm.faces.new((grid[(1, ni - 1, j)], grid[(1, ni - 1, j + 1)], grid[(-1, ni - 1, j + 1)], grid[(-1, ni - 1, j)]))
        bm.faces.new((grid[(1, 0, j + 1)], grid[(1, 0, j)], grid[(-1, 0, j)], grid[(-1, 0, j + 1)]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)  # leading/trailing edge points (edge_fade 0) weld
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _link(bm, name, m)
    return subd(ob, levels, apply) if levels else ob

# ------------------------------------------------------------------ sweeps
def rounded_rect(w, h, r, n=2):
    """closed 2D section (x across, y up) with corner radius r and n points per corner arc (n=2 + SubD = round)."""
    r = min(r, w / 2 * 0.99, h / 2 * 0.99); pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n); pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def circle(r, n=8):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _frames(path, closed, up_fn=None):
    pts = [Vector(p) for p in path]; n = len(pts); fr = []
    for i in range(n):
        a = pts[i - 1] if (closed or i > 0) else pts[i]
        b = pts[(i + 1) % n] if (closed or i < n - 1) else pts[i]
        t = (b - a).normalized()
        if up_fn:
            up = Vector(up_fn(pts[i]))
        elif fr:
            up = fr[-1][2]                              # parallel transport
        else:
            up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
        x = t.cross(up).normalized(); y = x.cross(t).normalized()
        fr.append((pts[i], x, y))
    return fr


def sweep(section, path, m, closed_path=False, up_fn=None, cap=True, levels=2, name="sweep", scale_fn=None, apply=False):
    """move a closed 2D section along a 3D path: quad rings, caps on open ends. up_fn(point) -> surface normal
    keeps the section upright on a surface (trim strips); scale_fn(i, n) tapers it. The ship's triangular scoop
    frames are a rounded_rect swept round a closed rounded triangle; its cables are circles swept along curves."""
    fr = _frames(path, closed_path, up_fn); bm = bmesh.new(); rings = []
    for i, (p, x, y) in enumerate(fr):
        s = scale_fn(i, len(fr)) if scale_fn else 1.0
        rings.append([bm.verts.new(p + x * u * s + y * v * s) for u, v in section])
    k = len(section)
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed_path else [])
    for A, B in pairs:
        for j in range(k):
            bm.faces.new((A[j], A[(j + 1) % k], B[(j + 1) % k], B[j]))
    if cap and not closed_path:
        for ring, rev in ((rings[0], True), (rings[-1], False)):
            c = bm.verts.new(sum((v.co for v in ring), Vector()) / k)
            for j in range(k):                           # triangle fan; SubD turns it into quads round one pole
                bm.faces.new((ring[j], ring[(j + 1) % k], c) if not rev else (c, ring[(j + 1) % k], ring[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _link(bm, name, m)
    return subd(ob, levels, apply) if levels else ob


def rounded_polygon(corners, r, n=3):
    """closed path through `corners` (3D) with each corner rounded by radius-ish r (n points per corner)."""
    cs = [Vector(c) for c in corners]; out = []
    for i, c in enumerate(cs):
        a, b = cs[i - 1], cs[(i + 1) % len(cs)]
        da, db = (a - c).normalized(), (b - c).normalized()
        p0, p1 = c + da * r, c + db * r
        for k in range(n + 1):
            t = k / n
            out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * c + t * t * p1)   # quadratic Bezier corner
    return out


def _tree(target):
    bm = bmesh.new(); bm.from_mesh(target.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh())
    bm.transform(target.matrix_world); t = BVHTree.FromBMesh(bm); bm.free(); return t


def trim_strip(target, pts, w, h, m, embed=0.6, step=None, levels=2, name="trim"):
    """a raised seam strip that hugs `target` along the polyline `pts` (points near the surface): each point is
    snapped to the surface, the section (w wide, h tall) stands on the surface normal and is sunk by
    embed x h, so only (1 - embed) x h shows (the ship: 9-16 mm strips, 2-3 mm proud). Densify with `step`."""
    tree = _tree(target); P = [Vector(p) for p in pts]
    if step:
        Q = [P[0]]
        for a, b in zip(P, P[1:]):
            n = max(1, int((b - a).length / step))
            Q += [a.lerp(b, k / n) for k in range(1, n + 1)]
        P = Q
    snapped, normals = [], {}
    for p in P:
        loc, nrm, _, _ = tree.find_nearest(p)
        snapped.append(loc); normals[tuple(round(c, 6) for c in loc)] = nrm
    sec = [(u, v + h * (0.5 - embed)) for u, v in rounded_rect(w, h, min(w, h) * 0.45, 2)]
    return sweep(sec, snapped, m, up_fn=lambda p: normals[tuple(round(c, 6) for c in p)], levels=levels, name=name)


def seam_ring(r, width, proud, z0, m, segs=16, name="seam_ring", levels=2):
    """a lathed band over the joint between two lathed parts (the ship's ring between the dome and the hull):
    sits `proud` above radius r, `width` long, holding loops on both lips."""
    prof = [(r - proud * 0.6, z0 - width / 2), (r + proud, z0 - width / 2), (r + proud, z0 + width / 2), (r - proud * 0.6, z0 + width / 2)]
    return lathe(prof, m, segs, crisp=(1, 2), hold=0.15, closed=True, name=name, levels=levels)

# ------------------------------------------------------------------ topology QA (calibrated on the ship)
def topology_report(ob, evaluated=True):
    """quad %, interior poles %, triangles, ngons, thin quads (aspect > 4: the holding loops), marked sharps,
    median edge as % of the part size. The same measures the ship was read with."""
    src = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh() if evaluated else ob.data
    bm = bmesh.new(); bm.from_mesh(src); bm.transform(ob.matrix_world)
    F = len(bm.faces) or 1
    q = sum(len(f.verts) == 4 for f in bm.faces); tri = sum(len(f.verts) == 3 for f in bm.faces)
    inner = [v for v in bm.verts if not v.is_boundary and v.link_edges]
    poles = sum(1 for v in inner if len(v.link_edges) != 4)
    asp = []
    for f in bm.faces:
        if len(f.verts) == 4:
            e = [l.edge.calc_length() for l in f.loops]; a, b = (e[0] + e[2]) / 2, (e[1] + e[3]) / 2
            if min(a, b) > 0:
                asp.append(max(a, b) / min(a, b))
    L = sorted(e.calc_length() for e in bm.edges) or [0]
    size = max(ob.dimensions) or 1
    r = {"faces": F, "quad": round(q / F, 3), "tri": tri, "ngon": F - q - tri,
         "pole_pct": round(100 * poles / max(1, len(inner)), 2), "thin_quads": round(sum(a > 4 for a in asp) / max(1, len(asp)), 3),
         "sharp": sum(not e.smooth for e in bm.edges), "edge_med_pct": round(100 * L[len(L) // 2] / size, 2)}
    bm.free()
    if evaluated:
        ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
    return r


GATES = {   # calibrated on the studied ship: hull 100% quads / 0.37% poles; fins 100% / 0; no sharps anywhere.
    # density = median edge / longest dimension: the ship's primary forms sit at 2.2-3.6%. Long thin parts (strips,
    # cables) can't be judged that way (the ship's own strips are 0.11%), so "detail" skips it. A small lathe's
    # axis tips leave 2 x (cage segs + 1) poles, which is why primary allows 2%.
    "primary": {"quad": 0.98, "pole_pct": 2.0, "sharp": 0, "edge_med_pct": (1.0, 5.0)},
    "detail":  {"quad": 0.95, "pole_pct": 3.0, "sharp": 0, "edge_med_pct": None},
}


def qa(objs, kind="primary"):
    """print a PASS/FAIL line per object against GATES[kind]; returns True when all pass."""
    g = GATES[kind]; ok_all = True
    for o in objs if isinstance(objs, (list, tuple)) else [objs]:
        r = topology_report(o); why = []
        if r["quad"] < g["quad"]: why.append(f"quad {r['quad']} < {g['quad']}")
        if r["pole_pct"] > g["pole_pct"]: why.append(f"poles {r['pole_pct']}% > {g['pole_pct']}%")
        if r["sharp"] > g["sharp"]: why.append(f"{r['sharp']} sharp edges (crispness must come from holding loops)")
        lo, hi = g["edge_med_pct"] or (0, 1e9)
        if not lo <= r["edge_med_pct"] <= hi: why.append(f"density {r['edge_med_pct']}% of size outside {lo}-{hi}%")
        ok = not why; ok_all &= ok
        print(f"TOPO {'PASS' if ok else 'FAIL'} {o.name:22s} {r}" + ("" if ok else "  <- " + "; ".join(why)))
    return ok_all
