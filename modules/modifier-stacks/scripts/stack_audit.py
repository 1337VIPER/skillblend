"""Study how a .blend was built: per object, its modifier stack in order with the settings that matter, base and
evaluated triangles, materials, sharp/seam/crease use, UVs, unapplied or negative scale, and kitbash-looking mesh
names. Read-only; run it on a COPY of someone else's file:

  blender.exe -b --factory-startup copy.blend --python stack_audit.py -- [out.json]

Prints a readable table plus a summary (bevel width ladder, stack patterns, materials, total tris) and writes the
full JSON if a path is given. The report is the start of a study; the modifier-stacks module shows how one study turned
into rules."""
import bpy, json, math, sys
from collections import Counter

KEEP = {"BEVEL": ("width", "segments", "profile", "limit_method", "angle_limit", "offset_type", "use_clamp_overlap", "harden_normals"),
        "SUBSURF": ("levels", "render_levels", "use_creases"),
        "BOOLEAN": ("operation", "solver", "object", "collection"),
        "SOLIDIFY": ("thickness", "offset", "use_even_offset", "use_rim"),
        "MIRROR": ("use_axis", "use_clip", "mirror_object"),
        "ARRAY": ("count", "relative_offset_displace", "use_object_offset", "offset_object"),
        "SKIN": ("use_smooth_shade",), "WEIGHTED_NORMAL": ("weight", "keep_sharp"),
        "SCREW": ("steps", "angle", "screw_offset"), "NODES": ("node_group",)}


def val(v):
    if hasattr(v, "name"):
        return v.name
    if isinstance(v, float):
        return round(v, 5)
    if hasattr(v, "__len__") and not isinstance(v, str):
        return [val(x) for x in v]
    return v


def main():
    out = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv and len(sys.argv) > sys.argv.index("--") + 1 else ""
    dg = bpy.context.evaluated_depsgraph_get()
    rows, widths, patterns, total = {}, Counter(), Counter(), 0
    for o in bpy.data.objects:
        if o.type not in ("MESH", "CURVE"):
            continue
        r = {"type": o.type, "data": o.data.name, "scale": [round(s, 3) for s in o.scale],
             "display": o.display_type, "visible": o.visible_get(), "mats": [s.material.name if s.material else None for s in o.material_slots],
             "stack": []}
        for m in o.modifiers:
            d = {"type": m.type}
            for k in KEEP.get(m.type, ()):
                if hasattr(m, k):
                    d[k] = val(getattr(m, k))
            if m.type == "BEVEL":
                d["angle_limit"] = round(math.degrees(m.angle_limit), 1); widths[round(m.width, 5)] += 1
            r["stack"].append(d)
        patterns[" > ".join(d["type"] for d in r["stack"]) or "(none)"] += 1
        if o.type == "MESH":
            me = o.data
            r.update(base_tris=sum(len(p.vertices) - 2 for p in me.polygons), ngons=sum(len(p.vertices) > 4 for p in me.polygons),
                     sharp=sum(e.use_edge_sharp for e in me.edges), seams=sum(e.use_seam for e in me.edges), uv=len(me.uv_layers))
        try:
            ev = o.evaluated_get(dg); em = ev.to_mesh(); r["eval_tris"] = sum(len(p.vertices) - 2 for p in em.polygons); ev.to_mesh_clear()
        except Exception:
            r["eval_tris"] = 0
        if o.visible_get() and o.display_type not in ("WIRE", "BOUNDS"):
            total += r["eval_tris"]
        rows[o.name] = r
    print(f"\n{'object':24s} {'base':>7s} {'eval':>8s}  stack")
    for n, r in sorted(rows.items(), key=lambda kv: -kv[1]["eval_tris"]):
        flag = (" [cutter]" if r["display"] == "WIRE" else "") + (" [neg-scale]" if any(s < 0 for s in r["scale"]) else "") \
            + (" [unapplied-scale]" if any(abs(abs(s) - 1) > 1e-3 for s in r["scale"]) else "")
        print(f"{n:24s} {r.get('base_tris', 0):>7d} {r['eval_tris']:>8d}  {' > '.join(d['type'] for d in r['stack'])}{flag}  data={r['data']}")
    print("\nbevel widths:", dict(widths))
    print("stack patterns:", dict(patterns.most_common()))
    mats = {}
    for m in bpy.data.materials:
        if m.users and m.use_nodes:
            p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if p:
                mats[m.name] = {"base": val(p.inputs["Base Color"].default_value)[:3], "metal": val(p.inputs["Metallic"].default_value),
                                "rough": val(p.inputs["Roughness"].default_value)}
            else:
                mats[m.name] = [n.type for n in m.node_tree.nodes]
    print("materials:", json.dumps(mats))
    print("TOTAL visible eval tris:", total)
    if out:
        json.dump({"objects": rows, "bevel_widths": {str(k): v for k, v in widths.items()}, "patterns": dict(patterns),
                   "materials": mats, "total_tris": total}, open(out, "w"), indent=1)


main()
