"""Style check: skinning and skeleton against the artist's character setup."""
import doclib as L


def check(doc, style):
    out = []
    mi = style.get("max_influences") or 4
    for o in L.meshes(doc):
        sk = o["mesh"].get("skin")
        if not sk:
            continue
        if sk["max_influences"] > mi:
            out.append(("warn", f"{o['name']}: up to {sk['max_influences']} weights per vertex; the style uses at most {mi}."))
        if sk["unweighted"] > 0.001:
            out.append(("warn", f"{o['name']}: {sk['unweighted'] * 100:.1f}% of vertices have no weights (they won't move)."))
        if sk["not_normalised"] > 0.05:
            out.append(("info", f"{o['name']}: {sk['not_normalised'] * 100:.0f}% of vertices have weights that don't add up to 1."))
    naming = style.get("skeleton_naming")
    for a in L.objects(doc, "ARMATURE"):
        info = a.get("armature") or {}
        if naming and info.get("naming") and info["naming"] != naming and naming != "custom":
            out.append(("info", f"{a['name']}: bones are named {info['naming']}-style; the style uses {naming}."))
        pose = style.get("rest_pose")
        ang = info.get("arm_angle_deg")
        if pose and ang is not None:
            mine = "T-pose" if ang < 15 else ("A-pose" if ang < 60 else "arms down")
            if mine != pose:
                out.append(("info", f"{a['name']}: rest pose is {mine}; the style uses {pose}."))
    for name, c in (doc.get("clearance") or {}).items():
        if isinstance(c, dict) and c.get("inside", 0) > 0.05:
            out.append(("warn", f"{name}: {c['inside'] * 100:.0f}% of the garment dips inside the body."))
    return out
