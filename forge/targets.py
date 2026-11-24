"""Install a built skill for any AI assistant.

A built skill is an Agent Skills folder: SKILL.md plus scripts/, references/ and style.json. Where it goes:

    claude      ~/.claude/skills/<name>/      (or <project>/.claude/skills/<name>/)
    agents      ~/.agents/skills/<name>/      (or <project>/.agents/skills/<name>/)
                one shared folder that OpenAI Codex, Cursor, Gemini CLI, GitHub Copilot and Windsurf all read
    agents-md   a short pointer in <project>/AGENTS.md, for tools that read AGENTS.md but not skills
    prompt      system-prompt.md, a compact prompt for any chat model (ChatGPT, Ollama, LM Studio...)

Installing over an earlier copy never throws hand-made work away (see ``sync_skill``): files you added are kept,
sections you wrote into SKILL.md move to NOTES.md, and anything you edited is saved to a backup folder first.
"""
import hashlib
import json
import os
import re
import shutil
import time

MANIFEST = ".skillblend.json"
NOTES = "NOTES.md"
IGNORE = ("exports", "__pycache__")

TARGETS = {
    "claude": "Claude Code (skills folder)",
    "agents": "Codex, Cursor, Gemini CLI, GitHub Copilot, Windsurf (shared .agents/skills folder)",
    "agents-md": "A short pointer in AGENTS.md, for tools that read AGENTS.md but not skills",
    "prompt": "Any chat model, including local ones (system-prompt.md)",
}
# every one of these tools reads .agents/skills, so one copy serves them all
ALIASES = {"codex": "agents", "cursor": "agents", "gemini": "agents", "copilot": "agents", "windsurf": "agents"}

# "## " headings SkillBlend itself writes into SKILL.md. A section under any other heading was written by hand.
STANDARD_HEADINGS = {"How this project is built", "How to work", "Key numbers", "Style card", "Your additions"}
# module titles of every release so far, for skills installed before the manifest existed (0.1 to 0.4)
LEGACY_HEADINGS = {
    "Bevels and shading", "Blockout to detail", "Blockout to final", "Booleans and cutters", "Build scripts",
    "Characters and rigging", "Game-ready and export", "Geometry Nodes", "Kit library and inserts",
    "Kitbash and insert library", "Lighting, world and render", "Materials", "Materials and slots", "Mesh quality",
    "Modifier stacks", "Parts and assemblies", "Python build scripts", "Scale, units and naming", "Sculpting",
    "Setup, scale and naming", "Shaders and node setups", "Structure and assemblies", "SubD modelling",
    "SubD topology", "UVs and texel density", "UVs and texture detail", "Vehicles"}
OBSOLETE = {"THIRD_PARTY.md"}  # written by early builds, no longer part of a skill
TEXT_EXT = (".md", ".py", ".json", ".txt", ".mdc")


# ------------------------------------------------------------------ front matter
def yaml_scalar(s):
    """A YAML value for one line of front matter: plain when that's safe, double-quoted otherwise."""
    s = " ".join(str(s).split())
    plain = (s and s[0] not in "!&*-?|>'\"%@`#[]{}," and ": " not in s and " #" not in s
             and not s.endswith(":") and s.lower() not in ("true", "false", "null", "yes", "no", "~")
             and not re.fullmatch(r"[-+]?[0-9.]+", s))
    return s if plain else json.dumps(s, ensure_ascii=False)


def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        try:
            return json.loads(v)
        except ValueError:
            return v[1:-1]
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return v


