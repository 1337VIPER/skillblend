"""Measured rules: units, real size, origins, naming."""
from collections import Counter


def rules(ctx):
    L, r = ctx.lib, ctx.result
    docs = ctx.files
    units = L.mode(d["scene"]["unit_system"] for d in docs)
    scale = L.mode(d["scene"]["scale_length"] for d in docs)
    r.number("unit_system", units, ctx.source())
    r.number("scale_length", scale, ctx.source())
    r.rule(f"Scene units: {units}, unit scale {L.fmt(scale)}." +
           (" Model in metres at real size." if units == "METRIC" and scale == 1.0 else ""))

    vis = [o for _, o in ctx.meshes()]
    if not vis:
        r.warn("No visible mesh objects were found in the submitted files.")
        return r
    sizes = []
    for d in docs:
        objs = [o for o in L.meshes(d)]
        if objs:
            sizes.append(max(L.max_dim(o) for o in objs))
    if sizes:
        listed = (", ".join(L.fmt(s) + " m" for s in sizes) if len(sizes) <= 5 else
                  f"{L.fmt(min(sizes))} m to {L.fmt(max(sizes))} m across {len(sizes)} files (median {L.fmt(L.median(sizes))} m)")
        r.rule(f"Largest part per file: {listed}. Every part is built at its real size, never scaled up later.")

    applied = L.share(vis, L.is_applied_scale)
    r.number("apply_scale", applied >= 0.8, f"{L.percent(applied)} of parts have scale 1")
    if applied >= 0.8:
        r.rule(f"Object scale is applied ({L.percent(applied)} of parts at scale 1,1,1).")
    else:
        r.rule(f"Object scale is often left unapplied ({L.percent(1 - applied)} of parts have a scale other than 1).")

    roots = [o for o in vis if not o.get("parent")]
    kinds = Counter(L.origin_kind(o) for o in roots if L.origin_kind(o))
    if kinds:
        top, cnt = kinds.most_common(1)[0]
        r.number("origin", top, f"{cnt} of {sum(kinds.values())} top-level parts")
        r.rule(f"Origins: {top} on {cnt} of {sum(kinds.values())} top-level parts"
               + ("" if len(kinds) == 1 else f" (others: {', '.join(f'{k} {v}' for k, v in kinds.items() if k != top)})") + ".")

    names = [o["name"] for d in docs for o in L.objects(d) if o["type"] in {"MESH", "CURVE", "EMPTY"}]
    defaults = sum(1 for n in names if L.is_default_name(n))
    cases = Counter(L.naming_case(n) for n in names if not L.is_default_name(n))
    prefixes = Counter(L.name_prefix(n) for n in names if not L.is_default_name(n))
    if cases:
        case, c = cases.most_common(1)[0]
        r.number("naming_case", case, f"{c} of {sum(cases.values())} names")
        pref, pc = prefixes.most_common(1)[0]
        r.number("naming_prefix", pref if pc >= 0.6 * sum(prefixes.values()) else "")
        examples = [n for n in names if L.naming_case(n) == case][:4]
        r.rule(f"Object names are {L.CASE_LABEL.get(case, case)} ({c} of {sum(cases.values())})"
               + (f" with the prefix `{pref}`" if pref and pc >= 0.6 * sum(prefixes.values()) else "")
               + f", for example {', '.join('`' + e + '`' for e in examples)}.")
    if names and defaults / len(names) > 0.2:
        r.warn(f"{defaults} of {len(names)} objects keep Blender's default names (Cube.001...). "
               "Is that how you deliver, or was this file unfinished?")
    elif names:
        r.rule("Every object gets a real name; default names like Cube.001 never ship.")

    cols = []
    for d in docs:
        stack = [d["collections"]]
        while stack:
            c = stack.pop()
            if c["name"] != "Scene Collection":
                cols.append(c["name"])
            stack.extend(c.get("children", []))
    if cols:
        r.rule(f"Collections used: {', '.join('`' + c + '`' for c in cols[:8])}"
               + (" ..." if len(cols) > 8 else "") + ".")
    if names and cases:
        r.headline(f"Models are built at real size in {('metres' if units == 'METRIC' and scale == 1.0 else units.lower())}, "
                   f"scale applied, names in {L.CASE_LABEL.get(case, case)}"
                   + (f", facing {ctx.answers['front_axis']}" if ctx.answers.get("front_axis") else "") + ".")
    for k in ("front_axis", "engine", "naming_notes"):
        if ctx.answers.get(k):
            label = {"front_axis": "Models face", "engine": "Target", "naming_notes": "Naming notes"}[k]
            r.rule(f"{label}: {ctx.answers[k]}.")
    return r


def detect(doc, L):
    """Every source file says something about units, sizes and naming (merged export files don't)."""
    if L.export_role(doc) in ("game", "lods"):
        return None
    n = len(list(L.meshes(doc)))
    return f"{n} parts" if n else None
