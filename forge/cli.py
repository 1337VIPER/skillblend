"""Command line for SkillBlend."""
import argparse
import json
import os
import shutil
import sys

from . import __version__, build as buildlib, modules as modlib, paths, profile
from .workspace import Workspace


def _val(s):
    low = s.strip().lower()
    if low in ("true", "yes", "y"):
        return True
    if low in ("false", "no", "n"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def _mod(mods, ref):
    m = modlib.find(mods, ref)
    if not m:
        sys.exit(f"Unknown module {ref!r}. Modules: {', '.join(x['id'] for x in mods)}")
    return m


def _next(ws, mods):
    skipped = set(ws.state.get("skipped", []))
    for m in mods:
        if m.get("source") == "scripts":
            continue  # read from the project, not submitted
        if not ws.submissions(m["id"]) and m["id"] not in skipped:
            return m
    return None


def cmd_status(ws, mods, a):
    rows = []
    for i, m in enumerate(mods, 1):
        subs = ws.submissions(m["id"])
        analysed = [s for s in subs if os.path.isfile(ws.analysis_path(m["id"], s))]
        state = ("skipped" if m["id"] in ws.state.get("skipped", []) else
                 f"{len(subs)} file(s)" + ("" if len(analysed) == len(subs) else f", {len(subs) - len(analysed)} not analysed")
                 if subs else "waiting")
        rows.append({"n": i, "id": m["id"], "title": m["title"], "optional": m["optional"], "state": state,
                     "answers": len(ws.answers.get(m["id"], {})), "questions": len(m["questions"]),
                     "has_generic": os.path.isfile(os.path.join(m["dir"], "generic.md"))})
    blender = ws.blender()
    nxt = _next(ws, mods)
    if a.json:
        print(json.dumps({"workspace": ws.root, "blender": blender, "author": ws.config.get("author"),
                          "modules": rows, "next": nxt["id"] if nxt else None}, indent=2))
        return 0
    print(f"SkillBlend {__version__}   workspace: {ws.root}")
    print(f"Blender: {blender or 'NOT FOUND (python skillblend.py config --blender PATH)'}")
    if ws.config.get("author"):
        print(f"Author: {ws.config['author']}")
    print()
    for r in rows:
        opt = " (optional)" if r["optional"] else ""
        print(f" {r['n']:>2}. {r['id']:<24} {r['state']:<28} answers {r['answers']}/{r['questions']}{opt}")
    print()
    print(f"Next: {nxt['id']}  ->  python skillblend.py request {nxt['id']}" if nxt else
          "Every module has a submission or is skipped. Build with: python skillblend.py build")
    return 0


def cmd_modules(ws, mods, a):
    for i, m in enumerate(mods, 1):
        print(f"{i:>2}. {m['id']:<24} {m['title']}{' (optional)' if m['optional'] else ''}\n    {m['summary']}")
    return 0


def cmd_request(ws, mods, a):
    m = _next(ws, mods) if a.module in (None, "next") else _mod(mods, a.module)
    if not m:
        print("Nothing left to request. Build with: python skillblend.py build")
        return 0
    rq = m["request"]
    if a.json:
        print(json.dumps({"id": m["id"], "title": m["title"], "request": rq, "questions": m["questions"]}, indent=2))
        return 0
    print(f"== {m['title']} ({m['id']}){' - optional' if m['optional'] else ''}\n")
    print(rq["brief"] + "\n")
    print("Must include:")
    for x in rq.get("must_include", []):
        print(f"  - {x}")
    print(f"\nSubmit: {rq.get('submit', 'one .blend file')}")
    if rq.get("ideas"):
        print("Ideas: " + ", ".join(rq["ideas"]))
    print(f"\nWhen it's ready: python skillblend.py submit {m['id']} PATH/TO/FILE.blend [--note \"...\"]")
    return 0


def _print_result(m, r):
    print(f"-- {m['title']}: what the files show")
    for x in r.rules:
        print(f"  - {x}")
    for w in r.warnings:
        print(f"  ! {w}")


def cmd_submit(ws, mods, a):
    m = _mod(mods, a.module)
    dst = ws.add_submission(m["id"], a.file, a.note or "")
    print(f"Stored as {os.path.relpath(dst, ws.root)}")
    if not dst.lower().endswith(".blend") or a.no_analyse:
        if not dst.lower().endswith(".blend"):
            print("Not a .blend: kept as a reference (shipped with the examples), not analysed.")
        return 0
    print("Analysing in Blender (headless)...")
    try:
        ws.analyse(m["id"], dst)
    except Exception as exc:
        print(str(exc))
        return 1
    r = profile.run_module(m, profile.load_analyses(ws.root), ws.answers)
    _print_result(m, r)
    unanswered = [q for q in m["questions"] if q["key"] not in ws.answers.get(m["id"], {})]
    if unanswered:
        print(f"\n{len(unanswered)} question(s) for this module: python skillblend.py questions {m['id']}")
    return 0


def cmd_remove(ws, mods, a):
    m = _mod(mods, a.module)
    p = ws.remove_submission(m["id"], a.ref)
    print(f"Removed {os.path.basename(p)}" if p else "No such submission.")
    return 0 if p else 1


def cmd_analyse(ws, mods, a):
    targets = [_mod(mods, a.module)] if a.module else mods
    fails = 0
    for m in targets:
        for s in ws.submissions(m["id"]):
            if not s.lower().endswith(".blend"):
                continue
            try:
                ws.analyse(m["id"], s)
                print(f"ok   {m['id']}: {os.path.basename(s)}")
            except Exception as exc:
                fails += 1
                print(f"FAIL {m['id']}: {exc}")
    return 1 if fails else 0


def cmd_report(ws, mods, a):
    analyses = profile.load_analyses(ws.root)
    targets = [_mod(mods, a.module)] if a.module and a.module != "all" else mods
    out = {}
    for m in targets:
        r = profile.run_module(m, analyses, ws.answers)
        out[m["id"]] = r.as_dict()
        if not a.json and (r.rules or r.warnings):
            _print_result(m, r)
            if r.numbers:
                print("  style: " + ", ".join(f"{k}={v}" for k, v in r.numbers.items()))
            print()
    if a.json:
        print(json.dumps(out, indent=2))
    return 0


def cmd_questions(ws, mods, a):
    m = _mod(mods, a.module)
    ans = ws.answers.get(m["id"], {})
    if a.json:
        print(json.dumps([{**q, "answer": ans.get(q["key"])} for q in m["questions"]], indent=2))
        return 0
    for q in m["questions"]:
        opts = (" [" + " | ".join(f"{o['label']}={o['value']}" for o in q["options"]) + "]") if q.get("options") else ""
        cur = f"   (answered: {ans[q['key']]})" if q["key"] in ans else ""
        print(f"- {q['key']}: {q['ask']}{opts}{cur}")
    print(f"\nAnswer with: python skillblend.py answer {m['id']} KEY \"VALUE\"")
    return 0


def cmd_answer(ws, mods, a):
    m = _mod(mods, a.module)
    keys = {q["key"] for q in m["questions"]}
    if a.key not in keys and not a.force:
        sys.exit(f"{a.key!r} isn't a question of {m['id']} ({', '.join(sorted(keys))}). Use --force to store it anyway.")
    if not a.value:
        sys.exit("Give a value: python skillblend.py answer MODULE KEY VALUE")
    ws.set_answer(m["id"], a.key, _val(" ".join(a.value)))
    print(f"Saved {m['id']}.{a.key}")
    return 0


def cmd_ask(ws, mods, a):
    m = _mod(mods, a.module)
    for q in m["questions"]:
        print(q["ask"])
        if q.get("options"):
            for i, o in enumerate(q["options"], 1):
                print(f"  {i}. {o['label']}")
        raw = input("> ").strip()
        if not raw:
            continue
        if q.get("options") and raw.isdigit() and 1 <= int(raw) <= len(q["options"]):
            val = q["options"][int(raw) - 1]["value"]
        else:
            val = _val(raw)
        ws.set_answer(m["id"], q["key"], val)
    return 0


def cmd_skip(ws, mods, a):
    m = _mod(mods, a.module)
    ws.skip(m["id"], not a.undo)
    print(("Unskipped " if a.undo else "Skipped ") + m["id"] + ("" if a.undo else " (the skill uses the generic section for it)"))
    return 0


def cmd_build(ws, mods, a):
    try:
        res = buildlib.build(ws, name=a.name, author=a.author, generic=a.generic,
                             exclude=[x for x in (a.exclude or "").split(",") if x],
                             include_examples=bool(getattr(a, "examples", False)) and not a.no_examples, out_dir=a.out)
    except buildlib.NothingSubmitted as exc:
        print(str(exc))
        return 2
    if a.json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"Built {'personal' if res['personal'] else 'GENERIC'} skill '{res['name']}' in {res['dir']}")
    if res["personal"]:
        print(f"  measured: {', '.join(res['covered']) or '-'}")
        print(f"  generic:  {', '.join(res['generic']) or '-'}")
    for k, ws_ in res["warnings"].items():
        for w in ws_:
            print(f"  ! {k}: {w}")
    print(f"\nInstall it: python skillblend.py install \"{res['dir']}\"")
    return 0


