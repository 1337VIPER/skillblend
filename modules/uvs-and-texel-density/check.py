"""Style check: texel density and UV presence on export meshes."""
import doclib as L


def check(doc, style):
    out = []
    td = style.get("texel_density_px_per_m")
    tex = style.get("texture_size") or 2048
    for o in L.meshes(doc):
        if L.name_suffix(o["name"]).lower() in ("_high", "_hp") or L.is_subd_cage(o):
            continue
        uv = o["mesh"].get("uv", {})
        export = L.name_suffix(o["name"]).lower() in ("_low", "_lp") or "lod" in o["name"].lower()
        if not uv.get("layers"):
            if export:
                out.append(("warn", f"{o['name']}: export mesh has no UV map."))
            continue
        game_file = len(list(L.meshes(doc))) <= 10
        rng = style.get("texel_density_range_px_per_m")
        if td and uv.get("uv_per_m") and (export or game_file or L.name_prefix(o["name"]) in ("SM_", "SK_")):
            mine = uv["uv_per_m"] * tex
            lo, hi = (rng[0] * 0.7, rng[1] * 1.3) if rng else (td * 0.7, td * 1.3)
            if mine < lo or mine > hi:
                out.append(("warn", f"{o['name']}: texel density {mine:.0f} px/m, the style's range is {lo:.0f}-{hi:.0f} px/m at {tex}."))
        if uv.get("density_cv") and uv["density_cv"] > 0.3:
            out.append(("info", f"{o['name']}: island densities vary by {uv['density_cv'] * 100:.0f}%."))
    return out
