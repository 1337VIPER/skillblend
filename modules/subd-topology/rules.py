"""Measured rules: subdivision cages."""


def rules(ctx):
    L, r = ctx.lib, ctx.result
    cages = [o for _, o in ctx.meshes() if L.is_subd_cage(o)]
    if not cages:
        r.warn("No object with a live Subdivision Surface modifier was found. Submit the cage with the "
               "modifier still on (not applied).")
        return r
    subs = [m for o in cages for m in L.mods(o, "SUBSURF")]
    lv = L.mode(m["levels"] for m in subs)
    rl = L.mode(m["render_levels"] for m in subs)
    cre = L.share(subs, lambda m: m.get("use_creases"))
    r.number("subd_levels_viewport", lv, ctx.source())
    r.number("subd_levels_render", rl, ctx.source())
    r.number("subd_use_creases", cre >= 0.5)
    r.rule(f"Subdivision Surface: viewport {lv}, render {rl}, Use Creases {'on' if cre >= 0.5 else 'off'} "
           f"({len(cages)} cage{'s' if len(cages) != 1 else ''}).")
    qr = [o["mesh"]["quad_ratio"] for o in cages if o["mesh"].get("quad_ratio") is not None]
    if qr:
        low = L.pct(qr, 0.1)
        r.number("subd_quad_ratio_min", round(max(0.0, low - 0.02), 2), "lowest quad share seen, minus 2%")
        r.rule(f"Cages are {L.percent(L.median(qr))} quads (lowest {L.percent(min(qr))}); "
               f"n-gons in cages: {sum(o['mesh']['ngons'] for o in cages)}, triangles: {sum(o['mesh']['tris'] for o in cages)}.")
    sr = [o["mesh"].get("support_ratio") for o in cages if o["mesh"].get("support_ratio")]
    if sr:
        r.number("subd_support_ratio", round(L.median(sr), 3), "10th-percentile edge / median edge")
        r.rule(f"Support loops sit tight: the shortest tenth of edges are about {L.fmt(L.median(sr) * 100)}% "
               "of the typical edge length. Holding loops go that close to the edge they hold.")
    r.headline(f"Curved hard-surface parts are SubD cages (level {lv}/{rl}), about {L.percent(L.median(qr)) if qr else 'mostly'} quads, "
               "held with tight support loops.")
    creased = [o for o in cages if o["mesh"].get("crease_edges")]
    if creased:
        r.rule(f"Edge creases on {len(creased)} cage(s), median crease {L.fmt(L.median(o['mesh'].get('crease_median') for o in creased))}.")
    poles = [(o["mesh"]["poles_3"] + o["mesh"]["poles_5plus"]) / max(1, o["mesh"]["verts"]) for o in cages]
    r.rule(f"Poles: about {L.fmt(L.median(poles) * 100)} per 100 vertices (3- and 5+-edge vertices).")
    order = [L.stack_types(o) for o in cages]
    pre = L.share(order, lambda s: "BEVEL" in s and s.index("BEVEL") < s.index("SUBSURF"))
    if pre:
        r.rule(f"A Bevel modifier before the subdivision holds edges on {L.percent(pre)} of cages.")
    sol = L.share(order, lambda s: "SOLIDIFY" in s)
    if sol:
        r.rule(f"Shells: Solidify before subdivision on {L.percent(sol)} of cages (thin shells modelled as a single surface).")
    for k, label in (("support_method", "Edge holding (artist)"), ("triangles_ok", "Triangles/n-gons (artist)")):
        if ctx.answers.get(k):
            r.rule(f"{label}: {ctx.answers[k]}.")
    return r


def detect(doc, L):
    n = sum(1 for o in L.meshes(doc) if L.is_subd_cage(o))
    return f"{n} live SubD cages" if n else None
