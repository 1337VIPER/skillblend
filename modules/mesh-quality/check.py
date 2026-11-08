"""Style check: topology quality against the artist's own tolerances."""
import doclib as L


def check(doc, style):
    out = []
    asp, skew, bent = style.get("quality_aspect_p90"), style.get("quality_skew_p90"), style.get("nonplanar_max")
    for o in L.meshes(doc):
        me = o["mesh"]
        q = me.get("quality") or {}
        if not q or me["faces"] < 6:
            continue
        if me.get("non_manifold_edges") and not style.get("non_manifold_ok"):
            out.append(("warn", f"{o['name']}: {me['non_manifold_edges']} non-manifold edge(s)."))
        if q.get("zero_area_faces"):
            out.append(("warn", f"{o['name']}: {q['zero_area_faces']} zero-area face(s)."))
        if asp and q.get("aspect_p90") and q["aspect_p90"] > asp * 1.5:
            out.append(("info", f"{o['name']}: stretched faces (90% under {q['aspect_p90']:.1f}:1; the style stays under {asp:.1f}:1)."))
        if skew is not None and q.get("quad_skew_p90") is not None and q["quad_skew_p90"] > skew + 15:
            out.append(("info", f"{o['name']}: skewed quads ({q['quad_skew_p90']:.0f} deg off square; the style stays within {skew:.0f})."))
        if bent is not None and q.get("nonplanar_quads") is not None and q["nonplanar_quads"] > bent * 2 + 0.05:
            out.append(("info", f"{o['name']}: {q['nonplanar_quads'] * 100:.0f}% of quads are bent out of plane."))
    return out
