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
    precious = os.path.join(tmp, "precious")
    os.makedirs(precious)
    with open(os.path.join(precious, "notes.txt"), "w") as fh:
        fh.write("keep me")
    code, out = forge(ws, "build", "--generic", "--out", precious)
    check(code == 1 and os.path.isfile(os.path.join(precious, "notes.txt")) and not os.path.exists(os.path.join(precious, "SKILL.md")),
          "build --out refuses a folder that holds somebody's files")

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
    check("TIERS_OK" in out, "style.bevel uses the measured bevel tiers")
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
              "lookdev_lamp_post.blend": "shaders-and-nodes", "character_demo.blend": "characters-and-rigging"}
    for f, mid in expect.items():
        check(mid in det.get(f, set()), f"learn detects {mid} in {f}")
    check("vehicles" not in det.get("boolean_panel.blend", set()), "no false vehicle")
    check({"geometry-nodes", "lookdev-and-render"} <= det.get("lookdev_lamp_post.blend", set()),
          "learn detects Geometry Nodes and look-dev in the lamp post")
    code, out = forge(ws2, "build", "--author", "Studio: Nine #1", "--json")
    res2 = json.loads(out) if code == 0 else {}
    check(code == 0 and res2.get("personal") and "subd-topology" in res2.get("covered", []), "builds from a learned project")
    from forge.targets import parse_skill
    sk2 = open(os.path.join(res2["dir"], "SKILL.md"), encoding="utf-8").read() if res2.get("dir") else ""
    meta2, _ = parse_skill(sk2)
    desc_line = next((ln for ln in sk2.splitlines() if ln.startswith("description:")), "")
    check("Studio: Nine #1" in meta2.get("description", "") and desc_line.startswith('description: "') and len(meta2["description"]) <= 1024,
          "an author name with a colon gives valid front matter (quoted, under 1024 characters)")
    try:
        import yaml
        fm = yaml.safe_load(sk2.split("---")[1])
        check(fm["name"] == res2["name"] and fm["description"] == meta2["description"], "front matter parses as YAML")
    except ImportError:
        pass
    check(sk2.count("\n") < 200 and len(sk2) < 20000 and len(res2.get("covered", [])) >= 15,
          f"SKILL.md stays short with every technique measured ({sk2.count(chr(10))} lines, {len(sk2)} characters)")
    check(all(f"references/{m}.md" in sk2 for m in res2.get("covered", [])) and os.path.isfile(os.path.join(res2["dir"], "references", "style-card.md")),
          "SKILL.md links every technique's page; the full style card is a reference")
    st2 = json.load(open(os.path.join(res2.get("dir", ""), "style.json"))) if res2.get("dir") else {"numbers": {}}
    n2 = st2["numbers"]
    check("SHRINKWRAP" in (n2.get("modifier_defaults") or {}) and "EDGE_SPLIT" in (n2.get("modifier_defaults") or {}),
          "modifier dictionary covers every modifier type (Shrinkwrap, Edge Split)")
    rec = (n2.get("material_recipes") or {}).get("SteelDark") or {}
    check(rec.get("metallic") == 1.0 and "Roughness" in (rec.get("procedural") or {}), "shader recipe measured (SteelDark)")
    rn = rec.get("roughness_noise") or {}
    check(rn.get("scale") == 24.0 and rn.get("low") == 0.25 and rn.get("high") == 0.55 and rec.get("bevel_radius") == 0.002,
          "the material's own noise scale, roughness range and bevel radius are measured")
    out = blender_run(exe, "--python", os.path.join(HERE, "use_built_skill.py"), "--", res2["dir"],
                      os.path.join(tmp, "good2.blend"), os.path.join(tmp, "bad2.blend"))
    check("DEEP noise 24.0 0.25 0.55" in out, "style.material rebuilds the measured noise break-up, not a fixed one")
    check(n2.get("bevel_miter_outer") in ("MITER_SHARP", "MITER_PATCH", "MITER_ARC"), "bevel miter measured")
    check(n2.get("view_transform") == "AgX" and n2.get("world_kind") == "sky", "look-dev measured (AgX, sky world)")
    check(n2.get("gn_groups") == ["CableFromCurve"], "Geometry Nodes group measured")
    check(n2.get("quality_aspect_p90") and n2.get("quality_skew_p90") is not None and "edge_profile" in n2, "mesh quality measured")
    check(n2.get("subd_hold_mm") and n2.get("subd_pinched_max") is not None, "SubD holding loops and pinching measured")
    check(n2.get("skeleton_naming") == "unreal" and n2.get("rest_pose") == "A-pose" and n2.get("face_shape_keys") == "arkit",
          "character measured (Unreal skeleton, A-pose, ARKit face keys)")
    check(n2.get("garment_clearance_mm") and 0 < n2["garment_clearance_mm"] < 20, "garment clearance over the body measured")
    check(n2.get("multires_levels") == 2 and n2.get("sculpt_detail_pct"), "sculpting measured (Multires levels, sculpt detail)")
    ex = os.path.join(res2["dir"], "exports") if res2.get("dir") else ""
    check(all(os.path.isfile(os.path.join(ex, f)) for f in ("AGENTS.md", "system-prompt.md", "README.md")),
          "exports for other AI tools written with the build")
    check(os.path.getsize(os.path.join(ex, "AGENTS.md")) < 2000, "the AGENTS.md export is a short pointer, not the whole skill")
    # a project that SkillBlend 0.4 installed into: the whole skill pasted into the instruction files, a copy in .skillblend
    name2 = res2["name"]
    aiproj_dir = os.path.join(tmp, "aiproj")
    old_block = (f"<!-- skillblend:{name2}:start -->\n# {name2}\nThe style's files are in `.skillblend/{name2}/`.\n"
                 + "old rule\n" * 400 + f"<!-- skillblend:{name2}:end -->\n")
    os.makedirs(os.path.join(aiproj_dir, ".cursor", "rules"))
    os.makedirs(os.path.join(aiproj_dir, ".skillblend", name2, "references"))
    with open(os.path.join(aiproj_dir, "AGENTS.md"), "w") as fh:
        fh.write("# Existing notes\n\n" + old_block)
    with open(os.path.join(aiproj_dir, "GEMINI.md"), "w") as fh:
        fh.write(old_block)
    with open(os.path.join(aiproj_dir, ".cursor", "rules", name2 + ".mdc"), "w") as fh:
        fh.write(old_block)
    for f, text in (("SKILL.md", f"---\nname: {name2}\ndescription: old\n---\n\n# Old\n"), ("style.json", "{}"),
                    ("references/mine.md", "my own reference\n")):
        with open(os.path.join(aiproj_dir, ".skillblend", name2, f), "w") as fh:
            fh.write(text)
    tools = "codex,cursor,gemini,copilot,windsurf,agents-md,prompt"
    code, out = forge(ws2, "install", res2.get("dir", ""), "--for", tools, "--project-dir", aiproj_dir)
    shared = os.path.join(aiproj_dir, ".agents", "skills", name2)
    agents = open(os.path.join(aiproj_dir, "AGENTS.md"), encoding="utf-8").read()
    check(code == 0 and os.path.isfile(os.path.join(shared, "SKILL.md")) and os.path.isfile(os.path.join(shared, "scripts", "style_check.py")),
          "one shared .agents/skills folder is installed for Codex, Cursor, Gemini CLI, Copilot and Windsurf")
    check(agents.startswith("# Existing notes") and agents.count(":start -->") == 1 and "old rule" not in agents
          and f".agents/skills/{name2}/SKILL.md" in agents and len(agents) < 2000,
          "the user's AGENTS.md is kept and gets a short pointer in place of the old pasted skill")
    check(not os.path.exists(os.path.join(aiproj_dir, "GEMINI.md")) and not os.path.exists(os.path.join(aiproj_dir, ".cursor", "rules", name2 + ".mdc"))
          and not os.path.exists(os.path.join(aiproj_dir, ".skillblend")),
          "what 0.4 pasted into GEMINI.md, the Cursor rule and .skillblend is cleaned up")
    check(os.path.isfile(os.path.join(shared, "references", "mine.md")), "a file added by hand to the old copy moves with it")
    code, out = forge(ws2, "install", res2.get("dir", ""), "--for", tools, "--project-dir", aiproj_dir)
    check(code != 0 and "already exists" in out, "installing over an existing skill asks for --force")
    code, out = forge(ws2, "install", res2.get("dir", ""), "--for", tools, "--project-dir", aiproj_dir, "--force")
    agents = open(os.path.join(aiproj_dir, "AGENTS.md"), encoding="utf-8").read()
    check(code == 0 and agents.count(":start -->") == 1 and os.path.isfile(os.path.join(shared, "references", "mine.md")),
          "updating replaces the pointer block and keeps the hand-added file")
    refs = os.listdir(os.path.join(res2["dir"], "references")) if res2.get("dir") else []
    check("modifier-dictionary.md" in refs and "shader-recipes.md" in refs, "reference tables written into the skill")

    # The eval harness. The "AI" here is tests/eval_standin.py: it proves the plumbing, and says nothing about any real AI.
    print("eval")
    from forge import evalkit
    standin = os.path.join(HERE, "eval_standin.py")
    ev_with, ev_without = os.path.join(tmp, "ev_with"), os.path.join(tmp, "ev_without")
    os.makedirs(ev_with)
    os.makedirs(ev_without)
    for t in ("supply-crate", "flashlight", "junction-box"):
        blender_run(exe, "--python", standin, "--", "with", res2["dir"], os.path.join(ev_with, t + ".blend"), t)
    blender_run(exe, "--python", standin, "--", "without", "", os.path.join(ev_without, "supply-crate.blend"), "supply-crate")
    with open(os.path.join(ev_without, "flashlight.blend"), "w") as fh:
        fh.write("this is not a .blend file")          # and junction-box.blend is missing altogether
    code, out = forge(ws2, "eval", "score", ev_with, ev_without, "--skill", res2["dir"], "--name", "check", "--json")
    ev = json.loads(out) if code == 0 else {"summary": {"with": {}, "without": {}}, "models": {"without": []}}
    sw, so = ev["summary"]["with"], ev["summary"]["without"]
    check(code == 0 and sw.get("built") == 3 and sw.get("prompts") == 3, "eval score: every styled model is scored")
    check(so.get("built") == 1 and so.get("prompts") == 3 and [r["built"] for r in ev["models"]["without"]] == [False, False, True],
          "eval score: a missing model and an unreadable one count as not built, and stay in the totals")
    check(so.get("warnings_per_model") is not None and sw.get("warnings_per_model") < so.get("warnings_per_model"),
          f"eval score: the styled models get fewer warnings than the careless one ({sw.get('warnings_per_model')} against {so.get('warnings_per_model')})")
    rdir = ev.get("dir", "")
    rmd = open(os.path.join(rdir, "report.md"), encoding="utf-8").read() if rdir and os.path.isfile(os.path.join(rdir, "report.md")) else ""
    check(os.path.isfile(os.path.join(rdir, "report.json")) and ev.get("headline", "x") in rmd and "(3 prompts;" in rmd
          and "not built (no model file)" in rmd and os.path.isfile(os.path.join(rdir, "scores", "with", "flashlight.json")),
          "eval score: report.md and report.json are written, with the headline and why a model wasn't built")
    runner = f'"{exe}" -b --factory-startup --python "{standin}" -- {{arm}} "{{skill_dir}}" "{{out}}" {{task}}'
    os.environ["EVAL_STANDIN_SKIP"] = "flashlight:without"   # that runner "fails": it saves nothing
    code, out = forge(ws2, "eval", "run", "--skill", res2["dir"], "--runner", runner, "--only", "supply-crate,flashlight",
                      "--name", "check", "--json")
    del os.environ["EVAL_STANDIN_SKIP"]
    ev2 = json.loads(out) if code == 0 else {"summary": {"with": {}, "without": {}}, "runs": [], "caveats": []}
    s2w, s2o = ev2["summary"]["with"], ev2["summary"]["without"]
    r2 = ev2.get("dir", "")
    check(code == 0 and ev2.get("run") == "check-2" and os.path.isfile(os.path.join(rdir, "report.md")),
          "eval run: a second run with the same name gets its own folder; the first is untouched")
    check(s2w.get("built") == 2 and s2o.get("built") == 1 and s2o.get("prompts") == 2
          and s2w.get("warnings_per_model") < s2o.get("warnings_per_model"),
          "eval run: both arms are built and scored, and a runner that saves nothing counts as not built")
    wd = os.path.join(r2, "supply-crate")
    check(os.path.isfile(os.path.join(wd, "with", ".claude", "skills", name2, "SKILL.md"))
          and os.path.isfile(os.path.join(wd, "with", ".agents", "skills", name2, "SKILL.md"))
          and not os.path.exists(os.path.join(wd, "without", ".claude")) and not os.path.exists(os.path.join(wd, "without", ".agents")),
          "eval run: the skill is installed in the with arm's folder only")
    same = [open(os.path.join(wd, arm, "PROMPT.md"), encoding="utf-8").read() for arm in ("with", "without")] if os.path.isdir(wd) else ["", "x"]
    check(same[0] == same[1] and "Sci-fi" not in same[0] and "supply crate" in same[0], "eval run: both arms get the same prompt")
    home_has_skills = bool(evalkit.home_skills())
    said = any("may have seen user-level skills" in c for c in ev2.get("caveats", []))
    check(said == home_has_skills, "eval run: the report warns that the without arm may have seen home-folder skills exactly when there are some")
    runs_before = sorted(os.listdir(os.path.join(ws2, "eval")))
    code, out = forge(ws2, "eval", "run", "--skill", res2["dir"], "--agent", "claude", "--only", "flashlight")
    check(code == 0 and "Nothing was started" in out and "--yes" in out and sorted(os.listdir(os.path.join(ws2, "eval"))) == runs_before,
          "eval run: an agent preset without --yes only prints its commands")
    code, out = forge(ws2, "eval", "report")
    check(code == 0 and out.startswith("# SkillBlend eval: check-2"), "eval report shows the latest run")

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
    inst = os.path.join(tmp, "proj", ".claude", "skills", res.get("name", "?"))
    check(code == 0 and os.path.isfile(os.path.join(inst, "SKILL.md")), "install to a project")
    # the artist adds a file, writes a section into SKILL.md and edits a script; then the skill is rebuilt and updated
    with open(os.path.join(inst, "references", "footwear.md"), "w") as fh:
        fh.write("# Footwear\nmy own notes\n")
    with open(os.path.join(inst, "SKILL.md"), "a", encoding="utf-8") as fh:
        fh.write("\n## Footwear and soft goods (measured)\n\n- Shoes are built from panels.\n")
    with open(os.path.join(inst, "scripts", "style.py"), "a", encoding="utf-8") as fh:
        fh.write("\n# my tweak\n")
    code, out = forge(ws, "install", pdir, "--scope", "project", "--project-dir", os.path.join(tmp, "proj"), "--force")
    sk = open(os.path.join(inst, "SKILL.md"), encoding="utf-8").read()
    notes = open(os.path.join(inst, "NOTES.md"), encoding="utf-8").read() if os.path.isfile(os.path.join(inst, "NOTES.md")) else ""
    check(code == 0 and os.path.isfile(os.path.join(inst, "references", "footwear.md")) and "references/footwear.md" in sk,
          "updating an installed skill keeps a file added by hand and lists it in SKILL.md")
    check("Shoes are built from panels" in notes and "Shoes are built from panels" not in sk and "NOTES.md" in sk,
          "a section written into SKILL.md by hand moves to NOTES.md")
    bdir = os.path.join(ws, "backups")
    saved = [os.path.join(d, f) for d, _, fs in os.walk(bdir) for f in fs] if os.path.isdir(bdir) else []
    check(any(p.endswith("style.py") and "# my tweak" in open(p, encoding="utf-8").read() for p in saved)
          and "# my tweak" not in open(os.path.join(inst, "scripts", "style.py"), encoding="utf-8").read(),
          "an edited SkillBlend file is backed up before it's replaced")
    code, out = forge(ws, "build", "--generic", "--out", inst)
    check(code == 1 and os.path.isfile(os.path.join(inst, "references", "footwear.md")), "build --out refuses an installed skill")

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
