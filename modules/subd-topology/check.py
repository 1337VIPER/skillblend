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
        pin = me.get("pinch") or {}
        tol = style.get("subd_pinched_max")
        if pin.get("poles") and pin.get("pinched_poles") is not None and pin["pinched_poles"] > (tol or 0) + 0.1:
            out.append(("warn", f"{o['name']}: {pin['pinched_poles'] * 100:.0f}% of poles pinch after subdivision; "
                                "move poles off curved areas or onto hard edges."))
        ratio = (me.get("quality") or {}).get("hold_ratio_median")
        target = style.get("subd_hold_ratio")
        if ratio and target and not (target / 3 <= ratio <= target * 3):
            out.append(("info", f"{o['name']}: holding loops sit {ratio * 100:.0f}% of an edge length from their edges; "
                                f"the style uses about {target * 100:.0f}%."))
        if me.get("non_manifold_edges"):
            out.append(("warn", f"{o['name']}: {me['non_manifold_edges']} non-manifold edge(s) in the cage."))
        for m in L.mods(o, "SUBSURF"):
            lv = style.get("subd_levels_viewport")
            if lv is not None and m["levels"] != lv:
                out.append(("info", f"{o['name']}: subdivision viewport level {m['levels']}, style uses {lv}."))
            if style.get("subd_use_creases") and not m.get("use_creases"):
                out.append(("info", f"{o['name']}: Use Creases is off."))
    return out
