"""Does the skill change what an AI builds? Build the same prompts with and without it, and score both.

    python skillblend.py eval tasks                                    # the prompts
    python skillblend.py eval score WITH_DIR WITHOUT_DIR --skill DIR   # score models you already have
    python skillblend.py eval run --skill DIR --agent claude --yes     # have an AI build them, then score
    python skillblend.py eval report                                   # the latest run's report

Every model is scored by the skill's own ``scripts/style_check.py``: the same check the skill tells an AI to run
before it calls a model done. A run lives in ``<workspace>/eval/<run>/`` and is never overwritten:

    <task>/<arm>/      one working folder per prompt and arm ("with" has the skill installed in it, "without" not)
    models/<arm>/      the models that were built, named after their task
    scores/<arm>/      each model's findings
    pictures/<arm>/    one picture of each model, all rendered the same way
    report.md, report.json

Standard library only. Nothing here starts an AI unless you run ``eval run`` yourself.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from . import __version__, paths
from .targets import install_skill, parse_skill, read_manifest

TASKS_FILE = os.path.join(paths.PKG, "eval", "tasks.json")
ARMS = ("with", "without")
MODEL_NAME = "model.blend"
RESERVED = {"models", "scores", "backups", "pictures"}  # folder names a run uses; a task id can't be one of them
# where assistants look for skills in a home folder (listed read-only, to say whether the "without" arm could see one)
HOME_SKILL_DIRS = (".claude/skills", ".agents/skills", ".codex/skills", ".gemini/skills", ".cursor/skills", ".copilot/skills")
TEXT_EXT = (".py", ".md", ".txt", ".json", ".jsonl", ".log", ".toml", ".yaml", ".yml")

# Runner presets. BEST EFFORT: written from each tool's own --help (Claude Code 2.1, Codex CLI 0.157), never run by
# SkillBlend's tests, because a run spends your AI usage. Check the flags against your tool's version before you rely
# on them, or pass your own command with --runner. The prompt is piped to the runner's standard input.
#   isolation: what the "without" arm does about skills installed in your home folder.
#     "flag"  the tool has a switch that its help says hides them; SkillBlend uses it but has not verified it
#     "none"  no switch known: the "without" arm can see your home-folder skills
#   home: the home folders this tool loads skills from
PRESETS = {
    "claude": {
        "label": "Claude Code (headless)",
        "with": 'claude -p --output-format json --no-session-persistence --permission-mode acceptEdits '
                '--allowedTools Bash,PowerShell,Read,Write,Edit,Glob,Grep,Skill --setting-sources project '
                '--strict-mcp-config',
        "without": 'claude -p --output-format json --no-session-persistence --permission-mode acceptEdits '
                   '--allowedTools Bash,PowerShell,Read,Write,Edit,Glob,Grep --safe-mode',
        "isolation": "flag",
        "isolation_note": "the without arm is started with --safe-mode, which hid every home-folder skill when it was "
                          "checked on Claude Code 2.1.319 (the with arm, with --setting-sources project, saw only the "
                          "skill installed in its run folder)",
        "home": ("~/.claude/skills",),
        "version": ["claude", "--version"],
        "model_flag": "--model",
    },
    "codex": {
        "label": "OpenAI Codex (exec)",
        "with": 'codex exec --skip-git-repo-check --sandbox workspace-write -C "{workdir}" -',
        "without": 'codex exec --skip-git-repo-check --sandbox workspace-write -C "{workdir}" -',
        "isolation": "none",
        "isolation_note": "Codex has no switch SkillBlend knows of that hides the skills in your home folder",
        "home": ("~/.agents/skills", "~/.codex/skills"),
        "version": ["codex", "--version"],
        "model_flag": "--model",
    },
}


# ------------------------------------------------------------------ tasks
def load_tasks(path=None, only=None):
    """The eval prompts: [{id, title, prompt, file}]. `only` keeps the named ids, in the file's order."""
    path = path or TASKS_FILE
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    raw = doc.get("tasks") if isinstance(doc, dict) else doc
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path}: expected a list of tasks (or {{\"tasks\": [...]}}).")
    tasks, seen, files = [], set(), set()
    for i, t in enumerate(raw, 1):
        tid = str((t or {}).get("id") or "")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", tid):
            raise ValueError(f"{path}: task {i} needs an id of lowercase letters, numbers and hyphens (got {tid!r}).")
        if tid in seen or tid in RESERVED:
            raise ValueError(f"{path}: task id {tid!r} is used twice or is a reserved name.")
        prompt = " ".join(str(t.get("prompt") or "").split())
        if not prompt:
            raise ValueError(f"{path}: task {tid!r} has no prompt.")
        fname = os.path.basename(str(t.get("file") or tid + ".blend"))
        if not fname.lower().endswith(".blend") or fname.lower() in files:
            raise ValueError(f"{path}: task {tid!r} needs its own .blend file name (got {fname!r}).")
        seen.add(tid)
        files.add(fname.lower())
        tasks.append({"id": tid, "title": str(t.get("title") or tid), "prompt": prompt, "file": fname})
    if only:
        want = [x.strip() for x in (only if isinstance(only, (list, tuple)) else str(only).split(",")) if x.strip()]
        missing = [x for x in want if x not in seen]
        if missing:
            raise ValueError(f"No such task: {', '.join(missing)}. Tasks: {', '.join(t['id'] for t in tasks)}.")
        tasks = [t for t in tasks if t["id"] in want]
    return tasks


def full_prompt(task, blender, skill_name=None):
    """What the AI is told: the task, then how to deliver it. The same text for both arms, unless `skill_name` is
    given (--name-skill), which adds one line to the "with" arm."""
    return (f"{task['prompt']}\n\n"
            "How to deliver it:\n"
            f"- Work only in the current folder. Build the model in Blender and save it as `{MODEL_NAME}` in the current folder.\n"
            f"- Blender is installed at: {blender}\n"
            f"  Run it without a window, for example: \"{blender}\" -b --factory-startup --python build_model.py\n"
            "- Build the model from a Python script that you write in this folder, and keep the script.\n"
            "- Don't ask questions: make sensible choices yourself. Stop as soon as the file is saved.\n"
            + (f"- Use the `{skill_name}` skill.\n" if skill_name else ""))


# ------------------------------------------------------------------ runner commands
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def split_command(template):
    """A command line as a list of words. Words are separated by spaces; "double" or 'single' quotes keep spaces
    inside one word. A backslash is an ordinary character, so Windows paths need no escaping."""
    words, cur, quote, open_word = [], [], None, False
    for ch in template:
        if quote:
            if ch == quote:
                quote = None
            else:
                cur.append(ch)
        elif ch in "\"'":
            quote, open_word = ch, True
        elif ch.isspace():
            if cur or open_word:
                words.append("".join(cur))
            cur, open_word = [], False
        else:
            cur.append(ch)
    if quote:
        raise ValueError(f"Unclosed {quote} in the runner command: {template}")
    if cur or open_word:
        words.append("".join(cur))
    return words


def render_command(template, values):
    """The runner's argument list: the template is split into words first and the {placeholders} are filled in
    afterwards, so a prompt or a path with spaces always stays one argument."""
    words = split_command(template)
    if not words:
        raise ValueError("The runner command is empty.")

    def fill(word):
        def rep(m):
            if m.group(1) not in values:
                raise ValueError(f"Unknown placeholder {{{m.group(1)}}} in the runner command. "
                                 f"Use: {', '.join('{' + k + '}' for k in sorted(values))}.")
            return str(values[m.group(1)])
        return PLACEHOLDER.sub(rep, word)
    return [fill(w) for w in words]


def _kill_tree(proc):
    """Stop a runner and whatever it started (an agent that timed out may have Blender running)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def run_command(argv, cwd, stdin_text, timeout, env):
    """Run one runner command. Returns {code, seconds, timed_out, error, output}."""
    t0 = time.time()
    exe = shutil.which(argv[0]) or argv[0]
    kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    try:
        proc = subprocess.Popen([exe] + argv[1:], cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", **kw)
    except OSError as exc:
        return {"code": None, "seconds": 0.0, "timed_out": False, "error": f"could not start {argv[0]}: {exc}", "output": ""}
    try:
        out, _ = proc.communicate(stdin_text, timeout=timeout)
        return {"code": proc.returncode, "seconds": round(time.time() - t0, 1), "timed_out": False, "error": None, "output": out or ""}
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            out, _ = proc.communicate(timeout=20)
        except Exception:
            out = ""
        return {"code": None, "seconds": round(time.time() - t0, 1), "timed_out": True,
                "error": f"stopped after {timeout} s (the time limit)", "output": out or ""}


# ------------------------------------------------------------------ what could have leaked
def home_skills(home=None):
    """{folder: [skill names]} for the skill folders in a home directory. Read-only: nothing there is touched."""
    home = home or os.path.expanduser("~")
    out = {}
    for rel in HOME_SKILL_DIRS:
        d = os.path.join(home, *rel.split("/"))
        if not os.path.isdir(d):
            continue
        try:
            names = sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n, "SKILL.md")))
        except OSError:
            names = []
        if names:
            out["~/" + rel] = names
    return out


def skill_signs(workdir, names, also=()):
    """Mentions of a skill in what a run left behind: its log and the text files it wrote (the installed copy of
    the skill itself is not searched). A heuristic: no mention is not proof that no skill was read."""
    pats = [(n, re.compile(r"skills[\\/]+" + re.escape(n) + r"\b", re.I)) for n in names]
    pats += [("the Skill tool", re.compile(r'"name"\s*:\s*"Skill"'))]
    pats += [(w, re.compile(re.escape(w))) for w in also]
    hits = set()
    for d, dirs, files in os.walk(workdir):
        dirs[:] = [x for x in dirs if x not in (".claude", ".agents", "__pycache__", ".git")]
        for f in files:
            p = os.path.join(d, f)
            if f == "PROMPT.md" or not f.lower().endswith(TEXT_EXT) or os.path.getsize(p) > (4 << 20):
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            hits.update(label for label, rx in pats if rx.search(text))
    return sorted(hits)


# ------------------------------------------------------------------ scoring
GREY = 0.8  # Blender's default Base Color and viewport colour


def _blank_material(m):
    """A material nobody set up: Blender's default grey, no metal, nothing plugged into the colour."""
    near = lambda c: c is not None and all(abs(float(x) - GREY) < 0.005 for x in list(c)[:3])
    pr = m.get("principled")
    if m.get("use_nodes") and pr:
        vals, linked = pr.get("values") or {}, pr.get("linked") or {}
        return ("Base Color" not in linked and near(vals.get("Base Color")) and not float(vals.get("Metallic") or 0)
                and not float(vals.get("Emission Strength") or 0) and not float(vals.get("Transmission Weight") or 0))
    if m.get("use_nodes"):
        return False
    return near((m.get("viewport") or {}).get("color"))


def look(an):
    """What the style check doesn't score: how much there is to the model, and whether its materials have colours.
    Parts leave out helpers (boolean cutters, wire or bounds display, hidden from render)."""
    objs = [o for o in an.get("objects", []) if o.get("type") == "MESH" and not o.get("outside_scene") and "error" not in o]
    cutters = {m.get("object") for o in objs for m in o.get("modifiers", []) if m.get("type") == "BOOLEAN" and m.get("object")}
    parts = [o for o in objs if o.get("name") not in cutters and o.get("display_type") not in ("WIRE", "BOUNDS") and not o.get("hide_render")]
    strip = lambda n: re.sub(r"\.\d{3,}$", "", n)
    used = {strip(m) for o in parts for m in (o.get("materials") or []) if m}
    mats = {strip(m["name"]): m for m in an.get("materials", [])}
    blank = sorted(n for n in used if n in mats and _blank_material(mats[n]))
    return {"parts": len(parts),
            "tris": sum(int((o.get("mesh") or {}).get("eval_tri_count") or (o.get("mesh") or {}).get("tri_count") or 0) for o in parts),
            "materials": len(used), "coloured": len(used) - len(blank), "blank": blank,
            "no_material": sum(1 for o in parts if not any(o.get("materials") or []))}


def summarise(model_path, doc, exists=True, detail=""):
    """One model's score from what style_check.py --json wrote (`doc`, or None when it wrote nothing)."""
    row = {"file": os.path.basename(model_path), "built": False, "why": "", "warnings": 0, "notes": 0, "style_ok": False,
           "meshes": 0, "tris": 0, "modules": {}, "findings": [], "look": None, "picture": None}
    if not exists:
        row["why"] = "no model file"
        return row
    if not doc or not isinstance(doc.get("analysis"), dict):
        row["why"] = "Blender could not open or check the file" + (f" ({detail})" if detail else "")
        return row
    an = doc["analysis"]
    if (an.get("file") or "").lower() != row["file"].lower():
        row["why"] = "Blender could not open the file"  # it checked its own start-up scene instead
        return row
    meshes = [o for o in an.get("objects", []) if o.get("type") == "MESH" and not o.get("outside_scene") and "error" not in o]
    row["meshes"] = len(meshes)
    row["tris"] = sum(int((o.get("mesh") or {}).get("eval_tri_count") or (o.get("mesh") or {}).get("tri_count") or 0) for o in meshes)
    if not meshes:
        row["why"] = "the file has no mesh in it"
        return row
    row["built"] = True
    row["look"] = look(an)
    for f in doc.get("findings", []):
        sev = "warnings" if f.get("severity") in ("warn", "error") else "notes"
        row[sev] += 1
        m = row["modules"].setdefault(f.get("module", "?"), {"warnings": 0, "notes": 0})
        m[sev] += 1
        row["findings"].append({"module": f.get("module", "?"), "severity": f.get("severity", "info"), "message": f.get("message", "")})
    row["style_ok"] = not row["findings"]
    return row


def score_model(blender, skill_dir, model_path, out_json, timeout=900):
    """Check one .blend against the skill's style, headless, with the skill's own style_check.py."""
    if not os.path.isfile(model_path):
        return summarise(model_path, None, exists=False)
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    if os.path.isfile(out_json):
        os.remove(out_json)
    cmd = [blender, "-b", "--factory-startup", model_path, "--python",
           os.path.join(skill_dir, "scripts", "style_check.py"), "--", "--json", out_json]
    detail = ""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        tail = [ln for ln in (p.stdout + p.stderr).strip().splitlines() if ln.strip()]
        detail = tail[-1][:160] if tail else ""
    except subprocess.TimeoutExpired:
        detail = f"the check took longer than {timeout} s"
    except OSError as exc:
        detail = str(exc)
    doc = None
    if os.path.isfile(out_json):
        try:
            with open(out_json, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            doc = None
    row = summarise(model_path, doc, detail=detail)
    with open(out_json, "w", encoding="utf-8") as fh:  # keep the findings, not the whole analysis (it can be megabytes)
        json.dump(row, fh, indent=1)
    return row


def picture(blender, model_path, out_png, timeout=300):
    """One picture of a model for the report: every model from the same angle, in the same light. True when made."""
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    if os.path.isfile(out_png):
        os.remove(out_png)
    try:
        subprocess.run([blender, "-b", "--factory-startup", model_path, "--python",
                        os.path.join(paths.BLENDER, "eval_thumb.py"), "--", out_png],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return os.path.isfile(out_png)


def aggregate(rows):
    """One arm's totals. A model that wasn't built stays in the count of prompts; the per-model means are over the
    models that were built."""
    built = [r for r in rows if r["built"]]
    mean = (lambda k: round(sum(r[k] for r in built) / len(built), 2)) if built else (lambda k: None)
    mods = {}
    for r in built:
        for name, c in r["modules"].items():
            m = mods.setdefault(name, {"warnings": 0, "notes": 0})
            m["warnings"] += c["warnings"]
            m["notes"] += c["notes"]
    for m in mods.values():
        m["warnings_per_model"] = round(m["warnings"] / len(built), 2)
    looks = [r["look"] for r in built if r.get("look")]
    lmean = (lambda k: round(sum(x[k] for x in looks) / len(looks), 1)) if looks else (lambda k: None)
    return {"prompts": len(rows), "built": len(built), "warnings_per_model": mean("warnings"), "notes_per_model": mean("notes"),
            "no_warnings": sum(1 for r in built if r["warnings"] == 0), "style_ok": sum(1 for r in built if r["style_ok"]),
            "modules": dict(sorted(mods.items())),
            "parts_per_model": lmean("parts"), "tris_per_model": lmean("tris"),
            "materials": sum(x["materials"] for x in looks), "coloured": sum(x["coloured"] for x in looks)}


def paired(with_rows, without_rows):
    """Prompt by prompt, for the prompts both arms built: which arm has fewer warnings."""
    out = {"both_built": 0, "with_fewer": 0, "same": 0, "without_fewer": 0}
    for a, b in zip(with_rows, without_rows):
        if a["built"] and b["built"]:
            out["both_built"] += 1
            out["with_fewer" if a["warnings"] < b["warnings"] else "same" if a["warnings"] == b["warnings"] else "without_fewer"] += 1
    return out


def _num(x):
    if x is None:
        return "n/a"
    return f"{x:.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def headline(summary):
    """The result in one sentence, with both numbers and how many prompts it rests on."""
    w, wo = summary["with"], summary["without"]
    n = w["prompts"]
    s = "" if n == 1 else "s"
    if not w["built"] and not wo["built"]:
        return f"No model was built in either arm ({n} prompt{s}), so there is nothing to compare."
    part = lambda a: _num(a["warnings_per_model"]) if a["built"] else "n/a (nothing built)"
    return (f"Warnings per model: {part(wo)} without the skill, {part(w)} with it "
            f"({n} prompt{s}; built {w['built']} of {n} with the skill, {wo['built']} of {n} without).")


def small_n_note(n):
    return (f"This rests on {n} prompt{'' if n == 1 else 's'} and one attempt at each. Read it as a direction, not as a "
            "statistically reliable difference; run it again, or with more prompts, before you quote it.")


# ------------------------------------------------------------------ report
def _pattern(msg):
    """A finding's message without the part that names the object, so the same complaint on ten parts counts once."""
    head, sep, rest = msg.partition(": ")
    body = rest if sep and len(head) <= 60 and " " not in head.strip() else msg
    return re.sub(r"\d+(\.\d+)?", "N", body)[:140]


def worst_findings(rows, limit=6):
    c, eg = Counter(), {}
    for r in rows:
        for f in r.get("findings", []):
            if f["severity"] not in ("warn", "error"):
                continue
            key = (f["module"], _pattern(f["message"]))
            c[key] += 1
            eg.setdefault(key, (r["file"], f["message"]))
    return [{"count": n, "module": k[0], "example": eg[k][1], "file": eg[k][0]} for k, n in c.most_common(limit)]


def render_report(doc):
    S = doc["summary"]
    w, wo = S["with"], S["without"]
    n = w["prompts"]
    L = [f"# SkillBlend eval: {doc['run']}", "", f"**{doc['headline']}**", "", small_n_note(n), ""]
    sk = doc["skill"]
    kind = "measured from the artist's files" if sk.get("personal") else "the generic skill"
    L += [f"- Skill: `{sk['name']}`" + (f" ({kind}, built {sk['built']})" if sk.get("built") else "") + f", from `{sk['dir']}`",
          "- Scored with the skill's own `scripts/style_check.py`: a warning is something the skill would tell an AI to fix before calling the model done; a note is something to explain.",
          f"- {doc['blender'] or 'Blender (version not read)'}; SkillBlend {doc['skillblend']}; {doc['date']}"]
    if doc["mode"] == "score":
        L += [f"- Models: `{doc['dirs']['with']}` (with the skill) and `{doc['dirs']['without']}` (without). "
              "SkillBlend did not build these models; it only scored them. How comparable the two folders are is up to how they were made."]
    else:
        r = doc["runner"]
        L += [f"- Built by: {r['label']}" + (f" ({r['version']})" if r.get("version") else ""),
              f"  - with the skill: `{r['with']}`", f"  - without: `{r['without']}`",
              "  - Each prompt ran in its own empty folder. The \"with\" folders had the skill installed in them "
              "(`.claude/skills` and `.agents/skills`); the \"without\" folders did not."
              + (" The \"with\" arm was told to use the skill by name." if doc.get("name_skill") else
                 " Both arms got exactly the same prompt, so whether the skill was picked up by itself is part of the result.")]
    for c in doc.get("caveats", []):
        L += ["", f"> **Caveat.** {c}"]
    L += ["", "## Summary", "", "| | With the skill | Without |", "|---|---|---|",
          f"| Models built | {w['built']} of {n} | {wo['built']} of {n} |",
          f"| Warnings per built model | {_num(w['warnings_per_model'])} | {_num(wo['warnings_per_model'])} |",
          f"| Notes per built model | {_num(w['notes_per_model'])} | {_num(wo['notes_per_model'])} |",
          f"| Models with no warnings | {w['no_warnings']} of {n} | {wo['no_warnings']} of {n} |",
          f"| Models with nothing to report (`STYLE ok`) | {w['style_ok']} of {n} | {wo['style_ok']} of {n} |",
          f"| Parts per built model | {_num(w.get('parts_per_model'))} | {_num(wo.get('parts_per_model'))} |",
          f"| Triangles per built model | {_num(w.get('tris_per_model'))} | {_num(wo.get('tris_per_model'))} |",
          f"| Materials given a colour | {w.get('coloured', 0)} of {w.get('materials', 0)} | {wo.get('coloured', 0)} of {wo.get('materials', 0)} |",
          "", "The warnings say how closely a model follows the style. They don't say how much detail it has, whether it "
          "matches the prompt, or how it looks. The last three rows and the pictures below are there for that: read "
          "them together with the score."]
    p = S["paired"]
    if p["both_built"]:
        L += ["", f"Prompt by prompt, on the {p['both_built']} that both arms built: the skill's model had fewer warnings on "
                  f"{p['with_fewer']}, the same number on {p['same']}, and more on {p['without_fewer']}."]
    L += ["", "## By prompt", "", "| Prompt | With: warnings / notes | Without: warnings / notes |", "|---|---|---|"]
    cell = lambda r: f"{r['warnings']} / {r['notes']}" if r["built"] else f"not built ({r['why']})"
    for t, a, b in zip(doc["tasks"], doc["models"]["with"], doc["models"]["without"]):
        L.append(f"| {t['title']} (`{t['file']}`) | {cell(a)} | {cell(b)} |")
    L += ["", "## The models", "", "Every model is drawn the same way: the same angle, the same light, its own material colours.", ""]

    def facts(r):
        if not r["built"]:
            return f"not built ({r['why']})"
        k = r.get("look") or {}
        return (f"{k.get('parts', 0)} parts, {k.get('tris', 0):,} triangles, {k.get('coloured', 0)} of {k.get('materials', 0)} "
                f"materials given a colour; {r['warnings']} warning{'' if r['warnings'] == 1 else 's'}, "
                f"{r['notes']} note{'' if r['notes'] == 1 else 's'}")
    pic = lambda r, alt: f"![{alt}]({r['picture']})" if r.get("picture") else "(no picture)"
    for t, a, b in zip(doc["tasks"], doc["models"]["with"], doc["models"]["without"]):
        L += [f"### {t['title']}", "", "| Without the skill | With the skill |", "|---|---|",
              f"| {pic(b, t['title'] + ', without the skill')} | {pic(a, t['title'] + ', with the skill')} |",
              f"| {facts(b)} | {facts(a)} |", ""]
    mods = sorted(m for m in set(w["modules"]) | set(wo["modules"])
                  if w["modules"].get(m, {}).get("warnings") or wo["modules"].get(m, {}).get("warnings"))
    if mods:
        L += ["", "## By check", "", "Warnings per built model, for each of the skill's checks that raised one.", "",
              "| Check | With the skill | Without |", "|---|---|---|"]
        for m in mods:
            L.append(f"| {m} | {_num(w['modules'].get(m, {}).get('warnings_per_model', 0.0) if w['built'] else None)} | "
                     f"{_num(wo['modules'].get(m, {}).get('warnings_per_model', 0.0) if wo['built'] else None)} |")
    for arm, title in (("without", "Without the skill"), ("with", "With the skill")):
        worst = doc["worst"][arm]
        L += ["", f"## Most common warnings: {title.lower()}", ""]
        L += [f"- {x['count']}x {x['module']}: {x['example']} (`{x['file']}`)" for x in worst] or ["- None."]
    if doc["mode"] == "run":
        L += ["", "## The runs", "", "| Prompt | Arm | Time | Result |", "|---|---|---|---|"]
        for r in doc["runs"]:
            res = "model saved" if r["saved"] else ("no model: " + (r["error"] or f"the runner ended (exit code {r['code']}) without saving {MODEL_NAME}"))
            L.append(f"| {r['task']} | {r['arm']} | {r['seconds']} s | {res} |")
        sg = doc.get("signs") or {}
        if sg:
            L += ["", "What each run left behind was searched for mentions of a skill (a rough check, not proof):",
                  f"- with the skill: its name or scripts appear in {sg['with_used']} of {sg['with_runs']} runs' logs and build files;",
                  "- without: " + ("no mention of any skill was found." if not sg["without_hits"] else
                                   "mentions found in " + "; ".join(f"{k} ({', '.join(v)})" for k, v in sorted(sg["without_hits"].items())) + ".")]
    return "\n".join(L).rstrip() + "\n"


# ------------------------------------------------------------------ runs
def new_run_dir(ws_root, name=None):
    """A new, empty folder for a run. An earlier run is never reused or overwritten: a taken name gets -2, -3, ..."""
    root = os.path.join(ws_root, "eval")
    os.makedirs(root, exist_ok=True)
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", name or "").strip("-.") or time.strftime("%Y%m%d-%H%M%S")
    cand, i = base, 2
    while True:
        try:
            os.makedirs(os.path.join(root, cand))
            return os.path.join(root, cand)
        except FileExistsError:
            cand, i = f"{base}-{i}", i + 1


def list_runs(ws_root):
    root = os.path.join(ws_root, "eval")
    if not os.path.isdir(root):
        return []
    runs = [d for d in os.listdir(root) if os.path.isfile(os.path.join(root, d, "report.json"))]
    return sorted(runs, key=lambda d: os.path.getmtime(os.path.join(root, d, "report.json")))


def skill_info(skill_dir):
    skill_dir = os.path.abspath(skill_dir)
    need = ("SKILL.md", "style.json", os.path.join("scripts", "style_check.py"))
    missing = [f for f in need if not os.path.isfile(os.path.join(skill_dir, f))]
    if missing:
        raise ValueError(f"{skill_dir} isn't a skill SkillBlend built (no {missing[0]}). Give the folder `build` printed.")
    with open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8") as fh:
        meta, _ = parse_skill(fh.read())
    man = read_manifest(skill_dir) or {}
    return {"name": meta.get("name") or os.path.basename(skill_dir), "dir": skill_dir, "personal": man.get("personal"),
            "built": man.get("built"), "skillblend": man.get("skillblend")}


def blender_version(blender):
    try:
        p = subprocess.run([blender, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        return (p.stdout.strip().splitlines() or [""])[0]
    except Exception:
        return ""


def score_dirs(blender, skill, tasks, with_dir, without_dir, run_dir, log=None):
    """Score both folders: one row per task and arm, matched on the task's file name."""
    models = {}
    for arm, d in (("with", with_dir), ("without", without_dir)):
        rows = []
        for t in tasks:
            row = score_model(blender, skill["dir"], os.path.join(d, t["file"]),
                              os.path.join(run_dir, "scores", arm, os.path.splitext(t["file"])[0] + ".json"))
            if row["built"]:
                rel = "pictures/%s/%s.png" % (arm, os.path.splitext(t["file"])[0])
                if picture(blender, os.path.join(d, t["file"]), os.path.join(run_dir, *rel.split("/"))):
                    row["picture"] = rel
            rows.append(row)
            if log:
                log(f"  {arm:<8} {t['file']:<28} " + (f"{row['warnings']} warning(s), {row['notes']} note(s)" if row["built"] else f"not built: {row['why']}"))
        models[arm] = rows
    return models


def finish(run_dir, doc, models):
    """Add the totals to `doc`, and write report.json and report.md."""
    doc["models"] = models
    doc["summary"] = {"with": aggregate(models["with"]), "without": aggregate(models["without"]),
                      "paired": paired(models["with"], models["without"])}
    doc["headline"] = headline(doc["summary"])
    doc["worst"] = {arm: worst_findings(models[arm]) for arm in ARMS}
    with open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(render_report(doc))
    return doc


def tasks_from_dirs(with_dir, without_dir, known=()):
    """Score-only: one task per .blend file name found in either folder (titles and prompts from `known` tasks)."""
    by_file = {t["file"].lower(): t for t in known}
    names = {}
    for d in (with_dir, without_dir):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".blend"):
                names.setdefault(f.lower(), f)
    out = []
    for low, f in sorted(names.items()):
        t = by_file.get(low)
        out.append({"id": t["id"] if t else os.path.splitext(f)[0], "title": t["title"] if t else os.path.splitext(f)[0],
                    "prompt": t["prompt"] if t else "", "file": f})
    return out


def score_only(ws, skill_dir, with_dir, without_dir, name=None, tasks_file=None, log=None):
    blender = ws.blender()
    if not blender:
        raise ValueError("Blender not found. Run: python skillblend.py config --blender PATH")
    skill = skill_info(skill_dir)
    with_dir, without_dir = os.path.abspath(with_dir), os.path.abspath(without_dir)
    for d in (with_dir, without_dir):
        if not os.path.isdir(d):
            raise ValueError(f"Not a folder: {d}")
    tasks = tasks_from_dirs(with_dir, without_dir, load_tasks(tasks_file))
    if not tasks:
        raise ValueError("Neither folder has a .blend file in it.")
    run_dir = new_run_dir(ws.root, name)
    models = score_dirs(blender, skill, tasks, with_dir, without_dir, run_dir, log)
    doc = {"run": os.path.basename(run_dir), "dir": run_dir, "mode": "score", "date": time.strftime("%Y-%m-%d %H:%M"),
           "skillblend": __version__, "blender": blender_version(blender), "skill": skill, "tasks": tasks,
           "dirs": {"with": with_dir, "without": without_dir}, "caveats": []}
    return finish(run_dir, doc, models)


def resolve_runner(agent=None, runner=None, runner_without=None, isolated=False, model=None):
    """The command for each arm, and what is known about hiding home-folder skills from the "without" arm.
    `model` pins both arms of a preset to one model, so the comparison isn't between two models."""
    if runner:
        if model:
            raise ValueError("--model works with the --agent presets. With --runner, put the model in your own command "
                             "(the same one in both arms).")
        return {"preset": None, "label": "your command (--runner)", "with": runner, "without": runner_without or runner,
                "isolation": "confirmed" if isolated else "unknown",
                "isolation_note": "you confirmed with --isolated that your command hides home-folder skills from the without arm"
                if isolated else "SkillBlend can't tell what your command lets the without arm see", "version_cmd": None,
                "home_dirs": None}
    if agent not in PRESETS:
        raise ValueError(f"Choose --agent {' or '.join(PRESETS)}, or give your own command with --runner.")
    p = PRESETS[agent]
    pin = f' {p["model_flag"]} {model}' if model else ""
    return {"preset": agent, "label": p["label"], "with": p["with"] + pin, "without": runner_without or (p["without"] + pin),
            "isolation": "confirmed" if isolated else p["isolation"], "isolation_note": p["isolation_note"],
            "version_cmd": p["version"], "home_dirs": p["home"], "model": model or None}


def isolation_caveat(rn, home):
    """The sentence the report carries when the "without" arm could have seen a skill from the home folder."""
    if rn.get("home_dirs"):  # only the folders this tool reads; your own command could read any of them
        home = {k: v for k, v in home.items() if k in rn["home_dirs"]}
    if rn["isolation"] == "confirmed" or not home:
        return None
    count = sum(len(v) for v in home.values())
    where = "; ".join(f"{len(v)} in {k}" for k, v in home.items())
    folders = f"{count} skill folder{'s exist' if count != 1 else ' exists'}"
    if rn["isolation"] == "flag":
        return (f"The without arm may have seen user-level skills. {folders} in the home folder ({where}). To hide them, "
                f"{rn['isolation_note']}; SkillBlend has not verified that for your version of the tool. If the without arm used one of "
                "them, its score is better than a bare AI's and the difference above is understated.")
    why = (f"and nothing hid them: {rn['isolation_note']}" if rn["isolation"] == "none" else
           f"and {rn['isolation_note']}")
    return (f"The without arm may have seen user-level skills. {folders} in the home folder ({where}), {why}. "
            "If the without arm used one of them, its score is better than a bare AI's and the difference above is "
            "understated. Run the eval on an account or machine without them for a clean comparison, or pass "
            "--isolated once you have checked that your runner hides them.")


def plan_commands(rn, tasks, arms, run_dir, blender, skill):
    """Every command a run would start, for --dry-run and for the record."""
    out = []
    for t in tasks:
        for arm in arms:
            wd = os.path.join(run_dir, t["id"], arm)
            vals = _values(t, arm, wd, blender, skill, "<the prompt>")
            out.append({"task": t["id"], "arm": arm, "argv": render_command(rn[arm], vals)})
    return out


def _values(task, arm, workdir, blender, skill, prompt):
    installed = os.path.join(workdir, ".claude", "skills", skill["name"]) if arm == "with" else ""
    return {"prompt": prompt, "prompt_file": os.path.join(workdir, "PROMPT.md"), "workdir": workdir,
            "out": os.path.join(workdir, MODEL_NAME), "skill_dir": installed, "blender": blender, "arm": arm, "task": task["id"]}


def run_one(task, arm, rn, run_dir, blender, skill, timeout, name_skill=False):
    """Build one prompt in one arm. Returns the run's record; the model, if any, is copied to models/<arm>/."""
    wd = os.path.join(run_dir, task["id"], arm)
    os.makedirs(wd, exist_ok=True)
    if arm == "with":  # the skill, where each tool looks for project skills
        install_skill(skill["dir"], ["claude", "agents"], scope="project", project_dir=wd,
                      backup_root=os.path.join(run_dir, "backups"))
    prompt = full_prompt(task, blender, skill["name"] if (name_skill and arm == "with") else None)
    with open(os.path.join(wd, "PROMPT.md"), "w", encoding="utf-8") as fh:
        fh.write(prompt)
    vals = _values(task, arm, wd, blender, skill, prompt)
    rec = {"task": task["id"], "arm": arm, "workdir": wd, "saved": False, "code": None, "seconds": 0.0, "error": None}
    try:
        argv = render_command(rn[arm], vals)
    except ValueError as exc:
        rec["error"] = str(exc)
        return rec
    env = dict(os.environ, SKILLBLEND_EVAL_ARM=arm, SKILLBLEND_EVAL_TASK=task["id"], SKILLBLEND_EVAL_OUT=vals["out"],
               SKILLBLEND_EVAL_BLENDER=blender)
    res = run_command(argv, wd, prompt, timeout, env)
    with open(os.path.join(wd, "runner.log"), "w", encoding="utf-8") as fh:
        fh.write("$ " + subprocess.list2cmdline(argv[:1] + [a if a != prompt else "<the prompt>" for a in argv[1:]]) + "\n\n" + res["output"])
    rec.update(code=res["code"], seconds=res["seconds"], error=res["error"])
    if os.path.isfile(vals["out"]):
        dst = os.path.join(run_dir, "models", arm, task["file"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(vals["out"], dst)
        rec["saved"] = True
    return rec


def run_eval(ws, skill_dir, rn, tasks, name=None, timeout=1800, jobs=1, name_skill=False, home=None, log=None):
    """Have the runner build every prompt in both arms, then score the models."""
    blender = ws.blender()
    if not blender:
        raise ValueError("Blender not found. Run: python skillblend.py config --blender PATH")
    skill = skill_info(skill_dir)
    run_dir = new_run_dir(ws.root, name)
    pairs = [(t, arm) for t in tasks for arm in ARMS]

    def work(pair):
        t, arm = pair
        rec = run_one(t, arm, rn, run_dir, blender, skill, timeout, name_skill)
        if log:
            log(f"  {t['id']:<18} {arm:<8} " + (f"model saved ({rec['seconds']} s)" if rec["saved"] else
                                               f"no model ({rec['error'] or 'exit code ' + str(rec['code'])})"))
        return rec
    with ThreadPoolExecutor(max_workers=max(1, int(jobs or 1))) as pool:
        runs = list(pool.map(work, pairs))
    for arm in ARMS:
        os.makedirs(os.path.join(run_dir, "models", arm), exist_ok=True)
    models = score_dirs(blender, skill, tasks, os.path.join(run_dir, "models", "with"),
                        os.path.join(run_dir, "models", "without"), run_dir)
    for arm in ARMS:  # a runner that failed says why, in place of "no model file"
        for row, rec in zip(models[arm], [r for r in runs if r["arm"] == arm]):
            if not row["built"] and not rec["saved"]:
                row["why"] = rec["error"] or f"the runner ended without saving {MODEL_NAME}"
    hs = home_skills(home)
    names = sorted({n for v in hs.values() for n in v})
    hits, used = {}, 0
    for rec in runs:
        if rec["arm"] == "without":
            found = skill_signs(rec["workdir"], names)
            if found:
                hits[rec["task"]] = found
        elif skill_signs(rec["workdir"], [skill["name"]], also=("style_check", "import style", skill["name"])):
            used += 1
    version = ""
    if rn.get("version_cmd"):
        try:
            exe = shutil.which(rn["version_cmd"][0]) or rn["version_cmd"][0]
            p = subprocess.run([exe] + rn["version_cmd"][1:], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            version = (p.stdout.strip().splitlines() or [""])[0]
        except Exception:
            version = ""
    caveats = [c for c in [isolation_caveat(rn, hs)] if c]
    if rn.get("preset") and not rn.get("model"):
        caveats.append("No model was pinned (--model). The two arms can end up on different models, because they load "
                       "different settings, and then the difference above is partly the models'. Check `runner.log` in "
                       "each run folder, or run again with --model.")
    if hits:
        caveats.append("What the without arm left behind mentions a skill in " + ", ".join(sorted(hits)) + ". Look at those runs' "
                       "`runner.log` before trusting their scores.")
    doc = {"run": os.path.basename(run_dir), "dir": run_dir, "mode": "run", "date": time.strftime("%Y-%m-%d %H:%M"),
           "skillblend": __version__, "blender": blender_version(blender), "skill": skill, "tasks": tasks,
           "runner": {"preset": rn["preset"], "label": rn["label"], "with": rn["with"], "without": rn["without"],
                      "isolation": rn["isolation"], "version": version, "model": rn.get("model")},
           "timeout": timeout, "name_skill": bool(name_skill), "runs": runs, "caveats": caveats,
           "signs": {"with_used": used, "with_runs": sum(1 for r in runs if r["arm"] == "with"), "without_hits": hits},
           "home_skills": {k: len(v) for k, v in hs.items()}}
    return finish(run_dir, doc, models)


# ------------------------------------------------------------------ command line
def add_parser(sp, handler):
    s = sp.add_parser("eval", help="does the skill change what an AI builds? the same prompts with and without it, scored against the style",
                      description="Measure a skill: build the same prompts with and without it, and score every model with the skill's own style check.")
    ev = s.add_subparsers(dest="eval_cmd", required=True)
    t = ev.add_parser("tasks", help="list the prompts")
    t.add_argument("--tasks", help="your own tasks file (JSON) instead of the built-in prompts")
    t.add_argument("--json", action="store_true")
    r = ev.add_parser("run", help="have an AI build every prompt with and without the skill, then score the models (spends your AI usage)",
                      description="Starts one AI run per prompt and arm, each in its own folder under <workspace>/eval/<run>/. "
                                  "A real run spends your AI usage. The --agent presets are best-effort command lines written from each "
                                  "tool's --help and not run by SkillBlend's tests: check the flags for your version (--dry-run prints "
                                  "them), or give your own with --runner. The Claude Code preset lets the agent run shell commands in "
                                  "the run folder without asking. In a --runner command, words are split on spaces, quotes keep spaces "
                                  "in one word, and these are filled in: {prompt} {prompt_file} {workdir} {out} {skill_dir} {blender} "
                                  "{arm} {task}. The prompt is also piped to the command's standard input. {skill_dir} is the copy "
                                  "installed in the run folder, and empty in the without arm.")
    r.add_argument("--skill", required=True, help="the built skill folder (what `build` printed)")
    r.add_argument("--agent", choices=sorted(PRESETS), help="a preset runner: " + ", ".join(f"{k} = {v['label']}" for k, v in sorted(PRESETS.items())))
    r.add_argument("--runner", help="your own command to build one prompt (see the placeholders above)")
    r.add_argument("--runner-without", help="a different command for the without arm (default: the same as --runner)")
    r.add_argument("--isolated", action="store_true",
                   help="you have checked that the runner hides the skills in your home folder from the without arm (drops that caveat from the report)")
    r.add_argument("--model", help="with --agent: the model both arms must use (recommended: without it the two arms can run on different models)")
    r.add_argument("--tasks", help="your own tasks file (JSON)")
    r.add_argument("--only", help="comma-separated task ids")
    r.add_argument("--timeout", type=int, default=1800, help="seconds allowed per prompt and arm (default 1800)")
    r.add_argument("--jobs", type=int, default=1, help="runs at the same time (default 1)")
    r.add_argument("--name", help="a name for the run's folder (default: date and time)")
    r.add_argument("--name-skill", action="store_true", help="tell the with arm to use the skill by name (default: both arms get the same prompt)")
    r.add_argument("--dry-run", action="store_true", help="print the commands and stop")
    r.add_argument("--yes", action="store_true", help="start an --agent preset (without it, the commands are printed and nothing runs)")
    r.add_argument("--json", action="store_true")
    c = ev.add_parser("score", help="score models you already have: a folder made with the skill and one made without",
                      description="Scores the .blend files in two folders against the skill, matching them by file name. "
                                  "Nothing is built and no AI is started: use it on models from any assistant, a chat model, or made by hand.")
    c.add_argument("with_dir", help="folder of .blend files made with the skill")
    c.add_argument("without_dir", help="folder of .blend files made without it (same file names)")
    c.add_argument("--skill", required=True, help="the built skill folder to score against")
    c.add_argument("--tasks", help="your own tasks file, for the prompts' titles in the report")
    c.add_argument("--name", help="a name for the run's folder (default: date and time)")
    c.add_argument("--json", action="store_true")
    p = ev.add_parser("report", help="show a finished run's report (the latest by default)")
    p.add_argument("run", nargs="?", help="the run's folder name")
    p.add_argument("--list", action="store_true", help="list the runs")
    p.add_argument("--json", action="store_true")
    for x in (t, r, c, p):
        x.set_defaults(f=handler)
    return s


def _say_result(doc, as_json):
    if as_json:
        print(json.dumps(doc, indent=1))
        return
    print()
    print(doc["headline"])
    print(small_n_note(doc["summary"]["with"]["prompts"]))
    for c in doc.get("caveats", []):
        print("Caveat: " + c)
    print(f"\nReport: {os.path.join(doc['dir'], 'report.md')}")


def main(ws, a):
    log = None if getattr(a, "json", False) else print
    try:
        if a.eval_cmd == "tasks":
            tasks = load_tasks(a.tasks)
            if a.json:
                print(json.dumps(tasks, indent=1))
            else:
                for t in tasks:
                    print(f"{t['id']:<16} {t['title']}\n    {t['prompt']}")
            return 0
        if a.eval_cmd == "score":
            if log:
                log("Scoring (Blender, headless)...")
            _say_result(score_only(ws, a.skill, a.with_dir, a.without_dir, a.name, a.tasks, log), a.json)
            return 0
        if a.eval_cmd == "report":
            runs = list_runs(ws.root)
            if a.list:
                print("\n".join(runs) or "No runs yet.")
                return 0
            name = a.run or (runs[-1] if runs else None)
            if not name or name not in runs:
                print("No such run." if a.run else "No runs yet. Start with: python skillblend.py eval score WITH_DIR WITHOUT_DIR --skill DIR")
                return 1
            with open(os.path.join(ws.root, "eval", name, "report.json" if a.json else "report.md"), encoding="utf-8") as fh:
                sys.stdout.write(fh.read())
            return 0
        # run
        if not a.runner and not a.agent:
            raise ValueError("Say how to build the models: --agent claude | codex, or your own command with --runner.")
        rn = resolve_runner(a.agent, a.runner, a.runner_without, a.isolated, a.model)
        tasks = load_tasks(a.tasks, a.only)
        skill = skill_info(a.skill)
        blender = ws.blender()
        if not blender:
            raise ValueError("Blender not found. Run: python skillblend.py config --blender PATH")
        if a.dry_run or (rn["preset"] and not a.yes):
            plan = plan_commands(rn, tasks, ARMS, os.path.join(ws.root, "eval", "<run>"), blender, skill)
            if a.json:
                print(json.dumps({"dry_run": True, "runs": len(plan), "commands": plan}, indent=1))
            else:
                print(f"{len(plan)} runs ({len(tasks)} prompt{'' if len(tasks) == 1 else 's'} x 2 arms), each given up to "
                      f"{a.timeout} s. Nothing was started.\n")
                for c in plan:
                    print(f"[{c['task']} / {c['arm']}]  " + subprocess.list2cmdline(c["argv"]))
                cav = isolation_caveat(rn, home_skills())
                if cav:
                    print("\nCaveat: " + cav)
                if rn["preset"] and not a.dry_run:
                    print(f"\nThese are best-effort commands for {rn['label']}: check the flags against your version. "
                          "A real run spends your AI usage. Add --yes to start it.")
            return 0
        if log:
            log(f"Building {len(tasks)} prompt(s) x 2 arms with {rn['label']}...")
        _say_result(run_eval(ws, a.skill, rn, tasks, a.name, a.timeout, a.jobs, a.name_skill, log=log), a.json)
        return 0
    except ValueError as exc:
        print(str(exc))
        return 1
