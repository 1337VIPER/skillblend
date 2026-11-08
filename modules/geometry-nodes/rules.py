"""Measured rules: which Geometry Nodes setups the artist builds and what they use them for."""
from collections import Counter, defaultdict

PURPOSES = [
    ({"CURVE_TO_MESH", "CURVE_PRIMITIVE_CIRCLE", "SET_CURVE_RADIUS", "RESAMPLE_CURVE", "FILL_CURVE"},
     "pipes, cables and profiles swept along curves"),
    ({"INSTANCE_ON_POINTS", "REALIZE_INSTANCES", "COLLECTION_INFO", "OBJECT_INFO"}, "instancing parts (kitbash, arrays)"),
    ({"DISTRIBUTE_POINTS_ON_FACES"}, "scattering details over surfaces"),
    ({"MESH_BOOLEAN"}, "procedural booleans"),
    ({"EXTRUDE_MESH", "SUBDIVIDE_MESH", "SUBDIVISION_SURFACE", "MESH_PRIMITIVE_CUBE", "MESH_PRIMITIVE_CYLINDER",
      "MESH_PRIMITIVE_GRID", "MESH_LINE"}, "building meshes procedurally"),
    ({"SET_POSITION"}, "deforming / displacing geometry"),
    ({"STORE_NAMED_ATTRIBUTE"}, "writing attributes for shading or export"),
    ({"SET_MATERIAL"}, "assigning materials in nodes"),
    ({"SET_SHADE_SMOOTH"}, "shading control"),
]


def _gn_mods(doc, L):
    for o in L.objects(doc, include_outside=False):
        for m in o.get("modifiers", []):
            if m["type"] == "NODES" and m.get("node_group") and not L.is_smooth_group(m["node_group"]):
                yield o, m


def rules(ctx):
    L, r = ctx.lib, ctx.result
    users = Counter()
    inputs = defaultdict(lambda: defaultdict(list))
    objtypes = defaultdict(Counter)
    trees = {}
    for d in ctx.files:
        for g in d.get("geometry_node_groups", []):
            if not L.is_smooth_group(g["name"]):
                trees.setdefault(g["name"], g)
        for o, m in _gn_mods(d, L):
            users[m["node_group"]] += 1
            objtypes[m["node_group"]][o["type"]] += 1
            for k, v in (m.get("inputs") or {}).items():
                inputs[m["node_group"]][k].append(v)
    if not users:
        return r
    r.number("gn_groups", [g for g, _ in users.most_common(12)], f"{sum(users.values())} Geometry Nodes modifiers")
    census = Counter()
    for name in users:
        census.update(L.tree_types(trees.get(name)))
    for u in L.UTIL_NODES:
        census.pop(u, None)
    purposes = []
    for types, label in PURPOSES:
        hits = sum(census.get(t, 0) for t in types)
        if hits:
            purposes.append((label, hits))
    purposes.sort(key=lambda x: -x[1])
    r.number("gn_purposes", [p for p, _ in purposes])
    r.headline("Geometry Nodes are used for " + (", ".join(p for p, _ in purposes[:3]) if purposes else "custom setups")
               + f" ({len(users)} group{'s' if len(users) != 1 else ''}).")
    for g, c in users.most_common(8):
        on = ", ".join(f"{t.lower()} {n}" for t, n in objtypes[g].most_common())
        tt = L.tree_types(trees.get(g))
        for u in L.UTIL_NODES:
            tt.pop(u, None)
        nodes = ", ".join(L.node_name(t) for t, _ in tt.most_common(6))
        ins = inputs.get(g, {})
        typical = []
        for k, vs in list(ins.items())[:6]:
            nums = [v for v in vs if isinstance(v, (int, float)) and not isinstance(v, bool)]
            typical.append(f"{k} {L.fmt(L.median(nums))}" if nums else f"{k} {L.mode(vs)}")
        r.rule(f"`{g}` on {c} object(s) ({on}): {nodes or 'nodes not readable'}"
               + (f"; inputs usually {', '.join(typical)}" if typical else "") + ".")
    if census:
        r.rule("Nodes used across the setups: " + ", ".join(f"{L.node_name(t)} {n}" for t, n in census.most_common(12)) + ".")
    return r


def detect(doc, L):
    n = sum(1 for _ in _gn_mods(doc, L))
    return f"{n} Geometry Nodes modifier(s)" if n else None
