"""End-to-end test: fixtures -> submit -> build (personal and generic) -> use and check the skill.

    python tests/run_tests.py [--blender PATH]

Needs Blender 4.2+. Uses a temporary workspace; your own workspace is untouched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
from forge.workspace import find_blender  # noqa: E402

FIXTURES = {
    "setup-and-scale": "setup_crate", "bevels-and-shading": "bevel_junction_box",
    "subd-topology": "subd_nozzle", "booleans-and-cutters": "boolean_panel",
    "modifier-stacks": "stack_rail", "kit-library": "kit_library",
    "uvs-and-texel-density": "gameready_canister", "game-ready-export": "gameready_canister",
    "vehicles": "vehicle_body",
}
failures = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def forge(ws, *args):
    env = dict(os.environ, FORGE_WORKSPACE=ws)
    p = subprocess.run([sys.executable, os.path.join(REPO, "skillblend.py"), *args], capture_output=True,
                       text=True, env=env, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout + p.stderr


def blender_run(exe, *args):
    p = subprocess.run([exe, "-b", "--factory-startup", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.stdout + p.stderr


def main():
    exe = None
    if "--blender" in sys.argv:
        exe = sys.argv[sys.argv.index("--blender") + 1]
    exe = find_blender(exe)
    if not exe:
        sys.exit("Blender not found; pass --blender PATH")
    tmp = tempfile.mkdtemp(prefix="forge-test-")
    ws = os.path.join(tmp, "ws")
    fx = os.path.join(tmp, "fixtures")
    print("fixtures")
    out = blender_run(exe, "--python", os.path.join(REPO, "forge", "demo", "make_demo.py"), "--", fx)
    check("FIXTURES_OK" in out, "fixture files made")
    forge(ws, "config", "--blender", exe)

    print("empty build")
    code, out = forge(ws, "build")
    check(code == 2 and "No models" in out, "build without submissions refuses (exit 2)")

    print("generic build")
    code, out = forge(ws, "build", "--generic", "--json")
    res = json.loads(out) if code == 0 else {}
    check(code == 0 and not res.get("personal"), "generic skill builds")
    gdir = res.get("dir", "")
    skill = open(os.path.join(gdir, "SKILL.md"), encoding="utf-8").read() if gdir else ""
    check("name: blender-modelling" in skill, "generic skill is named blender-modelling")
    check(all(os.path.isfile(os.path.join(gdir, "references", m + ".md")) for m in FIXTURES), "every module has a reference file")

    print("submissions")
    for mid, f in FIXTURES.items():
        code, out = forge(ws, "submit", mid, os.path.join(fx, f + ".blend"))
        check(code == 0 and "what the files show" in out, f"submit + analyse {mid}")
    forge(ws, "answer", "setup-and-scale", "front_axis", "-Y")
    forge(ws, "answer", "kit-library", "kit_redistribute", "true")
    code, out = forge(ws, "status", "--json")
    st = json.loads(out)
    check(st["next"] == "structure-and-assemblies", "status points at the first module still waiting")

    print("personal build")
    code, out = forge(ws, "build", "--author", "Test Artist", "--json")
    res = json.loads(out) if code == 0 else {}
    pdir = res.get("dir", "")
    check(code == 0 and res.get("personal"), "personal skill builds")
    style = json.load(open(os.path.join(pdir, "style.json"))) if pdir else {"numbers": {}}
    n = style["numbers"]
    check(n.get("front_axis") == "-Y", "an answer overrides the generic default")
    check(n.get("bevel_segments") == 3 and abs(n.get("bevel_width_m", 0) - 0.00225) < 1e-6, "bevel numbers measured")
    check(n.get("boolean_solver") == "EXACT" and n.get("cutter_display") == "WIRE", "boolean numbers measured")
    check(n.get("stack_order", [None])[0] == "MIRROR", "stack order measured")
    check(os.path.isdir(os.path.join(pdir, "kit")), "kit shipped when cleared")
    check("blockout-to-detail" in res.get("generic", []) and "bevels-and-shading" not in res.get("generic", []),
          "unsubmitted module stays generic")

    print("use the skill")
    good, bad = os.path.join(tmp, "good.blend"), os.path.join(tmp, "bad.blend")
    out = blender_run(exe, "--python", os.path.join(HERE, "use_built_skill.py"), "--", pdir, good, bad)
    check("USE_OK" in out, "style.py builds a model")
    check("DEEP_OK" in out and "DEEP solidify" in out, "style.modifier / style.material / style.setup_render work")
    out = blender_run(exe, good, "--python", os.path.join(pdir, "scripts", "style_check.py"))
    check("STYLE 0 warning" in out or "STYLE ok" in out, "a model built with style.py passes the check")
    out = blender_run(exe, bad, "--python", os.path.join(pdir, "scripts", "style_check.py"))
    check("Default names left" in out and "will render" in out, "a careless model fails the check")

    print("learn a project folder")
    ws2 = os.path.join(tmp, "ws2")
    forge(ws2, "config", "--blender", exe)
    code, out = forge(ws2, "learn", fx)
    check(code == 0, "learn runs on a folder")
    proj = json.load(open(os.path.join(ws2, "project.json")))
    det = {f["file"]: set(f["detected"]) for f in proj["files"]}
    expect = {"subd_nozzle.blend": "subd-topology", "boolean_panel.blend": "booleans-and-cutters",
              "kit_library.blend": "kit-library", "gameready_canister.blend": "game-ready-export",
              "vehicle_body.blend": "vehicles", "stack_rail.blend": "modifier-stacks",
              "bevel_junction_box.blend": "bevels-and-shading",
              "lookdev_lamp_post.blend": "shaders-and-nodes"}
    for f, mid in expect.items():
        check(mid in det.get(f, set()), f"learn detects {mid} in {f}")
    check("vehicles" not in det.get("boolean_panel.blend", set()), "no false vehicle")
    check({"geometry-nodes", "lookdev-and-render"} <= det.get("lookdev_lamp_post.blend", set()),
          "learn detects Geometry Nodes and look-dev in the lamp post")
    code, out = forge(ws2, "build", "--json")
    res2 = json.loads(out) if code == 0 else {}
    check(code == 0 and res2.get("personal") and "subd-topology" in res2.get("covered", []), "builds from a learned project")
    st2 = json.load(open(os.path.join(res2.get("dir", ""), "style.json"))) if res2.get("dir") else {"numbers": {}}
    n2 = st2["numbers"]
    check("SHRINKWRAP" in (n2.get("modifier_defaults") or {}) and "EDGE_SPLIT" in (n2.get("modifier_defaults") or {}),
          "modifier dictionary covers every modifier type (Shrinkwrap, Edge Split)")
    rec = (n2.get("material_recipes") or {}).get("SteelDark") or {}
    check(rec.get("metallic") == 1.0 and "Roughness" in (rec.get("procedural") or {}), "shader recipe measured (SteelDark)")
    check(n2.get("view_transform") == "AgX" and n2.get("world_kind") == "sky", "look-dev measured (AgX, sky world)")
    check(n2.get("gn_groups") == ["CableFromCurve"], "Geometry Nodes group measured")
    check(n2.get("quality_aspect_p90") and n2.get("quality_skew_p90") is not None and "edge_profile" in n2, "mesh quality measured")
    check(n2.get("subd_hold_mm") and n2.get("subd_pinched_max") is not None, "SubD holding loops and pinching measured")
    refs = os.listdir(os.path.join(res2["dir"], "references")) if res2.get("dir") else []
    check("modifier-dictionary.md" in refs and "shader-recipes.md" in refs, "reference tables written into the skill")

    print("app API")
    sys.path.insert(0, REPO)
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from forge.app import App, make_handler
    from forge.workspace import Workspace
    app = App(Workspace(ws2))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    def get(path, token=True):
        req = urllib.request.Request(base + path, headers={"X-Forge-Token": app.token} if token else {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, {}
    code, st = get("/api/state")
    check(code == 200 and len(st["project"]["files"]) == len(proj["files"]), "app state lists the learned files")
    check(get("/api/state", token=False)[0] == 403, "app refuses calls without the token")
    page = urllib.request.urlopen(base + "/").read().decode()
    check(app.token in page and "Learn how I model" in page, "app page is served with its token")
    httpd.shutdown()

    print("install")
    code, out = forge(ws, "install", pdir, "--scope", "project", "--project-dir", os.path.join(tmp, "proj"))
    check(code == 0 and os.path.isfile(os.path.join(tmp, "proj", ".claude", "skills", res.get("name", "?"), "SKILL.md")), "install to a project")

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
