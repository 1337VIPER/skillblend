"""The SkillBlend app: a local web page that learns a project's modelling style and builds the skill.

    python skillblend.py app            # opens http://127.0.0.1:4970 in your browser

Standard library only. The server listens on 127.0.0.1, and every API call must carry the
session token that is written into the page, so other websites can't drive it.
"""
import json
import os
import re
import secrets
import shutil
import string
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, build as buildlib, modules as modlib, paths, profile
from .project import Project

UI = os.path.join(paths.PKG, "ui", "index.html")


class App:
    def __init__(self, ws):
        self.ws = ws
        self.project = Project(ws)
        self.token = secrets.token_urlsafe(24)
        self.report = None          # cached {module_id: result dict}
        self.report_lock = threading.Lock()
        self.last_build = None
        self.scan_thread = None

    # ------------------------------------------------------------------ learned style
    def compute_report(self):
        mods = modlib.load_modules()
        analyses = profile.load_analyses(self.ws)
        answers = self.ws.answers
        out = {}
        for m in mods:
            r = profile.run_module(m, analyses, answers)
            out[m["id"]] = dict(r.as_dict(), files=len(analyses.get(m["id"], [])))
        out.pop("_", None)
        with self.report_lock:
            self.report = out
        return out

    def state(self):
        mods = modlib.load_modules()
        data = self.project.data
        rep = self.report if self.report is not None else (self.compute_report() if data.get("files") else {})
        answers = self.ws.answers
        mlist = []
        for m in mods:
            r = rep.get(m["id"], {})
            summary, _ = modlib.generic_text(m)
            mlist.append({"id": m["id"], "title": m["title"], "summary": m["summary"], "optional": m["optional"],
                          "files": r.get("files", 0), "rules": r.get("rules", []), "headlines": r.get("headlines", []), "numbers": r.get("numbers", {}),
                          "notes": r.get("notes", {}), "warnings": r.get("warnings", []),
                          "questions": m["questions"], "answers": answers.get(m["id"], {}),
                          "has_generic": bool(summary), "bundle": m.get("bundle")})
        files = []
        for e in data.get("files", []):
            used = set(e.get("detected", {}))
            for k, on in e.get("pinned", {}).items():
                (used.add if on else used.discard)(k)
            files.append({k: e.get(k) for k in ("sha", "rel", "file", "size", "excluded", "detected", "pinned", "analysed")}
                         | {"used_by": sorted(used)})
        cfg = self.ws.config
        return {"version": __version__, "blender": self.ws.blender(), "author": cfg.get("author"),
                "skill_name": cfg.get("skill_name"), "progress": self.project.progress,
                "project": {"roots": data.get("roots", []), "extra_files": data.get("extra_files", []),
                            "scanned": data.get("scanned"), "skipped": data.get("skipped", []), "files": files,
                            "scripts": [{"rel": s_["rel"], "role": s_.get("role", "build"), "kits": s_.get("kits", []),
                                         "doc": s_.get("doc", "")} for s_ in data.get("scripts", [])]},
                "modules": mlist, "last_build": self.last_build,
                "skills_dir": os.path.join(os.path.expanduser("~"), ".claude", "skills")}

    # ------------------------------------------------------------------ actions
    def start_scan(self, roots, extra=()):
        if self.project.progress.get("running"):
            raise RuntimeError("A scan is already running.")
        if not self.ws.blender():
            raise RuntimeError("Blender wasn't found. Set its path first.")

        def run():
            try:
                self.project.scan(roots, extra_files=extra)
            except Exception as exc:  # surface it in the progress panel
                self.project.progress["errors"].append(f"scan failed: {exc}")
                self.project.progress["running"] = False
            self.compute_report()
        self.report = None
        self.scan_thread = threading.Thread(target=run, daemon=True)
        self.scan_thread.start()

    def build(self, body):
        cfg = {k: body.get(k) for k in ("author", "skill_name") if body.get(k) is not None}
        self.ws.set_config(author=cfg.get("author") or None, skill_name=cfg.get("skill_name") or None)
        res = buildlib.build(self.ws, name=body.get("skill_name") or None, author=body.get("author") or None,
                             generic=bool(body.get("generic")), exclude=body.get("exclude") or [],
                             include_examples=bool(body.get("examples")))
        dst = os.path.join(os.path.expanduser("~"), ".claude", "skills", res["name"])
        res["installed_at"] = dst if os.path.exists(dst) else None
        res["built"] = time.strftime("%H:%M")
        self.last_build = res
        return res

    def install(self, body):
        """Install for Claude Code (skills folder) and/or other AI tools (instruction files in a project)."""
        from .targets import install_targets
        src = (self.last_build or {}).get("dir")
        if not src or not os.path.isfile(os.path.join(src, "SKILL.md")):
            raise RuntimeError("Make the skill first.")
        tools = body.get("targets") or ["claude"]
        done = {}
        if "claude" in tools:
            dst = os.path.join(os.path.expanduser("~"), ".claude", "skills", os.path.basename(src))
            if os.path.exists(dst):
                if not body.get("replace"):
                    return {"exists": True, "path": dst}
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("exports"))
            self.last_build["installed_at"] = dst
            done["claude"] = dst
        others = [t for t in tools if t != "claude"]
        if others:
            pd = body.get("project_dir") or None
            if any(t != "prompt" for t in others):
                if not pd or not os.path.isdir(pd):
                    raise RuntimeError("Choose the project folder your AI tool works in.")
            done.update(install_targets(src, others, pd))
        return {"installed": True, "done": done}

    def prompt(self):
        from .targets import system_prompt
        src = (self.last_build or {}).get("dir")
        if not src:
            raise RuntimeError("Make the skill first.")
        return {"text": system_prompt(src)}


