"""Install a built skill for any AI assistant, not only Claude Code.

Claude Code reads skill folders (SKILL.md). Other assistants read instruction files in a project:

    codex / agents   AGENTS.md                         (OpenAI Codex, Jules, Amp, OpenCode, Zed, Cursor, ...)
    cursor           .cursor/rules/<skill>.mdc         (Cursor project rule, picked by description)
    gemini           GEMINI.md                         (Gemini CLI)
    copilot          .github/copilot-instructions.md   (GitHub Copilot)
    windsurf         .windsurf/rules/<skill>.md        (Windsurf)
    prompt           system-prompt.md                  (any chat model: ChatGPT, local models in Ollama / LM Studio ...)

For project targets the skill's files (scripts, references, style.json) are copied to `<project>/.skillblend/<skill>/`
and the instruction file points there. Shared files (AGENTS.md, GEMINI.md, Copilot) get a marked block that is
replaced on reinstall, so the rest of the file is never touched.
"""
import json
import os
import re
import shutil

TARGETS = {
    "claude": "Claude Code (skill folder in ~/.claude/skills)",
    "codex": "OpenAI Codex and other AGENTS.md tools (AGENTS.md)",
    "cursor": "Cursor (.cursor/rules)",
    "gemini": "Gemini CLI (GEMINI.md)",
    "copilot": "GitHub Copilot (.github/copilot-instructions.md)",
    "windsurf": "Windsurf (.windsurf/rules)",
    "prompt": "Any chat model, including local ones (system-prompt.md)",
}
PROJECT_TARGETS = ("codex", "cursor", "gemini", "copilot", "windsurf")


def _read_skill(skill_dir):
    with open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    meta, body = {}, text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = text[m.end():]
    return meta, body.strip()


def portable_text(skill_dir, rel_root):
    """The skill as plain instructions for a project file; paths are relative to rel_root."""
    meta, body = _read_skill(skill_dir)
    name = meta.get("name", os.path.basename(skill_dir.rstrip("\\/")))
    head = (f"# {name} (Blender modelling style)\n\n"
            f"{meta.get('description', '')}\n\n"
            f"Use these instructions whenever you model, edit, check or export 3D models in Blender for this project. "
            f"The style's files are in `{rel_root}/`; every path below (`scripts/...`, `references/...`, `style.json`) "
            f"is relative to that folder. Run Blender scripts headless with `blender -b --factory-startup --python <script> -- <args>`.\n")
    body = re.sub(r"^# .*\n", "", body, count=1)
    body = body.replace("<this skill>", rel_root)
    return head + "\n" + body.strip() + "\n"


