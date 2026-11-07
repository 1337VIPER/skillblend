"""Style check: materials assigned, and names from the palette."""
import doclib as L


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
    if foreign:
        out.append(("info", f"Material names outside the palette: {', '.join(sorted(foreign)[:8])}."))
    return out
