"""Find and load technique modules (every folder in modules/ with a module.json)."""
import json
import os

from . import paths

GENERIC_SPLIT = "<!-- more -->"


def load_modules(root=None):
    root = root or paths.MODULES
    mods = []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        mj = os.path.join(d, "module.json")
        if not os.path.isfile(mj):
            continue
        with open(mj, encoding="utf-8") as fh:
            m = json.load(fh)
        m["dir"] = d
        m.setdefault("id", name)
        m.setdefault("order", 999)
        m.setdefault("optional", False)
        m.setdefault("questions", [])
        dj = os.path.join(d, "defaults.json")
        m["defaults"] = {}
        if os.path.isfile(dj):
            with open(dj, encoding="utf-8") as fh:
                m["defaults"] = json.load(fh)
        mods.append(m)
    mods.sort(key=lambda m: (m["order"], m["id"]))
    return mods


def find(mods, ref):
    """A module by id, by unique id prefix, or by its 1-based position."""
    if ref is None:
        return None
    if str(ref).isdigit():
        i = int(ref) - 1
        return mods[i] if 0 <= i < len(mods) else None
    exact = [m for m in mods if m["id"] == ref]
    if exact:
        return exact[0]
    pref = [m for m in mods if m["id"].startswith(ref)]
    return pref[0] if len(pref) == 1 else None


def generic_text(m):
    """(summary, detail) from the module's generic.md; either may be ''."""
    p = os.path.join(m["dir"], "generic.md")
    if not os.path.isfile(p):
        return "", ""
    with open(p, encoding="utf-8") as fh:
        text = fh.read().strip()
    if GENERIC_SPLIT in text:
        a, b = text.split(GENERIC_SPLIT, 1)
        return a.strip(), b.strip()
    return text, ""
