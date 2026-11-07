"""Style check: subdivision cages."""
import doclib as L


def check(doc, style):
    out = []
    qmin = style.get("subd_quad_ratio_min")
    for o in L.meshes(doc):
        if not L.is_subd_cage(o):
            continue
        me = o["mesh"]
        if qmin is not None and me.get("quad_ratio") is not None and me["quad_ratio"] < qmin:
            out.append(("warn", f"{o['name']}: cage is {L.percent(me['quad_ratio'])} quads, the style keeps at least {L.percent(qmin)}."))
        if me.get("non_manifold_edges"):
            out.append(("warn", f"{o['name']}: {me['non_manifold_edges']} non-manifold edge(s) in the cage."))
        for m in L.mods(o, "SUBSURF"):
            lv = style.get("subd_levels_viewport")
            if lv is not None and m["levels"] != lv:
                out.append(("info", f"{o['name']}: subdivision viewport level {m['levels']}, style uses {lv}."))
            if style.get("subd_use_creases") and not m.get("use_creases"):
                out.append(("info", f"{o['name']}: Use Creases is off."))
    return out