def system_prompt(skill_dir, max_chars=20000):
    """A compact, self-contained prompt for any chat model (fits small local models too): the overview, how to work,
    the key numbers, then each part's measured rules (or a few standard rules where nothing was measured)."""
    meta, body = _read_skill(skill_dir)
    with open(os.path.join(skill_dir, "style.json"), encoding="utf-8") as fh:
        style = json.load(fh)
    name = meta.get("name", "")
    secs = {}
    order = []
    for sec in re.split(r"\n(?=## )", "\n" + body):
        sec = sec.strip()
        if not sec.startswith("## "):
            continue
        title = sec.splitlines()[0][3:].strip()
        secs[title] = sec
        order.append(title)
    out = [f"You are a 3D modelling assistant working in Blender. Model the way the artist behind the `{name}` style does: "
           "follow the rules below, measured from the artist's own .blend files. Use real-world metres, keep modifiers live "
           "unless asked otherwise, and use the numbers in the style card. If you can't run code, give the steps in "
           "Blender's interface with the same settings."]
    for t in order:
        if t.startswith("How this project is built"):
            out.append(secs[t].replace("Read this first. It's the short version of everything measured below, in the order the work happens.\n\n", ""))
    nums = []
    for k, v in sorted(style.get("numbers", {}).items()):
        if k == "modifier_defaults":
            continue
        if k == "material_recipes" and isinstance(v, dict):
            v = "; ".join(f"{n}: " + ", ".join(f"{kk} {vv}" for kk, vv in r.items() if kk in ("base_color", "metallic", "roughness"))
                          for n, r in list(v.items())[:10])
        elif isinstance(v, dict):
            v = json.dumps(v, separators=(",", ":"))
        elif isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        nums.append(f"- {k}: {v}")
    out.append("## Style card\n" + "\n".join(nums))
    for t in order:
        if not re.search(r"\((measured|generic)", t):
            continue
        lines = secs[t].splitlines()[1:]
        bullets = []
        for ln in lines:
            if ln.strip().startswith("Method:") or ln.startswith("More:"):
                break
            if ln.startswith("- "):
                bullets.append(ln)
        if "(generic" in t:
            bullets = bullets[:3]
        else:
            bullets = bullets[:8]
        if bullets:
            out.append(f"## {t}\n" + "\n".join(bullets))
    text = "\n\n".join(out) + "\n"
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n\n(Trimmed to fit a chat model's prompt.)\n"
    return text


def merge_block(path, name, content):
    """Insert or replace a SkillBlend block in a shared instruction file, leaving everything else alone."""
    start, end = f"<!-- skillblend:{name}:start -->", f"<!-- skillblend:{name}:end -->"
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


def copy_portable(skill_dir, project_dir, name):
    dst = os.path.join(project_dir, ".skillblend", name)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(skill_dir, dst, ignore=shutil.ignore_patterns("__pycache__", "exports"))
    return dst


def install_targets(skill_dir, tools, project_dir=None):
    """Install for each tool in `tools`. Returns {tool: path written}."""
    skill_dir = os.path.abspath(skill_dir)
    meta, _ = _read_skill(skill_dir)
    name = meta.get("name") or os.path.basename(skill_dir.rstrip("\\/"))
    done = {}
    project_tools = [t for t in tools if t in PROJECT_TARGETS]
    if project_tools:
        if not project_dir:
            raise ValueError("Give the project folder the AI works in (--project-dir).")
        project_dir = os.path.abspath(project_dir)
        copy_portable(skill_dir, project_dir, name)
        rel = f".skillblend/{name}"
        text = portable_text(skill_dir, rel)
        desc = meta.get("description", "")
        for t in project_tools:
            if t == "codex":
                done[t] = merge_block(os.path.join(project_dir, "AGENTS.md"), name, text)
            elif t == "gemini":
                done[t] = merge_block(os.path.join(project_dir, "GEMINI.md"), name, text)
            elif t == "copilot":
                done[t] = merge_block(os.path.join(project_dir, ".github", "copilot-instructions.md"), name, text)
            elif t == "cursor":
                p = os.path.join(project_dir, ".cursor", "rules", f"{name}.mdc")
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(f"---\ndescription: {desc}\nglobs:\nalwaysApply: false\n---\n\n{text}")
                done[t] = p
            elif t == "windsurf":
                p = os.path.join(project_dir, ".windsurf", "rules", f"{name}.md")
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(f"---\ntrigger: model_decision\ndescription: {desc}\n---\n\n{text}")
                done[t] = p
    if "prompt" in tools:
        out_dir = project_dir or os.path.join(skill_dir, "exports")
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, "system-prompt.md" if not project_dir else f"{name}.system-prompt.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(system_prompt(skill_dir))
        done["prompt"] = p
    return done


def write_exports(skill_dir):
    """Every format, ready to copy, in <skill>/exports/ (written with each build)."""
    meta, _ = _read_skill(skill_dir)
    name = meta.get("name") or os.path.basename(skill_dir.rstrip("\\/"))
    ex = os.path.join(skill_dir, "exports")
    os.makedirs(ex, exist_ok=True)
    rel = f".skillblend/{name}"
    text = portable_text(skill_dir, rel)
    files = {
        "AGENTS.md": text,
        "GEMINI.md": text,
        "copilot-instructions.md": text,
        f"{name}.mdc": f"---\ndescription: {meta.get('description', '')}\nglobs:\nalwaysApply: false\n---\n\n{text}",
        "system-prompt.md": system_prompt(skill_dir),
        "README.md": ("# Using this skill with other AI tools\n\n"
                      f"Copy the whole `{name}` folder into your project as `{rel}/` (or run "
                      f"`python skillblend.py install <this folder> --for codex,cursor,gemini,copilot,windsurf --project-dir <project>`), then:\n\n"
                      "| Tool | File | Put it at |\n|---|---|---|\n"
                      "| OpenAI Codex, Jules, Amp, OpenCode, Zed and other AGENTS.md tools | `AGENTS.md` | project root (append if one exists) |\n"
                      f"| Cursor | `{name}.mdc` | `.cursor/rules/` |\n"
                      "| Gemini CLI | `GEMINI.md` | project root |\n"
                      "| GitHub Copilot | `copilot-instructions.md` | `.github/` |\n"
                      "| Any chat model (ChatGPT, Ollama, LM Studio, Open WebUI...) | `system-prompt.md` | paste as the system prompt or custom instructions |\n"),
    }
    for fn, content in files.items():
        with open(os.path.join(ex, fn), "w", encoding="utf-8") as fh:
            fh.write(content)
    return ex
