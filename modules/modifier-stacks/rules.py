"""Measured rules: which modifiers are stacked, and in what order."""
from collections import Counter, defaultdict


def global_order(stacks, default=()):
    """One order for all modifier types: A goes before B when the files put A first more often.

    A topological sort of those majority votes; ties go to the type that sits higher in its
    stacks on average, then to the generic default order.
    """
    before = defaultdict(int)
    types = Counter()
    pos = defaultdict(list)
    for s in stacks:
        seen = []
        for i, t in enumerate(s):
            types[t] += 1
            pos[t].append(i / max(1, len(s) - 1))
            for p in seen:
                if p != t:
                    before[(p, t)] += 1
            seen.append(t)
    rank = {t: i for i, t in enumerate(default)}
    def key(t):
        return (sum(pos[t]) / len(pos[t]), rank.get(t, len(rank)), t)
    must = {t: {a for a in types if before[(a, t)] > before[(t, a)]} for t in types}
    order, left = [], set(types)
    while left:
        ready = [t for t in left if not (must[t] & left)] or list(left)  # a cycle: take the best-placed
        nxt = min(ready, key=key)
        order.append(nxt)
        left.discard(nxt)
    return order, before, types


def merge_with_default(measured, default):
    """Measured order, plus default types it never saw, each placed after its nearest default predecessor."""
    out = list(measured)
    for i, t in enumerate(default):
        if t in out:
            continue
        pos = 0
        for prev in reversed(default[:i]):
            if prev in out:
                pos = out.index(prev) + 1
                break
        out.insert(pos, t)
    return out


def rules(ctx):
    L, r = ctx.lib, ctx.result
    parts = [o for _, o in ctx.meshes()] + [o for d in ctx.files for o in L.objects(d, "CURVE")]
    stacks = [L.stack_types(o) for o in parts if o.get("modifiers")]
    if not stacks:
        r.warn("No modifiers found on any part. This module needs a file built with a live modifier stack.")
        return r
    order, before, types = global_order(stacks, ctx.defaults.get("stack_order") or [])
    # the order itself is read from every submitted file, not only this module's
    every = [L.stack_types(o) for d in ctx.all_files for o in L.meshes(d) if o.get("modifiers")]
    full, _, _ = global_order(every or stacks, ctx.defaults.get("stack_order") or [])
    merged = merge_with_default(full, ctx.defaults.get("stack_order") or [])
    r.number("stack_order", merged, f"from {len(every or stacks)} stacks in all files"
             + ("; unseen types keep their generic place" if merged != full else ""))
    r.rule("Stack order (top to bottom): " + " > ".join(full) + ".")
    r.headline("Modifier stacks run " + " > ".join(full) + ".")
    conflicts = [(a, b, v, before.get((b, a), 0)) for (a, b), v in before.items()
                 if order.index(a) < order.index(b) and before.get((b, a), 0)]
    for a, b, v, w in conflicts[:3]:
        r.rule(f"Mostly {a} before {b} ({v} times), but {b} before {a} {w} time(s).")
    common = Counter(tuple(s) for s in stacks).most_common(3)
    r.rule("Most common stacks: " + "; ".join(f"{' > '.join(s)} ({c})" for s, c in common) + ".")
    r.rule("Modifier use: " + ", ".join(f"{t} on {c} part(s)" for t, c in types.most_common()) + ".")
    mir = [m for o in parts for m in L.mods(o, "MIRROR")]
    if mir:
        clip = L.share(mir, lambda m: m.get("use_clip"))
        bis = L.share(mir, lambda m: any(m.get("use_bisect_axis") or []))
        mo = L.share(mir, lambda m: m.get("mirror_object"))
        r.rule(f"Mirror: clipping {L.percent(clip)}, bisect {L.percent(bis)}, around another object {L.percent(mo)}.")
    arr = [m for o in parts for m in L.mods(o, "ARRAY")]
    if arr:
        r.rule(f"Array: fit {L.mode(m.get('fit_type') for m in arr)}, typical count {L.mode(m.get('count') for m in arr)}, "
               f"merge {L.percent(L.share(arr, lambda m: m.get('use_merge_vertices')))}, caps on {sum(1 for m in arr if m.get('start_cap') or m.get('end_cap'))}.")
    sol = [(o, m) for o in parts for m in L.mods(o, "SOLIDIFY")]
    if sol:
        th = [abs(m["thickness"]) for _, m in sol if m.get("thickness")]
        r.rule(f"Solidify: thickness median {L.mm(L.median(th))}, even thickness {L.percent(L.share((m for _, m in sol), lambda m: m.get('use_even_offset')))}.")
    curves = [o for d in ctx.files for o in L.objects(d, "CURVE")]
    pipes = [o for o in curves if (o.get("curve") or {}).get("bevel_depth")]
    if pipes:
        r.rule(f"Pipes and cables as curves with a bevel depth ({len(pipes)}), median radius "
               f"{L.mm(L.median(o['curve']['bevel_depth'] for o in pipes))}.")
    skins = [o for o in parts if "SKIN" in L.stack_types(o)]
    if skins:
        r.rule(f"Skin modifier used for {len(skins)} part(s) (pipes, frames, armatures).")
    hidden = sum(1 for o in parts for m in o.get("modifiers", []) if not m.get("show_viewport"))
    if hidden:
        r.rule(f"{hidden} modifier(s) are switched off in the viewport while working.")
    if ctx.answers.get("stack_notes"):
        r.rule(f"Artist's notes: {ctx.answers['stack_notes']}.")
    return r


STACK_TYPES = {"MIRROR", "ARRAY", "SOLIDIFY", "SKIN", "SCREW", "BOOLEAN", "SUBSURF", "BEVEL", "CURVE",
               "SIMPLE_DEFORM", "DISPLACE", "SHRINKWRAP", "WELD"}


def detect(doc, L):
    parts = [o for o in L.meshes(doc) if set(L.stack_types(o)) & STACK_TYPES]
    return f"{len(parts)} parts with live modifier stacks" if parts else None
