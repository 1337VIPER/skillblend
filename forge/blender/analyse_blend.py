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

VERSION = 2


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
    boundary = 0
    for v in bm.verts:
        if any(e.is_boundary for e in v.link_edges):
            boundary += 1
            continue
        n = len(v.link_edges)
        if n == 3:
            p3 += 1
        elif n >= 5:
            p5 += 1
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
    bm.free()

    # after modifiers
    try:
        ev = obj.evaluated_get(depsgraph)
        em = ev.to_mesh()
        st["eval_tri_count"] = sum(len(p.vertices) - 2 for p in em.polygons)
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
    }
    if obj.type in {"MESH", "CURVE", "FONT"}:
        try:
            d["origin_in_bbox"] = origin_in_bbox(obj)
        except Exception:
            pass
    if obj.type == "MESH":
        d["mesh"] = mesh_stats(obj, depsgraph)
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


def material_info(mat):
    d = {"name": mat.name, "users": mat.users, "use_nodes": mat.use_nodes}
    if mat.use_nodes and mat.node_tree:
        types = Counter(n.type for n in mat.node_tree.nodes)
        d["nodes"] = dict(types)
        d["images"] = sorted({n.image.name for n in mat.node_tree.nodes
                              if n.type == "TEX_IMAGE" and n.image})
        groups = sorted({n.node_tree.name for n in mat.node_tree.nodes
                         if n.type == "GROUP" and n.node_tree})
        if groups:
            d["groups"] = groups
    return d


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
