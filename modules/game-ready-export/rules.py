"""Measured rules: high/low pairs, budgets, LODs, materials."""
import re
from collections import Counter

HIGH = ("_high", "_hp", "_High", "_HP", "_hi")
LOW = ("_low", "_lp", "_Low", "_LP", "_lo")


def split(name, L):
    n = L.strip_suffix(name)
    for s in HIGH:
        if n.endswith(s):
            return n[: -len(s)], "high", s
    for s in LOW:
        if n.endswith(s):
            return n[: -len(s)], "low", s
    m = re.match(r"^(.*?)(_LOD|_lod)(\d+)$", n)
    if m:
        return m.group(1), "lod" + m.group(3), m.group(2) + m.group(3)
    return n, None, ""


def tris(o):
    me = o.get("mesh", {})
    return me.get("eval_tri_count", me.get("tri_count", 0))


FILE_ROLES = (("_high", "high"), ("_hi", "high"), ("_low", "low"), ("_lo", "low"),
              ("_game", "game"), ("_lods", "lods"))


def file_pairs(ctx, r, L):
    """High, low and game meshes kept in separate files: name.blend, name_low.blend, name_game.blend."""
    import os
    sets = {}
    for d in ctx.files:
        stem = os.path.splitext(d.get("_submission", {}).get("file", d.get("file", "")))[0]
        role = "high"
        for s, rr in FILE_ROLES:
            if stem.endswith(s):
                stem, role = stem[: -len(s)], rr
                break
        sets.setdefault(stem, {})[role] = d
    rows, ratios, slots, lods = [], [], [], []
    for stem, s in sorted(sets.items()):
        hi = s.get("high")
        lo = s.get("game") or s.get("low")
        if not hi or not lo:
            continue
        th = sum(tris(o) for o in L.meshes(hi))
        lo_objs = [o for o in L.meshes(lo) if not re.search(r"_LOD[1-9]\d*$", L.strip_suffix(o["name"]), re.I)]
        tl = sum(tris(o) for o in lo_objs)
        if not tl:
            continue
        ratios.append(th / tl)
        nl = 1 + max([int(m.group(1)) for o in L.meshes(s.get("lods") or lo)
                      for m in [re.search(r"_LOD(\d+)$", L.strip_suffix(o["name"]), re.I)] if m] or [0])
        lods.append(nl)
        slots += [len(o.get("materials", [])) for o in lo_objs]
        merged = len(lo_objs) == 1
        rows.append(f"`{stem}`: high {th:,} tris in {len(list(L.meshes(hi)))} parts, game mesh {tl:,} tris"
                    f"{' as one merged object' if merged else f' in {len(lo_objs)} objects'}, {nl} LOD level(s)")
    if not rows:
        return
    r.number("high_low_tri_ratio", round(L.median(ratios), 1), f"{len(rows)} high/game file set(s)")
    r.number("lod_count", max(lods))
    if slots:
        r.number("max_material_slots", max(slots))
    r.rule("High, low and game meshes live in separate files: `name.blend` (high, the bake source), "
           "`name_low.blend` (low parts), `name_game.blend` / `name_lods.blend` (the merged game mesh and its LODs).")
    for row in rows:
        r.rule(row + ".")
    r.headline(f"Each asset ships as a high poly bake source plus a game mesh about 1/{L.fmt(L.median(ratios))} of its triangles, "
               f"with {max(lods)} LOD level(s).")
    r.rule(f"The high is about {L.fmt(L.median(ratios))}x the game mesh's triangles; LODs are named `_LOD1`, `_LOD2`, ...; "
           f"the game mesh carries up to {max(slots) if slots else 'n/a'} material slot(s).")


