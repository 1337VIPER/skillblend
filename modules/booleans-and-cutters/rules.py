"""Measured rules: booleans and cutters."""
from collections import Counter


def rules(ctx):
    L, r = ctx.lib, ctx.result
    bools = [(o, m) for d in ctx.files for o in L.meshes(d, helpers=True) for m in L.mods(o, "BOOLEAN")]
    if not bools:
        r.number("boolean_keep_live", False, "no live Boolean modifiers in the files")
        ng = sum(o["mesh"]["ngons"] for _, o in ctx.meshes())
        r.warn("No live Boolean modifiers found. If you apply booleans (or use an add-on that does), "
               f"say so in the interview. The files hold {ng} n-gons, which applied cuts often leave.")
        return r
    r.number("boolean_keep_live", True, f"{len(bools)} live Boolean modifiers")
    solver = L.mode(m.get("solver") for _, m in bools)
    op = Counter(m.get("operation") for _, m in bools)
    operand = L.mode(m.get("operand_type") for _, m in bools)
    r.number("boolean_solver", solver, ctx.source())
    r.headline(f"Openings are live {solver} booleans with cutters kept as hidden helpers.")
    r.rule(f"{len(bools)} live Boolean modifiers, solver {solver}, operations "
           + ", ".join(f"{k} {v}" for k, v in op.most_common())
           + f"; cutters given as {'a collection' if operand == 'COLLECTION' else 'single objects'}.")
    cutters = []
    for d in ctx.files:
        names = L.cutter_names(d)
        cutters += [o for o in L.objects(d, include_outside=True) if o["name"] in names]
    if cutters:
        disp = L.mode(o.get("display_type") for o in cutters)
        r.number("cutter_display", disp if disp in ("WIRE", "BOUNDS") else None)
        hid = L.share(cutters, lambda o: o.get("hide_render"))
        par = L.share(cutters, lambda o: o.get("parent"))
        cols = Counter(c for o in cutters for c in o.get("collections", []))
        col, cc = cols.most_common(1)[0]
        if cc >= 0.6 * len(cutters):
            r.number("cutter_collection", col)
        tokens = Counter()
        for o in cutters:
            n = L.strip_suffix(o["name"]).lower()
            for t in ("cutter", "cut", "bool", "boolean", "hole", "cb_", "bc_"):
                if t in n:
                    tokens[t] += 1
                    break
        pref = L.mode(L.name_prefix(o["name"]) for o in cutters)
        if pref:
            r.number("cutter_prefix", pref)
        elif tokens:
            t, tc = tokens.most_common(1)[0]
            if tc >= 0.6 * len(cutters):
                r.number("cutter_prefix", t)
        r.rule(f"{len(cutters)} cutters: displayed as {disp}, hidden from render on {L.percent(hid)}, "
               f"parented to the cut object on {L.percent(par)}, kept in collection `{col}` ({cc} of {len(cutters)}).")
        ex = [o["name"] for o in cutters][:4]
        r.rule(f"Cutter names look like {', '.join('`' + e + '`' for e in ex)}.")
    before = L.share((o for o, _ in bools), lambda o: "BEVEL" in L.stack_types(o) and
                     L.stack_types(o).index("BOOLEAN") < L.stack_types(o).index("BEVEL"))
    if before is not None:
        r.rule(f"The Boolean sits before the Bevel in the stack on {L.percent(before)} of cut objects, "
               "so the bevel runs around the cut edges too." if before >= 0.5 else
               f"The Boolean comes after the Bevel on {L.percent(1 - before)} of cut objects.")
    if ctx.answers.get("boolean_workflow"):
        r.rule(f"In the end booleans {ctx.answers['boolean_workflow']}.")
    if ctx.answers.get("boolean_addon"):
        r.rule(f"Add-on used: {ctx.answers['boolean_addon']}. Without it, rebuild its cuts with plain Boolean modifiers.")
    return r


def detect(doc, L):
    n = sum(1 for o in L.objects(doc, "MESH", include_outside=True) for _ in L.mods(o, "BOOLEAN"))
    return f"{n} live Boolean modifiers" if n else None
