"""Measured rules: which modifiers are stacked, and in what order."""
from collections import Counter, defaultdict


def global_order(stacks, default=()):
    """One order for all modifier types: A goes before B when the files put A first more often.

    A topological sort of those majority votes; ties go to the type that sits higher in its
    stacks on average, then to the generic default order.
    """
    before = defaultdict(int)
    types = Counter()
    pos = defaultdict(list)
    for s in stacks:
        seen = []
        for i, t in enumerate(s):
            types[t] += 1
            pos[t].append(i / max(1, len(s) - 1))
            for p in seen:
                if p != t:
                    before[(p, t)] += 1
            seen.append(t)
    rank = {t: i for i, t in enumerate(default)}
    def key(t):
        return (sum(pos[t]) / len(pos[t]), rank.get(t, len(rank)), t)
    must = {t: {a for a in types if before[(a, t)] > before[(t, a)]} for t in types}
    order, left = [], set(types)
    while left:
        ready = [t for t in left if not (must[t] & left)] or list(left)  # a cycle: take the best-placed
        nxt = min(ready, key=key)
        order.append(nxt)
        left.discard(nxt)
    return order, before, types


NAME_KEYS = {"target", "object", "vertex_group", "collection", "node_group", "offset_object", "mirror_object",
             "start_cap", "end_cap", "auxiliary_target", "subtarget", "uv_layer", "texture", "texture_coords_object",
             "origin", "center", "armature", "curve", "lattice", "invert_vertex_group", "material", "attribute_name",
             "uvlayer_name", "vertex_group_a", "vertex_group_b", "mask_vertex_group", "rest_source", "shape",
             "edge_weight", "vertex_weight", "bone_from", "bone_to", "object_from", "object_to", "projector_count"}
NICE_TYPE = {"SUBSURF": "Subdivision Surface", "WEIGHTED_NORMAL": "Weighted Normal", "NODES": "Geometry Nodes",
             "EDGE_SPLIT": "Edge Split", "SIMPLE_DEFORM": "Simple Deform", "DATA_TRANSFER": "Data Transfer",
             "CORRECTIVE_SMOOTH": "Corrective Smooth", "SURFACE_DEFORM": "Surface Deform", "MESH_DEFORM": "Mesh Deform"}


PRIORITY = ["width", "segments", "levels", "render_levels", "thickness", "offset", "count", "angle_limit", "split_angle",
            "wrap_method", "wrap_mode", "solver", "operation", "limit_method", "profile", "use_even_offset", "use_rim",
            "use_clip", "use_axis", "relative_offset_displace", "keep_sharp", "weight", "mode", "harden_normals",
            "use_clamp_overlap", "miter_outer", "use_creases", "quality", "steps", "angle", "decimate_type", "ratio"]


def _same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) <= 1e-4 * max(1.0, abs(float(b)))
        except (TypeError, ValueError):
            return False
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return all(_same(x, y) for x, y in zip(a, b))
    return a == b


def modifier_dictionary(ctx, L):
    """For every modifier type in the project: how often, and the artist's typical value for every setting."""
    import json
    insts = defaultdict(list)
    defaults = {}
    for d in ctx.all_files:
        defaults.update(d.get("modifier_rna_defaults") or {})
        for o in L.objects(d, include_outside=True):
            if o.get("type") not in ("MESH", "CURVE", "FONT", "CURVES"):
                continue
            for m in o.get("modifiers", []):
                if m["type"] == "NODES" and L.is_smooth_group(m.get("node_group")):
                    continue
                insts[m["type"]].append(m)
    table, typical_all = [], {}
    for t, ms in sorted(insts.items(), key=lambda kv: -len(kv[1])):
        keys = set()
        for m in ms:
            keys |= set((m.get("settings") or {}).keys())
        typical, changed = {}, []
        for k in sorted(keys - NAME_KEYS):
            vals = [(m.get("settings") or {}).get(k) for m in ms if k in (m.get("settings") or {})]
            if not vals:
                continue
            nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if nums and len(nums) == len(vals) and any(isinstance(v, float) for v in nums):
                tv = round(L.median(nums), 6)
                spread = (min(nums), max(nums))
                share = None
            else:
                c = Counter(json.dumps(v, sort_keys=True) for v in vals)
                top, n = c.most_common(1)[0]
                tv, share, spread = json.loads(top), n / len(vals), None
            typical[k] = tv
            dflt = (defaults.get(t) or {}).get(k)
            if dflt is not None and not _same(tv, dflt):
                changed.append((k, tv, dflt, share, spread))
        if typical.get("offset_type") != "PERCENT":
            changed = [c for c in changed if c[0] != "width_pct"]
        changed.sort(key=lambda c: (PRIORITY.index(c[0]) if c[0] in PRIORITY else len(PRIORITY), c[0]))
        typical_all[t] = typical
        table.append((t, len(ms), changed))
    return table, typical_all


