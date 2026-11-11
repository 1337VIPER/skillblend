"""Measured rules: how the artist sculpts and hands a sculpt over to the game mesh."""
import os
from collections import Counter

PAIR_HIGH = ("_sculpt", "_high", "_hp", "_hi", "_zb", "_dyn")
PAIR_LOW = ("_retopo", "_low", "_lp", "_lo", "_base", "_game")


def _sculpts(doc, L):
    for o in L.objects(doc, "MESH", include_outside=False):
        sk = o.get("mesh", {}).get("sculpt") or {}
        verts = o.get("mesh", {}).get("verts", 0)
        # face sets and masks linger on any mesh that has been in Sculpt Mode, so alone they need a dense mesh to count
        marks = (isinstance(sk.get("face_sets"), int) and sk["face_sets"] > 1) or sk.get("mask")
        if sk.get("kind") or sk.get("multires") or sk.get("voxel_size") or (marks and verts >= 20000):
            yield o, sk


def _base(name, L):
    n = L.strip_suffix(name).lower()
    for s in PAIR_HIGH + PAIR_LOW:
        if n.endswith(s):
            return n[: -len(s)]
    return n


def rules(ctx):
    L, r = ctx.lib, ctx.result
    found = [(d, o, sk) for d in ctx.files for o, sk in _sculpts(d, L)]
    if not found:
        return r
    kinds = Counter(sk.get("kind") or ("multires" if sk.get("multires") else "dense sculpt") for _, _, sk in found)
    method = kinds.most_common(1)[0][0]
    r.number("sculpt_method", method, f"{len(found)} sculpt object(s)")
    r.rule(f"{len(found)} sculpt object(s): " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()) + ".")
    mr = [sk["multires"] for _, _, sk in found if sk.get("multires")]
    if mr:
        r.number("multires_levels", L.mode(m["total_levels"] for m in mr))
        r.rule(f"Multires: usually {L.mode(m['total_levels'] for m in mr)} levels, sculpting at level "
               f"{L.mode(m['sculpt_levels'] for m in mr)}, rendering at {L.mode(m['render_levels'] for m in mr)}.")
    dense = [(o, sk) for _, o, sk in found if sk.get("kind") in ("dyntopo", "voxel-or-applied-multires")]
    if dense:
        pct = [sk["edge_pct_of_size"] for _, sk in dense if sk.get("edge_pct_of_size")]
        tris = [o["mesh"]["tri_count"] for o, _ in dense]
        if pct:
            r.number("sculpt_detail_pct", round(L.median(pct), 4), "median edge / object size, %")
        r.rule(f"Dense sculpts: about {L.fmt(L.median(tris) / 1000)}k triangles"
               + (f", median edge {L.fmt(L.median(pct))}% of the object's size "
                  f"({'fine detail: pores, wrinkles' if L.median(pct) < 0.3 else 'medium detail: forms and folds' if L.median(pct) < 1.5 else 'blocking-out density'})" if pct else "") + ".")
    vox = [sk["voxel_size"] for _, _, sk in found if sk.get("voxel_size")]
    if vox:
        r.number("voxel_size_mm", round(L.median(vox) * 1000, 3))
        r.rule(f"Voxel remesh size about {L.fmt(L.median(vox) * 1000)} mm.")
    fsets = [sk["face_sets"] for _, _, sk in found if isinstance(sk.get("face_sets"), int)]
    masks = sum(1 for _, _, sk in found if sk.get("mask"))
    if fsets or masks:
        r.rule((f"Face sets on {len(fsets)} sculpt(s) (median {L.fmt(L.median(fsets))} sets)" if fsets else "No face sets")
               + (f"; masks kept on {masks}" if masks else "") + ".")
    sym = [o["mesh"].get("symmetry") for _, o, _ in found if o["mesh"].get("symmetry") is not None]
    if sym:
        r.rule(f"Sculpts are {L.percent(L.median(sym))} symmetric across X (median); "
               + ("symmetry kept on." if L.median(sym) > 0.9 else "an asymmetric pass is part of the workflow."))
    # hand-over: sculpt objects with a clean partner of the same base name (in the same file or a sibling file)
    names = Counter()
    clean = set()
    for d in ctx.all_files:
        for o in L.meshes(d):
            q = o["mesh"].get("quad_ratio") or 0
            if q > 0.9 and o["mesh"]["verts"] < 60000:
                clean.add(_base(o["name"], L))
    paired = sum(1 for o, _ in dense if _base(o["name"], L) in clean)
    if dense:
        r.rule(f"{paired} of {len(dense)} dense sculpt(s) have a clean quad mesh of the same name: "
               + ("the sculpt is baked onto a separate game mesh." if paired else "no game mesh found next to the sculpt."))
    r.headline(f"Sculpting is done with {method.replace('-', ' ')}"
               + (f" ({L.mode(m['total_levels'] for m in mr)} Multires levels)" if mr else "")
               + (f", detail down to {L.fmt(r.numbers['sculpt_detail_pct'])}% of the object's size" if r.numbers.get("sculpt_detail_pct") else "")
               + ", kept as its own stage.")
    if ctx.answers.get("sculpt_notes"):
        r.rule(f"Artist: {ctx.answers['sculpt_notes']}.")
    return r


def detect(doc, L):
    n = sum(1 for _ in _sculpts(doc, L))
    return f"{n} sculpt object(s)" if n else None
