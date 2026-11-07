"""Style check: round-part segment counts."""
import doclib as L


def check(doc, style):
    out = []
    seg = style.get("round_segments")
    if not seg:
        return out
    odd = []
    for o in L.meshes(doc):
        for k in (o["mesh"].get("ngon_sizes") or {}):
            k = int(k)
            if k >= 8 and (k < seg / 2 or k > seg * 2):
                odd.append(f"{o['name']} ({k})")
                break
    if odd:
        out.append(("info", f"Round parts far from the style's {seg} segments: {', '.join(odd[:6])}."))
    return out
