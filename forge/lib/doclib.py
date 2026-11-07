"""Helpers for reading analysis documents (the JSON that analyse_blend.py writes).

Pure Python: used by the forge (outside Blender), by module rules.py / check.py files,
and shipped inside every built skill so its style checks can run in Blender.
"""
import math
import re
from collections import Counter

DEFAULT_NAMES = {"cube", "cylinder", "sphere", "uv sphere", "ico sphere", "icosphere", "plane",
                 "circle", "torus", "cone", "monkey", "suzanne", "grid", "empty", "bezier curve",
                 "bezierCurve".lower(), "nurbs path", "text", "camera", "light", "point", "sun",
                 "area", "spot"}


# ------------------------------------------------------------------ numbers
def median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def pct(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = (len(vals) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def mode(vals):
    vals = [v if not isinstance(v, list) else tuple(v) for v in vals if v is not None]
    if not vals:
        return None
    return Counter(vals).most_common(1)[0][0]


def share(vals, pred):
    vals = list(vals)
    if not vals:
        return None
    return sum(1 for v in vals if pred(v)) / len(vals)


def fmt(x, digits=3):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        if x == 0:
            return "0"
        if abs(x) >= 100:
            return f"{x:.0f}"
        return f"{x:.{digits}g}"
    return str(x)


def mm(x):
    return "n/a" if x is None else f"{x * 1000:.3g} mm"


def percent(x):
    return "n/a" if x is None else f"{x * 100:.0f}%"


# ------------------------------------------------------------------ objects
def objects(doc, kind=None, include_outside=False):
    for o in doc.get("objects", []):
        if "error" in o:
            continue
        if o.get("outside_scene") and not include_outside:
            continue
        if kind and o.get("type") != kind:
            continue
        yield o


def cutter_names(doc):
    names = set()
    coll_names = set()
    for o in objects(doc, include_outside=True):
        for m in o.get("modifiers", []):
            if m["type"] == "BOOLEAN":
                if m.get("object"):
                    names.add(m["object"])
                if m.get("collection"):
                    coll_names.add(m["collection"])
    for o in objects(doc, include_outside=True):
        if set(o.get("collections", [])) & coll_names:
            names.add(o["name"])
    return names


def is_helper(o, cutters):
    """Cutters, wire/bounds display objects and hidden-from-render objects."""
    return (o["name"] in cutters or o.get("display_type") in {"WIRE", "BOUNDS"}
            or o.get("hide_render"))


def meshes(doc, helpers=False, include_outside=False):
    cut = cutter_names(doc)
    for o in objects(doc, "MESH", include_outside=include_outside):
        if not helpers and is_helper(o, cut):
            continue
        yield o


def mods(o, mtype=None):
    for m in o.get("modifiers", []):
        if mtype is None or m["type"] == mtype:
            yield m


def all_mods(docs, mtype, helpers=False):
    for d in docs:
        for o in meshes(d, helpers=helpers):
            for m in mods(o, mtype):
                yield o, m


def max_dim(o):
    dims = o.get("dimensions") or [0, 0, 0]
    return max(dims) if dims else 0


def stack_types(o, skip=("NODES",)):
    """The modifier types in order, with smooth-by-angle node modifiers named SMOOTH_BY_ANGLE."""
    out = []
    for m in o.get("modifiers", []):
        t = m["type"]
        if t == "NODES":
            ng = (m.get("node_group") or "").lower()
            if "smooth by angle" in ng:
                t = "SMOOTH_BY_ANGLE"
            elif "NODES" in skip:
                continue
        out.append(t)
    return out


# ------------------------------------------------------------------ naming
def strip_suffix(name):
    return re.sub(r"\.\d{3,}$", "", name)


def is_default_name(name):
    base = strip_suffix(name).lower()
    return base in DEFAULT_NAMES


def naming_case(name):
    n = strip_suffix(name)
    m = re.match(r"^([A-Z]{1,4})_(.+)$", n)
    rest = m.group(2) if m else n
    if " " in rest:
        return "spaces"
    if "-" in rest:
        return "kebab"
    if "_" in rest:
        if rest == rest.lower():
            return "snake"
        if all(p[:1].isupper() for p in rest.split("_") if p):
            return "pascal_underscore"
        return "mixed_underscore"
    if re.match(r"^[A-Z][a-z0-9]+([A-Z][a-z0-9]*)*$", rest):
        return "pascal"
    if re.match(r"^[a-z][a-z0-9]*([A-Z][a-z0-9]*)+$", rest):
        return "camel"
    if rest == rest.lower():
        return "lower"
    return "other"


CASE_LABEL = {"snake": "snake_case", "pascal": "PascalCase", "camel": "camelCase", "kebab": "kebab-case",
              "pascal_underscore": "Pascal_Underscore", "mixed_underscore": "Mixed_underscore", "lower": "lowercase",
              "spaces": "words with spaces", "other": "mixed styles"}


def name_prefix(name):
    m = re.match(r"^([A-Za-z]{1,4})_", strip_suffix(name))
    return (m.group(1) + "_") if m else ""


def name_suffix(name, candidates=("_high", "_low", "_hp", "_lp", "_HP", "_LP", "_High", "_Low",
                                  "_cage", "_LOD0", "_LOD1", "_LOD2", "_LOD3", "_lod0", "_lod1",
                                  "_lod2", "_lod3", "_cutter", "_bool")):
    n = strip_suffix(name)
    for c in candidates:
        if n.endswith(c):
            return c
    return ""


def origin_kind(o):
    b = o.get("origin_in_bbox")
    if not b:
        return None
    x, y, z = b
    centred = abs(x - 0.5) < 0.08 and abs(y - 0.5) < 0.08
    if centred and abs(z) < 0.06:
        return "bottom-center"
    if centred and abs(z - 0.5) < 0.08:
        return "center"
    if all(abs(c) < 0.06 for c in b):
        return "corner"
    return "other"


def is_applied_scale(o):
    s = o.get("scale") or [1, 1, 1]
    return all(abs(abs(c) - 1.0) < 1e-4 for c in s)


def is_subd_cage(o):
    return any(m["type"] == "SUBSURF" for m in o.get("modifiers", []))


# ------------------------------------------------------------------ files
def file_stem(doc):
    import os
    return os.path.splitext(doc.get("_submission", {}).get("file") or doc.get("file") or "")[0]


def export_role(doc):
    """'game', 'lods' or 'low' when the file name marks it as an export product of another file."""
    s = file_stem(doc).lower()
    for suf, role in (("_game", "game"), ("_lods", "lods"), ("_low", "low"), ("_lo", "low")):
        if s.endswith(suf):
            return role
    return None


def name_tokens(name):
    return [t for t in re.split(r"[^a-z]+", strip_suffix(name).lower()) if t]
