"""Measured rules: characters - proportions, pose, skeleton, weights, loops, garments, gear and face shapes."""
from collections import Counter

ARKIT = {"jawopen", "eyeblinkleft", "eyeblinkright", "mouthsmileleft", "mouthsmileright", "browinnerup", "mouthfunnel",
         "mouthpucker", "cheekpuff", "eyewideleft", "eyewideright", "jawleft", "jawright"}


def _armatures(doc, L):
    return [o for o in L.objects(doc, "ARMATURE") if o.get("armature") and "error" not in o["armature"]]


def _skinned(doc, L):
    return [o for o in L.meshes(doc) if o["mesh"].get("skin")]


def rules(ctx):
    L, r = ctx.lib, ctx.result
    arms, skinned, heads = [], [], []
    for d in ctx.files:
        arms += _armatures(d, L)
        skinned += _skinned(d, L)
    if not arms and not skinned:
        return r
    if arms:
        a = [x["armature"] for x in arms]
        hs = [x["height"] for x in a if x.get("height")]
        if hs:
            r.number("character_height_m", round(L.median(hs), 3), f"{len(hs)} skeleton(s)")
        conv = L.mode(x["naming"] for x in a)
        r.number("skeleton_naming", conv)
        angles = [x["arm_angle_deg"] for x in a if x.get("arm_angle_deg") is not None]
        if angles:
            ang = L.median(angles)
            pose = "T-pose" if ang < 15 else ("A-pose" if ang < 60 else "arms down")
            r.number("rest_pose", pose, f"upper arm about {L.fmt(ang)} deg below horizontal")
        r.rule(f"{len(arms)} skeleton(s): {L.fmt(L.median(x['bones'] for x in a))} bones "
               f"({L.fmt(L.median(x['deform_bones'] for x in a))} deform), naming {conv}, chains up to {max(x['max_depth'] for x in a)} deep"
               + (f", about {L.fmt(L.median(hs))} m tall" if hs else "")
               + (f", rest pose {r.numbers['rest_pose']} (upper arm {L.fmt(L.median(angles))} deg down)" if angles else "") + ".")
        cons = Counter()
        for x in a:
            cons.update(x.get("constraints") or {})
        if cons:
            r.rule("Bone constraints: " + ", ".join(f"{k.replace('_', ' ').title()} {v}" for k, v in cons.most_common(6)) + ".")
        gear = sum(o.get("children_on_bones", 0) for o in arms)
        if gear:
            r.rule(f"{gear} rigid part(s) ride on a single bone (bone-parented gear) instead of being weighted.")
    if skinned:
        sk = [o["mesh"]["skin"] for o in skinned]
        mi = int(L.pct([s["max_influences"] for s in sk], 0.9))
        r.number("max_influences", mi, f"90th percentile over {len(sk)} skinned mesh(es)")
        unw = L.median(s["unweighted"] for s in sk)
        over = L.median(s["over_4"] for s in sk)
        unn = L.median(s["not_normalised"] for s in sk)
        pv = L.share(sk, lambda s: s.get("preserve_volume"))
        r.rule(f"Weights: up to {mi} influences per vertex"
               + (f" ({L.percent(over)} of vertices over 4)" if over else "") + f"; unweighted vertices {L.percent(unw)}; "
               f"not normalised {L.percent(unn)}; Preserve Volume on {L.percent(pv)} of skinned meshes.")
    loops = Counter()
    for d in ctx.files:
        for o in L.meshes(d):
            if o["mesh"].get("skin") or any(k in o["name"].lower() for k in ("head", "face", "body")):
                cl = o["mesh"].get("closed_loops") or {}
                if isinstance(cl, dict) and "error" not in cl:
                    for k, v in cl.items():
                        loops[int(k)] += v
                toks = set(L.name_tokens(o["name"]))
                if toks & {"head", "face"} and 0.12 <= max(o["dimensions"]) <= 0.4:  # a head, not a helmet assembly
                    heads.append(o)
    if loops:
        r.rule("Closed edge loops on bodies and heads (edges per loop x how many): "
               + ", ".join(f"{k} x{v}" for k, v in sorted(loops.items(), key=lambda kv: -kv[1])[:8])
               + ". These are the rings round neck, limbs, eyes and mouth that bend cleanly.")
    ratios = []
    for d in ctx.files:  # from the skeleton and the meshes skinned to it: top of the body, base of the skull, feet
        for a_ in _armatures(d, L):
            hz = a_["armature"].get("head_base_z")
            body = [o for o in L.meshes(d) if (o["mesh"].get("skin") or {}).get("armature") == a_["name"] and o.get("world_z")]
            if hz is None or not body:
                continue
            top = max(o["world_z"][1] for o in body)
            bottom = min(o["world_z"][0] for o in body)
            if top - hz > 0.05:
                ratios.append((top - bottom) / (top - hz))
    ratios = [x for x in ratios if 3 <= x <= 10]
    if ratios:
        r.number("heads_tall", round(L.median(ratios), 2), f"{len(ratios)} skinned character(s)")
        r.rule(f"Proportions: about {L.fmt(L.median(ratios))} heads tall (full height over the head, from the top of the "
               "skinned body down to where the head bone starts).")
    sym = [o["mesh"].get("symmetry") for d in ctx.files for o in L.meshes(d) if o["mesh"].get("skin") and o["mesh"].get("symmetry") is not None]
    if sym:
        r.rule(f"Skinned meshes are {L.percent(L.median(sym))} mirror-symmetric across X (median).")
    cl = [c for d in ctx.files for c in (d.get("clearance") or {}).values() if isinstance(c, dict) and "median" in c]
    if cl:
        med = L.median(c["median"] for c in cl)
        r.number("garment_clearance_mm", round(med * 1000, 2), f"{len(cl)} garment(s)")
        ins = L.median(c["inside"] for c in cl)
        r.rule(f"Garments sit about {L.fmt(med * 1000)} mm off the body (10% of each garment under "
               f"{L.fmt(L.median(c['p10'] for c in cl) * 1000)} mm); {L.percent(ins)} of garment vertices dip inside; "
               f"{sum(1 for c in cl if c['shrinkwrap'])} of {len(cl)} are Shrinkwrapped to the body.")
    keys = Counter(k for d in ctx.files for o in L.meshes(d) for k in (o["mesh"].get("shape_key_names") or [])[1:])
    if keys:
        arkit = sum(1 for k in keys if k.lower() in ARKIT)
        r.number("face_shape_keys", "arkit" if arkit >= 3 else "custom")
        r.rule(f"{len(keys)} shape keys" + (f", {arkit} in the ARKit naming" if arkit else "") + ": "
               + ", ".join(f"`{k}`" for k, _ in keys.most_common(8)) + ".")
    acts = [a for d in ctx.files for a in (d.get("actions") or [])]
    if acts:
        r.rule(f"{len(acts)} animation action(s) in the files, e.g. " + ", ".join(f"`{a['name']}`" for a in acts[:5]) + ".")
    bits = []
    if r.numbers.get("character_height_m"):
        bits.append(f"about {L.fmt(r.numbers['character_height_m'])} m tall")
    if r.numbers.get("rest_pose"):
        bits.append(f"in {r.numbers['rest_pose']}")
    if r.numbers.get("skeleton_naming"):
        nm = r.numbers["skeleton_naming"]
        bits.append("on a custom skeleton" if nm == "custom" else f"on an {nm.title()}-named skeleton" if nm[0] in "aeiou" else f"on a {nm.title()}-named skeleton")
    if r.numbers.get("max_influences"):
        bits.append(f"up to {r.numbers['max_influences']} weights per vertex")
    if r.numbers.get("garment_clearance_mm"):
        bits.append(f"garments {L.fmt(r.numbers['garment_clearance_mm'])} mm off the body")
    r.headline("Characters are built " + ", ".join(bits) + "." if bits else "Characters are rigged and skinned.")
    for k in ("engine_skeleton", "character_notes"):
        if ctx.answers.get(k):
            r.rule(f"Artist: {ctx.answers[k]}.")
    return r


def detect(doc, L):
    arms = _armatures(doc, L)
    sk = _skinned(doc, L)
    if arms or sk:
        return f"{len(arms)} armature(s), {len(sk)} skinned mesh(es)"
    return None
