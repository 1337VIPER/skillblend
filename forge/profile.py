"""Turn analysis documents into measured rules, one module at a time.

Each module folder may hold a ``rules.py`` with ``rules(ctx) -> ctx.result`` (see
``ModuleContext``). The forge runs it on the module's own submissions; the rules,
style numbers and warnings it returns feed the built skill.
"""
import importlib.util
import json
import os
import sys

from . import paths

sys.path.insert(0, paths.LIB)
import doclib  # noqa: E402


class Result:
    def __init__(self):
        self.rules = []       # plain sentences for the skill: "Bevel width is ..."
        self.numbers = {}     # style.json values: key -> value
        self.notes = {}       # key -> how it was measured
        self.warnings = []    # things to raise with the artist (missing technique, odd values)
        self.headlines = []   # one or two sentences for the skill's "how this project is built" overview
        self.extra = {}       # module-specific data (kit catalogue etc.)

    def rule(self, text):
        self.rules.append(text)

    def number(self, key, value, note=""):
        if value is None:
            return
        self.numbers[key] = value
        if note:
            self.notes[key] = note

    def headline(self, text):
        self.headlines.append(text)

    def warn(self, text):
        self.warnings.append(text)

    def as_dict(self):
        return {"rules": self.rules, "numbers": self.numbers, "notes": self.notes, "headlines": self.headlines,
                "warnings": self.warnings, "extra": self.extra}


class ModuleContext:
    """What a module's rules.py gets to work with."""

    def __init__(self, module, files, all_files, answers, defaults):
        self.module = module
        self.files = files            # analysis docs submitted for this module
        self.all_files = all_files    # every analysis doc, any module
        self.answers = answers        # this module's interview answers
        self.defaults = defaults      # generic numbers (defaults.json)
        self.lib = doclib
        self.result = Result()

    @property
    def n(self):
        return len(self.files)

    def meshes(self, files=None, helpers=False):
        for d in (self.files if files is None else files):
            for o in doclib.meshes(d, helpers=helpers):
                yield d, o

    def mods(self, mtype, files=None):
        for d, o in self.meshes(files):
            for m in doclib.mods(o, mtype):
                yield o, m

    def source(self):
        names = [d.get("_submission", {}).get("file", d.get("file")) for d in self.files]
        return f"measured from {len(names)} file{'s' if len(names) != 1 else ''}"


def _load_py(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_analyses(ws):
    """Return {module_id: [doc, ...]}: files picked from the learned project, plus manual submissions."""
    from .project import Project
    root = ws if isinstance(ws, str) else ws.root
    out = {}
    adir = os.path.join(root, "analysis")
    if os.path.isdir(adir):
        for mid in sorted(os.listdir(adir)):
            mdir = os.path.join(adir, mid)
            if not os.path.isdir(mdir):
                continue
            for fn in sorted(os.listdir(mdir)):
                if fn.endswith(".json"):
                    with open(os.path.join(mdir, fn), encoding="utf-8") as fh:
                        out.setdefault(mid, []).append(json.load(fh))
    if os.path.isfile(os.path.join(root, "project.json")):
        from .workspace import Workspace
        for mid, docs in Project(Workspace(root)).analyses().items():
            out.setdefault(mid, []).extend(docs)
    return out


def run_module(module, analyses, answers):
    files = analyses.get(module["id"], [])
    seen, all_files = set(), []
    for docs in analyses.values():
        for d in docs:
            if "_script" in d:
                continue  # build-script records are not .blend analyses
            if id(d) not in seen:
                seen.add(id(d))
                all_files.append(d)
    ctx = ModuleContext(module, files, all_files, answers.get(module["id"], {}), module["defaults"])
    rules_py = os.path.join(module["dir"], "rules.py")
    if files and os.path.exists(rules_py):
        mod = _load_py(rules_py, "forge_rules_" + module["id"].replace("-", "_"))
        try:
            mod.rules(ctx)
        except Exception as exc:  # a broken module must not stop the build
            ctx.result.warn(f"rules.py failed: {exc!r}")
    # answers that set style numbers directly
    for q in module.get("questions", []):
        key = q.get("number_key")
        if key and q["key"] in ctx.answers:
            ctx.result.number(key, ctx.answers[q["key"]], "your answer")
    return ctx.result


def merged_numbers(modules, results):
    """defaults <- measured <- answered, with where each value came from."""
    style, source = {}, {}
    for m in modules:  # every default first, so a later module's default never hides a measurement
        for k, v in m["defaults"].items():
            if k.startswith("_"):
                continue
            style.setdefault(k, v)
            source.setdefault(k, "generic default")
    for m in modules:
        r = results.get(m["id"])
        if r:
            for k, v in r.numbers.items():
                style[k] = v
                source[k] = r.notes.get(k) or "measured"
    return style, source
