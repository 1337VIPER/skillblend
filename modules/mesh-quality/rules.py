"""Measured rules: how clean the artist's topology is."""
from collections import Counter


def _parts(ctx):
    L = ctx.lib
    for d in ctx.files:
        if L.export_role(d) in ("game", "lods", "low"):
            continue
        for o in L.meshes(d):
            q = o["mesh"].get("quality") or {}
            if q and "error" not in q and o["mesh"]["faces"] >= 6:
                yield d, o, q


def rules(ctx):
    L, r = ctx.lib, ctx.result
    parts = list(_parts(ctx))
    if not parts:
        return r
    qs = [q for _, _, q in parts]
    me = [o["mesh"] for _, o, _ in parts]
    quad = L.median(m["quad_ratio"] for m in me if m.get("quad_ratio") is not None)
    tri_share = L.share(me, lambda m: m["tris"] > 0)
    ngon_share = L.share(me, lambda m: m["ngons"] > 0)
    asp = [q["aspect_p90"] for q in qs if q.get("aspect_p90")]
    skew = [q["quad_skew_p90"] for q in qs if q.get("quad_skew_p90") is not None]
    bent = [q["nonplanar_quads"] for q in qs if q.get("nonplanar_quads") is not None]
    if asp:
        r.number("quality_aspect_p90", round(L.pct(asp, 0.9), 2), "90th percentile over parts of each part's 90th-percentile aspect")
    if skew:
        r.number("quality_skew_p90", round(L.pct(skew, 0.9), 1), "worst-corner skew, 90th percentile over parts")
    if bent:
        r.number("nonplanar_max", round(L.pct(bent, 0.9), 3), "share of bent quads, 90th percentile over parts")
    nm = [m.get("non_manifold_edges", 0) for m in me]
    nm_parts = sum(1 for x in nm if x)
    r.number("non_manifold_ok", nm_parts > 0.05 * len(me), f"{nm_parts} of {len(me)} parts have non-manifold edges")
    r.rule(f"{len(parts)} source parts measured: median {L.percent(quad)} quads; triangles on {L.percent(tri_share)} of parts, "
           f"n-gons on {L.percent(ngon_share)}.")
    if asp:
        r.rule(f"Face shape: half the parts keep 90% of faces under {L.fmt(L.median(asp))}:1 aspect; "
               f"stretched faces up to {L.fmt(L.pct(asp, 0.9))}:1 appear on chamfer strips and thin parts.")
    if skew:
        r.rule(f"Quad corners stay within about {L.fmt(L.median(skew))} deg of square on a typical part "
               f"(up to {L.fmt(L.pct(skew, 0.9))} deg); bent quads on {L.percent(L.median(bent) if bent else 0)} of faces.")
    zero = sum(q.get("zero_area_faces", 0) for q in qs)
    r.rule(f"Non-manifold edges on {nm_parts} of {len(me)} parts; zero-area faces: {zero}; "
           f"loose bits: {sum(1 for m in me if m.get('loose_parts', 1) > 1)} parts are made of several separate pieces.")
    val = Counter()
    for q in qs:
        for k, v in (q.get("valence") or {}).items():
            val[k] += v
    tv = sum(val.values())
    if tv:
        irr = 1 - val.get("4", 0) / tv
        r.number("valence_irregular", round(irr, 4))
        r.rule("Vertex valence (interior): " + ", ".join(f"{ {'2-': '2 or fewer'}.get(k, k)}-edge {L.percent(v / tv)}" for k, v in sorted(val.items()) if v / tv >= 0.005) + ".")
    bands = Counter()
    for q in qs:
        for k, v in (q.get("edge_angles") or {}).items():
            bands[k] += v
    tb = sum(bands.values())
    if tb:
        prof = {k: bands[k] / tb for k in ("flat", "smooth", "soft", "hard", "sharp") if bands.get(k)}
        r.number("edge_profile", {k: round(v, 3) for k, v in prof.items()})
        r.rule("Edge profile of the base meshes: " + ", ".join(f"{k} {L.percent(v)}" for k, v in prof.items())
               + " (flat <1 deg, smooth <10, soft <30, hard <60, sharp 60+). "
               + ("Base meshes are blocky; modifiers do the rounding." if prof.get("sharp", 0) + prof.get("flat", 0) > 0.6
                  else "Forms are built soft in the mesh itself."))
    r.headline(f"Topology is {L.percent(quad)} quads; on a typical part faces stay under {L.fmt(L.median(asp)) if asp else '?'}:1 "
               f"and quads within {L.fmt(L.median(skew)) if skew else '?'} deg of square"
               + ("" if nm_parts else ", with no non-manifold edges") + ".")
    if ctx.answers.get("quality_notes"):
        r.rule(f"Artist's notes: {ctx.answers['quality_notes']}.")
    return r


def detect(doc, L):
    if L.export_role(doc) in ("game", "lods", "low"):
        return None
    n = sum(1 for o in L.meshes(doc) if (o["mesh"].get("quality") or {}).get("sampled_faces"))
    return f"{n} parts measured" if n else None
