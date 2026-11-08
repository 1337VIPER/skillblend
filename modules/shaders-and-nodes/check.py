"""Style check: material node setups against the learned recipes."""
import doclib as L


def check(doc, style):
    out = []
    recipes = style.get("material_recipes") or {}
    model = style.get("shader_model")
    for m in L.materials(doc):
        name = L.strip_suffix(m["name"])
        if not m.get("use_nodes"):
            out.append(("info", f"material {name}: doesn't use nodes."))
            continue
        sh = m.get("shaders") or {}
        if model == "principled" and not sh.get("BSDF_PRINCIPLED") and not sh.get("EMISSION"):
            out.append(("info", f"material {name}: no Principled BSDF (the style builds materials on Principled)."))
        rec = recipes.get(name)
        vals = (m.get("principled") or {}).get("values") or {}
        if rec and vals:
            for key, rk, tol in (("Metallic", "metallic", 0.5), ("Roughness", "roughness", 0.3)):
                if isinstance(vals.get(key), (int, float)) and rk in rec and abs(vals[key] - rec[rk]) > tol:
                    out.append(("info", f"material {name}: {key} {vals[key]:.2f}, the style's {name} uses {rec[rk]:.2f}."))
    return out