def parse_skill(text):
    """(front matter dict, body) of a SKILL.md."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    meta, body = {}, text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith((" ", "\t", "#")):
                k, v = line.split(":", 1)
                meta[k.strip()] = _unquote(v)
        body = text[m.end():]
    return meta, body.strip()


def _read_skill(skill_dir):
    with open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8") as fh:
        return parse_skill(fh.read())


def headings(text):
    """The '## ' headings of a SKILL.md, without their (measured) / (generic) tags."""
    out = []
    for line in text.splitlines():
        if line.startswith("## "):
            out.append(re.sub(r"\s*\((measured|generic)[^)]*\)\s*$", "", line[3:].strip()))
    return out


# ------------------------------------------------------------------ manifest
def file_sha(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_files(root, ignore=IGNORE):
    """Every file under root as a forward-slash relative path, skipping `ignore` folders."""
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in ignore)
        for f in sorted(files):
            if f.endswith(".pyc"):
                continue
            out.append(os.path.relpath(os.path.join(d, f), root).replace("\\", "/"))
    return out


def read_manifest(skill_dir):
    p = os.path.join(skill_dir, MANIFEST)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_manifest(skill_dir, info=None):
    """Record which files SkillBlend wrote (and their hashes), so a later install can tell them from yours."""
    files = {rel: file_sha(os.path.join(skill_dir, rel)) for rel in list_files(skill_dir) if rel != MANIFEST}
    with open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8") as fh:
        heads = headings(fh.read())
    doc = dict(info or {}, files=files, headings=heads)
    with open(os.path.join(skill_dir, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    return doc


def is_skill_build(path):
    """True for a folder SkillBlend built or installed (so it's safe to rebuild or update in place)."""
    if os.path.isfile(os.path.join(path, MANIFEST)):
        return True
    return all(os.path.isfile(os.path.join(path, f)) for f in ("SKILL.md", "style.json"))


# ------------------------------------------------------------------ safe install
def _hand_sections(text, generated):
    """The '## ' sections of an edited SKILL.md whose headings SkillBlend didn't write."""
    _, body = parse_skill(text)
    body = re.sub(r"<!-- skillblend:additions:start -->.*?<!-- skillblend:additions:end -->\n?", "", body, flags=re.S)
    out = []
    for sec in re.split(r"\n(?=## )", "\n" + body):
        sec = sec.strip()
        if not sec.startswith("## "):
            continue
        head = headings(sec.splitlines()[0])[0]
        if head not in generated:
            out.append((head, sec))
    return out


def _additions_block(kept):
    groups, singles = {}, []
    for rel in kept:
        top = rel.split("/")[0]
        if "/" in rel and top not in ("references", "scripts"):
            groups.setdefault(top, []).append(rel)
        else:
            singles.append(rel)
    singles.sort(key=lambda r: (r != NOTES, r))
    lines = ["<!-- skillblend:additions:start -->", "## Your additions", "",
             "These files were added to this skill by hand. SkillBlend keeps them when the skill is rebuilt. "
             + (f"`{NOTES}` holds the artist's own rules and wins over this page. " if NOTES in kept else "")
             + "Read the ones that fit the task.", ""]
    for rel in singles[:40]:
        lines.append(f"- [{rel}]({rel})" if rel.endswith(".md") else f"- `{rel}`")
    for top, items in sorted(groups.items()):
        lines.append(f"- `{top}/` ({len(items)} file{'s' if len(items) != 1 else ''})")
    return "\n".join(lines + ["<!-- skillblend:additions:end -->"]) + "\n"


def sync_skill(src, dst, backup_root=None):
    """Install the build at `src` into `dst` without losing anything made by hand.

    - A file SkillBlend didn't write (not in the installed manifest, not in the new build) is kept where it is.
    - A SkillBlend file you edited is copied to the backup folder before it's replaced.
    - Sections you added to SKILL.md are moved into NOTES.md, which every built skill tells the AI to read first.
    - Files an earlier build wrote that the new one doesn't are removed.

    Returns a report: path, new, kept, edited, removed, notes, backup."""
    src, dst = os.path.abspath(src), os.path.abspath(dst)
    rep = {"path": dst, "new": True, "kept": [], "edited": [], "removed": [], "notes": [], "backup": None}
    new_files = [f for f in list_files(src) if f != MANIFEST]
    src_manifest = read_manifest(src) or {}
    if os.path.isdir(dst) and os.listdir(dst):
        if not is_skill_build(dst):
            raise ValueError(f"{dst} already exists and isn't a skill SkillBlend made, so it was left alone.")
        rep["new"] = False
        old = read_manifest(dst)
        old_files = (old or {}).get("files", {})
        bdir = os.path.join(backup_root or os.path.join(os.path.expanduser("~"), ".skillblend", "backups"),
                            f"{os.path.basename(dst)}-{time.strftime('%Y%m%d-%H%M%S')}")

        def backup(rel):
            p = os.path.join(bdir, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            shutil.copy2(os.path.join(dst, rel), p)
            rep["backup"] = bdir

        new_set = set(new_files)
        for rel in list_files(dst, ignore=("__pycache__",)):
            if rel == MANIFEST:
                continue
            p = os.path.join(dst, rel)
            sha = file_sha(p)
            if rel in new_set:
                if sha == file_sha(os.path.join(src, rel)):
                    continue  # unchanged by this build
                if old is None:
                    # no record of what was installed: keep a copy of every text file that's about to change
                    if rel.endswith(TEXT_EXT) and os.path.getsize(p) < (2 << 20):
                        backup(rel)
                elif sha != old_files.get(rel):
                    # edited since it was installed, or a file of yours with the name of a new SkillBlend file
                    backup(rel)
                    rep["edited"].append(rel)
            elif rel in old_files or (old is None and rel in OBSOLETE):
                if rel in old_files and sha != old_files[rel]:
                    backup(rel)
                    rep["edited"].append(rel)
                os.remove(p)
                rep["removed"].append(rel)
            else:
                rep["kept"].append(rel)
        # sections written into SKILL.md by hand move to NOTES.md
        old_skill = os.path.join(dst, "SKILL.md")
        if os.path.isfile(old_skill) and (old is None or file_sha(old_skill) != old_files.get("SKILL.md")):
            with open(old_skill, encoding="utf-8") as fh:
                old_text = fh.read()
            with open(os.path.join(src, "SKILL.md"), encoding="utf-8") as fh:
                new_heads = set(headings(fh.read()))
            generated = STANDARD_HEADINGS | new_heads | (set(old["headings"]) if old and old.get("headings") else LEGACY_HEADINGS)
            hand = _hand_sections(old_text, generated)
            if hand:
                notes = os.path.join(dst, NOTES)
                first = not os.path.isfile(notes)
                with open(notes, "a", encoding="utf-8") as fh:
                    if first:
                        fh.write("# Notes\n\nYour own rules for this skill. SkillBlend never changes what you write here, "
                                 "and the skill tells the AI to read this page first.\n")
                    fh.write(f"\n<!-- moved here from SKILL.md by SkillBlend on {time.strftime('%Y-%m-%d')} -->\n\n")
                    fh.write("\n\n".join(sec for _, sec in hand) + "\n")
                rep["notes"] = [h for h, _ in hand]
                if NOTES not in rep["kept"]:
                    rep["kept"].append(NOTES)
    for rel in new_files:
        p = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copy2(os.path.join(src, rel), p)
    for d, dirs, files in os.walk(dst, topdown=False):  # folders emptied by the clean-up
        if d != dst and not dirs and not files and not os.listdir(d):
            os.rmdir(d)
    rep["kept"].sort()
    if rep["kept"]:
        sp = os.path.join(dst, "SKILL.md")
        with open(sp, encoding="utf-8") as fh:
            text = fh.read()
        with open(sp, "w", encoding="utf-8") as fh:
            fh.write(text.rstrip() + "\n\n" + _additions_block(rep["kept"]))
    files = {rel: file_sha(os.path.join(dst, rel)) for rel in new_files}
    with open(os.path.join(dst, "SKILL.md"), encoding="utf-8") as fh:
        heads = [h for h in headings(fh.read())]
    meta = {k: v for k, v in src_manifest.items() if k not in ("files", "headings")}
    with open(os.path.join(dst, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(dict(meta, installed=time.strftime("%Y-%m-%d %H:%M"), files=files, headings=heads), fh, indent=1)
    return rep


def describe(rep):
    """A report from sync_skill as plain lines for the artist."""
    out = []
    if rep.get("kept"):
        k = rep["kept"]
        out.append(f"Kept {len(k)} file{'s' if len(k) != 1 else ''} you added: " + ", ".join(k[:8]) + ("..." if len(k) > 8 else "") + ".")
    if rep.get("notes"):
        out.append(f"Moved your own SKILL.md section{'s' if len(rep['notes']) != 1 else ''} into {NOTES}: " + ", ".join(rep["notes"]) + ".")
    if rep.get("edited"):
        e = rep["edited"]
        out.append(f"You had edited {len(e)} file{'s' if len(e) != 1 else ''} SkillBlend wrote (" + ", ".join(e[:6]) + ("..." if len(e) > 6 else "")
                   + f"); they were replaced. Put changes you want to keep in {NOTES}.")
    if rep.get("backup"):
        out.append(f"The earlier versions are saved in {rep['backup']}.")
    return out


# ------------------------------------------------------------------ AGENTS.md pointer
def _markers(name):
    return f"<!-- skillblend:{name}:start -->", f"<!-- skillblend:{name}:end -->"


def merge_block(path, name, content):
    """Insert or replace a SkillBlend block in a shared instruction file, leaving everything else alone."""
    start, end = _markers(name)
    block = f"{start}\n{content.rstrip()}\n{end}\n"
    old = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            old = fh.read()
    if start in old and end in old:
        new = old[:old.index(start)] + block + old[old.index(end) + len(end):].lstrip("\n")
    else:
        new = (old.rstrip() + "\n\n" if old.strip() else "") + block
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    return path


def remove_block(path, name, only_if=None):
    """Take a SkillBlend block out of a file (only when it contains `only_if`, if given). True when removed."""
    start, end = _markers(name)
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as fh:
        old = fh.read()
    if start not in old or end not in old:
        return False
    a, b = old.index(start), old.index(end) + len(end)
    if only_if and only_if not in old[a:b]:
        return False
    new = (old[:a].rstrip() + "\n\n" + old[b:].lstrip("\n")).strip()
    if new:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new + "\n")
    else:
        os.remove(path)
    return True


def pointer_text(name, description, rel):
    """A few lines for AGENTS.md that send the assistant to the skill folder. Short on purpose: AGENTS.md is
    loaded into every session, the skill only when Blender work comes up."""
    return (f"## Blender modelling style: {name}\n\n"
            f"When you model, edit, check or export 3D models in Blender in this project, first read "
            f"`{rel}/SKILL.md` and follow it. It holds the artist's measured modelling style (naming, bevels, modifier "
            f"stacks, topology, materials, UVs, export), with the full method per technique in `{rel}/references/` and "
            f"helper scripts in `{rel}/scripts/`. Before calling a model done, run "
            f"`blender -b --factory-startup MODEL.blend --python {rel}/scripts/style_check.py` and fix what it reports.\n")


def clean_legacy(project_dir, name, dst):
    """Remove what SkillBlend 0.4 wrote into a project: the whole skill pasted into AGENTS.md, GEMINI.md and the
    Copilot file, the Cursor and Windsurf rules, and the `.skillblend/<name>` copy (moved to `dst`, so files added
    there by hand are kept). Returns the paths it cleaned."""
    done = []
    mark = f".skillblend/{name}"
    for rel in ("AGENTS.md", "GEMINI.md", os.path.join(".github", "copilot-instructions.md")):
        p = os.path.join(project_dir, rel)
        if remove_block(p, name, only_if=mark):
            done.append(p)
    for rel in (os.path.join(".cursor", "rules", f"{name}.mdc"), os.path.join(".windsurf", "rules", f"{name}.md")):
        p = os.path.join(project_dir, rel)
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                ours = mark in fh.read()
            if ours:
                os.remove(p)
                done.append(p)
    old = os.path.join(project_dir, ".skillblend", name)
    if os.path.isdir(old) and is_skill_build(old) and not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(old, dst)
        done.append(old)
        try:
            os.rmdir(os.path.dirname(old))
        except OSError:
            pass
    return done


# ------------------------------------------------------------------ install
def canonical(tools):
    """Tool names as install targets: codex, cursor, gemini, copilot and windsurf all mean 'agents'."""
    out = []
    for t in tools:
        t = ALIASES.get(t, t)
        if t not in out:
            out.append(t)
    return out


def skill_dirs(skill_dir, tools, scope="user", project_dir=None, home=None):
    """{target: folder the skill would be installed into} for the skill-folder targets in `tools`."""
    meta, _ = _read_skill(skill_dir)
    name = meta.get("name") or os.path.basename(os.path.abspath(skill_dir))
    home = home or os.path.expanduser("~")
    tools = canonical(tools)
    out = {}
    if "claude" in tools:
        base = os.path.join(os.path.abspath(project_dir or os.getcwd()), ".claude") if scope == "project" \
            else os.path.join(home, ".claude")
        out["claude"] = os.path.join(base, "skills", name)
    if "agents" in tools or "agents-md" in tools:
        in_project = scope == "project" or bool(project_dir)
        base = os.path.join(os.path.abspath(project_dir or os.getcwd()), ".agents") if in_project \
            else os.path.join(home, ".agents")
        out["agents"] = os.path.join(base, "skills", name)
    return out


def install_skill(skill_dir, tools, scope="user", project_dir=None, backup_root=None, home=None):
    """Install for each target in `tools`. Returns {target: report} (see sync_skill; 'path' is what was written).

    Claude Code gets the skill in the user's skills folder, or the project's with scope="project". The shared
    `.agents/skills` copy goes into the project when a project folder is given, otherwise into the user's home."""
    skill_dir = os.path.abspath(skill_dir)
    tools = canonical(tools)
    bad = [t for t in tools if t not in TARGETS]
    if bad:
        raise ValueError(f"Unknown target(s) {bad}. Choose from: {', '.join(list(TARGETS) + sorted(ALIASES))}.")
    meta, _ = _read_skill(skill_dir)
    name = meta.get("name") or os.path.basename(skill_dir)
    if "agents-md" in tools and not project_dir:
        raise ValueError("Give the project folder whose AGENTS.md should point at the skill (--project-dir).")
    dirs = skill_dirs(skill_dir, tools, scope, project_dir, home)
    done = {}
    if "claude" in dirs:
        done["claude"] = sync_skill(skill_dir, dirs["claude"], backup_root)
    if "agents" in dirs:
        dst = dirs["agents"]
        project = os.path.abspath(project_dir or os.getcwd())
        in_project = scope == "project" or bool(project_dir)
        cleaned = clean_legacy(project, name, dst) if in_project else []
        rep = sync_skill(skill_dir, dst, backup_root)
        rep["cleaned"] = cleaned
        if "agents" in tools:
            done["agents"] = rep
        if "agents-md" in tools:
            rel = os.path.relpath(dst, project).replace("\\", "/")
            p = merge_block(os.path.join(project, "AGENTS.md"), name, pointer_text(name, meta.get("description", ""), rel))
            done["agents-md"] = dict(rep if "agents" not in tools else {}, path=p)
    if "prompt" in tools:
        src = os.path.join(skill_dir, "exports", "system-prompt.md")
        if not os.path.isfile(src):
            raise ValueError("This skill has no exports/system-prompt.md; rebuild it with this version of SkillBlend.")
        if project_dir:
            p = os.path.join(os.path.abspath(project_dir), f"{name}.system-prompt.md")
            shutil.copy2(src, p)
        else:
            p = src
        done["prompt"] = {"path": p}
    return done


def system_prompt(skill_dir):
    """The compact prompt for chat models, written with every build."""
    p = os.path.join(skill_dir, "exports", "system-prompt.md")
    if not os.path.isfile(p):
        raise ValueError("This skill has no exports/system-prompt.md; rebuild it with this version of SkillBlend.")
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def write_exports(skill_dir, prompt_text):
    """<skill>/exports/: the system prompt for chat models, the AGENTS.md pointer, and how to install by hand."""
    meta, _ = _read_skill(skill_dir)
    name = meta.get("name") or os.path.basename(skill_dir.rstrip("\\/"))
    ex = os.path.join(skill_dir, "exports")
    os.makedirs(ex, exist_ok=True)
    rel = f".agents/skills/{name}"
    files = {
        "system-prompt.md": prompt_text,
        "AGENTS.md": pointer_text(name, meta.get("description", ""), rel),
        "README.md": (
            "# Using this skill with other AI tools\n\n"
            f"This folder is an Agent Skill (`SKILL.md` plus `scripts/`, `references/` and `style.json`). "
            f"`python skillblend.py install <this folder> --for codex` (or cursor, gemini, copilot, windsurf) installs it "
            "for you. By hand:\n\n"
            "| Tool | What to do |\n|---|---|\n"
            f"| Claude Code | copy this folder to `~/.claude/skills/{name}/` |\n"
            f"| OpenAI Codex, Cursor, Gemini CLI, GitHub Copilot, Windsurf | copy this folder to `{rel}/` in your "
            f"project, or `~/{rel}/` for every project. They all read skills from `.agents/skills` |\n"
            "| A tool that reads `AGENTS.md` but not skills | copy the folder into the project as above and paste "
            "`exports/AGENTS.md` into the project's `AGENTS.md` |\n"
            "| Any chat model (ChatGPT, Ollama, LM Studio, Open WebUI...) | paste `exports/system-prompt.md` as the "
            "system prompt or custom instructions |\n\n"
            "Leave the `exports` folder out when you copy: the tools don't need it.\n"),
    }
    for fn, content in files.items():
        with open(os.path.join(ex, fn), "w", encoding="utf-8") as fh:
            fh.write(content)
    return ex
