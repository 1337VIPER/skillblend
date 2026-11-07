"""Style check: bevel modifier settings and normals on hard-surface parts."""
import doclib as L


def _inside(v, rng, slack=1.5):
    return rng and rng[0] / slack <= v <= rng[1] * slack


def check(doc, style):
    out = []
    ratio = style.get("bevel_width_ratio")
    wr = style.get("bevel_width_range_m")
    rr = style.get("bevel_ratio_range")
    segs = style.get("bevel_segments")
    lim = style.get("bevel_limit_method")
    cover = style.get("bevel_coverage", 1.0)
    missing = []
    for o in L.meshes(doc):
        if L.is_subd_cage(o) or L.name_suffix(o["name"]).lower() in ("_low", "_lp"):
            continue
        bevs = list(L.mods(o, "BEVEL"))
        if not bevs and not o["mesh"].get("bevel_weight_edges"):
            missing.append(o["name"])
            continue
        for m in bevs:
            if lim and m["limit_method"] != lim:
                out.append(("info", f"{o['name']}: bevel limit {m['limit_method']}, style uses {lim}."))
            if segs and abs(m["segments"] - segs) > 2:
                out.append(("info", f"{o['name']}: {m['segments']} bevel segments, style uses {segs}."))
            md = L.max_dim(o)
            if md > 0 and m.get("offset_type") in (None, "OFFSET", "WIDTH", "DEPTH"):
                w, rel = m["width"], m["width"] / md
                ok = _inside(w, wr) or _inside(rel, rr) if (wr or rr) else (not ratio or ratio / 3 <= rel <= ratio * 3)
                if not ok:
                    out.append(("warn", f"{o['name']}: bevel {L.mm(w)} ({L.fmt(rel * 100)}% of the part) is outside the style's "
                                        f"range ({L.mm(wr[0]) if wr else '?'} to {L.mm(wr[1]) if wr else '?'})."))
        if style.get("weighted_normal") and not list(L.mods(o, "WEIGHTED_NORMAL")) and cover >= 0.5:
            out.append(("info", f"{o['name']}: no Weighted Normal modifier."))
    parts = len(list(L.meshes(doc)))
    if missing and parts and len(missing) / parts > (1 - cover) + 0.25:
        out.append(("info", f"{len(missing)} of {parts} parts have no live bevel (the style bevels about {L.percent(cover)}): "
                            + ", ".join(missing[:6]) + ("..." if len(missing) > 6 else "")))
    return out