def _fmt_v(v, L):
    if isinstance(v, float):
        return L.fmt(v)
    if isinstance(v, list):
        return "[" + ", ".join(_fmt_v(x, L) for x in v[:4]) + "]"
    return str(v)


def dictionary_md(table, typical_all, L):
    rows = ["# Modifier dictionary", "",
            "Every modifier type found in the artist's files, how often it appears, and the settings the artist changes "
            "from Blender's defaults (typical value, with the spread or how many instances agree). "
            "`style.modifier(obj, TYPE)` adds a modifier with these typical settings.", ""]
    for t, n, changed in table:
        rows.append(f"## {NICE_TYPE.get(t, t.replace('_', ' ').title())} (`{t}`), {n} use{'s' if n != 1 else ''}")
        if not changed:
            rows += ["", "Blender's default settings.", ""]
            continue
        rows += ["", "| Setting | Typical | Blender default | Agreement |", "|---|---|---|---|"]
        for k, tv, dflt, share, spread in changed[:30]:
            agree = (f"{_fmt_v(spread[0], L)} to {_fmt_v(spread[1], L)}" if spread else L.percent(share))
            rows.append(f"| `{k}` | {_fmt_v(tv, L)} | {_fmt_v(dflt, L)} | {agree} |")
        rows.append("")
    return "\n".join(rows) + "\n"


def merge_with_default(measured, default):
    """Measured order, plus default types it never saw, each placed after its nearest default predecessor."""
    out = list(measured)
    for i, t in enumerate(default):
        if t in out:
            continue
        pos = 0
        for prev in reversed(default[:i]):
            if prev in out:
                pos = out.index(prev) + 1
                break
        out.insert(pos, t)
    return out


