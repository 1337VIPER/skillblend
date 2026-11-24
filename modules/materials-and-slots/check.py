"""Style check: materials assigned, given a real colour, and named from the palette."""
import doclib as L

GREY = 0.8  # Blender's default Base Color and viewport colour


def _is_blank(m):
    """A material nobody set up: Blender's default grey, no metal, nothing plugged into the colour."""
    near = lambda c: c is not None and all(abs(float(x) - GREY) < 0.005 for x in list(c)[:3])
    pr = m.get("principled")
    if m.get("use_nodes") and pr:
        vals = pr.get("values") or {}
        linked = pr.get("linked") or {}
        return ("Base Color" not in linked and near(vals.get("Base Color")) and not float(vals.get("Metallic") or 0)
                and not float(vals.get("Emission Strength") or 0) and not float(vals.get("Transmission Weight") or 0))
    if m.get("use_nodes"):
        return False  # some other shader setup: not ours to judge
    return near((m.get("viewport") or {}).get("color"))


def check(doc, style):
    out = []
    palette = set(style.get("material_palette") or [])
    unassigned, foreign = [], set()
    for o in L.meshes(doc):
        slots = [m for m in o.get("materials", []) if m]
        if not slots:
            unassigned.append(o["name"])
        for m in slots:
            if palette and L.strip_suffix(m) not in palette:
                foreign.add(L.strip_suffix(m))
    if unassigned:
        out.append(("warn", f"{len(unassigned)} part(s) without a material: {', '.join(unassigned[:6])}."))
    used = {L.strip_suffix(m) for o in L.meshes(doc) for m in o.get("materials", []) if m}
    recipes = style.get("material_recipes") or {}
    blank = []
    for m in L.materials(doc):
        name = L.strip_suffix(m["name"])
        own = recipes.get(name) or {}
        grey_by_style = own.get("base_color") and all(abs(float(x) - GREY) < 0.005 for x in own["base_color"][:3])
        if name in used and _is_blank(m) and not grey_by_style:
            blank.append(name)
    if blank:
        out.append(("warn", f"{len(blank)} material(s) are still Blender's default grey: {', '.join(sorted(blank)[:8])}. "
                            "Give each a real colour: `style.material(obj, name)` uses the style's recipe or the standard "
                            "palette, and `color=(r, g, b)` sets your own."))
    if foreign:
        out.append(("info", f"Material names outside the palette: {', '.join(sorted(foreign)[:8])}."))
    return out
