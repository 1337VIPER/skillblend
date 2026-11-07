"""Measured rules: the material palette and slot habits."""
from collections import Counter


def rules(ctx):
    L, r = ctx.lib, ctx.result
    docs = [d for d in ctx.files if L.export_role(d) not in ("game", "lods")]
    if not docs:
        return r
    names, per_file, per_part, empty = Counter(), [], [], 0
    for d in docs:
        mats = set()
        for o in L.meshes(d):
            slots = [m for m in o.get("materials", []) if m]
            per_part.append(len(o.get("materials", [])))
            if not slots:
                empty += 1
            for m in slots:
                mats.add(L.strip_suffix(m))
        per_file.append(len(mats))
        for m in mats:
            names[m] += 1
    if not names:
        r.warn("No materials are assigned in these files.")
        return r
    shared = [m for m, c in names.most_common() if c >= max(2, 0.3 * len(docs))]
    palette = [m for m, _ in names.most_common(14)]
    r.number("material_palette", palette, f"most used across {len(docs)} files")
    r.number("slots_per_part", L.mode(per_part))
    cases = Counter(L.naming_case(m) for m in palette)
    r.headline(f"One shared material palette across assets ({', '.join(palette[:6])}), "
               f"{L.mode(per_part)} slot per part.")
    r.rule("Material palette, most used first: " + ", ".join(f"`{m}` ({names[m]} files)" for m in palette) + ".")
    if shared:
        r.rule(f"{len(shared)} materials are reused across most assets, so they act as a shared library: "
               + ", ".join(f"`{m}`" for m in shared[:10]) + ". Reuse these names before inventing new ones.")
    r.rule(f"Each asset uses about {L.fmt(L.median(per_file))} materials; parts carry {L.mode(per_part)} slot each "
           f"(names are mostly {cases.most_common(1)[0][0]}).")
    if empty:
        r.rule(f"{empty} part(s) have no material assigned.")
    procedural = image = 0
    for d in docs:
        for m in d.get("materials", []):
            nodes = m.get("nodes") or {}
            if nodes.get("TEX_IMAGE"):
                image += 1
            elif any(k.startswith("TEX_") for k in nodes):
                procedural += 1
    if procedural or image:
        r.rule(f"Shaders: {procedural} procedural, {image} image-textured materials in the high-poly files "
               "(final look comes from the bake / texturing step).")
    if ctx.answers.get("material_notes"):
        r.rule(f"Artist's notes: {ctx.answers['material_notes']}.")
    return r


def detect(doc, L):
    if L.export_role(doc) in ("game", "lods"):
        return None
    mats = {m for o in L.meshes(doc) for m in o.get("materials", []) if m}
    return f"{len(mats)} materials" if len(mats) >= 2 else None
