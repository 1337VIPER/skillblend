"""Measured rules: the scene around the model - render engine, colour management, world, lights and cameras."""
from collections import Counter

ENGINE = {"BLENDER_EEVEE": "EEVEE", "BLENDER_EEVEE_NEXT": "EEVEE", "CYCLES": "Cycles", "BLENDER_WORKBENCH": "Workbench"}


def _has_scene(doc, L):
    lights = [o for o in L.objects(doc, "LIGHT")]
    cams = [o for o in L.objects(doc, "CAMERA")]
    w = doc.get("world") or {}
    return lights, cams, w.get("kind") not in (None, "color") or bool(w.get("use_nodes") and w.get("strength") not in (None, 1.0))


def rules(ctx):
    L, r = ctx.lib, ctx.result
    docs = ctx.files
    if not docs:
        return r
    rend = [d.get("render") or {} for d in docs]
    eng = L.mode(x.get("engine") for x in rend)
    vt = L.mode(x.get("view_transform") for x in rend)
    look = L.mode(x.get("look") for x in rend)
    r.number("render_engine", eng, f"{len(docs)} files")
    r.number("view_transform", vt)
    if look and look != "None":
        r.number("look", look)
    exp = [x.get("exposure") for x in rend if x.get("exposure") is not None]
    if exp and L.median(exp):
        r.number("exposure", L.median(exp))
    samples = [x.get("samples") for x in rend if isinstance(x.get("samples"), int)]
    r.rule(f"Render engine {ENGINE.get(eng, eng)}" + (f", about {int(L.median(samples))} samples" if samples else "")
           + f"; colour management {vt}" + (f" with look {look}" if look and look != "None" else "")
           + (f", exposure {L.fmt(L.median(exp))}" if exp and L.median(exp) else "") + ".")
    ft = L.share(rend, lambda x: x.get("film_transparent"))
    if ft:
        r.rule(f"Transparent film background in {L.percent(ft)} of files.")
    worlds = [d.get("world") for d in docs if d.get("world")]
    if worlds:
        kinds = Counter(w.get("kind") for w in worlds)
        kind = kinds.most_common(1)[0][0]
        r.number("world_kind", kind)
        st = [w.get("strength") for w in worlds if isinstance(w.get("strength"), (int, float))]
        if st:
            r.number("world_strength", round(L.median(st), 3))
        hdris = sorted({h for w in worlds for h in (w.get("hdri") or [])})
        r.rule("World: " + ", ".join(f"{k} {c}" for k, c in kinds.most_common())
               + (f", strength about {L.fmt(L.median(st))}" if st else "")
               + (f"; HDRIs {', '.join('`' + h + '`' for h in hdris[:4])}" if hdris else "") + ".")
    lights = [o for d in docs for o in L.objects(d, "LIGHT") if o.get("light")]
    if lights:
        types = Counter(o["light"]["type"] for o in lights)
        rig = [t for t, _ in types.most_common()]
        r.number("light_rig", rig)
        per = []
        for t, c in types.most_common():
            en = [o["light"]["energy"] for o in lights if o["light"]["type"] == t]
            per.append(f"{t.lower()} x{c} (about {L.fmt(L.median(en))} {'W/m2' if t == 'SUN' else 'W'})")
        r.number("light_energy", {t: round(L.median([o["light"]["energy"] for o in lights if o["light"]["type"] == t]), 3)
                                  for t in types})
        r.rule(f"Lights ({len(lights)} in {sum(1 for d in docs if any(True for _ in L.objects(d, 'LIGHT')))} files): " + ", ".join(per) + ".")
    cams = [o for d in docs for o in L.objects(d, "CAMERA") if o.get("camera")]
    if cams:
        persp = [o["camera"]["lens"] for o in cams if o["camera"]["type"] == "PERSP"]
        ortho = sum(1 for o in cams if o["camera"]["type"] == "ORTHO")
        if persp:
            r.number("review_lens_mm", round(L.median(persp), 1))
        r.rule(f"Cameras: {len(cams)}" + (f", lenses {L.fmt(min(persp))}-{L.fmt(max(persp))} mm (median {L.fmt(L.median(persp))})" if persp else "")
               + (f", {ortho} orthographic" if ortho else "") + ".")
    world_txt = {"hdri": "an HDRI world", "sky": "a sky world", "gradient": "a gradient world", "color": "a flat-colour world"}
    r.headline(f"Models are looked at in {ENGINE.get(eng, eng)} with {vt} colour"
               + (f", {world_txt.get(r.numbers.get('world_kind'), 'a world')}" if worlds else "")
               + (f" and a {' + '.join(t.lower() for t in r.numbers['light_rig'][:3])} light rig" if lights else "")
               + (f"; review camera about {L.fmt(r.numbers['review_lens_mm'])} mm" if r.numbers.get("review_lens_mm") else "") + ".")
    return r


def detect(doc, L):
    if L.export_role(doc) in ("game", "lods"):
        return None
    lights, cams, world = _has_scene(doc, L)
    if lights or cams or world:
        bits = []
        if lights:
            bits.append(f"{len(lights)} light(s)")
        if cams:
            bits.append(f"{len(cams)} camera(s)")
        if world:
            bits.append(f"{(doc.get('world') or {}).get('kind')} world")
        return ", ".join(bits)
    return None
