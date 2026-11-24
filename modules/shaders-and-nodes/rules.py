"""Measured rules: how materials are built as node setups (shader model, procedural or image, chains, PBR values)."""
from collections import Counter, defaultdict

TEXTURE_TYPES = ("TEX_NOISE", "TEX_VORONOI", "TEX_MUSGRAVE", "TEX_WAVE", "TEX_GRADIENT", "TEX_MAGIC", "TEX_BRICK",
                 "TEX_CHECKER", "TEX_WHITE_NOISE", "TEX_IMAGE")
SHADER_MAIN = ("BSDF_PRINCIPLED", "EMISSION", "BSDF_GLASS", "BSDF_DIFFUSE", "BSDF_GLOSSY", "BSDF_TOON",
               "BSDF_TRANSPARENT", "BSDF_METALLIC", "SUBSURFACE_SCATTERING", "PRINCIPLED_VOLUME")


def _is_default_tree(m):
    t = m.get("nodes") or {}
    return set(t) <= {"BSDF_PRINCIPLED", "OUTPUT_MATERIAL"} and not (m.get("principled") or {}).get("linked")


def _collect(ctx):
    """One entry per (file, material), skipping merged export files."""
    L = ctx.lib
    out = []
    for d in ctx.files:
        if L.export_role(d) in ("game", "lods"):
            continue
        for m in L.materials(d):
            if m.get("use_nodes") and m.get("tree"):
                out.append(m)
    return out


