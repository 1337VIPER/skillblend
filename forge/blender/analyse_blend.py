"""Measure how a .blend file was built. Runs INSIDE Blender (4.2 or newer).

    blender -b --factory-startup FILE.blend --python analyse_blend.py -- OUT.json

Writes one JSON document: scene settings, collections, materials, images, and for
every object its transform, modifier stack (with the settings that carry style),
mesh topology, shading marks, edge-length spread and UV/texel data. It only reads
the file; nothing is saved.
"""
import bpy
import bmesh
import json
import math
import sys
import os
from collections import Counter

VERSION = 6


def _r(x, n=6):
    try:
        return round(float(x), n)
    except Exception:
        return None


def _vec(v):
    return [_r(c) for c in v]


def _pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ---------------------------------------------------------------- modifiers
MOD_FIELDS = {
    "BEVEL": ["width", "offset_type", "segments", "limit_method", "angle_limit", "profile",
              "harden_normals", "use_clamp_overlap", "miter_outer", "miter_inner", "affect",
              "loop_slide", "mark_sharp", "profile_type"],
    "SUBSURF": ["levels", "render_levels", "quality", "use_creases", "boundary_smooth",
                "subdivision_type", "use_limit_surface"],
    "WEIGHTED_NORMAL": ["mode", "weight", "keep_sharp", "use_face_influence", "thresh"],
    "BOOLEAN": ["operation", "solver", "operand_type", "use_self", "use_hole_tolerant"],
    "MIRROR": ["use_axis", "use_bisect_axis", "use_bisect_flip_axis", "use_clip",
               "use_mirror_merge", "merge_threshold"],
    "ARRAY": ["count", "fit_type", "use_relative_offset", "relative_offset_displace",
              "use_constant_offset", "constant_offset_displace", "use_merge_vertices",
              "use_object_offset"],
    "SOLIDIFY": ["thickness", "offset", "use_even_offset", "use_rim", "use_rim_only",
                 "solidify_mode", "use_flip_normals"],
    "SKIN": ["use_smooth_shade", "branch_smoothing"],
    "SCREW": ["angle", "steps", "render_steps", "screw_offset", "axis", "use_merge_vertices"],
    "WELD": ["merge_threshold", "mode"],
    "TRIANGULATE": ["quad_method", "ngon_method", "min_vertices", "keep_custom_normals"],
    "DECIMATE": ["decimate_type", "ratio", "angle_limit"],
    "DISPLACE": ["strength", "mid_level", "direction"],
    "SHRINKWRAP": ["wrap_method", "wrap_mode", "offset"],
    "DATA_TRANSFER": ["use_loop_data", "data_types_loops"],
    "EDGE_SPLIT": ["split_angle", "use_edge_angle", "use_edge_sharp"],
    "CURVE": ["deform_axis"],
    "SIMPLE_DEFORM": ["deform_method", "angle", "factor", "deform_axis"],
    "LATTICE": ["strength"],
}


def _jsonable(v):
    if isinstance(v, (bool, int, str)) or v is None:
        return v
    if isinstance(v, float):
        return _r(v)
    if isinstance(v, set):
        return sorted(v)
    try:
        return [_jsonable(x) for x in v]
    except TypeError:
        return str(v)


def modifier_info(m):
    d = {"type": m.type, "name": m.name, "show_viewport": m.show_viewport,
         "show_render": m.show_render}
    for f in MOD_FIELDS.get(m.type, []):
        if hasattr(m, f):
            d[f] = _jsonable(getattr(m, f))
    if m.type == "BEVEL":
        d["angle_limit_deg"] = _r(math.degrees(m.angle_limit), 3)
        d["vertex_group"] = m.vertex_group or None
    if m.type == "BOOLEAN":
        d["object"] = m.object.name if getattr(m, "object", None) else None
        d["collection"] = m.collection.name if getattr(m, "collection", None) else None
    if m.type == "MIRROR":
        d["mirror_object"] = m.mirror_object.name if m.mirror_object else None
    if m.type == "ARRAY":
        d["offset_object"] = m.offset_object.name if m.offset_object else None
        d["start_cap"] = m.start_cap.name if m.start_cap else None
        d["end_cap"] = m.end_cap.name if m.end_cap else None
    if m.type == "NODES":
        ng = getattr(m, "node_group", None)
        d["node_group"] = ng.name if ng else None
        if ng and "smooth by angle" in ng.name.lower():
            for key in ("Input_1", "Socket_1"):
                try:
                    d["smooth_angle_deg"] = _r(math.degrees(m[key]), 3)
                    break
                except Exception:
                    pass
    if m.type == "EDGE_SPLIT":
        d["split_angle_deg"] = _r(math.degrees(m.split_angle), 3)
    if m.type == "NODES":
        d["inputs"] = gn_inputs(m)
    try:
        d["settings"] = rna_settings(m)
    except Exception:
        pass
    return d


# ---------------------------------------------------------------- mesh data
def _attr_true_count(mesh, name, domain):
    a = mesh.attributes.get(name)
    if a is None or a.domain != domain:
        return 0
    n = 0
    if a.data_type == "BOOLEAN":
        for d in a.data:
            n += 1 if d.value else 0
    elif a.data_type == "FLOAT":
        for d in a.data:
            n += 1 if d.value > 0.0 else 0
    return n


def _attr_values(mesh, name, domain):
    a = mesh.attributes.get(name)
    if a is None or a.domain != domain or a.data_type != "FLOAT":
        return []
    return [d.value for d in a.data if d.value > 0.0]


