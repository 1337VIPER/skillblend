"""Measured rules: bevel modifiers, bevel weights, normals and smoothing."""
from collections import Counter


def bevel_tiers(widths, k=3, min_share=0.05):
    """Fine / mid / heavy tiers: 1D k-means on log width (widths are continuous, so gaps alone don't split them)."""
    import math
    ws = sorted(w for w in widths if w and w > 0)
    if len(ws) < 6 or ws[int(len(ws) * 0.9)] < 2.5 * ws[int(len(ws) * 0.1)]:
        return [(ws[len(ws) // 2], 1.0)] if ws else []
    xs = [math.log(w) for w in ws]
    cs = [xs[int((i + 0.5) / k * (len(xs) - 1))] for i in range(k)]
    for _ in range(30):
        groups = [[] for _ in cs]
        for x in xs:
            groups[min(range(len(cs)), key=lambda i: abs(x - cs[i]))].append(x)
        new = [sum(g) / len(g) if g else c for g, c in zip(groups, cs)]
        if new == cs:
            break
        cs = new
    out = []
    for g in groups:
        if len(g) / len(xs) >= min_share:
            g = sorted(g)
            out.append((math.exp(g[len(g) // 2]), len(g) / len(xs)))
    return sorted(out)


def wn_any(parts, L):
    return any(True for o in parts for _ in L.mods(o, "WEIGHTED_NORMAL"))


def rules(ctx):
    L, r = ctx.lib, ctx.result
    parts = [o for _, o in ctx.meshes()]
    if not parts:
        r.warn("No visible mesh parts found.")
        return r
    bevs = [(o, m) for o in parts for m in L.mods(o, "BEVEL")]
    with_bevel = {o["name"] for o, _ in bevs}
    r.rule(f"{len(with_bevel)} of {len(parts)} parts carry a live Bevel modifier"
           + (f"; {sum(1 for o in parts if len(list(L.mods(o, 'BEVEL'))) > 1)} stack two or more bevel modifiers." if bevs else "."))
    if bevs:
        widths = [m["width"] for _, m in bevs if m.get("offset_type") in (None, "OFFSET", "WIDTH", "DEPTH")]
        ratios = [m["width"] / L.max_dim(o) for o, m in bevs if L.max_dim(o) > 0
                  and m.get("offset_type") in (None, "OFFSET", "WIDTH", "DEPTH")]
        segs = [m["segments"] for _, m in bevs]
        lim = L.mode(m["limit_method"] for _, m in bevs)
        ang = L.median(m.get("angle_limit_deg") for _, m in bevs if m["limit_method"] == "ANGLE")
        prof = L.median(m.get("profile") for _, m in bevs)
        harden = L.share((m for _, m in bevs), lambda m: m.get("harden_normals"))
        clamp = L.share((m for _, m in bevs), lambda m: m.get("use_clamp_overlap"))
        miter = L.mode(m.get("miter_outer") for _, m in bevs)
        if widths:
            r.number("bevel_width_m", round(L.median(widths), 5), ctx.source())
            r.rule(f"Bevel width: median {L.mm(L.median(widths))} (range {L.mm(min(widths))} to {L.mm(max(widths))}).")
        if widths:
            r.number("bevel_width_range_m", [round(L.pct(widths, 0.05), 5), round(L.pct(widths, 0.95), 5)],
                     "5th-95th percentile of bevel widths")
        r.number("bevel_coverage", round(len(with_bevel) / len(parts), 3), "share of parts with a live bevel")
        if ratios:
            r.number("bevel_ratio_range", [round(L.pct(ratios, 0.05), 5), round(L.pct(ratios, 0.95), 5)],
                     "5th-95th percentile of width / part size")
            r.number("bevel_width_ratio", round(L.median(ratios), 5), "bevel width / the part's largest dimension")
            r.rule(f"Relative to the part: median {L.fmt(L.median(ratios) * 100)}% of its largest dimension "
                   f"(small edges about {L.fmt(L.pct(ratios, 0.1) * 100)}%, big chamfers about {L.fmt(L.pct(ratios, 0.9) * 100)}%). "
                   "Scale bevels with the part, don't reuse one absolute width on everything.")
        tiers = bevel_tiers(widths)
        if len(tiers) > 1:
            r.number("bevel_tiers_m", [round(t, 5) for t, _ in tiers], "clusters of bevel widths")
            r.rule("Bevel tiers (clusters of widths, share of bevels): "
                   + ", ".join(f"{L.mm(t)} ({L.percent(s)})" for t, s in tiers)
                   + ". Pick the tier by the edge's role, not a new width each time.")
        r.headline(f"Hard edges get a live Bevel ({L.mode(segs)} segments, {lim.lower()} limit"
                   + (f" {L.fmt(ang)} deg" if lim == "ANGLE" and ang else "") + ")"
                   + (" in tiers of " + ", ".join(L.mm(t) for t, _ in tiers) if len(tiers) > 1 else
                      f", about {L.mm(L.median(widths))}" if widths else "")
                   + (", with a Weighted Normal last." if wn_any(parts, L) else "."))
        r.number("bevel_segments", L.mode(segs), ctx.source())
        r.rule(f"Segments: usually {L.mode(segs)} (seen {', '.join(str(s) for s in sorted(set(segs)))}).")
        r.number("bevel_limit_method", lim)
        if lim == "ANGLE":
            r.number("bevel_angle_deg", round(ang, 1) if ang else None)
            r.rule(f"Limit method: Angle at {L.fmt(ang)} degrees.")
        elif lim == "WEIGHT":
            r.rule("Limit method: bevel weights. Mark which edges bevel with edge bevel weights, not by angle.")
        else:
            r.rule(f"Limit method: {lim}.")
        r.number("bevel_profile", round(prof, 3) if prof is not None else None)
        if prof is not None and abs(prof - 0.5) > 0.02:
            r.rule(f"Profile shape: {L.fmt(prof)} (not the default 0.5).")
        r.number("bevel_harden_normals", harden >= 0.5)
        r.number("bevel_clamp", clamp >= 0.5)
        r.rule(f"Harden Normals {'on' if harden >= 0.5 else 'off'} ({L.percent(harden)}), "
               f"Clamp Overlap {'on' if clamp >= 0.5 else 'off'} ({L.percent(clamp)}), outer miter {miter}.")
    bw = [o for o in parts if o["mesh"].get("bevel_weight_edges")]
    if bw:
        r.rule(f"Bevel weights are painted on {len(bw)} part(s) (median weight {L.fmt(L.median(o['mesh'].get('bevel_weight_median') for o in bw))}).")
    wn = [(o, m) for o in parts for m in L.mods(o, "WEIGHTED_NORMAL")]
    r.number("weighted_normal", len({o['name'] for o, _ in wn}) >= 0.5 * len(parts))
    if wn:
        keep = L.share((m for _, m in wn), lambda m: m.get("keep_sharp"))
        r.number("weighted_normal_keep_sharp", keep >= 0.5)
        last = L.share((o for o, _ in wn), lambda o: L.stack_types(o)[-1:] == ["WEIGHTED_NORMAL"])
        r.rule(f"Weighted Normal modifier on {len({o['name'] for o, _ in wn})} of {len(parts)} parts, "
               f"Keep Sharp {'on' if keep >= 0.5 else 'off'}, last in the stack on {L.percent(last)} of them.")
    else:
        r.rule("No Weighted Normal modifier: normals come from the bevel's Harden Normals or from sharp edges.")
    sba = [m.get("smooth_angle_deg") for o in parts for m in L.mods(o, "NODES") if m.get("smooth_angle_deg")]
    smooth_share = L.share(parts, lambda o: o["mesh"]["faces"] and o["mesh"]["smooth_faces"] / o["mesh"]["faces"] > 0.5)
    sharp = [o for o in parts if o["mesh"].get("sharp_edges")]
    if sba:
        r.number("smooth_angle_deg", round(L.median(sba), 1), "Smooth by Angle modifier")
        r.rule(f"Shading: Smooth by Angle modifier at {L.fmt(L.median(sba))} degrees.")
    r.rule(f"Shade smooth on {L.percent(smooth_share)} of parts; sharp edges marked on {len(sharp)} of {len(parts)}.")
    if not bevs and not bw:
        r.warn("No Bevel modifiers or bevel weights found. If you model bevels into the mesh or apply them, "
               "say so in the interview; otherwise submit a file with your live bevel setup.")
    if ctx.answers.get("bevel_method"):
        r.rule(f"Bevel method (artist): {ctx.answers['bevel_method']}.")
    if "apply_before_export" in ctx.answers:
        r.rule("Bevels are applied on export." if ctx.answers["apply_before_export"] else
               "Bevels stay on the high poly and get baked down; the low poly doesn't carry them.")
    return r


def detect(doc, L):
    if L.export_role(doc) in ("game", "lods"):
        return None  # merged export meshes: their bevels are baked, not authored
    parts = list(L.meshes(doc))
    bev = sum(1 for o in parts if any(True for _ in L.mods(o, "BEVEL")) or o["mesh"].get("bevel_weight_edges"))
    return f"{bev} of {len(parts)} parts with live bevels" if bev else None
