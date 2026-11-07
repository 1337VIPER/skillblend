"""Measured rules: vehicle proportions."""
TYRE = ("tire", "tyre", "tires", "tyres")
WHEEL = ("wheel", "wheels", "rim", "rims")


def extent(objs):
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for o in objs:
        for i in range(3):
            h = o["dimensions"][i] / 2
            lo[i] = min(lo[i], o["location"][i] - h)
            hi[i] = max(hi[i], o["location"][i] + h)
    return [b - a for a, b in zip(lo, hi)]


def wheel_parts(objs):
    """The round parts that set the wheel size: tyres if named, else the biggest wheel-named parts."""
    def named(words):
        from doclib import name_tokens
        return [o for o in objs if set(name_tokens(o["name"])) & set(words)
                or any(set(name_tokens(c)) & set(words) for c in o.get("collections", []))]
    cands = named(TYRE) or named(WHEEL)
    if not cands:
        return []
    biggest = max(max(o["dimensions"]) for o in cands)
    return [o for o in cands if max(o["dimensions"]) >= 0.8 * biggest]


def rules(ctx):
    L, r = ctx.lib, ctx.result
    ratios = []
    for d in ctx.files:
        objs = list(L.meshes(d))
        if not objs:
            continue
        name = d.get("_submission", {}).get("file", d.get("file"))
        ex = extent(objs)
        axis = "X" if ex[0] >= ex[1] else "Y"
        length = max(ex[0], ex[1])
        r.rule(f"{name}: {L.fmt(length)} m long along {axis}, {L.fmt(min(ex[0], ex[1]))} m wide, "
               f"{L.fmt(ex[2])} m tall ({len(objs)} parts).")
        wheels = wheel_parts(objs)
        if wheels:
            dia = L.median(sorted(o["dimensions"], reverse=True)[1] if len(o["dimensions"]) == 3 else max(o["dimensions"])
                           for o in wheels)
            ratios.append(dia / length)
            r.rule(f"Wheels about {L.fmt(dia)} m across, {L.fmt(dia / length * 100)}% of the overall length.")
        if any(L.is_subd_cage(o) for o in objs):
            r.rule("Body panels are SubD cages (live Subdivision Surface).")
    if ratios:
        r.number("car_wheel_diameter_of_length", round(L.median(ratios), 3), "wheel diameter / overall length")
        r.headline(f"Vehicles are proportioned from the wheel: wheels about {L.fmt(L.median(ratios) * 100)}% of the overall length.")
    if ctx.answers.get("vehicle_method"):
        r.rule(f"Body method (artist): {ctx.answers['vehicle_method']}.")
    return r


def detect(doc, L):
    objs = list(L.meshes(doc))
    if not objs or len(wheel_parts(objs)) < 3:  # a ship's wheel or a spare is not a vehicle
        return None
    ex = extent(objs)
    length = max(ex[0], ex[1])
    return f"vehicle, {length:.2f} m long" if length >= 1.2 else None