def uv_islands(bm, uv_layer):
    """Count UV islands: faces joined by an edge whose two loops share UVs."""
    faces = list(bm.faces)
    idx = {f: i for i, f in enumerate(faces)}
    parent = list(range(len(faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    eps = 1e-5
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) != 2 or e.seam:
            continue
        f1, f2 = lf[0], lf[1]
        def loop_uvs(f):
            out = {}
            for l in f.loops:
                out[l.vert.index] = l[uv_layer].uv.copy()
            return out
        u1, u2 = loop_uvs(f1), loop_uvs(f2)
        a, b = e.verts[0].index, e.verts[1].index
        if a in u1 and a in u2 and b in u1 and b in u2:
            if (u1[a] - u2[a]).length < eps and (u1[b] - u2[b]).length < eps:
                ra, rb = find(idx[f1]), find(idx[f2])
                if ra != rb:
                    parent[ra] = rb
    roots = [find(i) for i in range(len(faces))]
    return roots


def uv_stats(bm, mesh):
    out = {"layers": [l.name for l in mesh.uv_layers], "active": None}
    if not mesh.uv_layers or not bm.faces:
        return out
    out["active"] = mesh.uv_layers.active.name if mesh.uv_layers.active else mesh.uv_layers[0].name
    uv_layer = bm.loops.layers.uv.active or bm.loops.layers.uv[0]
    roots = uv_islands(bm, uv_layer)
    island_area3 = Counter()
    island_areauv = Counter()
    total3 = 0.0
    totaluv = 0.0
    tiles = set()
    minu = minv = 1e9
    maxu = maxv = -1e9
    for i, f in enumerate(bm.faces):
        a3 = f.calc_area()
        uvs = [l[uv_layer].uv for l in f.loops]
        auv = 0.0
        for k in range(1, len(uvs) - 1):
            p, q, r = uvs[0], uvs[k], uvs[k + 1]
            auv += abs((q.x - p.x) * (r.y - p.y) - (r.x - p.x) * (q.y - p.y)) * 0.5
        total3 += a3
        totaluv += auv
        island_area3[roots[i]] += a3
        island_areauv[roots[i]] += auv
        for uv in uvs:
            minu, minv = min(minu, uv.x), min(minv, uv.y)
            maxu, maxv = max(maxu, uv.x), max(maxv, uv.y)
        if uvs:
            cu = sum(uv.x for uv in uvs) / len(uvs)
            cv = sum(uv.y for uv in uvs) / len(uvs)
            tiles.add((math.floor(cu), math.floor(cv)))
    out["islands"] = len(island_area3)
    out["seams"] = sum(1 for e in bm.edges if e.seam)
    out["area_3d_m2"] = _r(total3)
    out["area_uv"] = _r(totaluv)
    out["bounds"] = [_r(minu, 4), _r(minv, 4), _r(maxu, 4), _r(maxv, 4)]
    out["tiles"] = len(tiles)
    out["packing"] = _r(totaluv / max(1, len(tiles)), 4)
    if total3 > 0 and totaluv > 0:
        out["uv_per_m"] = _r(math.sqrt(totaluv / total3), 5)
        dens = []
        for r_, a3 in island_area3.items():
            if a3 > total3 * 0.002 and island_areauv[r_] > 0:
                dens.append(math.sqrt(island_areauv[r_] / a3))
        if len(dens) > 1:
            mean = sum(dens) / len(dens)
            var = sum((d - mean) ** 2 for d in dens) / len(dens)
            out["density_cv"] = _r(math.sqrt(var) / mean, 4)
    return out


# ---------------------------------------------------------------- mesh quality (face shape, edge angles, holding loops)
QUALITY_CAP = 40000  # faces / edges sampled per object (evenly spread) so huge meshes stay fast


def mesh_quality(bm):
    """Face shape, edge-angle profile, true support-loop distances and vertex valence, on the base mesh."""
    q = {}
    faces = bm.faces
    nf = len(faces)
    if not nf:
        return q
    step = max(1, nf // QUALITY_CAP)
    aspect, skew, tri_min = [], [], []
    nonplanar = quads = zero = 0
    for i in range(0, nf, step):
        f = faces[i]
        vs = [v.co for v in f.verts]
        k = len(vs)
        lens = [(vs[j] - vs[(j + 1) % k]).length for j in range(k)]
        if f.calc_area() < 1e-12:
            zero += 1
            continue
        if min(lens) > 1e-9:
            aspect.append(max(lens) / min(lens))
        if k == 4:
            quads += 1
            worst = 0.0
            for j in range(4):
                a, b = vs[j - 1] - vs[j], vs[(j + 1) % 4] - vs[j]
                if a.length > 1e-9 and b.length > 1e-9:
                    worst = max(worst, abs(math.degrees(a.angle(b)) - 90.0))
            skew.append(worst)
            nrm = (vs[1] - vs[0]).cross(vs[2] - vs[0])
            if nrm.length > 1e-12 and abs((vs[3] - vs[0]).dot(nrm.normalized())) > 0.05 * (sum(lens) / 4):
                nonplanar += 1
        elif k == 3:
            angs = []
            for j in range(3):
                a, b = vs[j - 1] - vs[j], vs[(j + 1) % 3] - vs[j]
                if a.length > 1e-9 and b.length > 1e-9:
                    angs.append(math.degrees(a.angle(b)))
            if angs:
                tri_min.append(min(angs))
    sampled = len(range(0, nf, step))
    q["sampled_faces"] = sampled
    if aspect:
        q["aspect_median"] = _r(_pct(aspect, 0.5), 3)
        q["aspect_p90"] = _r(_pct(aspect, 0.9), 3)
    if skew:
        q["quad_skew_median"] = _r(_pct(skew, 0.5), 2)
        q["quad_skew_p90"] = _r(_pct(skew, 0.9), 2)
        q["skewed_quads"] = _r(sum(1 for s in skew if s > 30) / len(skew), 4)
    if quads:
        q["nonplanar_quads"] = _r(nonplanar / quads, 4)
    if tri_min:
        q["tri_min_angle_p10"] = _r(_pct(tri_min, 0.1), 2)
    q["zero_area_faces"] = zero
    # edge angles: how crisp or soft the form is, and how far holding loops sit from the edges they hold
    edges = bm.edges
    ne = len(edges)
    estep = max(1, ne // QUALITY_CAP)
    bands = Counter()
    hold, hold_ratio = [], []
    lens_all = [edges[i].calc_length() for i in range(0, ne, estep)]
    med = _pct(lens_all, 0.5) or 0.0
    for i in range(0, ne, estep):
        e = edges[i]
        if len(e.link_faces) != 2:
            continue
        ang = math.degrees(e.calc_face_angle(0.0))
        bands["flat" if ang < 1 else "smooth" if ang < 10 else "soft" if ang < 30 else "hard" if ang < 60 else "sharp"] += 1
        if ang >= 30:
            a, b = e.verts[0].co, e.verts[1].co
            mid = (a + b) / 2
            sides = []
            for f in e.link_faces:  # the nearer of the two neighbouring quads is the holding loop
                if len(f.verts) != 4:
                    continue
                opp = [x for x in f.edges if not (set(x.verts) & set(e.verts))]
                if opp:
                    om = (opp[0].verts[0].co + opp[0].verts[1].co) / 2
                    sides.append((om - mid).length)
            if sides:
                d = min(sides)
                hold.append(d)
                if med > 0:
                    hold_ratio.append(d / med)
    tot = sum(bands.values())
    if tot:
        q["edge_angles"] = {k: _r(v / tot, 4) for k, v in bands.items()}
    if hold:
        q["hold_distance_median"] = _r(_pct(hold, 0.5), 6)
        q["hold_distance_p10"] = _r(_pct(hold, 0.1), 6)
        q["hold_ratio_median"] = _r(_pct(hold_ratio, 0.5), 4) if hold_ratio else None
        q["held_edges"] = len(hold)
    # valence of interior vertices
    val = Counter()
    vs = bm.verts
    vstep = max(1, len(vs) // QUALITY_CAP)
    for i in range(0, len(vs), vstep):
        v = vs[i]
        if any(e.is_boundary for e in v.link_edges) or not v.link_faces:
            continue
        n = len(v.link_edges)
        val["3" if n == 3 else "4" if n == 4 else "5" if n == 5 else "6+" if n >= 6 else "2-"] += 1
    tv = sum(val.values())
    if tv:
        q["valence"] = {k: _r(v / tv, 4) for k, v in val.items()}
    return q


def pinch_stats(mesh, max_verts=300000):
    """On a subdivided result: does shading kink at poles? Each pole's normal deviation is compared with its own
    neighbours, so crisp corners (where every vertex bends) aren't mistaken for pinching."""
    if len(mesh.vertices) > max_verts:
        return {"skipped": "too dense"}
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.normal_update()
    dev = {}
    for v in bm.verts:
        if any(e.is_boundary for e in v.link_edges) or len(v.link_faces) < 3:
            continue
        n = v.normal
        dev[v.index] = max((math.degrees(n.angle(f.normal)) for f in v.link_faces if f.normal.length > 0), default=0.0)
    regular, ratios, pinched, poles = [], [], 0, 0
    for v in bm.verts:
        d = dev.get(v.index)
        if d is None:
            continue
        if len(v.link_edges) == 4:
            regular.append(d)
            continue
        poles += 1
        ring = [dev[e.other_vert(v).index] for e in v.link_edges if e.other_vert(v).index in dev]
        local = _pct(ring, 0.5) if ring else None
        if local and local > 1e-6:
            ratios.append(d / local)
            if d > 2.5 * local and d > 5.0:
                pinched += 1
    bm.free()
    out = {"poles": poles}
    if regular:
        out["regular_dev_median"] = _r(_pct(regular, 0.5), 3)
    if ratios:
        out["pinch_ratio"] = _r(_pct(ratios, 0.5), 3)
        out["pinch_ratio_p90"] = _r(_pct(ratios, 0.9), 3)
    if poles:
        out["pinched_poles"] = _r(pinched / poles, 4)
    return out


# ---------------------------------------------------------------- characters: skeletons, skinning, loops, symmetry
NAMING_HINTS = (
    ("unreal", ("pelvis", "spine_01", "upperarm_l", "thigh_l", "calf_l", "clavicle_l", "neck_01")),
    ("mixamo", ("mixamorig:", "mixamorig_")),
    ("rigify", ("DEF-", "ORG-", "MCH-")),
    ("unity", ("Hips", "Spine", "LeftUpperArm", "LeftUpLeg", "LeftArm")),
)
UPPER_ARM = ("upperarm_l", "upper_arm.l", "upper_arm_l", "leftarm", "mixamorig:leftarm", "def-upper_arm.l",
             "l_upperarm", "upperarm.l", "arm.l", "leftupperarm")


def armature_info(obj):
    arm = obj.data
    bones = list(arm.bones)
    names = [b.name for b in bones]
    low = [n.lower() for n in names]
    conv = "custom"
    for label, keys in NAMING_HINTS:
        hits = sum(1 for n in names for k in keys if (k.lower() in n.lower() if label in ("mixamo", "rigify") else n.lower() == k.lower()))
        if hits >= 2:
            conv = label
            break
    if conv == "custom" and sum(1 for n in names if n.endswith((".L", ".R", "_L", "_R", ".l", ".r", "_l", "_r"))) >= 4:
        conv = "blender-sides"

    def depth(b):
        d = 0
        while b.parent:
            d += 1
            b = b.parent
        return d
    mw = obj.matrix_world
    zs = [(mw @ b.head_local).z for b in bones] + [(mw @ b.tail_local).z for b in bones]
    d = {"bones": len(bones), "deform_bones": sum(1 for b in bones if b.use_deform),
         "naming": conv, "max_depth": max((depth(b) for b in bones), default=0),
         "height": _r(max(zs) - min(zs), 4) if zs else None, "names": names[:80],
         "pose_position": arm.pose_position, "display": arm.display_type}
    ua = next((b for b in bones if b.name.lower() in UPPER_ARM), None)
    if ua is None:
        ua = next((b for b in bones if ("upper" in b.name.lower() and "arm" in b.name.lower())
                   and b.name.lower().endswith(("l", ".l", "_l", "left"))), None)
    if ua is not None:
        v = (mw @ ua.tail_local) - (mw @ ua.head_local)
        if v.length > 1e-6:
            d["arm_angle_deg"] = _r(math.degrees(math.asin(max(-1, min(1, -v.z / v.length)))), 2)  # 0 = T-pose, ~45 = A-pose
    hb = next((b for b in bones if b.name.lower() in ("head", "mixamorig:head", "def-spine.006", "head.x", "c_head.x")), None)
    if hb is not None:
        d["head_base_z"] = _r((mw @ hb.head_local).z, 4)
    cons = Counter()
    if obj.pose:
        for pb in obj.pose.bones:
            for c in pb.constraints:
                cons[c.type] += 1
    d["constraints"] = dict(cons)
    return d


def skin_info(obj, max_verts=40000):
    """Weights on a skinned mesh: influences per vertex, unweighted share, normalisation."""
    arm_mod = next((m for m in obj.modifiers if m.type == "ARMATURE"), None)
    if arm_mod is None or not obj.vertex_groups:
        return None
    me = obj.data
    bones = set(b.name for b in arm_mod.object.data.bones) if arm_mod.object and arm_mod.object.type == "ARMATURE" else set()
    deform_idx = {g.index for g in obj.vertex_groups if not bones or g.name in bones}
    n = len(me.vertices)
    step = max(1, n // max_verts)
    infl, unweighted, unnorm, total = Counter(), 0, 0, 0
    for i in range(0, n, step):
        v = me.vertices[i]
        ws = [g.weight for g in v.groups if g.group in deform_idx and g.weight > 1e-4]
        total += 1
        infl[min(len(ws), 8)] += 1
        if not ws:
            unweighted += 1
        elif abs(sum(ws) - 1.0) > 0.02:
            unnorm += 1
    return {"armature": arm_mod.object.name if arm_mod.object else None,
            "groups": len(obj.vertex_groups), "deform_groups": len(deform_idx),
            "max_influences": max((k for k, c in infl.items() if c), default=0),
            "over_4": _r(sum(c for k, c in infl.items() if k > 4) / total, 4) if total else 0,
            "unweighted": _r(unweighted / total, 4) if total else 0,
            "not_normalised": _r(unnorm / total, 4) if total else 0,
            "influence_hist": {str(k): c for k, c in sorted(infl.items())},
            "preserve_volume": arm_mod.use_deform_preserve_volume}


def closed_loops(bm, max_faces=60000):
    """Closed edge loops through regular (valence-4) vertices, as a histogram of loop lengths (the character
    study's measure: rings round the neck, limbs, eyes and mouth)."""
    if len(bm.faces) > max_faces or len(bm.faces) < 40:
        return None
    seen = set()
    hist = Counter()

    def nxt(e, v):
        if len(v.link_edges) != 4 or any(x.is_boundary for x in v.link_edges):
            return None
        fs = set(e.link_faces)
        for e2 in v.link_edges:
            if e2 is not e and not (set(e2.link_faces) & fs):
                return e2
        return None
    for e in bm.edges:
        if e.index in seen:
            continue
        seen.add(e.index)
        n, closed = 1, False
        for start in (e.verts[0], e.verts[1]):
            cur, v = e, start
            while True:
                nx = nxt(cur, v)
                if nx is None:
                    break
                if nx.index in seen:
                    closed = nx is e
                    break
                seen.add(nx.index)
                n += 1
                v = nx.other_vert(v)
                cur = nx
            if closed:
                break
        if closed:
            hist[n] += 1
    return {str(k): c for k, c in sorted(hist.items())}


def symmetry_share(me, max_verts=60000, tol_ratio=0.002):
    """Share of vertices with a mirror partner across X (local space)."""
    from mathutils import kdtree
    n = len(me.vertices)
    if n < 20 or n > 400000:
        return None
    kd = kdtree.KDTree(n)
    for v in me.vertices:
        kd.insert(v.co, v.index)
    kd.balance()
    xs = [v.co.x for v in me.vertices]
    size = max(max(xs) - min(xs), 1e-6)
    tol = size * tol_ratio
    step = max(1, n // max_verts)
    hit = tot = 0
    for i in range(0, n, step):
        co = me.vertices[i].co
        m = co.copy()
        m.x = -m.x
        _, _, dist = kd.find(m)
        tot += 1
        hit += 1 if dist is not None and dist <= tol else 0
    return _r(hit / tot, 4) if tot else None


def sculpt_info(obj, me, st):
    """Signs of a sculpt workflow: Multires, dyntopo-style triangles with wild valence, voxel remesh, face sets, masks."""
    d = {}
    mr = next((m for m in obj.modifiers if m.type == "MULTIRES"), None)
    if mr:
        d["multires"] = {"levels": mr.levels, "sculpt_levels": mr.sculpt_levels, "render_levels": mr.render_levels,
                         "total_levels": mr.total_levels}
    names = {a.name for a in me.attributes}
    if {".sculpt_face_set", "sculpt_face_set"} & names:
        a = me.attributes.get(".sculpt_face_set") or me.attributes.get("sculpt_face_set")
        try:
            d["face_sets"] = len({x.value for x in a.data})
        except Exception:
            d["face_sets"] = True
    if {".sculpt_mask", "sculpt_mask"} & names:
        d["mask"] = True
    vs = getattr(me, "remesh_voxel_size", None)
    if vs and abs(vs - 0.1) > 1e-6:  # 0.1 is Blender's default: only a changed size says the artist voxel-remeshes
        d["voxel_size"] = _r(vs, 6)
    dims = max(obj.dimensions) if max(obj.dimensions) > 0 else 1.0
    if st.get("edge_len_median"):
        d["edge_pct_of_size"] = _r(st["edge_len_median"] / dims * 100, 4)
    dense = st["verts"] >= 100000
    trimesh = st["faces"] and st["tris"] / st["faces"] > 0.6
    wild = st.get("valence_max", 0) >= 9
    if dense and (trimesh or wild):
        d["kind"] = "dyntopo"
    elif dense and st["quad_ratio"] and st["quad_ratio"] > 0.9 and not any(m.type == "SUBSURF" for m in obj.modifiers):
        d["kind"] = "voxel-or-applied-multires"
    elif mr:
        d["kind"] = "multires"
    return d if d else None


def clearance_pass(scene_objects):
    """Garment clearance over a body: for each mesh that wraps a skinned body (Shrinkwrap target, or most of it within
    5 cm of the body), the signed distance of its vertices to the body surface."""
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    meshes = [o for o in scene_objects if o.type == "MESH" and o.visible_get() is not False]
    bodies = [o for o in meshes if any(m.type == "ARMATURE" for m in o.modifiers)
              and any(k in o.name.lower() for k in ("body", "form", "base", "skin", "torso", "mannequin"))]
    if not bodies:
        skinned = [o for o in meshes if any(m.type == "ARMATURE" for m in o.modifiers)]
        bodies = sorted(skinned, key=lambda o: -len(o.data.vertices))[:1]
    out = {}
    for body in bodies[:2]:
        bm = bmesh.new()
        bm.from_object(body, dg)
        bm.transform(body.matrix_world)
        if len(bm.verts) > 400000:
            bm.free()
            continue
        bvh = BVHTree.FromBMesh(bm)
        h = max(v.co.z for v in bm.verts) - min(v.co.z for v in bm.verts) if bm.verts else 1.0
        for o in meshes:
            if o is body or len(o.data.vertices) > 200000:
                continue
            wraps = any(m.type == "SHRINKWRAP" and m.target is body for m in o.modifiers)
            nm = o.name.lower()
            if not wraps and any(k in nm for k in ("head", "face", "eye", "teeth", "tongue", "hand", "foot", "body", "sculpt")):
                continue  # body parts sit on the body; they aren't garments
            g = bmesh.new()
            g.from_object(o, dg)
            g.transform(o.matrix_world)
            step = max(1, len(g.verts) // 3000)
            ds = []
            for i, v in enumerate(g.verts):
                if i % step:
                    continue
                hit = bvh.find_nearest(v.co)
                if hit[0] is not None:
                    p, n, _, dist = hit
                    ds.append(dist if (v.co - p).dot(n) >= 0 else -dist)
            g.free()
            if not ds:
                continue
            near = sum(1 for x in ds if -0.01 <= x <= 0.05) / len(ds)
            if not wraps and near < 0.6:
                continue
            ds.sort()
            out[o.name] = {"body": body.name, "shrinkwrap": wraps, "p10": _r(ds[len(ds) // 10], 5),
                           "median": _r(ds[len(ds) // 2], 5), "p90": _r(ds[len(ds) * 9 // 10], 5),
                           "inside": _r(sum(1 for x in ds if x < -0.001) / len(ds), 4), "body_height": _r(h, 4)}
        bm.free()
    return out


def mesh_stats(obj, depsgraph):
    me = obj.data
    st = {"verts": len(me.vertices), "edges": len(me.edges), "faces": len(me.polygons)}
    sizes = Counter(len(p.vertices) for p in me.polygons)
    st["tris"] = sizes.get(3, 0)
    st["quads"] = sizes.get(4, 0)
    st["ngons"] = sum(c for k, c in sizes.items() if k > 4)
    st["quad_ratio"] = _r(st["quads"] / st["faces"], 4) if st["faces"] else None
    st["tri_count"] = sum((k - 2) * c for k, c in sizes.items())
    st["area_m2"] = _r(sum(p.area for p in me.polygons))
    caps = {k: c for k, c in sizes.items() if k >= 6}
    if caps:  # n-gon caps tell how many segments round parts get
        st["ngon_sizes"] = {str(k): c for k, c in sorted(caps.items(), key=lambda kv: -kv[1])[:4]}
    st["smooth_faces"] = sum(1 for p in me.polygons if p.use_smooth)
    st["sharp_edges"] = _attr_true_count(me, "sharp_edge", "EDGE")
    st["seam_edges"] = sum(1 for e in me.edges if e.use_seam)
    st["crease_edges"] = _attr_true_count(me, "crease_edge", "EDGE")
    st["bevel_weight_edges"] = _attr_true_count(me, "bevel_weight_edge", "EDGE")
    bw = _attr_values(me, "bevel_weight_edge", "EDGE")
    st["bevel_weight_median"] = _r(_pct(bw, 0.5), 4) if bw else None
    cr = _attr_values(me, "crease_edge", "EDGE")
    st["crease_median"] = _r(_pct(cr, 0.5), 4) if cr else None
    st["custom_normals"] = bool(getattr(me, "has_custom_normals", False))
    st["vertex_groups"] = [vg.name for vg in obj.vertex_groups]
    st["attributes"] = sorted(a.name for a in me.attributes if not a.name.startswith("."))

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    # poles on interior vertices of quad-dominant meshes
    p3 = p5 = 0
    vmax = 0
    boundary = 0
    for v in bm.verts:
        if any(e.is_boundary for e in v.link_edges):
            boundary += 1
            continue
        n = len(v.link_edges)
        vmax = max(vmax, n)
        if n == 3:
            p3 += 1
        elif n >= 5:
            p5 += 1
    st["valence_max"] = vmax
    st["poles_3"] = p3
    st["poles_5plus"] = p5
    st["boundary_verts"] = boundary
    st["non_manifold_edges"] = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
    st["loose_parts"] = _loose_parts(bm)
    lens = [e.calc_length() for e in bm.edges]
    if lens:
        med = _pct(lens, 0.5)
        st["edge_len_median"] = _r(med)
        st["edge_len_p05"] = _r(_pct(lens, 0.05))
        st["edge_len_p10"] = _r(_pct(lens, 0.10))
        st["support_ratio"] = _r(_pct(lens, 0.10) / med, 4) if med > 0 else None
    st["uv"] = uv_stats(bm, me)
    organic = any(m.type in ("ARMATURE", "MULTIRES") for m in obj.modifiers) or any(
        k in obj.name.lower() for k in ("head", "face", "body", "torso", "hand", "foot", "char", "base_mesh", "basemesh"))
    if organic:
        try:
            st["closed_loops"] = closed_loops(bm)
        except Exception as exc:  # pragma: no cover
            st["closed_loops"] = {"error": str(exc)}
    try:
        st["quality"] = mesh_quality(bm)
    except Exception as exc:  # pragma: no cover
        st["quality"] = {"error": str(exc)}
    bm.free()

    try:
        sk = sculpt_info(obj, me, st)
        if sk:
            st["sculpt"] = sk
        if organic or (sk and sk.get("kind")):
            st["symmetry"] = symmetry_share(me)
        sk_info = skin_info(obj)
        if sk_info:
            st["skin"] = sk_info
    except Exception as exc:  # pragma: no cover
        st["character_error"] = str(exc)
    if me.shape_keys:
        st["shape_key_names"] = [k.name for k in me.shape_keys.key_blocks][:80]
    # after modifiers
    try:
        ev = obj.evaluated_get(depsgraph)
        em = ev.to_mesh()
        st["eval_tri_count"] = sum(len(p.vertices) - 2 for p in em.polygons)
        if any(m.type == "SUBSURF" and m.show_viewport for m in obj.modifiers):
            try:
                st["pinch"] = pinch_stats(em)
            except Exception as exc:  # pragma: no cover
                st["pinch"] = {"error": str(exc)}
        st["eval_verts"] = len(em.vertices)
        ev.to_mesh_clear()
    except Exception as exc:  # pragma: no cover
        st["eval_error"] = str(exc)
    return st


def _loose_parts(bm):
    seen = set()
    parts = 0
    for v in bm.verts:
        if v.index in seen:
            continue
        parts += 1
        stack = [v]
        seen.add(v.index)
        while stack:
            cur = stack.pop()
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
    return parts


# ---------------------------------------------------------------- objects
def origin_in_bbox(obj):
    """Where the origin sits inside the object's local bounding box, 0..1 per axis."""
    xs = [c[0] for c in obj.bound_box]
    ys = [c[1] for c in obj.bound_box]
    zs = [c[2] for c in obj.bound_box]
    out = []
    for lo, hi in ((min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))):
        span = hi - lo
        out.append(_r((0 - lo) / span, 3) if span > 1e-9 else 0.5)
    return out


def object_info(obj, depsgraph):
    d = {
        "name": obj.name, "type": obj.type,
        "data": obj.data.name if obj.data else None,
        "data_users": obj.data.users if obj.data else 0,
        "parent": obj.parent.name if obj.parent else None,
        "parent_type": obj.parent_type, "parent_bone": obj.parent_bone or None,
        "collections": [c.name for c in obj.users_collection],
        "hide_viewport": obj.hide_get() if hasattr(obj, "hide_get") else False,
        "hide_render": obj.hide_render,
        "display_type": obj.display_type,
        "location": _vec(obj.location),
        "rotation_deg": [_r(math.degrees(a), 3) for a in obj.rotation_euler],
        "scale": _vec(obj.scale),
        "dimensions": _vec(obj.dimensions),
        "instance_type": obj.instance_type,
        "instance_collection": obj.instance_collection.name if obj.instance_collection else None,
        "is_asset": obj.asset_data is not None,
        "fake_user": obj.use_fake_user,
        "library": obj.library.filepath if obj.library else None,
        "materials": [s.material.name if s.material else None for s in obj.material_slots],
        "modifiers": [modifier_info(m) for m in obj.modifiers],
        "custom_props": sorted(k for k in obj.keys() if not k.startswith("_")),
        "constraints": [c.type for c in obj.constraints],
        "animated": bool(obj.animation_data and (obj.animation_data.action or obj.animation_data.drivers)),
        "drivers": len(obj.animation_data.drivers) if obj.animation_data else 0,
    }
    if obj.type == "MESH":
        me = obj.data
        try:
            zs = [(obj.matrix_world @ __import__("mathutils").Vector(c)).z for c in obj.bound_box]
            d["world_z"] = [_r(min(zs), 4), _r(max(zs), 4)]
        except Exception:
            pass
        d["color_attributes"] = [f"{a.name}:{a.domain}" for a in getattr(me, "color_attributes", [])]
        d["shape_keys"] = len(me.shape_keys.key_blocks) if me.shape_keys else 0
        d["particle_systems"] = [ps.settings.type for ps in obj.particle_systems]
    if obj.type in {"MESH", "CURVE", "FONT"}:
        try:
            d["origin_in_bbox"] = origin_in_bbox(obj)
        except Exception:
            pass
    if obj.type == "MESH":
        d["mesh"] = mesh_stats(obj, depsgraph)
    elif obj.type == "LIGHT":
        L = obj.data
        d["light"] = {"type": L.type, "energy": _r(L.energy, 3), "color": _vec(L.color),
                      "size": _r(getattr(L, "shadow_soft_size", 0), 4), "use_shadow": getattr(L, "use_shadow", None)}
        if L.type == "SPOT":
            d["light"]["spot_size_deg"] = _r(math.degrees(L.spot_size), 2)
        if L.type == "AREA":
            d["light"]["shape"] = L.shape
            d["light"]["area_size"] = _r(L.size, 4)
        if L.type == "SUN":
            d["light"]["angle_deg"] = _r(math.degrees(L.angle), 3)
    elif obj.type == "ARMATURE":
        try:
            d["armature"] = armature_info(obj)
        except Exception as exc:  # pragma: no cover
            d["armature"] = {"error": str(exc)}
        d["children_on_bones"] = sum(1 for c in obj.children if c.parent_type == "BONE")
    elif obj.type == "CAMERA":
        c = obj.data
        d["camera"] = {"type": c.type, "lens": _r(c.lens, 3), "sensor_width": _r(c.sensor_width, 3),
                       "ortho_scale": _r(c.ortho_scale, 4), "dof": c.dof.use_dof,
                       "clip": [_r(c.clip_start, 4), _r(c.clip_end, 2)]}
    elif obj.type == "EMPTY":
        d["empty"] = {"display": obj.empty_display_type, "size": _r(obj.empty_display_size),
                      "children": len(obj.children),
                      "image": obj.data.name if obj.empty_display_type == "IMAGE" and obj.data else None}
    elif obj.type == "CURVE":
        c = obj.data
        d["curve"] = {"bevel_depth": _r(c.bevel_depth), "bevel_resolution": c.bevel_resolution,
                      "resolution_u": c.resolution_u, "extrude": _r(c.extrude),
                      "bevel_mode": getattr(c, "bevel_mode", None),
                      "splines": len(c.splines), "fill_mode": c.fill_mode}
    return d


def collection_tree(col, depth=0):
    return {"name": col.name, "objects": len(col.objects),
            "hide_render": col.hide_render,
            "is_asset": col.asset_data is not None,
            "children": [collection_tree(c, depth + 1) for c in col.children]}


# ---------------------------------------------------------------- full settings (any modifier, node, light...)
SKIP_PROPS = {"rna_type", "name", "type", "show_viewport", "show_render", "show_in_editmode", "show_on_cage",
              "show_expanded", "is_active", "is_override_data", "use_apply_on_spline", "persistent_uid",
              "execution_time", "use_pin_to_last", "is_override_data_editable", "bl_idname", "bl_label",
              "bl_description", "bl_icon", "bl_static_type", "bl_width_default", "bl_width_min", "bl_width_max",
              "bl_height_default", "bl_height_min", "bl_height_max", "internal_links", "warning_propagation",
              "color_tag", "debug_zone_body_lazy_function_graph", "debug_zone_lazy_function_graph"}
# editor-only properties of nodes (where the node sits, how it's drawn), not how it shades
NODE_SKIP = {"location", "location_absolute", "width", "height", "dimensions", "label", "parent", "select",
             "show_options", "show_preview", "hide", "mute", "show_texture", "use_custom_color", "color"}


def rna_settings(struct, skip=()):
    """Every plain property of an RNA struct (enums, numbers, vectors, flags, and names of linked data)."""
    out = {}
    for p in struct.bl_rna.properties:
        k = p.identifier
        if k in SKIP_PROPS or k in skip or p.type == "COLLECTION" or k.startswith(("open_", "show_", "is_")) \
                or k in ("bake_directory", "bake_target"):
            continue
        try:
            v = getattr(struct, k)
        except Exception:
            continue
        if p.type == "POINTER":
            if v is None:
                continue
            nm = getattr(v, "name", None)
            if isinstance(nm, str):
                out[k] = nm
            continue
        jv = _jsonable(v)
        if isinstance(jv, str) and len(jv) > 200:
            continue
        out[k] = jv
    return out


def _sock_value(s):
    v = getattr(s, "default_value", None)
    if v is None:
        return None
    if hasattr(v, "name") and isinstance(getattr(v, "name"), str):
        return v.name
    jv = _jsonable(v)
    if isinstance(jv, list):
        jv = jv[:4]
    return jv


# ---------------------------------------------------------------- node trees
PBR_INPUTS = ("Base Color", "Metallic", "Roughness", "IOR", "Alpha", "Normal", "Specular IOR Level",
              "Transmission Weight", "Coat Weight", "Coat Roughness", "Sheen Weight", "Subsurface Weight",
              "Emission Color", "Emission Strength", "Anisotropic")


def _upstream(sock, depth=0, max_depth=5):
    """A short signature of what feeds a socket, e.g. 'TEX_NOISE>VALTORGB'."""
    if not sock.is_linked or depth >= max_depth:
        return []
    link = sock.links[0]
    n = link.from_node
    name = n.type if n.type != "GROUP" else "GROUP:" + (n.node_tree.name if n.node_tree else "?")
    if n.type == "REROUTE":
        return _upstream(n.inputs[0], depth, max_depth)
    best = []
    for s in n.inputs:
        if s.is_linked:
            up = _upstream(s, depth + 1, max_depth)
            if len(up) > len(best):
                best = up
    return best + [name]


def node_info(n):
    d = {"type": n.type}
    if n.type == "GROUP":
        d["group"] = n.node_tree.name if n.node_tree else None
    if n.type == "TEX_IMAGE":
        img = n.image
        if img:
            d["image"] = img.name
            d["size"] = list(img.size)
            d["colorspace"] = img.colorspace_settings.name
            d["source"] = img.source
        d["projection"] = n.projection
        d["interpolation"] = n.interpolation
        d["extension"] = n.extension
    elif n.type == "TEX_ENVIRONMENT" and n.image:
        d["image"] = n.image.name
        d["size"] = list(n.image.size)
    elif n.type == "VALTORGB":
        cr = n.color_ramp
        d["interpolation"] = cr.interpolation
        d["stops"] = [[_r(e.position, 3), _vec(e.color)[:3]] for e in cr.elements][:8]
    elif n.type in ("ATTRIBUTE",):
        d["attribute"] = n.attribute_name
    elif n.type == "VERTEX_COLOR":
        d["layer"] = n.layer_name
    elif n.type == "UVMAP":
        d["uv_map"] = n.uv_map
    else:
        try:
            st = rna_settings(n, skip=NODE_SKIP)
            if st:
                d["settings"] = st
        except Exception:
            pass
    vals = {}
    for s in n.inputs:
        if not s.is_linked and s.enabled and not s.hide:
            v = _sock_value(s)
            if v is not None:
                vals[s.name] = v
    if vals and n.type not in ("OUTPUT_MATERIAL", "OUTPUT_WORLD", "GROUP_INPUT", "GROUP_OUTPUT", "REROUTE"):
        d["inputs"] = dict(list(vals.items())[:24])
    used_out = [s.name for s in n.outputs if s.is_linked]
    if used_out and n.type in ("TEX_COORD", "NEW_GEOMETRY", "OBJECT_INFO", "LIGHT_PATH", "INPUT_POSITION"):
        d["outputs_used"] = used_out
    return d


def tree_info(nt, seen=None, depth=0):
    """Census of a node tree: node types, settings, links, groups (followed once), outputs."""
    seen = seen if seen is not None else set()
    out = {"name": nt.name, "kind": nt.bl_idname, "node_count": len(nt.nodes)}
    types = Counter(n.type for n in nt.nodes if n.type not in ("REROUTE", "FRAME"))
    out["node_types"] = dict(types)
    out["nodes"] = [node_info(n) for n in nt.nodes if n.type not in ("REROUTE", "FRAME")][:120]
    links = Counter()
    for l in nt.links:
        if l.is_valid and not l.is_muted:
            links[f"{l.from_node.type}.{l.from_socket.name}>{l.to_node.type}.{l.to_socket.name}"] += 1
    out["links"] = dict(links.most_common(80))
    groups = sorted({n.node_tree.name for n in nt.nodes if n.type == "GROUP" and n.node_tree})
    if groups:
        out["groups"] = groups
        if depth < 3:
            out["group_trees"] = []
            for n in nt.nodes:
                if n.type == "GROUP" and n.node_tree and n.node_tree.name not in seen:
                    seen.add(n.node_tree.name)
                    out["group_trees"].append(tree_info(n.node_tree, seen, depth + 1))
    return out


def material_info(mat):
    d = {"name": mat.name, "users": mat.users, "use_nodes": mat.use_nodes,
         "viewport": {"color": _vec(mat.diffuse_color)[:3], "metallic": _r(mat.metallic, 3),
                      "roughness": _r(mat.roughness, 3)}}
    for k in ("surface_render_method", "blend_method", "use_backface_culling", "displacement_method",
              "use_transparency_overlap", "use_screen_refraction", "pass_index", "use_thickness_from_shadow"):
        if hasattr(mat, k):
            d[k] = _jsonable(getattr(mat, k))
    if mat.use_nodes and mat.node_tree:
        nt = mat.node_tree
        info = tree_info(nt)
        d["tree"] = info
        d["nodes"] = info["node_types"]
        d["images"] = sorted({n.image.name for n in nt.nodes if n.type == "TEX_IMAGE" and n.image})
        if info.get("groups"):
            d["groups"] = info["groups"]
        out_node = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None) or \
            next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if out_node:
            d["output"] = {s.name: ">".join(_upstream(s)) for s in out_node.inputs if s.is_linked}
        pr = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"]
        if pr:
            p = pr[0]
            pbr, fed = {}, {}
            for name in PBR_INPUTS:
                s = p.inputs.get(name)
                if s is None:
                    continue
                if s.is_linked:
                    fed[name] = ">".join(_upstream(s))
                else:
                    v = _sock_value(s)
                    if v is not None and name != "Normal":
                        pbr[name] = v
            d["principled"] = {"values": pbr, "linked": fed, "count": len(pr),
                               "distribution": getattr(p, "distribution", None),
                               "subsurface_method": getattr(p, "subsurface_method", None)}
        shaders = Counter(n.type for n in nt.nodes if n.type.startswith("BSDF_") or n.type in
                          ("EMISSION", "MIX_SHADER", "ADD_SHADER", "HOLDOUT", "SUBSURFACE_SCATTERING",
                           "PRINCIPLED_VOLUME", "VOLUME_ABSORPTION", "VOLUME_SCATTER", "BACKGROUND", "EEVEE_SPECULAR"))
        d["shaders"] = dict(shaders)
    return d


def world_info(w):
    if w is None:
        return None
    d = {"name": w.name, "use_nodes": w.use_nodes, "color": _vec(w.color)[:3]}
    if w.use_nodes and w.node_tree:
        info = tree_info(w.node_tree)
        d["tree"] = info
        kinds = set(info["node_types"])
        d["kind"] = ("hdri" if "TEX_ENVIRONMENT" in kinds else "sky" if "TEX_SKY" in kinds else
                     "gradient" if kinds & {"TEX_GRADIENT", "VALTORGB"} else "color")
        bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg:
            d["strength"] = _sock_value(bg.inputs["Strength"]) if not bg.inputs["Strength"].is_linked else "linked"
            if not bg.inputs["Color"].is_linked:
                d["background_color"] = _sock_value(bg.inputs["Color"])
        env = [n.image.name for n in w.node_tree.nodes if n.type == "TEX_ENVIRONMENT" and n.image]
        if env:
            d["hdri"] = env
    else:
        d["kind"] = "color"
    return d


def render_info(scene):
    r = scene.render
    vs = scene.view_settings
    d = {"engine": r.engine, "resolution": [r.resolution_x, r.resolution_y, r.resolution_percentage],
         "film_transparent": r.film_transparent, "fps": r.fps,
         "view_transform": vs.view_transform, "look": vs.look, "exposure": _r(vs.exposure, 3),
         "gamma": _r(vs.gamma, 3), "display_device": scene.display_settings.display_device,
         "use_curve_mapping": vs.use_curve_mapping}
    try:
        if r.engine == "CYCLES":
            c = scene.cycles
            d["samples"] = c.samples
            d["denoise"] = c.use_denoising
            d["device"] = c.device
        elif "EEVEE" in r.engine:
            e = scene.eevee
            d["samples"] = getattr(e, "taa_render_samples", None)
            for k in ("use_raytracing", "use_shadows", "use_gtao", "use_bloom", "use_ssr"):
                if hasattr(e, k):
                    d[k] = getattr(e, k)
    except Exception:
        pass
    try:
        if scene.use_nodes and scene.node_tree:
            d["compositor"] = tree_info(scene.node_tree)
    except Exception:
        pass
    return d


def rna_defaults(struct):
    """Blender's own default for each plain property (to tell the artist's choices from untouched settings)."""
    out = {}
    for p in struct.bl_rna.properties:
        k = p.identifier
        if k in SKIP_PROPS or p.type in ("POINTER", "COLLECTION") or k.startswith(("open_", "show_", "is_")):
            continue
        try:
            if getattr(p, "is_array", False) or getattr(p, "array_length", 0) > 0:
                out[k] = _jsonable(list(p.default_array))
            elif p.type == "ENUM":
                out[k] = sorted(p.default_flag) if p.is_enum_flag else p.default
            else:
                out[k] = _jsonable(p.default)
        except Exception:
            pass
    return out


def gn_inputs(m):
    """Geometry Nodes modifier: the group's exposed inputs and the values set on this modifier."""
    ng = m.node_group
    out = {}
    if not ng:
        return out
    try:
        items = [i for i in ng.interface.items_tree if getattr(i, "item_type", "") == "SOCKET" and i.in_out == "INPUT"]
    except Exception:
        items = []
    for it in items:
        ident = it.identifier
        if it.socket_type == "NodeSocketGeometry":
            continue
        v = None
        props = getattr(m, "properties", None)  # Blender 5: modifier.properties.inputs.<Socket_N>.value
        sock = getattr(getattr(props, "inputs", None), ident, None) if props is not None else None
        if sock is not None:
            if getattr(sock, "type", "") == "ATTRIBUTE" and getattr(sock, "attribute_name", ""):
                out[it.name] = "attribute:" + sock.attribute_name
                continue
            v = getattr(sock, "value", None)
        else:  # Blender 4: modifier["Socket_N"]
            try:
                v = m[ident]
            except Exception:
                continue
        if hasattr(v, "name"):
            v = v.name
        elif hasattr(v, "to_list"):
            v = v.to_list()
        elif hasattr(v, "__len__") and not isinstance(v, str):
            v = [_r(x) if isinstance(x, float) else x for x in v]
        elif isinstance(v, float):
            v = _r(v)
        out[it.name] = v
    return out


def analyse():
    """Return the analysis document for the open file."""
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    us = scene.unit_settings
    doc = {
        "analyser_version": VERSION,
        "blender_version": bpy.app.version_string,
        "file": os.path.basename(bpy.data.filepath),
        "scene": {"name": scene.name, "unit_system": us.system, "scale_length": _r(us.scale_length),
                  "length_unit": us.length_unit, "render_engine": scene.render.engine,
                  "frame_end": scene.frame_end},
        "collections": collection_tree(scene.collection),
        "objects": [],
        "materials": [material_info(m) for m in bpy.data.materials if m.users],
        "images": [{"name": i.name, "size": list(i.size), "source": i.source,
                    "packed": i.packed_file is not None} for i in bpy.data.images
                   if i.users and i.type == "IMAGE"],
        "libraries": [l.filepath for l in bpy.data.libraries],
        "node_groups": sorted(g.name for g in bpy.data.node_groups if g.users),
        "geometry_node_groups": [tree_info(g) for g in bpy.data.node_groups
                                 if g.bl_idname == "GeometryNodeTree" and g.users][:40],
        "world": world_info(scene.world),
        "render": render_info(scene),
        "text_blocks": sorted(t.name for t in bpy.data.texts),
    }
    for obj in scene.objects:
        try:
            doc["objects"].append(object_info(obj, depsgraph))
        except Exception as exc:
            doc["objects"].append({"name": obj.name, "type": obj.type, "error": str(exc)})
    # objects that live only inside collections used as instances (kit libraries)
    in_scene = {o.name for o in scene.objects}
    # library files often keep pieces outside the scene: in unlinked collections or as fake-user objects
    extra = [o for o in bpy.data.objects if o.name not in in_scene and o.library is None]
    doc["objects_outside_scene"] = len(extra)
    seen_types, defaults = set(), {}
    for o in bpy.data.objects:
        for m in getattr(o, "modifiers", []):
            if m.type not in seen_types:
                seen_types.add(m.type)
                try:
                    defaults[m.type] = rna_defaults(m)
                except Exception:
                    pass
    doc["modifier_rna_defaults"] = defaults
    try:
        doc["clearance"] = clearance_pass(list(scene.objects))
    except Exception as exc:  # pragma: no cover
        doc["clearance"] = {"error": str(exc)}
    doc["actions"] = [{"name": a.name, "frames": [_r(x, 1) for x in a.frame_range]} for a in bpy.data.actions][:60]
    for obj in extra[:400]:
        try:
            info = object_info(obj, depsgraph)
            info["outside_scene"] = True
            doc["objects"].append(info)
        except Exception:
            pass
    return doc


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        print("usage: blender -b FILE --python analyse_blend.py -- OUT.json")
        return
    out_path = argv[0]
    doc = analyse()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    print("FORGE_ANALYSIS_OK", out_path, len(doc["objects"]), "objects")


if __name__ == "__main__":
    main()