def browse(path):
    """Folders (and .blend counts) under path; with no path, the drives or home."""
    if not path:
        if os.name == "nt":
            roots = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        else:
            roots = ["/"]
        home = os.path.expanduser("~")
        return {"path": "", "parent": None, "dirs": [{"name": home, "path": home}] +
                [{"name": r, "path": r} for r in roots], "blends": 0}
    path = os.path.abspath(path)
    dirs, blends = [], 0
    try:
        for e in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            if e.is_dir(follow_symlinks=False) and not e.name.startswith((".", "$")):
                dirs.append({"name": e.name, "path": e.path})
            elif e.is_file() and e.name.lower().endswith(".blend"):
                blends += 1
    except OSError as exc:
        return {"path": path, "parent": os.path.dirname(path), "dirs": [], "blends": 0, "error": str(exc)}
    parent = os.path.dirname(path)
    return {"path": path, "parent": parent if parent != path else "", "dirs": dirs[:500], "blends": blends}


def make_handler(app):
    class H(BaseHTTPRequestHandler):
        server_version = "SkillBlend/" + __version__

        def log_message(self, fmt, *args):  # quiet
            pass

        # -------------------------------------------------------------- helpers
        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if not isinstance(body, bytes) or ctype.startswith("text") else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                return False
            return secrets.compare_digest(self.headers.get("X-Forge-Token", ""), app.token)

        def _json_body(self, limit=1 << 20):
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ValueError("request too large")
            return json.loads(self.rfile.read(n) or b"{}")

        # -------------------------------------------------------------- routes
        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                host = (self.headers.get("Host") or "").split(":")[0]
                if host not in ("127.0.0.1", "localhost"):
                    return self._send(403, {"error": "forbidden"})
                with open(UI, encoding="utf-8") as fh:
                    html = fh.read().replace("{{TOKEN}}", app.token)
                return self._send(200, html, "text/html")
            if not self._authorised():
                return self._send(403, {"error": "forbidden"})
            q = parse_qs(u.query)
            try:
                if u.path == "/api/state":
                    return self._send(200, app.state())
                if u.path == "/api/browse":
                    return self._send(200, browse((q.get("path") or [""])[0]))
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authorised():
                return self._send(403, {"error": "forbidden"})
            u = urlparse(self.path)
            try:
                if u.path == "/api/upload":
                    return self._send(200, self.upload())
                body = self._json_body()
                if u.path == "/api/config":
                    if body.get("blender") and not os.path.isfile(body["blender"]):
                        return self._send(400, {"error": "That Blender path doesn't exist."})
                    app.ws.set_config(blender=body.get("blender") or None, author=body.get("author"),
                                      skill_name=body.get("skill_name"))
                    return self._send(200, app.state())
                if u.path == "/api/scan":
                    roots = [r for r in body.get("roots", []) if r]
                    for r in roots:
                        if not os.path.exists(r):
                            return self._send(400, {"error": f"Not found: {r}"})
                    app.start_scan(roots, body.get("extra_files", []))
                    return self._send(200, {"started": True})
                if u.path == "/api/file":
                    app.project.set_file(body["sha"], excluded=body.get("excluded"), module=body.get("module"),
                                         use=body.get("use"))
                    app.compute_report()
                    return self._send(200, app.state())
                if u.path == "/api/answer":
                    app.ws.set_answer(body["module"], body["key"], body.get("value"))
                    app.compute_report()
                    return self._send(200, app.state())
                if u.path == "/api/build":
                    return self._send(200, app.build(body))
                if u.path == "/api/install":
                    return self._send(200, app.install(body))
                if u.path == "/api/prompt":
                    return self._send(200, app.prompt())
            except buildlib.NothingSubmitted as exc:
                return self._send(409, {"error": str(exc), "nothing": True})
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
            self._send(404, {"error": "not found"})

        def upload(self):
            """Raw .blend body, file name in X-Filename. Saved to the workspace and added to the project."""
            name = os.path.basename(self.headers.get("X-Filename") or "")
            if not name.lower().endswith(".blend"):
                raise ValueError("Only .blend files can be added.")
            name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > 4 << 30:
                raise ValueError("Empty or too large.")
            up = os.path.join(app.ws.root, "uploads")
            os.makedirs(up, exist_ok=True)
            dst = os.path.join(up, name)
            with open(dst, "wb") as fh:
                left = n
                while left:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    fh.write(chunk)
                    left -= len(chunk)
            return {"path": dst}

    return H


def serve(ws, port=4970, open_browser=True):
    app = App(ws)
    httpd = None
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), make_handler(app))
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        print("No free port found.")
        return 1
    url = f"http://127.0.0.1:{port}/"
    print(f"SkillBlend app running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