def rules(ctx):
    L, r = ctx.lib, ctx.result
    objs = [o for d in ctx.files for o in L.objects(d, "MESH")]
    groups = {}
    sfx = Counter()
    for o in objs:
        base, role, s = split(o["name"], L)
        if role:
            groups.setdefault(base, {}).setdefault(role, []).append(o)
            if role in ("high", "low"):
                sfx[(role, s)] += 1
    pairs = {b: g for b, g in groups.items() if "high" in g and "low" in g}
    if not pairs:
        file_pairs(ctx, r, L)
        if r.numbers.get("high_low_tri_ratio"):
            return r
    hs = [s for (role, s), _ in sfx.most_common() if role == "high"]
    ls = [s for (role, s), _ in sfx.most_common() if role == "low"]
    if hs:
        r.number("high_suffix", hs[0], ctx.source())
    if ls:
        r.number("low_suffix", ls[0], ctx.source())
    if not pairs:
        r.warn("No high/low pair found by name (e.g. crate_high / crate_low). Name them the way you bake "
               "them, or say in the interview how you pair them.")
    else:
        ratios, lows = [], []
        for b, g in pairs.items():
            th = sum(tris(o) for o in g["high"])
            tl = sum(tris(o) for o in g["low"])
            lows.append(tl)
            if tl:
                ratios.append(th / tl)
        r.number("high_low_tri_ratio", round(L.median(ratios), 1) if ratios else None, f"{len(pairs)} pair(s)")
        if ratios:
            r.headline(f"Each asset has a high poly (`{hs[0] if hs else '_high'}`) baked onto a low poly (`{ls[0] if ls else '_low'}`) "
                       f"with about 1/{L.fmt(L.median(ratios))} of its triangles.")
        r.rule(f"High/low naming: `name{hs[0] if hs else '_high'}` and `name{ls[0] if ls else '_low'}` "
               f"({len(pairs)} pair(s)). The high is about {L.fmt(L.median(ratios))}x the low's triangles; "
               f"low polys here have {', '.join(str(t) for t in lows)} triangles.")
    lods = Counter()
    for b, g in groups.items():
        n = len([k for k in g if k.startswith("lod")])
        if n:
            lods[n] += 1
    lowobjs = [o for b, g in groups.items() for k in ("low", "lod0") for o in g.get(k, [])] or \
              [o for o in objs if not split(o["name"], L)[1]]
    if lods:
        r.number("lod_count", max(lods))
        r.rule(f"LODs: {max(lods)} levels, named `_LOD0`.. style.")
    if lowobjs:
        slots = [len(o.get("materials", [])) for o in lowobjs]
        r.number("max_material_slots", max(slots) if slots else None)
        r.rule(f"Low polys carry at most {max(slots)} material slot(s) (median {L.fmt(L.median(slots))}).")
        mats = sorted({m for o in lowobjs for m in o.get("materials", []) if m})
        if mats:
            r.rule(f"Material names look like {', '.join('`' + m + '`' for m in mats[:4])}.")
        tri_mod = L.share(lowobjs, lambda o: "TRIANGULATE" in L.stack_types(o))
        r.number("triangulate_before_export", tri_mod >= 0.5)
        if tri_mod:
            r.rule(f"Low polys keep a Triangulate modifier ({L.percent(tri_mod)}) so the bake and the engine see the same triangles.")
        ng = sum(o["mesh"]["ngons"] for o in lowobjs)
        r.rule(f"N-gons on low polys: {ng}." + (" Keep them out of the export mesh." if not ng else ""))
        cn = L.share(lowobjs, lambda o: o["mesh"].get("custom_normals"))
        if cn:
            r.rule(f"{L.percent(cn)} of low polys carry custom normals.")
        mods = Counter(t for o in lowobjs for t in L.stack_types(o))
        if mods:
            r.rule("Modifiers left on low polys: " + ", ".join(f"{t} {c}" for t, c in mods.most_common()) + ".")
    cages = [o for o in objs if "cage" in o["name"].lower()]
    if cages:
        r.rule(f"Bake cages are kept as separate objects ({len(cages)}), named like `{cages[0]['name']}`.")
    for k, label in (("baker", "Baking in"), ("tri_budget", "Triangle budgets (artist)")):
        if ctx.answers.get(k):
            r.rule(f"{label}: {ctx.answers[k]}.")
    return r


def detect(doc, L):
    import os
    stem = os.path.splitext(doc.get("_submission", {}).get("file", doc.get("file", "")))[0]
    for s, role in FILE_ROLES:
        if stem.endswith(s):
            return f"{role} file of a high/low set"
    roles = {split(o["name"], L)[1] for o in L.objects(doc, "MESH")}
    if {"high", "low"} <= roles:
        return "high/low pair in one file"
    if any(r and r.startswith("lod") for r in roles):
        return "LODs"
    return None


def detect_project(docs, L, picked):
    """Add the high-poly file of every set whose _low/_game/_lods file was picked."""
    import os
    def stem(d):
        return os.path.splitext(d.get("_submission", {}).get("file", d.get("file", "")))[0]
    bases = set()
    for d in picked:
        s = stem(d)
        for suf, _ in FILE_ROLES:
            if s.endswith(suf):
                bases.add(s[: -len(suf)])
    return {id(d): "high file of a high/low set" for d in docs if stem(d) in bases and d not in picked}