def rules(ctx):
    L, r = ctx.lib, ctx.result
    mats = _collect(ctx)
    if not mats:
        r.warn("No node-based materials found in these files.")
        return r
    names = Counter(L.strip_suffix(m["name"]) for m in mats)
    main = Counter()
    for m in mats:
        sh = m.get("shaders") or {}
        kind = next((k for k in SHADER_MAIN if sh.get(k)), "other")
        if sh.get("MIX_SHADER"):
            kind += "+mix"
        main[kind] += 1
    pr_share = sum(c for k, c in main.items() if k.startswith("BSDF_PRINCIPLED")) / len(mats)
    r.number("shader_model", "principled" if pr_share >= 0.6 else main.most_common(1)[0][0].lower(), f"{len(mats)} materials")
    r.rule(f"{len(mats)} node materials ({len(names)} distinct names). Main shader: "
           + ", ".join(f"{L.node_name(k.split('+')[0])}{' with Mix Shader' if '+mix' in k else ''} {c}" for k, c in main.most_common(5)) + ".")
    # what drives each Principled input
    fed = defaultdict(Counter)
    for m in mats:
        for inp, sig in ((m.get("principled") or {}).get("linked") or {}).items():
            fed[inp][sig] += 1
    for inp in ("Base Color", "Roughness", "Metallic", "Normal", "Emission Color", "Alpha"):
        if fed.get(inp):
            sig, c = fed[inp].most_common(1)[0]
            r.rule(f"{inp} is driven by a node setup in {sum(fed[inp].values())} materials; most often "
                   f"`{L.chain_name(sig)}` ({c}).")
    # texture census, procedural vs image
    tex = Counter()
    for m in mats:
        tt = L.tree_types(m.get("tree"))
        for t in TEXTURE_TYPES:
            if tt.get(t):
                tex[t] += 1
    proc = sum(c for t, c in tex.items() if t != "TEX_IMAGE")
    img = tex.get("TEX_IMAGE", 0)
    if tex:
        r.rule("Texture nodes (materials using each): " + ", ".join(f"{L.node_name(t)} {c}" for t, c in tex.most_common(8)) + ".")
    style = "procedural" if proc and proc >= img * 2 else ("image" if img and img >= proc * 2 else ("mixed" if proc or img else "flat"))
    r.number("texturing", style, f"{proc} procedural / {img} image-texture uses")
    # image textures: sizes, colour spaces, projection
    sizes, spaces, proj = Counter(), Counter(), Counter()
    for m in mats:
        for n in L.tree_nodes(m.get("tree")):
            if n.get("type") == "TEX_IMAGE":
                if n.get("size") and max(n["size"]) > 0:
                    sizes[max(n["size"])] += 1
                if n.get("colorspace"):
                    spaces[n["colorspace"]] += 1
                if n.get("projection"):
                    proj[n["projection"]] += 1
    if sizes:
        r.rule("Image textures: sizes " + ", ".join(f"{s}px x{c}" for s, c in sizes.most_common(4))
               + "; colour spaces " + ", ".join(f"{s} {c}" for s, c in spaces.most_common(4))
               + (f"; Box (triplanar) projection on {proj['BOX']}" if proj.get("BOX") else "") + ".")
    # detail methods
    tt_all = Counter()
    for m in mats:
        for t, c in L.tree_types(m.get("tree")).items():
            tt_all[t] += 1
    methods = []
    for t, label in (("BEVEL", "shader Bevel node for rounded edges without geometry"), ("NORMAL_MAP", "Normal Map nodes"),
                     ("BUMP", "Bump nodes"), ("AMBIENT_OCCLUSION", "Ambient Occlusion node (edge wear/dirt masks)"),
                     ("GEOMETRY", "Geometry node (pointiness/edge masks)"), ("LAYER_WEIGHT", "Layer Weight / facing masks"),
                     ("VALTORGB", "Color Ramps to shape masks"), ("MAPPING", "Mapping nodes"),
                     ("ATTRIBUTE", "Attribute nodes (driven by mesh attributes)"), ("VERTEX_COLOR", "Color Attributes"),
                     ("DISPLACEMENT", "Displacement output")):
        if tt_all.get(t):
            methods.append(f"{label} in {tt_all[t]}")
    if methods:
        r.rule("Shading tricks used: " + "; ".join(methods) + ".")
    r.number("uses_shader_bevel", bool(tt_all.get("BEVEL")))
    coords = Counter()
    for m in mats:
        for n in L.tree_nodes(m.get("tree")):
            if n.get("type") == "TEX_COORD":
                for o in n.get("outputs_used", []):
                    coords[o] += 1
    if coords:
        r.number("texture_coordinates", coords.most_common(1)[0][0])
        r.rule("Procedural textures are placed with Texture Coordinate " + ", ".join(f"{o} {c}" for o, c in coords.most_common()) + ".")
    groups = Counter(g for m in mats for g in (m.get("groups") or []))
    shared = [(g, c) for g, c in groups.most_common() if c >= 2]
    if shared:
        r.rule("Shader node groups reused across materials: " + ", ".join(f"`{g}` ({c})" for g, c in shared[:8]) + ".")
    # material settings
    cull = L.share(mats, lambda m: m.get("use_backface_culling"))
    rm = L.mode(m.get("surface_render_method") or m.get("blend_method") for m in mats)
    r.rule(f"Backface culling on {L.percent(cull)} of materials; render method mostly {rm}.")
    # PBR recipes per material name
    recipes = {}
    by_name = defaultdict(list)
    for m in mats:
        by_name[L.strip_suffix(m["name"])].append(m)
    for name, ms in sorted(by_name.items(), key=lambda kv: -len(kv[1]))[:30]:
        vals = [(x.get("principled") or {}).get("values", {}) for x in ms]
        rec = {}
        bc = [v.get("Base Color") for v in vals if isinstance(v.get("Base Color"), list)]
        if bc:
            rec["base_color"] = [round(L.median([c[i] for c in bc]), 4) for i in range(3)]
        for key, out in (("Metallic", "metallic"), ("Roughness", "roughness"), ("Emission Strength", "emission_strength"),
                         ("Alpha", "alpha"), ("IOR", "ior"), ("Transmission Weight", "transmission")):
            vs = [v.get(key) for v in vals if isinstance(v.get(key), (int, float))]
            if vs:
                rec[out] = round(L.median(vs), 4)
        ec = [v.get("Emission Color") for v in vals if isinstance(v.get("Emission Color"), list)]
        if ec and rec.get("emission_strength", 0) > 0:
            rec["emission_color"] = [round(L.median([c[i] for c in ec]), 4) for i in range(3)]
        own = defaultdict(Counter)
        for x in ms:
            for k, sig in ((x.get("principled") or {}).get("linked") or {}).items():
                own[k][sig] += 1
        if own:
            rec["procedural"] = {k: L.chain_name(c.most_common(1)[0][0]) for k, c in own.items()}
            noise = _roughness_noise(ms, L)
            if noise:
                rec["roughness_noise"] = noise
            radii = [n["inputs"]["Radius"] for x in ms for n in L.tree_nodes(x.get("tree"))
                     if n.get("type") == "BEVEL" and isinstance((n.get("inputs") or {}).get("Radius"), (int, float))]
            if radii and "BEVEL" in "".join(own.get("Normal", {})):
                rec["bevel_radius"] = round(L.median(radii), 5)
        for k, dv in (("alpha", 1.0), ("ior", 1.5), ("emission_strength", 0.0), ("transmission", 0.0)):
            if k in rec and abs(rec[k] - dv) < 1e-3:
                del rec[k]
        if rec:
            recipes[name] = rec
    if recipes:
        r.number("material_recipes", recipes, f"{len(recipes)} materials")
        r.extra["reference_md"] = {"shader-recipes.md": recipes_md(recipes, L)}
        metals = [v for v in recipes.values() if v.get("metallic", 0) >= 0.5 and "roughness" in v]
        diel = [v for v in recipes.values() if v.get("metallic", 1) < 0.5 and "roughness" in v]
        if metals:
            r.rule(f"Metals ({len(metals)}): roughness {L.fmt(min(v['roughness'] for v in metals))}-"
                   f"{L.fmt(max(v['roughness'] for v in metals))}, median {L.fmt(L.median(v['roughness'] for v in metals))}.")
        if diel:
            r.rule(f"Non-metals ({len(diel)}): roughness {L.fmt(min(v['roughness'] for v in diel))}-"
                   f"{L.fmt(max(v['roughness'] for v in diel))}, median {L.fmt(L.median(v['roughness'] for v in diel))}. "
                   "Every material's values are in references/shader-recipes.md; `style.material(obj, name)` rebuilds them.")
    trick = []
    if fed.get("Roughness"):
        trick.append("procedural roughness break-up")
    if tt_all.get("BEVEL"):
        trick.append("shader-bevelled edges")
    if img:
        trick.append("image textures")
    r.headline(f"Materials are {'Principled BSDF' if pr_share >= 0.6 else 'mixed'} node setups"
               + (f" with {', '.join(trick)}" if trick else ", mostly flat values") + ".")
    return r


