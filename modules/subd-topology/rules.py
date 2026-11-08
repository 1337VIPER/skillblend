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
        tight = L.median(sr) < 0.4
        r.rule(f"The shortest tenth of cage edges are about {L.fmt(L.median(sr) * 100)}% of the typical edge length"
               + (": tight support loops." if tight else ": no tight support loops, edges are held another way (see creases)."))
    hq = [(o["mesh"].get("quality") or {}) for o in cages]
    hd = [q["hold_distance_median"] for q in hq if q.get("hold_distance_median")]
    hr = [q["hold_ratio_median"] for q in hq if q.get("hold_ratio_median")]
    if hd:
        r.number("subd_hold_mm", round(L.median(hd) * 1000, 2), "distance from each held edge to its nearest loop")
        r.number("subd_hold_ratio", round(L.median(hr), 3) if hr else None, "holding distance / typical edge length")
        r.rule(f"Holding loops sit about {L.fmt(L.median(hd) * 1000)} mm from the edges they hold "
               f"(measured at {sum(q.get('held_edges', 0) for q in hq)} held edges"
               + (f"; about {L.percent(L.median(hr))} of a typical edge length" if hr else "") + ").")
    pin = [o["mesh"].get("pinch") or {} for o in cages]
    pin = [p for p in pin if p.get("poles") is not None and "error" not in p]
    if pin:
        poles = sum(p["poles"] for p in pin)
        bad = sum(round(p.get("pinched_poles", 0) * p["poles"]) for p in pin)
        r.number("subd_pinched_max", round(L.pct([p.get("pinched_poles", 0) for p in pin], 0.9), 3),
                 "share of pinched poles per cage, 90th percentile")
        r.rule(f"Pinching: {bad} of {poles} poles shade with a kink after subdivision (a pole bending much more than "
               "its neighbours); " + ("cages are essentially pinch-free." if poles and bad / poles < 0.05 else
                                      "watch pole placement on curved areas."))
    skews = [q.get("quad_skew_p90") for q in hq if q.get("quad_skew_p90") is not None]
    if skews:
        r.rule(f"Cage quads stay within about {L.fmt(L.median(skews))} deg of square (90th percentile per cage).")
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
    crease_share = len(creased) / len(cages)
    hold_ratio = r.numbers.get("subd_hold_ratio")
    how = ("edge creases" if crease_share >= 0.5 else
           "tight support loops" if hold_ratio is not None and hold_ratio < 0.4 else
           "bevel-before-subdivision" if pre and pre >= 0.5 else "soft, evenly spaced loops")
    r.number("subd_hold_method", how)
    r.headline(f"Curved parts are SubD cages (level {lv}/{rl}), about {L.percent(L.median(qr)) if qr else 'mostly'} quads, "
               f"edges held with {how}"
               + (", and pinch-free" if r.numbers.get("subd_pinched_max") is not None and r.numbers["subd_pinched_max"] < 0.05 else "") + ".")
    for k, label in (("support_method", "Edge holding (artist)"), ("triangles_ok", "Triangles/n-gons (artist)")):
        if ctx.answers.get(k):
            r.rule(f"{label}: {ctx.answers[k]}.")
    return r


def detect(doc, L):
    n = sum(1 for o in L.meshes(doc) if L.is_subd_cage(o))
    return f"{n} live SubD cages" if n else None
