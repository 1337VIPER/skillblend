"""Measured rules: blockout versus finished model."""


def coll_objects(d, L, word):
    """Mesh objects in a collection whose name contains `word` (or its child collections)."""
    names = set()
    def walk(c, inside):
        inside = inside or word in c["name"].lower()
        if inside:
            names.add(c["name"])
        for ch in c.get("children", []):
            walk(ch, inside)
    walk(d["collections"], False)
    return [o for o in L.objects(d, "MESH") if set(o.get("collections", [])) & names
            and o.get("display_type") not in ("WIRE", "BOUNDS")]


def extent(objs):
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for o in objs:
        for i in range(3):
            half = o["dimensions"][i] / 2
            lo[i] = min(lo[i], o["location"][i] - half)
            hi[i] = max(hi[i], o["location"][i] + half)
    return [h - l for l, h in zip(lo, hi)]


def rules(ctx):
    L, r = ctx.lib, ctx.result
    found = 0
    for d in ctx.files:
        blk = coll_objects(d, L, "block")
        fin = coll_objects(d, L, "final") or [o for o in L.meshes(d) if o not in blk]
        refs = [o for o in L.objects(d, "EMPTY") if (o.get("empty") or {}).get("image")]
        name = d.get("_submission", {}).get("file", d.get("file"))
        if not blk:
            r.warn(f"{name}: no collection named Blockout was found, so blockout and final can't be compared.")
            continue
        found += 1
        tb = sum(o["mesh"].get("eval_tri_count", 0) for o in blk)
        tf = sum(o["mesh"].get("eval_tri_count", 0) for o in fin)
        eb, ef = extent(blk), extent(fin)
        drift = max(abs(a - b) / max(a, 1e-6) for a, b in zip(eb, ef)) if fin else 0
        r.rule(f"{name}: blockout {len(blk)} parts / {tb} tris, final {len(fin)} parts / {tf} tris "
               f"({L.fmt(len(fin) / max(1, len(blk)))}x the parts). The final stays within {L.percent(drift)} of the blockout's overall size.")
        bmods = sum(len(o.get("modifiers", [])) for o in blk)
        r.rule(f"The blockout uses {'plain primitives with no modifiers' if not bmods else str(bmods) + ' modifiers'}"
               f"; median {L.fmt(L.median(o['mesh']['faces'] for o in blk))} faces per blockout part.")
        if refs:
            r.rule(f"The reference picture sits in the scene as an image empty ({len(refs)}).")
    if found:
        r.headline("Every model starts as a blockout that fixes the proportions before any detail.")
        r.rule("Proportions are settled in the blockout: the finished model keeps its overall size and adds parts and detail on top.")
    for k, label in (("start_from", "Starts from"), ("blockout_method", "Blockout method"),
                     ("detail_order", "Detail order")):
        if ctx.answers.get(k):
            r.rule(f"{label} (artist): {ctx.answers[k]}.")
    return r


def detect(doc, L):
    blk = coll_objects(doc, L, "block")
    return f"Blockout collection with {len(blk)} parts" if blk else None