def _skills_dir(scope, project_dir):
    if scope == "project":
        return os.path.join(os.path.abspath(project_dir or os.getcwd()), ".claude", "skills")
    return os.path.join(os.path.expanduser("~"), ".claude", "skills")


def cmd_install(ws, mods, a):
    src = os.path.abspath(a.dir)
    if not os.path.isfile(os.path.join(src, "SKILL.md")):
        sys.exit(f"No SKILL.md in {src}")
    name = os.path.basename(src.rstrip("\\/"))
    dst = os.path.join(_skills_dir(a.scope, a.project_dir), name)
    if os.path.exists(dst):
        if not a.force:
            sys.exit(f"{dst} already exists. Re-run with --force to replace it.")
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"Installed to {dst}. Start a new Claude Code session to load it.")
    return 0


def cmd_install_driver(ws, mods, a):
    src = os.path.join(paths.REPO, "driver-skill", "SKILL.md")
    dst_dir = os.path.join(_skills_dir(a.scope, a.project_dir), "skillblend")
    if os.path.exists(dst_dir) and not a.force:
        sys.exit(f"{dst_dir} already exists. Re-run with --force to replace it.")
    os.makedirs(dst_dir, exist_ok=True)
    with open(src, encoding="utf-8") as fh:
        text = fh.read().replace("{{FORGE}}", os.path.join(paths.REPO, "skillblend.py").replace("\\", "/"))
    with open(os.path.join(dst_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"Installed the driver skill to {dst_dir}. In Claude Code, say \"start skillblend\".")
    return 0


def cmd_learn(ws, mods, a):
    from .project import Project
    pr = Project(ws)
    if not ws.blender():
        sys.exit("Blender not found. Run: python skillblend.py config --blender PATH")
    print(f"Learning from {', '.join(a.folder)} ...")
    data = pr.scan(a.folder, workers=a.workers)
    used = [f for f in data["files"] if f.get("detected")]
    print(f"{len(data['files'])} .blend file(s) analysed, {len(data['skipped'])} skipped (backups, autosaves, duplicates).")
    for e in pr.progress["errors"]:
        print(f"  ! {e}")
    picked = pr.analyses()
    for m in mods:
        docs = picked.get(m["id"], [])
        kind = "script(s)" if m.get("source") == "scripts" else "file(s)"
        files = [f for f in data["files"] if m["id"] in f.get("detected", {})]
        eg = (f"  e.g. {files[0]['rel']}: {files[0]['detected'][m['id']]}" if files else
              (f"  e.g. {docs[0]['_submission']['file']}" if docs else "  (generic)"))
        print(f"  {m['id']:<24} {len(docs):>3} {kind:<9}{eg}")
    if a.build:
        return cmd_build(ws, mods, a)
    print("\nSee what it learned: python skillblend.py report    Build: python skillblend.py build")
    return 0


def cmd_demo(ws, mods, a):
    import subprocess
    out = os.path.abspath(a.dir or os.path.join(ws.root, "demo-project"))
    exe = ws.blender()
    if not exe:
        sys.exit("Blender not found. Run: python skillblend.py config --blender PATH")
    os.makedirs(out, exist_ok=True)
    p = subprocess.run([exe, "-b", "--factory-startup", "--python", os.path.join(paths.PKG, "demo", "make_demo.py"),
                        "--", out], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if "FIXTURES_OK" not in p.stdout:
        print(p.stdout[-2000:] + p.stderr[-2000:])
        return 1
    for f in ("demokit.py", "setup_crate.py"):
        shutil.copy2(os.path.join(paths.PKG, "demo", f), os.path.join(out, f))
    print(f"Demo project written to {out}")
    print(f"Learn it:  python skillblend.py learn \"{out}\"   (or add the folder in the app)")
    return 0


def cmd_app(ws, mods, a):
    from .app import serve
    return serve(ws, port=a.port, open_browser=not a.no_browser)


def cmd_config(ws, mods, a):
    if a.blender and not os.path.isfile(a.blender):
        sys.exit(f"Not a file: {a.blender}")
    ws.set_config(blender=a.blender, author=a.author)
    print(json.dumps(ws.config, indent=2))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="skillblend.py", description="SkillBlend: build a Claude Code skill that models like you.")
    p.add_argument("--workspace", help="workspace folder (default: ./workspace or $FORGE_WORKSPACE)")
    p.add_argument("--version", action="version", version=__version__)
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("status", help="modules, submissions and what's next"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_status)
    s = sp.add_parser("modules", help="list the technique modules"); s.set_defaults(f=cmd_modules)
    s = sp.add_parser("request", help="show what to model and submit for a module"); s.add_argument("module", nargs="?"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_request)
    s = sp.add_parser("submit", help="submit a .blend (or a reference image) for a module")
    s.add_argument("module"); s.add_argument("file"); s.add_argument("--note"); s.add_argument("--no-analyse", action="store_true"); s.set_defaults(f=cmd_submit)
    s = sp.add_parser("remove", help="remove a submission (by number or file name)"); s.add_argument("module"); s.add_argument("ref"); s.set_defaults(f=cmd_remove)
    s = sp.add_parser("analyse", help="re-run the Blender analysis"); s.add_argument("module", nargs="?"); s.set_defaults(f=cmd_analyse)
    s = sp.add_parser("report", help="show the measured rules"); s.add_argument("module", nargs="?"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_report)
    s = sp.add_parser("questions", help="the interview questions for a module"); s.add_argument("module"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_questions)
    s = sp.add_parser("answer", help="store an interview answer (values starting with - are fine)"); s.add_argument("module"); s.add_argument("key"); s.add_argument("value", nargs=argparse.REMAINDER); s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_answer)
    s = sp.add_parser("ask", help="answer a module's questions interactively"); s.add_argument("module"); s.set_defaults(f=cmd_ask)
    s = sp.add_parser("skip", help="skip a module (it stays generic)"); s.add_argument("module"); s.add_argument("--undo", action="store_true"); s.set_defaults(f=cmd_skip)
    s = sp.add_parser("build", help="build the skill")
    s.add_argument("--name"); s.add_argument("--author"); s.add_argument("--generic", action="store_true", help="build the generic skill, ignoring submissions")
    s.add_argument("--exclude", help="comma-separated module ids to leave out")
    s.add_argument("--examples", action="store_true", help="copy your .blend files and build scripts into the skill so Claude can study them")
    s.add_argument("--no-examples", action="store_true", help=argparse.SUPPRESS)
    s.add_argument("--out"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_build)
    for name, fn, hlp in (("install", cmd_install, "copy a built skill into Claude Code's skills folder"),
                          ("install-driver", cmd_install_driver, "install the skill that lets Claude run the SkillBlend interview")):
        s = sp.add_parser(name, help=hlp)
        if name == "install":
            s.add_argument("dir")
        s.add_argument("--scope", choices=["user", "project"], default="user"); s.add_argument("--project-dir"); s.add_argument("--force", action="store_true"); s.set_defaults(f=fn)
    s = sp.add_parser("learn", help="learn the style of a whole project folder (finds and sorts the .blend files itself)")
    s.add_argument("folder", nargs="+", help="project folder(s); add your kit library's folder or file too"); s.add_argument("--workers", type=int); s.add_argument("--build", action="store_true", help="build the skill right after")
    s.add_argument("--name"); s.add_argument("--author"); s.add_argument("--generic", action="store_true", help=argparse.SUPPRESS)
    s.add_argument("--exclude"); s.add_argument("--examples", action="store_true"); s.add_argument("--no-examples", action="store_true", help=argparse.SUPPRESS)
    s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s.set_defaults(f=cmd_learn)
    s = sp.add_parser("demo", help="write a small demo project to try SkillBlend on"); s.add_argument("dir", nargs="?"); s.set_defaults(f=cmd_demo)
    s = sp.add_parser("app", help="open the SkillBlend app in your browser"); s.add_argument("--port", type=int, default=4970)
    s.add_argument("--no-browser", action="store_true"); s.set_defaults(f=cmd_app)
    s = sp.add_parser("config", help="set the Blender path or your author name"); s.add_argument("--blender"); s.add_argument("--author"); s.set_defaults(f=cmd_config)

    a = p.parse_args(argv)
    ws = Workspace(a.workspace)
    mods = modlib.load_modules()
    return a.f(ws, mods, a)
