"""Measured rules: parts, assemblies, pivots, detail density and round-part segments."""
import os
import re
from collections import Counter

PIVOT_WORDS = ("pivot", "socket", "anchor", "mount", "attach", "hinge", "muzzle", "fx", "spawn")


def collections_of(doc):
    out = []
    stack = [doc["collections"]]
    while stack:
        c = stack.pop()
        if c["name"] != "Scene Collection":
            out.append(c)
        stack.extend(c.get("children", []))
    return out


def common_prefix(names):
    """A short asset code shared by most names, like 'SR7_' or 'BY_'."""
    pref = Counter()
    for n in names:
        m = re.match(r"^([A-Za-z0-9]{1,6}_)", n)
        if m:
            pref[m.group(1)] += 1
    if not pref:
        return None, 0
    p, c = pref.most_common(1)[0]
    return (p, c) if c >= max(3, 0.6 * len(names)) else (None, 0)


def rules(ctx):
    L, r = ctx.lib, ctx.result
    docs = [d for d in ctx.files if L.export_role(d) not in ("game", "lods")]
    if not docs:
        return r
    counts, sizes, dens = [], [], {"small": [], "medium": [], "large": []}
    for d in docs:
        parts = list(L.meshes(d))
        counts.append(len(parts))
        for o in parts:
            md = L.max_dim(o)
            if md <= 0:
                continue
            sizes.append(md)
            area = o["mesh"].get("area_m2") or 0
            tris = o["mesh"].get("eval_tri_count") or o["mesh"].get("tri_count") or 0
            if area > 0 and tris:
                band = "small" if md < 0.05 else ("medium" if md < 0.5 else "large")
                dens[band].append(tris / (area * 1e4))  # triangles per cm2
    r.number("parts_per_asset", int(L.median(counts)), f"median over {len(docs)} files")
    small = L.pct(sizes, 0.05)
    r.number("min_detail_mm", round(small * 1000, 1) if small else None, "5th percentile of part size")
    r.headline(f"Every real part is its own object: a typical asset has about {int(L.median(counts))} parts, "
               f"with details down to about {L.fmt(small * 1000)} mm.")
    r.rule(f"Parts per asset: median {int(L.median(counts))} (from {min(counts)} to {max(counts)}). "
           f"Part sizes: smallest tenth under {L.fmt(L.pct(sizes, 0.1) * 1000)} mm, median {L.fmt(L.median(sizes) * 1000)} mm.")
    d_txt = []
    for band, label in (("small", "under 5 cm"), ("medium", "5-50 cm"), ("large", "over 50 cm")):
        if dens[band]:
            v = L.median(dens[band])
            r.number(f"tri_density_{band}", round(v, 2), f"triangles per cm2, parts {label}")
            d_txt.append(f"{label}: {L.fmt(v)} tris/cm2")
    if d_txt:
        r.rule("Detail density (high poly, after modifiers): " + "; ".join(d_txt) +
               ". Small parts are far denser than big panels: spend triangles where the eye lands.")
    caps = Counter()
    for d in docs:
        for o in L.meshes(d):
            for k, c in (o["mesh"].get("ngon_sizes") or {}).items():
                if int(k) >= 8:
                    caps[int(k)] += 1
    if caps:
        top = [k for k, _ in caps.most_common(3)]
        r.number("round_segments", top[0], "most common n-gon cap size")
        r.rule("Round parts use " + ", ".join(f"{k} segments ({caps[k]} parts)" for k in top) + ".")
    # assemblies
    col_counts, codes, examples = [], Counter(), []
    for d in docs:
        cols = collections_of(d)
        col_counts.append(len(cols))
        p, _ = common_prefix([c["name"] for c in cols])
        if p:
            codes[p] += 1
            examples += [c["name"] for c in cols[:3] if c["name"] not in examples]
    if any(col_counts):
        with_cols = sum(1 for c in col_counts if c >= 3)
        r.number("assembly_collections", with_cols >= 0.5 * len(docs))
        r.rule(f"{with_cols} of {len(docs)} assets are split into assembly collections (median {L.fmt(L.median(col_counts))} per asset).")
    if codes:
        r.number("assembly_code_prefix", True, f"{sum(codes.values())} assets")
        r.rule("Each asset gets a short code, and its assembly collections are named `CODE_Assembly` "
               f"(e.g. {', '.join('`' + e + '`' for e in examples[:4])}).")
        r.headline("Assets are organised into assembly collections named with a short asset code (`CODE_Assembly`).")
    parented = L.share([o for d in docs for o in L.meshes(d)], lambda o: o.get("parent"))
    r.rule(f"{L.percent(parented)} of parts are parented " + ("(assemblies use parent hierarchies)." if parented and parented > 0.3
                                                              else "(parts stay flat; collections do the grouping)."))
    empties = [o for d in docs for o in L.objects(d, "EMPTY")]
    piv = [o for o in empties if any(w in o["name"].lower() for w in PIVOT_WORDS)]
    if piv:
        pref, _ = common_prefix([o["name"] for o in piv])
        r.number("pivot_empty_prefix", pref or None)
        r.rule(f"{len(piv)} pivot/socket empties mark where things turn, mount or spawn effects, named like "
               + ", ".join(f"`{o['name']}`" for o in piv[:4]) + ".")
        r.headline("Moving parts and effect points are marked with named pivot/socket empties.")
    if ctx.answers.get("assembly_notes"):
        r.rule(f"Artist's notes: {ctx.answers['assembly_notes']}.")
    return r


def detect(doc, L):
    if L.export_role(doc) in ("game", "lods"):
        return None
    n = len(list(L.meshes(doc)))
    return f"{n}-part asset" if n >= 5 else None
