"""Style check: units, applied scale, naming, origins."""
import doclib as L


def check(doc, style):
    out = []
    sc = doc["scene"]
    if style.get("unit_system") and sc["unit_system"] != style["unit_system"]:
        out.append(("warn", f"Scene units are {sc['unit_system']}, the style uses {style['unit_system']}."))
    if style.get("scale_length") and abs(sc["scale_length"] - style["scale_length"]) > 1e-6:
        out.append(("warn", f"Unit scale is {sc['scale_length']}, the style uses {style['scale_length']}."))
    vis = list(L.meshes(doc))
    if style.get("apply_scale"):
        bad = [o["name"] for o in vis if not L.is_applied_scale(o)]
        if bad:
            out.append(("warn", f"Scale not applied on {len(bad)} part(s): {', '.join(bad[:6])}."))
    defaults = [o["name"] for o in L.objects(doc) if L.is_default_name(o["name"])]
    if defaults:
        out.append(("warn", f"Default names left: {', '.join(defaults[:8])}."))
    case = style.get("naming_case")
    if case:
        bad = [o["name"] for o in vis if not L.is_default_name(o["name"]) and L.naming_case(o["name"]) != case]
        if bad:
            out.append(("info", f"{len(bad)} name(s) aren't {case}: {', '.join(bad[:6])}."))
    pref = style.get("naming_prefix")
    if pref:
        bad = [o["name"] for o in vis if not o["name"].startswith(pref)]
        if bad:
            out.append(("info", f"{len(bad)} name(s) lack the prefix {pref}: {', '.join(bad[:6])}."))
    origin = style.get("origin")
    if origin in {"bottom-center", "center"}:
        bad = [o["name"] for o in vis if not o.get("parent") and L.origin_kind(o) not in (None, origin)]
        if bad:
            out.append(("info", f"Origin isn't {origin} on: {', '.join(bad[:6])}."))
    return out
