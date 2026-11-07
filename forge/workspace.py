"""The artist's workspace: submissions, analyses, answers, config."""
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import time

from . import paths


class Workspace:
    def __init__(self, root=None):
        self.root = os.path.abspath(root or paths.DEFAULT_WORKSPACE)
        for sub in ("submissions", "analysis", "build"):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)

    # ---------------------------------------------------------------- json state
    def _json(self, name, default):
        p = os.path.join(self.root, name)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        return default

    def _save(self, name, data):
        with open(os.path.join(self.root, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    @property
    def config(self):
        return self._json("config.json", {})

    def set_config(self, **kw):
        c = self.config
        c.update({k: v for k, v in kw.items() if v is not None})
        self._save("config.json", c)

    @property
    def answers(self):
        return self._json("answers.json", {})

    def set_answer(self, mid, key, value):
        a = self.answers
        a.setdefault(mid, {})[key] = value
        self._save("answers.json", a)

    @property
    def state(self):
        return self._json("state.json", {"skipped": []})

    def skip(self, mid, on=True):
        s = self.state
        sk = set(s.get("skipped", []))
        (sk.add if on else sk.discard)(mid)
        s["skipped"] = sorted(sk)
        self._save("state.json", s)

    # ---------------------------------------------------------------- submissions
    def submissions(self, mid):
        d = os.path.join(self.root, "submissions", mid)
        if not os.path.isdir(d):
            return []
        return sorted(os.path.join(d, f) for f in os.listdir(d) if not f.startswith("."))

    def analysis_path(self, mid, sub_path):
        stem = os.path.splitext(os.path.basename(sub_path))[0]
        return os.path.join(self.root, "analysis", mid, stem + ".json")

    def add_submission(self, mid, src, note=""):
        if not os.path.isfile(src):
            raise FileNotFoundError(src)
        d = os.path.join(self.root, "submissions", mid)
        os.makedirs(d, exist_ok=True)
        n = len(self.submissions(mid)) + 1
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(src))
        dst = os.path.join(d, f"{n:02d}_{base}")
        shutil.copy2(src, dst)
        meta = self._json("submissions.json", {})
        meta[os.path.relpath(dst, self.root).replace("\\", "/")] = {
            "module": mid, "file": os.path.basename(src), "note": note,
            "submitted": time.strftime("%Y-%m-%d %H:%M")}
        self._save("submissions.json", meta)
        self.skip(mid, False)
        return dst

    def remove_submission(self, mid, ref):
        for p in self.submissions(mid):
            if os.path.basename(p) == ref or os.path.basename(p).startswith(f"{int(ref):02d}_" if str(ref).isdigit() else ref):
                os.remove(p)
                a = self.analysis_path(mid, p)
                if os.path.isfile(a):
                    os.remove(a)
                return p
        return None

    def submission_meta(self, path):
        meta = self._json("submissions.json", {})
        return meta.get(os.path.relpath(path, self.root).replace("\\", "/"), {})

    # ---------------------------------------------------------------- blender
    def blender(self):
        return find_blender(self.config.get("blender"))

    def analyse_to(self, src, out, meta=None, timeout=900):
        """Analyse any .blend (read-only) into the JSON file `out`."""
        exe = self.blender()
        if not exe:
            raise RuntimeError("Blender not found. Set it with: python skillblend.py config --blender PATH_TO_BLENDER")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = out + ".part"
        cmd = [exe, "-b", "--factory-startup", src, "--python",
               os.path.join(paths.BLENDER, "analyse_blend.py"), "--", tmp]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        if "FORGE_ANALYSIS_OK" not in p.stdout or not os.path.isfile(tmp):
            tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-25:])
            raise RuntimeError(f"Analysis failed for {os.path.basename(src)}:\n{tail}")
        with open(tmp, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["_submission"] = dict(meta or {})
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
        os.remove(tmp)
        return doc

    def analyse(self, mid, sub_path, timeout=900):
        meta = self.submission_meta(sub_path)
        return self.analyse_to(sub_path, self.analysis_path(mid, sub_path), timeout=timeout, meta={
            "file": meta.get("file", os.path.basename(sub_path)), "stored_as": os.path.basename(sub_path),
            "note": meta.get("note", ""), "module": mid})


def find_blender(configured=None):
    cands = []
    if configured:
        cands.append(configured)
    if os.environ.get("BLENDER_PATH"):
        cands.append(os.environ["BLENDER_PATH"])
    w = shutil.which("blender")
    if w:
        cands.append(w)
    sysname = platform.system()
    if sysname == "Windows":
        pf = [os.environ.get("ProgramFiles", r"C:\Program Files"),
              os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
        for root in pf:
            cands += sorted(glob.glob(os.path.join(root, "Blender Foundation", "Blender*", "blender.exe")), reverse=True)
            cands.append(os.path.join(root, "Steam", "steamapps", "common", "Blender", "blender.exe"))
    elif sysname == "Darwin":
        cands.append("/Applications/Blender.app/Contents/MacOS/Blender")
    else:
        cands += ["/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender"]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None
