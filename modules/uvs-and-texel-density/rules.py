"""Measured rules: UVs, texel density, packing."""


def rules(ctx):
    L, r = ctx.lib, ctx.result
    parts = [o for _, o in ctx.meshes() if o["mesh"].get("uv", {}).get("uv_per_m")
             and L.name_suffix(o["name"]).lower() not in ("_high", "_hp")]
    if not parts:
        r.warn("No unwrapped mesh found (no UV map with area). Submit the mesh you'd export, with its UVs.")
        return r
    tex = ctx.answers.get("texture_size")
    if not tex:
        sizes = [max(i["size"]) for d in ctx.files for i in d.get("images", []) if i.get("size") and max(i["size"]) > 0]
        tex = L.mode(sizes) if sizes else None
    tex_note = "your texture size" if tex else "assumed 2048"
    tex = int(tex or ctx.defaults.get("texture_size") or 2048)
    r.number("texture_size", tex, tex_note)
    upm = [o["mesh"]["uv"]["uv_per_m"] for o in parts]
    td = L.median(upm) * tex
    r.number("texel_density_px_per_m", round(td), f"at {tex} px")
    per_file = [L.median(o["mesh"]["uv"]["uv_per_m"] for o in parts_f) * tex
                for d in ctx.files for parts_f in [[o for o in L.meshes(d) if o["mesh"].get("uv", {}).get("uv_per_m")]] if parts_f]
    if len(per_file) > 1:
        r.number("texel_density_range_px_per_m", [round(L.pct(upm, 0.05) * tex), round(L.pct(upm, 0.95) * tex)],
                 "5th-95th percentile of export parts")
        if max(per_file) > 2 * min(per_file):
            r.rule(f"Density follows the asset, not one fixed number: {', '.join(L.fmt(x) for x in sorted(per_file))} px/m across "
                   "the files. Each asset gets its own texture set, so small assets land far denser than big ones.")
    r.rule(f"Texel density: about {L.fmt(td)} px per metre at {tex} px "
           f"(most parts between {L.fmt(L.pct(upm, 0.05) * tex)} and {L.fmt(L.pct(upm, 0.95) * tex)}).")
    r.headline(f"Export meshes are unwrapped to about {L.fmt(td)} px/m at {tex} px"
               + (" (density follows the asset)" if len(per_file) > 1 and max(per_file) > 2 * min(per_file) else "") + ".")
    cv = [o["mesh"]["uv"].get("density_cv") for o in parts if o["mesh"]["uv"].get("density_cv") is not None]
    if cv:
        r.rule(f"Islands are kept to an even density inside a part (variation {L.percent(L.median(cv))}).")
    pk = [o["mesh"]["uv"].get("packing") for o in parts if o["mesh"]["uv"].get("packing")]
    if pk:
        r.rule(f"Packing uses about {L.percent(L.median(pk))} of the UV square.")
    isl = [o["mesh"]["uv"]["islands"] / max(1, o["mesh"]["faces"]) * 100 for o in parts]
    r.rule(f"About {L.fmt(L.median(isl))} UV islands per 100 faces.")
    seams = L.share(parts, lambda o: o["mesh"]["uv"].get("seams"))
    r.rule(f"Seams are marked on {L.percent(seams)} of parts." if seams else
           "Seams aren't marked on the mesh (islands come from the unwrap tool).")
    layers = L.mode(len(o["mesh"]["uv"]["layers"]) for o in parts)
    if layers and layers > 1:
        r.rule(f"Parts carry {layers} UV maps (e.g. a second channel for lightmaps or trims).")
    udim = [o for o in parts if o["mesh"]["uv"].get("tiles", 1) > 1]
    if udim:
        r.rule(f"UDIM tiles used on {len(udim)} part(s).")
    for k, label in (("texel_density", "Texel density target (artist)"), ("uv_tools", "UV tools")):
        if ctx.answers.get(k):
            r.rule(f"{label}: {ctx.answers[k]}.")
    return r


def detect(doc, L):
    """Files that hold export meshes with UVs: game/low files, LOD-named meshes, or small finished files."""
    import os
    stem = os.path.splitext(doc.get("_submission", {}).get("file", doc.get("file", "")))[0].lower()
    parts = [o for o in L.meshes(doc) if o["mesh"].get("uv", {}).get("uv_per_m")]
    if not parts:
        return None
    exportish = stem.endswith(("_low", "_lo", "_game", "_lods")) or any(
        "lod" in o["name"].lower() or L.name_suffix(o["name"]).lower() in ("_low", "_lp") for o in parts)
    if exportish or len(list(L.meshes(doc))) <= 10:
        return f"{len(parts)} unwrapped export mesh(es)"
    return None
