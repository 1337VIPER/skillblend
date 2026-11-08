"""Assemble a Claude Code skill from the modules, the artist's measurements and answers."""
import json
import os
import re
import shutil
import time

from . import __version__, modules as modlib, paths, profile


class NothingSubmitted(Exception):
    pass


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60] or "blender-modelling"


REF_FOR = {"modifier_defaults": "references/modifier-dictionary.md", "material_recipes": "references/shader-recipes.md"}


def _fmt_val(v, key=None):
    if isinstance(v, dict):
        return f"{len(v)} entries ({', '.join(list(v)[:5])}{'...' if len(v) > 5 else ''})" + (f", see {REF_FOR[key]}" if key in REF_FOR else "")
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, list):
        return " > ".join(str(x) for x in v) if all(isinstance(x, str) for x in v) else json.dumps(v)
    return str(v)


def build(ws, name=None, author=None, generic=False, exclude=(), include_examples=True,
          max_example_mb=200, out_dir=None):
    mods = [m for m in modlib.load_modules() if m["id"] not in set(exclude)]
    analyses = profile.load_analyses(ws.root)
    analyses = {k: v for k, v in analyses.items() if any(m["id"] == k for m in mods)}
    answers = ws.answers
    personal = bool(analyses) and not generic
    if not analyses and not generic:
        raise NothingSubmitted(
            "No models have been submitted yet. Submit models for at least one module, "
            "or build the generic skill with --generic.")
    author = author or ws.config.get("author")
    if not name:
        name = (f"{author} modelling style" if author else "my blender modelling style") if personal \
            else "blender modelling"
    sname = slug(name)
    out = os.path.abspath(out_dir or os.path.join(ws.root, "build", sname))
    if os.path.isdir(out):
        shutil.rmtree(out)
    for sub in ("scripts/checks", "references"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    results = {}
    if personal:
        for m in mods:
            results[m["id"]] = profile.run_module(m, analyses, answers)
    else:
        # answers still count in a generic build (e.g. texture size, export format)
        for m in mods:
            r = profile.run_module(m, {}, answers)
            if r.numbers or r.rules:
                results[m["id"]] = r
    style, source = profile.merged_numbers(mods, results)

    # ---- style.json
    with open(os.path.join(out, "style.json"), "w", encoding="utf-8") as fh:
        json.dump({"skill": sname, "built": time.strftime("%Y-%m-%d"), "personal": personal,
                   "numbers": style, "source": source}, fh, indent=2)

    # ---- scripts
    for f in ("style.py", "style_check.py"):
        shutil.copy2(os.path.join(paths.TEMPLATES, f), os.path.join(out, "scripts", f))
    shutil.copy2(os.path.join(paths.BLENDER, "analyse_blend.py"), os.path.join(out, "scripts", "analyse_blend.py"))
    shutil.copy2(os.path.join(paths.LIB, "doclib.py"), os.path.join(out, "scripts", "doclib.py"))
    module_scripts = {}
    for m in mods:
        chk = os.path.join(m["dir"], "check.py")
        if os.path.isfile(chk):
            shutil.copy2(chk, os.path.join(out, "scripts", "checks", m["id"] + ".py"))
        sdir = os.path.join(m["dir"], "scripts")
        if os.path.isdir(sdir):
            for f in sorted(os.listdir(sdir)):
                if f.endswith((".py", ".md", ".json")) and not f.startswith("_"):
                    shutil.copy2(os.path.join(sdir, f), os.path.join(out, "scripts", f))
                    module_scripts.setdefault(m["id"], []).append(f)

    # ---- examples and kit
    copied = {}
    if personal:
        budget = max_example_mb * 1024 * 1024
        for m in mods:
            bundle = m.get("bundle")  # e.g. {"answer": "kit_redistribute", "to": "kit"}
            allowed = answers.get(m["id"], {}).get(bundle["answer"]) if bundle else True
            if allowed is not True:
                continue  # never ship files the artist hasn't cleared
            special = set((results.get(m["id"]).extra.get("bundle_files", []) if results.get(m["id"]) else []))
            items = []  # (source path, key, display name)
            for d in analyses.get(m["id"], []):
                sub = d.get("_submission", {})
                src = sub.get("source") or (os.path.join(ws.root, "submissions", m["id"], sub["stored_as"])
                                            if sub.get("stored_as") else None)
                if src and os.path.isfile(src):
                    items.append((src, sub.get("sha") or sub.get("stored_as"), sub.get("file") or os.path.basename(src)))
            items += [(p, None, os.path.basename(p)) for p in ws.submissions(m["id"]) if not p.lower().endswith(".blend")]
            for src, key, disp in items:
                is_bundle = bool(bundle) and key in special
                if not include_examples and not is_bundle:
                    continue  # --no-examples still ships cleared kit files
                size = os.path.getsize(src)
                if size > budget:
                    continue
                rel = bundle["to"] if is_bundle else "examples/" + m["id"]
                os.makedirs(os.path.join(out, rel), exist_ok=True)
                shutil.copy2(src, os.path.join(out, rel, disp))
                budget -= size
                copied.setdefault(m["id"], []).append(f"{rel}/{disp}")

    bs = results.get("build-scripts")
    if personal and include_examples and bs:
        kits = bs.numbers.get("helper_kits") or []
        for src in bs.extra.get("kit_files", []):
            dst = os.path.join(out, "examples", "build-scripts", "kit")
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(src, os.path.join(dst, os.path.basename(src)))
            copied.setdefault("build-scripts", []).append(f"examples/build-scripts/kit/{os.path.basename(src)}")
        for d in bs.extra.get("lib_paths", []):
            for k in kits:
                src = os.path.join(d, k + ".py")
                if os.path.isfile(src) and not os.path.isfile(os.path.join(out, "examples", "build-scripts", "kit", k + ".py")):
                    dst = os.path.join(out, "examples", "build-scripts", "kit")
                    os.makedirs(dst, exist_ok=True)
                    shutil.copy2(src, os.path.join(dst, k + ".py"))
                    copied.setdefault("build-scripts", []).append(f"examples/build-scripts/kit/{k}.py")

    # ---- references
    for m in mods:
        summary, detail = modlib.generic_text(m)
        r = results.get(m["id"])
        lines = [f"# {m['title']}", ""]
        if r and r.rules:
            lines += ["## Measured from the artist's files" if personal and analyses.get(m["id"]) else "## From the interview", ""]
            lines += [f"- {x}" for x in r.rules] + [""]
        if personal and analyses.get(m["id"]):
            lines += ["Files: " + ", ".join(f"`{d['_submission']['file']}`" + (f" ({d['_submission']['note']})" if d['_submission'].get('note') else "")
                                            for d in analyses[m["id"]]), ""]
        if summary or detail:
            lines += ["## Method", "", _strip_h2(summary), "", detail, ""]
        with open(os.path.join(out, "references", m["id"] + ".md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines).rstrip() + "\n")
    kit = results.get("kit-library")
    if kit and kit.extra.get("kit_catalogue"):
        rows = ["# Kit catalogue", "", "| Piece | Category | Size (mm) | Tris | Modifiers |", "|---|---|---|---|---|"]
        for p in kit.extra["kit_catalogue"]:
            rows.append(f"| `{p['name']}` | {p['category']} | {' x '.join(str(x) for x in p['dims_mm'])} | "
                        f"{p.get('tris') or ''} | {' > '.join(p['modifiers'])} |")
        with open(os.path.join(out, "references", "kit-catalogue.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(rows) + "\n")

    for r_ in results.values():
        for fname, text in (r_.extra.get("reference_md") or {}).items():
            with open(os.path.join(out, "references", os.path.basename(fname)), "w", encoding="utf-8") as fh:
                fh.write(text)

    # ---- SKILL.md
    covered = [m for m in mods if personal and analyses.get(m["id"])]
    text = render_skill(sname, name, author, personal, mods, results, analyses, style, source,
                        covered, copied, module_scripts)
    with open(os.path.join(out, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(out, "SOURCE.md"), "w", encoding="utf-8") as fh:
        fh.write(render_source(sname, personal, mods, analyses, results, answers))
    warnings = {k: r.warnings for k, r in results.items() if r.warnings}
    return {"dir": out, "name": sname, "personal": personal, "covered": [m["id"] for m in covered],
            "generic": [m["id"] for m in mods if m not in covered], "warnings": warnings}


def _unique_blends(analyses):
    return len({id(d) for docs in analyses.values() for d in docs if "_script" not in d})


def _title(name):
    words = name.replace("-", " ").replace("_", " ").split()
    return " ".join(w[:1].upper() + w[1:] for w in words) if name == name.lower() else name


def _strip_h2(s):
    return re.sub(r"^##\s+.*\n?", "", s.strip(), count=1).strip()


def render_skill(sname, name, author, personal, mods, results, analyses, style, source, covered, copied, module_scripts):
    who = author or "the artist"
    titles = ", ".join(m["title"].lower() for m in (covered or mods))
    if personal:
        desc = (f"Model in Blender the way {who} does, with rules measured from {who}'s own .blend files "
                f"({titles}). Use it whenever the user asks to model, remodel, block out, bevel, unwrap, "
                f"optimise or export a 3D model, prop, kit piece or vehicle in Blender (headless scripts or a live "
                f"session), or to check a model against {who}'s style.")
    else:
        desc = ("A complete hard-surface and game-asset modelling workflow for Blender: real-scale setup, "
                "blockout to detail, bevels and shading, SubD topology, booleans, modifier stacks, kit inserts, "
                "UVs and texel density, game-ready export and vehicles. Use it whenever the user asks to model, "
                "remodel, block out, bevel, unwrap, optimise or export a 3D model, prop, kit piece or vehicle "
                "in Blender, or to review one.")
    L = ["---", f"name: {sname}", f"description: {desc}", "---", "", f"# {_title(name)}", ""]
    if personal:
        L += [f"This skill models like {who}. It was built by SkillBlend on {time.strftime('%Y-%m-%d')} "
              f"from {_unique_blends(analyses)} .blend file(s)"
              + (f" and {len(analyses.get('build-scripts', []))} build script(s)" if analyses.get("build-scripts") else "") + ". Sections marked "
              "**measured** come from those files and from the interview; sections marked **generic** had no "
              "submission and use SkillBlend's built-in workflow. Where the two disagree, the measured rules win.", ""]
    else:
        L += ["This is the generic skill from SkillBlend: a complete, tested modelling workflow. "
              "It wasn't personalised, because no models were submitted. Rebuild it with SkillBlend after "
              "submitting models to make it model like you.", ""]
    heads = [(m, h) for m in mods for r_ in [results.get(m["id"])] if r_ and personal and analyses.get(m["id"])
             for h in r_.headlines]
    if heads:
        L += ["## How this project is built", "",
              "Read this first. It's the short version of everything measured below, in the order the work happens.", ""]
        L += [f"{i}. {h}" for i, (m, h) in enumerate(heads, 1)] + [""]
    bs = results.get("build-scripts")
    kits = (bs.numbers.get("helper_kits") if bs else None) or []
    L += ["## How to work", "",
          "- Build models as Python scripts run in headless Blender: `blender -b --factory-startup --python build_model.py -- OUT.blend`. A fix is an edit and a re-run, never a hand edit to a generated file.",
          *([f"- Write build scripts the way the artist does: import their helper kit ({', '.join('`' + k + '`' for k in kits[:4])}) and use its calls "
             f"(see Build scripts below) rather than raw bpy." + (" Copies of the kit and example scripts are in `examples/build-scripts/`." if copied.get("build-scripts") else "")]
            if kits else []),
          "- Load the style at the top of every build script: `sys.path.insert(0, r\"<this skill>/scripts\")`, then `import style`. "
          "`style.setup_scene()`, `style.name()`, `style.box()`, `style.bevel()`, `style.finish()`, `style.subd()`, "
          "`style.cutter()`, `style.order_stack()`, `style.modifier()` (any modifier type, with the artist's typical settings), "
          "`style.material()` (rebuilds the artist's measured material recipes), `style.setup_render()`, `style.kit_piece()` "
          "and `style.texel_density()` all use the numbers in `style.json`.",
          "- Before calling a model done, run `blender -b --factory-startup MODEL.blend --python <this skill>/scripts/style_check.py` "
          "and fix every warning, or tell the user why it's intended. It must end with `STYLE ok` or only notes you can explain.",
          "- Render review shots (front, side, top, 3/4 and close-ups of the busiest areas) and compare them with the reference before adding detail.",
          "- Read the module's file in `references/` before working on that technique; this page is the summary."]
    if copied:
        L += ["- Example files from the artist are in " + ", ".join(sorted({os.path.dirname(p) for v in copied.values() for p in v})) +
              ". When unsure how the artist would build something, open the closest example headless and study its "
              "modifier stacks and topology (`scripts/stack_audit.py` prints a file's stacks, if this skill has it)."]
    L += ["", "## Style card", "", "| Setting | Value | From |", "|---|---|---|"]
    for k in sorted(style):
        L.append(f"| `{k}` | {_fmt_val(style[k], k)} | {source.get(k, '')} |")
    L.append("")
    for m in mods:
        r = results.get(m["id"])
        measured = personal and bool(analyses.get(m["id"]))
        tag = "measured" if measured else ("generic + interview" if r and r.rules else "generic")
        summary, detail = modlib.generic_text(m)
        L += [f"## {m['title']} ({tag})", ""]
        if r and r.rules:
            L += [f"- {x}" for x in r.rules] + [""]
            if summary:
                L += ["Method:", ""]
        if summary:
            L += [_strip_h2(summary), ""]
        extras = []
        if os.path.isfile(os.path.join(m["dir"], "generic.md")) or (r and r.rules):
            extras.append(f"[references/{m['id']}.md](references/{m['id']}.md)")
        if m["id"] == "kit-library" and r and r.extra.get("kit_catalogue"):
            extras.append("[references/kit-catalogue.md](references/kit-catalogue.md)")
        for fname in ((r.extra.get("reference_md") or {}) if r else {}):
            extras.append(f"[references/{fname}](references/{fname})")
        for f in module_scripts.get(m["id"], []):
            extras.append(f"`scripts/{f}`")
        if extras:
            L += ["More: " + ", ".join(extras), ""]
    return "\n".join(L).rstrip() + "\n"


def render_source(sname, personal, mods, analyses, results, answers):
    L = [f"# How {sname} was built", "", f"- Built: {time.strftime('%Y-%m-%d %H:%M')} by SkillBlend {__version__}",
         f"- Personal: {'yes' if personal else 'no (generic)'}", "", "| Module | Files | Answers | Warnings |", "|---|---|---|---|"]
    for m in mods:
        files = analyses.get(m["id"], [])
        r = results.get(m["id"])
        L.append(f"| {m['title']} | {', '.join(d['_submission']['file'] for d in files) or '-'} | "
                 f"{len(answers.get(m['id'], {}))} | {'; '.join(r.warnings) if r and r.warnings else ''} |")
    return "\n".join(L) + "\n"