def rules(ctx):
    L, r = ctx.lib, ctx.result
    parts = [o for _, o in ctx.meshes()] + [o for d in ctx.files for o in L.objects(d, "CURVE")]
    stacks = [L.stack_types(o) for o in parts if o.get("modifiers")]
    if not stacks:
        r.warn("No modifiers found on any part. This module needs a file built with a live modifier stack.")
        return r
    order, before, types = global_order(stacks, ctx.defaults.get("stack_order") or [])
    # the order itself is read from every submitted file, not only this module's
    every = [L.stack_types(o) for d in ctx.all_files for o in L.meshes(d) if o.get("modifiers")]
    full, _, _ = global_order(every or stacks, ctx.defaults.get("stack_order") or [])
    merged = merge_with_default(full, ctx.defaults.get("stack_order") or [])
    r.number("stack_order", merged, f"from {len(every or stacks)} stacks in all files"
             + ("; unseen types keep their generic place" if merged != full else ""))
    r.rule("Stack order (top to bottom): " + " > ".join(full) + ".")
    r.headline("Modifier stacks run " + " > ".join(full) + ".")
    conflicts = [(a, b, v, before.get((b, a), 0)) for (a, b), v in before.items()
                 if order.index(a) < order.index(b) and before.get((b, a), 0)]
    for a, b, v, w in conflicts[:3]:
        r.rule(f"Mostly {a} before {b} ({v} times), but {b} before {a} {w} time(s).")
    common = Counter(tuple(s) for s in stacks).most_common(3)
    r.rule("Most common stacks: " + "; ".join(f"{' > '.join(s)} ({c})" for s, c in common) + ".")
    r.rule("Modifier use: " + ", ".join(f"{t} on {c} part(s)" for t, c in types.most_common()) + ".")
    mir = [m for o in parts for m in L.mods(o, "MIRROR")]
    if mir:
        clip = L.share(mir, lambda m: m.get("use_clip"))
        bis = L.share(mir, lambda m: any(m.get("use_bisect_axis") or []))
        mo = L.share(mir, lambda m: m.get("mirror_object"))
        r.rule(f"Mirror: clipping {L.percent(clip)}, bisect {L.percent(bis)}, around another object {L.percent(mo)}.")
    arr = [m for o in parts for m in L.mods(o, "ARRAY")]
    if arr:
        r.rule(f"Array: fit {L.mode(m.get('fit_type') for m in arr)}, typical count {L.mode(m.get('count') for m in arr)}, "
               f"merge {L.percent(L.share(arr, lambda m: m.get('use_merge_vertices')))}, caps on {sum(1 for m in arr if m.get('start_cap') or m.get('end_cap'))}.")
    sol = [(o, m) for o in parts for m in L.mods(o, "SOLIDIFY")]
    if sol:
        th = [abs(m["thickness"]) for _, m in sol if m.get("thickness")]
        r.rule(f"Solidify: thickness median {L.mm(L.median(th))}, even thickness {L.percent(L.share((m for _, m in sol), lambda m: m.get('use_even_offset')))}.")
    curves = [o for d in ctx.files for o in L.objects(d, "CURVE")]
    pipes = [o for o in curves if (o.get("curve") or {}).get("bevel_depth")]
    if pipes:
        r.rule(f"Pipes and cables as curves with a bevel depth ({len(pipes)}), median radius "
               f"{L.mm(L.median(o['curve']['bevel_depth'] for o in pipes))}.")
    skins = [o for o in parts if "SKIN" in L.stack_types(o)]
    if skins:
        r.rule(f"Skin modifier used for {len(skins)} part(s) (pipes, frames, armatures).")
    hidden = sum(1 for o in parts for m in o.get("modifiers", []) if not m.get("show_viewport"))
    if hidden:
        r.rule(f"{hidden} modifier(s) are switched off in the viewport while working.")
    table, typical_all = modifier_dictionary(ctx, L)
    if table:
        r.number("modifier_defaults", typical_all, f"{len(table)} modifier types")
        r.extra["reference_md"] = {"modifier-dictionary.md": dictionary_md(table, typical_all, L)}
        r.rule(f"{len(table)} modifier types in the project: " + ", ".join(
            f"{NICE_TYPE.get(t, t.replace('_', ' ').title())} {n}" for t, n, _ in table[:14]) + ".")
        for t, n, changed in table[:8]:
            if changed:
                r.rule(f"{NICE_TYPE.get(t, t.replace('_', ' ').title())}: changed from Blender's defaults: " + ", ".join(
                    f"{k} {_fmt_v(tv, L)} (default {_fmt_v(d, L)})" for k, tv, d, _, _ in changed[:5])
                       + ". Full list in references/modifier-dictionary.md.")
    if ctx.answers.get("stack_notes"):
        r.rule(f"Artist's notes: {ctx.answers['stack_notes']}.")
    return r


STACK_TYPES = {"MIRROR", "ARRAY", "SOLIDIFY", "SKIN", "SCREW", "BOOLEAN", "SUBSURF", "BEVEL", "CURVE",
               "SIMPLE_DEFORM", "DISPLACE", "SHRINKWRAP", "WELD"}


def detect(doc, L):
    parts = [o for o in L.meshes(doc) if set(L.stack_types(o)) & STACK_TYPES]
    return f"{len(parts)} parts with live modifier stacks" if parts else None