def _roughness_noise(ms, L):
    """The Noise break-up that feeds Roughness, as the artist set it: noise scale and detail, and the roughness
    range the Color Ramp or Map Range after it maps to (medians over the materials of one name)."""
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    scale, detail, lo, hi, via = [], [], [], [], Counter()
    for x in ms:
        sig = ((x.get("principled") or {}).get("linked") or {}).get("Roughness", "")
        if "TEX_NOISE" not in sig:
            continue
        for n in L.tree_nodes(x.get("tree")):
            inp = n.get("inputs") or {}
            if n.get("type") == "TEX_NOISE":
                if num(inp.get("Scale")):
                    scale.append(inp["Scale"])
                if num(inp.get("Detail")):
                    detail.append(inp["Detail"])
            elif n.get("type") == "VALTORGB" and "VALTORGB" in sig and n.get("stops"):
                vals = [sum(c[:3]) / 3 for _, c in n["stops"] if c and all(num(v) for v in c[:3])]
                if len(vals) >= 2:
                    lo.append(min(vals))
                    hi.append(max(vals))
                    via["ramp"] += 1
            elif n.get("type") == "MAP_RANGE" and "MAP_RANGE" in sig and num(inp.get("To Min")) and num(inp.get("To Max")):
                lo.append(min(inp["To Min"], inp["To Max"]))
                hi.append(max(inp["To Min"], inp["To Max"]))
                via["map_range"] += 1
    if not scale:
        return None
    out = {"scale": round(L.median(scale), 3)}
    if detail:
        out["detail"] = round(L.median(detail), 3)
    if lo and hi:
        out.update(low=round(max(0.0, min(1.0, L.median(lo))), 4), high=round(max(0.0, min(1.0, L.median(hi))), 4),
                   via=via.most_common(1)[0][0])
    return out


def recipes_md(recipes, L):
    rows = ["# Shader recipes", "", "Measured Principled BSDF values per material name (median over files). "
            "`style.material(obj, name)` rebuilds a material from this table.", "",
            "| Material | Base colour (linear RGB) | Metallic | Roughness | Other | Procedural inputs |", "|---|---|---|---|---|---|"]
    for name, v in recipes.items():
        other = ", ".join(f"{k} {v[k]}" for k in ("emission_strength", "alpha", "ior", "transmission") if k in v)
        proc = "; ".join(f"{k}: {c}" for k, c in (v.get("procedural") or {}).items())
        rn = v.get("roughness_noise")
        if rn:
            proc += f" (noise scale {rn['scale']}" + (f", roughness {rn['low']} to {rn['high']}" if "low" in rn else "") + ")"
        if "bevel_radius" in v:
            proc += f" (bevel radius {v['bevel_radius'] * 1000:.3g} mm)"
        rows.append(f"| `{name}` | {v.get('base_color', '')} | {v.get('metallic', '')} | {v.get('roughness', '')} | {other} | {proc} |")
    return "\n".join(rows) + "\n"


def detect(doc, L):
    if L.export_role(doc) in ("game", "lods"):
        return None
    mats = [m for m in L.materials(doc) if m.get("use_nodes") and m.get("tree")]
    if not mats:
        return None
    built = [m for m in mats if not _is_default_tree(m)]
    if built:
        return f"{len(built)} node-built material(s)"
    valued = [m for m in mats if (m.get("principled") or {}).get("values")]
    return f"{len(valued)} Principled material(s)" if valued else None
