"""Measured rules: the kit/insert library and how its pieces are placed."""
import re
from collections import Counter

KIT_WORDS = ("kit", "insert", "library", "lib", "greeble", "asset")


def is_kit_doc(d, L):
    objs = list(L.objects(d, include_outside=True))
    assets = sum(1 for o in objs if o.get("is_asset"))
    cols = []
    stack = [d["collections"]]
    while stack:
        c = stack.pop()
        cols.append(c["name"].lower())
        stack.extend(c.get("children", []))
    named = any(any(w in c for w in KIT_WORDS) for c in cols)
    stored = sum(1 for o in objs if o.get("outside_scene"))  # pieces kept out of the scene (fake user)
    return assets >= 3 or named or stored >= 3


def category(name):
    n = name.lower()
    for cat, words in (("fasteners", ("screw", "bolt", "rivet", "nut", "washer")),
                       ("vents and grilles", ("vent", "grill", "grate", "louver", "louvre")),
                       ("panels and hatches", ("panel", "hatch", "plate", "door", "cover")),
                       ("pipes and cables", ("pipe", "cable", "hose", "tube", "conduit", "clamp")),
                       ("controls", ("button", "switch", "knob", "dial", "lever", "screen")),
                       ("lights", ("light", "lamp", "led")),
                       ("trims and frames", ("trim", "frame", "rail", "strip", "edge"))):
        if any(w in n for w in words):
            return cat
    return "other"


def rules(ctx):
    L, r = ctx.lib, ctx.result
    kit_docs = [d for d in ctx.files if is_kit_doc(d, L)]
    use_docs = [d for d in ctx.files if d not in kit_docs]
    pieces = []
    for d in kit_docs:
        objs = [o for o in L.objects(d, "MESH", include_outside=True)]
        assets = [o for o in objs if o.get("is_asset")]
        stored = [o for o in objs if o.get("outside_scene")]
        chosen = assets if len(assets) >= 3 else (stored if len(stored) >= 3 else objs)
        for o in chosen:
            if o.get("display_type") in ("WIRE", "BOUNDS"):
                continue
            me = o.get("mesh", {})
            pieces.append({"name": L.strip_suffix(o["name"]), "file": d.get("_submission", {}).get("file", d.get("file")),
                           "dims_mm": [round(x * 1000, 1) for x in o.get("dimensions", [0, 0, 0])],
                           "tris": me.get("eval_tri_count", me.get("tri_count")),
                           "modifiers": L.stack_types(o), "asset": o.get("is_asset"),
                           "category": category(o["name"]), "stored": bool(o.get("outside_scene"))})
    seen, uniq = set(), []
    for p in pieces:
        if p["name"] not in seen:
            seen.add(p["name"])
            uniq.append(p)
    r.extra["kit_catalogue"] = uniq
    r.extra["bundle_files"] = [d.get("_submission", {}).get("sha") or d.get("_submission", {}).get("stored_as")
                               for d in kit_docs]
    if not kit_docs:
        r.warn("None of the files looks like a kit library (no asset-marked pieces or kit/insert collection). "
               "Submit your kit .blend, or mark its pieces as assets.")
    else:
        cats = Counter(p["category"] for p in uniq)
        r.headline(f"Small hardware comes from the artist's own insert kit ({len(uniq)} pieces: "
                   + ", ".join(c for c, _ in cats.most_common(3)) + ").")
        r.rule(f"Kit: {len(uniq)} pieces in {len(kit_docs)} file(s): " +
               ", ".join(f"{c} {n}" for c, n in cats.most_common()) + ". The full list is in references/kit-catalogue.md.")
        asset_share = L.share(uniq, lambda p: p["asset"])
        fake = L.share(uniq, lambda p: p.get("stored"))
        r.rule(f"{L.percent(asset_share)} of kit pieces are marked as assets." if asset_share else
               ("Kit pieces are kept out of the scene as fake-user objects (appended by name), not marked assets."
                if fake else "Kit pieces are plain objects in collections, not marked assets."))
        lows = [p for p in uniq if p["name"].endswith(("_lo", "_low"))]
        if lows:
            r.rule(f"Each insert comes as a high and a low version ({len(lows)} `_lo` pieces): the high goes on the bake source, the low on the game mesh.")
        small = [p for p in uniq if p["dims_mm"] and max(p["dims_mm"]) < 50]
        if small:
            r.rule(f"Small inserts ({len(small)}) are modelled at real size, e.g. "
                   + ", ".join(f"`{p['name']}` {max(p['dims_mm'])} mm" for p in small[:4]) + ".")
    if use_docs or kit_docs:
        docs = use_docs or kit_docs
        objs = [o for d in docs for o in L.objects(d, include_outside=False)]
        linked = sum(1 for o in objs if o["type"] == "MESH" and o.get("data_users", 1) > 1)
        inst = sum(1 for o in objs if o.get("instance_type") == "COLLECTION" and o.get("instance_collection"))
        libs = sum(len(d.get("libraries", [])) for d in docs)
        mode = None
        if inst > linked and inst:
            mode = "collection-instances"
        elif linked:
            mode = "linked-duplicates"
        elif use_docs:
            mode = "real-copies"
        if mode:
            r.number("insert_instancing", mode, f"{linked} linked duplicates, {inst} collection instances")
            r.rule({"collection-instances": f"Inserts are placed as collection instances ({inst}).",
                    "linked-duplicates": f"Inserts are placed as linked duplicates that share mesh data ({linked}).",
                    "real-copies": "Inserts are placed as real copies (separate mesh data)."}[mode])
        if libs:
            r.rule(f"The model links {libs} external library file(s) rather than appending.")
    if ctx.answers.get("kit_placement"):
        r.rule(f"Placement (artist): {ctx.answers['kit_placement']}.")
    if ctx.answers.get("kit_redistribute") is False:
        r.rule("The kit files themselves are not shipped with this skill (licence); build new pieces in the same style instead.")
    return r


def detect(doc, L):
    if is_kit_doc(doc, L):
        n = sum(1 for o in L.objects(doc, "MESH", include_outside=True))
        return f"kit library ({n} pieces)"
    objs = list(L.objects(doc))
    shared = sum(1 for o in objs if o["type"] == "MESH" and o.get("data_users", 1) > 1)
    inst = sum(1 for o in objs if o.get("instance_type") == "COLLECTION" and o.get("instance_collection"))
    if shared + inst >= 3:
        return f"places inserts ({shared} linked duplicates, {inst} collection instances)"
    return None
