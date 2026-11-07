"""Style check: modifier order against the style's stack order."""
import doclib as L


def check(doc, style):
    out = []
    order = style.get("stack_order") or []
    if not order:
        return out
    rank = {t: i for i, t in enumerate(order)}
    for o in L.meshes(doc):
        s = [t for t in L.stack_types(o) if t in rank]
        for a, b in zip(s, s[1:]):
            if rank[a] > rank[b]:
                out.append(("info", f"{o['name']}: {a} comes before {b}; the style puts {b} first."))
                break
    return out
