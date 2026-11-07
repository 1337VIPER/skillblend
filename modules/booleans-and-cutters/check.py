"""Style check: booleans and cutters."""
import doclib as L


def check(doc, style):
    out = []
    solver = style.get("boolean_solver")
    disp = style.get("cutter_display")
    cut = L.cutter_names(doc)
    for o in L.objects(doc, "MESH", include_outside=True):
        for m in L.mods(o, "BOOLEAN"):
            if solver and m.get("solver") != solver:
                out.append(("info", f"{o['name']}: boolean solver {m.get('solver')}, style uses {solver}."))
            if not m.get("object") and not m.get("collection"):
                out.append(("warn", f"{o['name']}: Boolean modifier '{m['name']}' has no cutter."))
    for o in L.objects(doc, include_outside=True):
        if o["name"] not in cut:
            continue
        if disp and o.get("display_type") != disp:
            out.append(("info", f"cutter {o['name']}: displayed as {o.get('display_type')}, style uses {disp}."))
        if not o.get("hide_render"):
            out.append(("warn", f"cutter {o['name']} will render (hide it from render)."))
    return out
