"""Learn from a whole project: find every .blend, analyse each once, and let the modules pick their files.

The analyses live in ``<workspace>/library/<sha1>.json`` (keyed by file content, so a re-scan only
analyses new or changed files). ``<workspace>/project.json`` lists the files found, which modules
detected their technique (and why), and which files the artist excluded.
"""
import fnmatch
import re
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import modules as modlib, paths

sys.path.insert(0, paths.LIB)
import doclib  # noqa: E402

ANALYSER_VERSION = 4  # bump with forge/blender/analyse_blend.py VERSION to re-read every file
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}
SKIP_PATTERNS = ["*backup*", "*autosave*", "*recovered*", "*_before_*", "*.blend[0-9]*", "*_bak*", "*_old*",
                 "*quit.blend", "*_test.blend", "*untitled*", "*unsaved*", "*uvtest*", "*_r[0-9][0-9][0-9].blend",
                 "*/prev/*", "*/old/*", "*/archive/*", "*/backup*/*", "*/wip/*"]
# folders whose names start with "_" (_prev, _stages, _review, _render...) hold revisions and scratch, not deliverables
SKIP_UNDERSCORE_DIRS = True


def sha1(path, chunk=1 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def find_blends(root, skip_patterns=None, max_files=2000):
    """Every .blend under root, minus backups, autosaves and other non-deliverables."""
    pats = [p.lower() for p in (skip_patterns if skip_patterns is not None else SKIP_PATTERNS)]
    found, skipped = [], []
    for d, dirs, files in os.walk(root):
        keep = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")
                      and not (SKIP_UNDERSCORE_DIRS and x.startswith("_")))
        for x in sorted(set(dirs) - set(keep)):
            if x.startswith("_"):
                skipped.append(os.path.relpath(os.path.join(d, x), root).replace("\\", "/") + "/ (folder)")
        dirs[:] = keep
        for f in sorted(files):
            if not f.lower().endswith(".blend"):
                continue
            p = os.path.join(d, f)
            rel = os.path.relpath(p, root).replace("\\", "/")
            if any(fnmatch.fnmatch("/" + rel.lower(), pat) or fnmatch.fnmatch(f.lower(), pat) for pat in pats):
                skipped.append(rel)
                continue
            found.append(p)
            if len(found) >= max_files:
                return found, skipped
    return found, skipped


