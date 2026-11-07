"""Style check: export meshes (objects named with the low suffix)."""
import doclib as L


def check(doc, style):
    out = []
    low = (style.get("low_suffix") or "_low")
    high = (style.get("high_suffix") or "_high")
    names = {L.strip_suffix(o["name"]) for o in L.objects(doc, "MESH")}
    maxm = style.get("max_material_slots")
    for o in L.meshes(doc):
        n = L.strip_suffix(o["name"])
        if not n.endswith(low):
            continue
        base = n[: -len(low)]
        if base + high not in names:
            out.append(("info", f"{o['name']}: no matching {base + high} to bake from."))
        if maxm and len(o.get("materials", [])) > maxm:
            out.append(("warn", f"{o['name']}: {len(o['materials'])} material slots, the style uses at most {maxm}."))
        if o["mesh"]["ngons"]:
            out.append(("warn", f"{o['name']}: {o['mesh']['ngons']} n-gon(s) on an export mesh."))
        if not o["mesh"].get("uv", {}).get("layers"):
            out.append(("warn", f"{o['name']}: export mesh has no UVs."))
    return out