def _detectors(mods):
    out = {}
    for m in mods:
        p = os.path.join(m["dir"], "rules.py")
        if not os.path.isfile(p):
            continue
        spec = importlib.util.spec_from_file_location("forge_detect_" + m["id"].replace("-", "_"), p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out[m["id"]] = mod
    return out


def _fresh(path):
    """True when an analysis exists and was made by the current analyser."""
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as fh:
        head = fh.read(200)
    m = re.search(r'"analyser_version":\s*(\d+)', head)
    return bool(m) and int(m.group(1)) >= ANALYSER_VERSION


def _rel(p, root, roots):
    if not root:
        return os.path.basename(p)
    rel = os.path.relpath(p, root).replace("\\", "/")
    return f"{os.path.basename(root)}/{rel}" if len(roots) > 1 else rel


class Project:
    """Scan state shared with the app (thread-safe enough for one scan at a time)."""

    def __init__(self, ws):
        self.ws = ws
        self.lib_dir = os.path.join(ws.root, "library")
        os.makedirs(self.lib_dir, exist_ok=True)
        self.lock = threading.Lock()
        self.progress = {"running": False, "done": 0, "total": 0, "current": [], "errors": [], "phase": "idle"}

    # ------------------------------------------------------------------ state
    @property
    def data(self):
        p = os.path.join(self.ws.root, "project.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        return {"roots": [], "files": [], "skipped": []}

    def save(self, data):
        with open(os.path.join(self.ws.root, "project.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)

    def doc(self, sha):
        p = os.path.join(self.lib_dir, sha + ".json")
        if not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)

    # ------------------------------------------------------------------ scan
    def scan(self, roots, workers=None, skip_patterns=None, extra_files=()):
        """Find, analyse (cached) and assign. Blocking; the app runs it in a thread.

        roots: one folder or a list of folders (a project plus, say, the kit library it uses);
        a .blend path in the list is taken as a single file."""
        if isinstance(roots, str):
            roots = [roots]
        roots = [os.path.abspath(r) for r in roots if r]
        extra_files = list(extra_files) + [r for r in roots if r.lower().endswith(".blend")]
        roots = [r for r in roots if os.path.isdir(r)]
        with self.lock:
            self.progress = {"running": True, "done": 0, "total": 0, "current": [], "errors": [],
                             "phase": "finding files", "started": time.time()}
        try:
            paths_, skipped, owner = [], [], {}
            for root in roots:
                f_, s_ = find_blends(root, skip_patterns)
                for p in f_:
                    owner[p] = root
                paths_ += f_
                skipped += [os.path.join(os.path.basename(root), x).replace("\\", "/") if len(roots) > 1 else x for x in s_]
            paths_ += [p for p in extra_files if p not in paths_ and os.path.isfile(p)]
            old = {f["sha"]: f for f in self.data.get("files", [])}
            entries, seen = [], {}
            self.progress["phase"] = "hashing"
            for p in paths_:
                try:
                    h = sha1(p)
                except OSError as exc:
                    self.progress["errors"].append(f"{p}: {exc}")
                    continue
                root = owner.get(p)
                if h in seen:  # identical copy of a file already listed
                    skipped.append((os.path.relpath(p, root).replace("\\", "/") if root else os.path.basename(p)) + " (duplicate)")
                    continue
                seen[h] = p
                prev = old.get(h, {})
                entries.append({"sha": h, "path": p,
                                "rel": _rel(p, root, roots),
                                "file": os.path.basename(p), "size": os.path.getsize(p),
                                "excluded": prev.get("excluded", False), "pinned": prev.get("pinned", {})})
            todo = [e for e in entries if not _fresh(os.path.join(self.lib_dir, e["sha"] + ".json"))]
            self.progress.update(phase="analysing", total=len(todo), done=0)
            workers = workers or max(1, min(4, (os.cpu_count() or 4) // 2))

            def work(e):
                with self.lock:
                    self.progress["current"].append(e["file"])
                try:
                    self.ws.analyse_to(e["path"], os.path.join(self.lib_dir, e["sha"] + ".json"),
                                       meta={"file": e["file"], "sha": e["sha"]})
                except Exception as exc:
                    with self.lock:
                        self.progress["errors"].append(f"{e['rel']}: {str(exc).splitlines()[0]}")
                finally:
                    with self.lock:
                        self.progress["current"].remove(e["file"])
                        self.progress["done"] += 1

            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(work, todo))
            self.progress["phase"] = "reading build scripts"
            scripts = self.read_scripts(roots, entries)
            self.progress["phase"] = "learning"
            data = {"scripts": scripts, "roots": roots, "extra_files": [p for p in extra_files], "scanned": time.strftime("%Y-%m-%d %H:%M"), "files": entries,
                    "skipped": skipped}
            self.assign(data)
            self.save(data)
            self.progress["phase"] = "done"
            return data
        finally:
            self.progress["running"] = False

    def read_scripts(self, roots, entries):
        from .scripts_scan import find_scripts, read_script
        stems = {}
        for e in entries:
            stems.setdefault(os.path.splitext(e["file"])[0], []).append(e["rel"])
        out = []
        skip = lambda x: x in SKIP_DIRS or x.startswith(".") or (SKIP_UNDERSCORE_DIRS and x.startswith("_"))
        for root, p in find_scripts(roots, skip):
            info = read_script(p)
            if not info or not info["uses_bpy"]:
                continue
            stem = os.path.splitext(os.path.basename(p))[0]
            from .scripts_scan import TOOL_NAME
            parts = p.replace("\\", "/").lower().split("/")
            info["role"] = ("build" if stems.get(stem) else
                            "tool" if TOOL_NAME.search(stem) or "renders" in parts else "build")
            info.update({"rel": _rel(p, root, roots), "path": p, "file": os.path.basename(p),
                         "blends": stems.get(stem, [])})
            out.append(info)
        # a script other scripts import is the artist's helper kit, not a model build
        imported = {k for sc in out for k in sc.get("kits", [])}
        for sc in out:
            if os.path.splitext(sc["file"])[0] in imported:
                sc["role"] = "kit"
        return out

    def scripts(self):
        return [s for s in self.data.get("scripts", []) if not s.get("excluded")]

    def assign(self, data=None):
        """Ask every module which files show its technique."""
        persist = data is None
        data = data or self.data
        mods = modlib.load_modules()
        det = _detectors(mods)
        docs = []
        for e in data["files"]:
            d = self.doc(e["sha"])
            e["analysed"] = d is not None
            e["detected"] = {}
            if d is None:
                continue
            d.setdefault("_submission", {}).update({"file": e["file"], "sha": e["sha"]})
            docs.append((e, d))
            for m in mods:
                fn = getattr(det.get(m["id"]), "detect", None)
                if fn:
                    try:
                        why = fn(d, doclib)
                    except Exception as exc:
                        why = None
                        self.progress["errors"].append(f"{m['id']} detect on {e['file']}: {exc!r}")
                    if why:
                        e["detected"][m["id"]] = why
        for m in mods:
            fn = getattr(det.get(m["id"]), "detect_project", None)
            if fn:
                picked = [d for e, d in docs if m["id"] in e["detected"]]
                extra = fn([d for _, d in docs], doclib, picked) or {}
                for e, d in docs:
                    if id(d) in extra:
                        e["detected"][m["id"]] = extra[id(d)]
        if persist:
            self.save(data)
        return data

    def set_file(self, sha, excluded=None, module=None, use=None):
        """Exclude a file, or force a module on (True) / off (False) / back to automatic (None)."""
        data = self.data
        for e in data["files"]:
            if e["sha"] == sha:
                if excluded is not None:
                    e["excluded"] = bool(excluded)
                if module:
                    pins = e.setdefault("pinned", {})
                    if use is None:
                        pins.pop(module, None)
                    else:
                        pins[module] = bool(use)
        self.save(data)
        return data

    # ------------------------------------------------------------------ for the build
    def analyses(self):
        """{module_id: [doc, ...]} from detections, pins and exclusions (one shared dict per file)."""
        out = {}
        for e in self.data.get("files", []):
            if e.get("excluded") or not e.get("analysed", True):
                continue
            mods = {m for m in e.get("detected", {})}
            for m, on in e.get("pinned", {}).items():
                (mods.add if on else mods.discard)(m)
            if not mods:
                continue
            d = self.doc(e["sha"])
            if d is None:
                continue
            d.setdefault("_submission", {}).update({"file": e["file"], "sha": e["sha"], "stored_as": None,
                                                    "source": e["path"]})
            for m in mods:
                out.setdefault(m, []).append(d)
        scripts = self.scripts()
        if scripts:
            out["build-scripts"] = [{"_script": sc, "_submission": {"file": sc["rel"], "source": sc["path"]}}
                                    for sc in scripts]
        return out
