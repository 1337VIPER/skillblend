"""Assemble a skill (an Agent Skills folder: SKILL.md, scripts, references) from the modules, measurements and answers.

SKILL.md is kept short on purpose. An assistant loads the whole file every time the skill triggers, so it holds
only the overview (one line per technique, in the order the work happens), how to work and the key numbers.
Each technique's measured rules and full method live in ``references/<module>.md``, read when that work comes up.
"""
import json
import os
import re
import shutil
import time

from . import __version__, modules as modlib, paths, profile
from .targets import is_skill_build, read_manifest, write_exports, write_manifest, yaml_scalar


class NothingSubmitted(Exception):
    pass


class UnsafeOutput(Exception):
    """The output folder holds something SkillBlend didn't build, so it won't be replaced."""


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60].strip("-") or "blender-modelling"


REF_FOR = {"modifier_defaults": "references/modifier-dictionary.md", "material_recipes": "references/shader-recipes.md"}
MAX_DESCRIPTION = 1000   # the Agent Skills limit is 1024 characters
MAX_KEY_NUMBERS = 36
# the numbers worth having on the first page, in the order the work happens; the full card is references/style-card.md
KEY_NUMBERS = [
    "unit_system", "scale_length", "up_axis", "front_axis", "naming_case", "naming_prefix", "origin", "apply_scale",
    "helper_kits", "parts_per_asset", "min_detail_mm", "round_segments",
    "bevel_tiers_m", "bevel_width_m", "bevel_width_ratio", "bevel_segments", "bevel_limit_method", "bevel_angle_deg",
    "bevel_profile", "bevel_harden_normals", "weighted_normal", "smooth_angle_deg",
    "subd_levels_viewport", "subd_levels_render", "subd_use_creases", "subd_hold_mm",
    "boolean_solver", "cutter_display", "cutter_collection", "cutter_prefix", "stack_order",
    "material_palette", "shader_model", "texturing", "texture_size", "texel_density_px_per_m", "uv_margin_px",
    "high_suffix", "low_suffix", "high_low_tri_ratio", "lod_count", "triangulate_before_export", "export_format",
    "skeleton_naming", "rest_pose", "character_height_m", "max_influences", "sculpt_method", "multires_levels",
    "render_engine", "view_transform", "world_kind"]


def _fmt_val(v, key=None):
    if isinstance(v, dict):
        return f"{len(v)} entries ({', '.join(list(v)[:5])}{'...' if len(v) > 5 else ''})" + (f", see {REF_FOR[key]}" if key in REF_FOR else "")
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, list):
        if all(isinstance(x, str) for x in v):  # an arrow only where the order is the point (stack_order)
            return (" > " if key and key.endswith("_order") else ", ").join(v)
        return json.dumps(v)
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
    author = " ".join((author or ws.config.get("author") or "").split()) or None
    if not name:
        name = (f"{author} modelling style" if author else "my blender modelling style") if personal \
            else "blender modelling"
    sname = slug(name)
    out = os.path.abspath(out_dir or os.path.join(ws.root, "build", sname))
    if os.path.isfile(out):
        raise UnsafeOutput(f"{out} is a file. Give a folder to build the skill into.")
    if os.path.isdir(out) and os.listdir(out):
        # only ever replace a folder an earlier build made: never somebody's documents, never an installed skill
        if not is_skill_build(out):
            raise UnsafeOutput(f"{out} already has files in it that SkillBlend didn't build, so it was left alone. "
                               "Give an empty or new folder.")
        if (read_manifest(out) or {}).get("installed"):
            raise UnsafeOutput(f"{out} is an installed skill. Build somewhere else, then update it with: "
                               "python skillblend.py install <built folder> --force  (files you added there are kept).")
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

    # ---- references: one page per technique (measured rules, then the full method), plus the tables
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
    with open(os.path.join(out, "references", "style-card.md"), "w", encoding="utf-8") as fh:
        fh.write(render_style_card(style, source))

    # ---- SKILL.md
    covered = [m for m in mods if personal and analyses.get(m["id"])]
    text = render_skill(sname, name, author, personal, mods, results, analyses, style, source,
                        covered, copied, module_scripts)
    with open(os.path.join(out, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    write_exports(out, render_prompt(sname, personal, mods, results, analyses, style))
    with open(os.path.join(out, "SOURCE.md"), "w", encoding="utf-8") as fh:
        fh.write(render_source(sname, personal, mods, analyses, results, answers))
    write_manifest(out, {"skill": sname, "skillblend": __version__, "built": time.strftime("%Y-%m-%d"),
                         "personal": personal})
    warnings = {k: r.warnings for k, r in results.items() if r.warnings}
    return {"dir": out, "name": sname, "personal": personal, "covered": [m["id"] for m in covered],
            "generic": [m["id"] for m in mods if m not in covered], "warnings": warnings,
            "skill_md": {"lines": text.count("\n"), "chars": len(text)}}


def _unique_blends(analyses):
    return len({id(d) for docs in analyses.values() for d in docs if "_script" not in d})


def _title(name):
    words = name.replace("-", " ").replace("_", " ").split()
    return " ".join(w[:1].upper() + w[1:] for w in words) if name == name.lower() else name


def _strip_h2(s):
    return re.sub(r"^##\s+.*\n?", "", s.strip(), count=1).strip()


def _one_line(text, limit=300):
    """A sentence or two that fits on one line of the overview."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(": "))
    return cut[:end].rstrip() + "." if end > limit * 0.4 else cut.rsplit(" ", 1)[0] + "..."


def _generic_bullets(m):
    summary, _ = modlib.generic_text(m)
    return [ln[2:].strip() for ln in summary.splitlines() if ln.startswith("- ")]


def description(who, titles, personal):
    """The line an assistant reads to decide whether to load the skill. Agent Skills allow 1024 characters."""
    if not personal:
        return ("A complete hard-surface and game-asset modelling workflow for Blender: real-scale setup, "
                "blockout to detail, bevels and shading, SubD topology, booleans, modifier stacks, kit inserts, "
                "UVs and texel density, game-ready export and vehicles. Use it whenever the user asks to model, "
                "remodel, block out, bevel, unwrap, optimise or export a 3D model, prop, kit piece or vehicle "
                "in Blender, or to review one.")

    def make(who_, titles_):
        return (f"Model in Blender the way {who_} does, with rules measured from {who_}'s own .blend files"
                + (f" ({titles_})" if titles_ else "") + ". Use it whenever the user asks to model, remodel, block out, "
                "bevel, unwrap, optimise or export a 3D model, prop, kit piece or vehicle in Blender (headless scripts or "
                f"a live session), or to check a model against {who_}'s style.")
    for w, t in ((who, titles), (who, None), ("the artist", None)):
        d = make(w, t)
        if len(d) <= MAX_DESCRIPTION:
            return d
    return d


def render_skill(sname, name, author, personal, mods, results, analyses, style, source, covered, copied, module_scripts):
    who = author or "the artist"
    titles = ", ".join(m["title"].lower() for m in (covered or mods))
    L = ["---", f"name: {sname}", f"description: {yaml_scalar(description(who, titles, personal))}", "---", "",
         f"# {_title(name)}", ""]
    if personal:
        L += [f"This skill models like {who}. It was built by SkillBlend on {time.strftime('%Y-%m-%d')} "
              f"from {_unique_blends(analyses)} .blend file(s)"
              + (f" and {len(analyses.get('build-scripts', []))} build script(s)" if analyses.get("build-scripts") else "") + ". Lines marked "
              "**measured** come from those files and from the interview. Lines marked **standard method** had no "
              "example to learn from and use SkillBlend's built-in workflow. Where the two disagree, the measured rules win.", ""]
    else:
        L += ["This is the generic skill from SkillBlend: a complete, tested modelling workflow. "
              "It wasn't personalised, because no models were submitted. Rebuild it with SkillBlend after "
              "submitting models to make it model like you.", ""]

    # ---- the overview: one line per technique, each pointing at its own page
    L += ["## How this project is built", "",
          "Read this first: one line per technique, in the order the work happens. Each technique has its own page in "
          "`references/` with every measured rule, the numbers and the step-by-step method. **Read that page before "
          "you do that kind of work**; the line here is only the summary.", ""]
    for i, m in enumerate(mods, 1):
        r = results.get(m["id"])
        files = analyses.get(m["id"], []) if personal else []
        if files:
            unit = "script" if m.get("source") == "scripts" else "file"
            tag = f"measured from {len(files)} {unit}{'s' if len(files) != 1 else ''}"
            text = " ".join(r.headlines) if r and r.headlines else (_one_line(r.rules[0]) if r and r.rules else m.get("summary", ""))
        else:
            tag = "standard method" + (", with your answers" if r and r.rules else "")
            bullets = _generic_bullets(m)
            text = _one_line(bullets[0]) if bullets else m.get("summary", "")
        more = []
        if m["id"] == "kit-library" and r and r.extra.get("kit_catalogue"):
            more.append("[references/kit-catalogue.md](references/kit-catalogue.md)")
        for fname in ((r.extra.get("reference_md") or {}) if r else {}):
            more.append(f"[references/{fname}](references/{fname})")
        more += [f"`scripts/{f}`" for f in module_scripts.get(m["id"], [])]
        if copied.get(m["id"]):
            more.append("`" + sorted({os.path.dirname(p) for p in copied[m["id"]]})[0] + "/`")
        L.append(f"{i}. **{m['title']}** ({tag}). {text} Page: [references/{m['id']}.md](references/{m['id']}.md)"
                 + (". Also " + ", ".join(more) if more else "") + ".")
    L.append("")

    # ---- how to work
    bs = results.get("build-scripts")
    kits = (bs.numbers.get("helper_kits") if bs else None) or []
    L += ["## How to work", "",
          "`<this skill>` below is the folder this file is in.", "",
          "- If this folder has a `NOTES.md`, read it before modelling. It holds the artist's own hand-written rules, and they win over this page.",
          "- Build models as Python scripts run in headless Blender: `blender -b --factory-startup --python build_model.py -- OUT.blend`. A fix is an edit and a re-run, never a hand edit to a generated file.",
          *([f"- Write build scripts the way the artist does: import their helper kit ({', '.join('`' + k + '`' for k in kits[:4])}) and use its calls "
             f"(see [references/build-scripts.md](references/build-scripts.md)) rather than raw bpy." + (" Copies of the kit and example scripts are in `examples/build-scripts/`." if copied.get("build-scripts") else "")]
            if kits else []),
          "- Load the style at the top of every build script: `sys.path.insert(0, r\"<this skill>/scripts\")`, then `import style`. "
          "`style.setup_scene()`, `style.name()`, `style.box()`, `style.bevel()` (pick `tier=\"small\"`, `\"medium\"` or "
          "`\"large\"` by the edge's role), `style.finish()`, `style.subd()`, "
          "`style.cutter()`, `style.order_stack()`, `style.modifier()` (any modifier type, with the artist's typical settings), "
          "`style.material()` (rebuilds the artist's measured material recipes), `style.setup_render()`, `style.kit_piece()` "
          "and `style.texel_density()` all use the numbers in `style.json`.",
          "- Before calling a model done, run `blender -b --factory-startup MODEL.blend --python <this skill>/scripts/style_check.py` "
          "and fix every warning, or tell the user why it's intended. It must end with `STYLE ok` or only notes you can explain.",
          "- Render review shots (front, side, top, 3/4 and close-ups of the busiest areas) and compare them with the reference before adding detail."]
    if copied:
        L += ["- Example files from the artist are in " + ", ".join(sorted({os.path.dirname(p) for v in copied.values() for p in v})) +
              ". When unsure how the artist would build something, open the closest example headless and study its "
              "modifier stacks and topology (`scripts/stack_audit.py` prints a file's stacks, if this skill has it)."]

    # ---- key numbers
    shown = [k for k in KEY_NUMBERS if style.get(k) not in (None, "", [], {})]
    measured = [k for k in shown if source.get(k) != "generic default"]
    standard = [k for k in shown if source.get(k) == "generic default"]
    keys = (measured + standard)[:MAX_KEY_NUMBERS]
    keys.sort(key=KEY_NUMBERS.index)
    L += ["", "## Key numbers", "",
          f"The numbers you need most often. All {len(style)} settings, with where each came from, are in "
          "[references/style-card.md](references/style-card.md); `style.py` reads them from `style.json`.", "",
          "| Setting | Value | From |", "|---|---|---|"]
    for k in keys:
        L.append(f"| `{k}` | {_fmt_val(style[k], k)} | {source.get(k, '')} |")
    return "\n".join(L).rstrip() + "\n"


def render_style_card(style, source):
    L = ["# Style card", "",
         "Every style number and where it came from: measured from the artist's files, the artist's answer, or "
         "SkillBlend's generic default. `scripts/style.py` reads the same values from `style.json`.", "",
         "| Setting | Value | From |", "|---|---|---|"]
    for k in sorted(style):
        L.append(f"| `{k}` | {_fmt_val(style[k], k)} | {source.get(k, '')} |")
    return "\n".join(L) + "\n"


def render_prompt(sname, personal, mods, results, analyses, style, max_chars=20000):
    """A compact, self-contained prompt for any chat model (it fits small local models too): the overview, the
    numbers, then each technique's measured rules, or a few standard rules where nothing was measured."""
    out = [f"You are a 3D modelling assistant working in Blender. Model the way the artist behind the `{sname}` style does: "
           "follow the rules below, measured from the artist's own .blend files. Use real-world metres, keep modifiers live "
           "unless asked otherwise, and use the numbers in the style card. If you can't run code, give the steps in "
           "Blender's interface with the same settings." if personal else
           "You are a 3D modelling assistant working in Blender. Follow the modelling workflow below. Use real-world "
           "metres, keep modifiers live unless asked otherwise, and use the numbers in the style card. If you can't run "
           "code, give the steps in Blender's interface with the same settings."]
    heads = [h for m in mods for r in [results.get(m["id"])] if r and personal and analyses.get(m["id"]) for h in r.headlines]
    if heads:
        out.append("## How this project is built\n\n" + "\n".join(f"{i}. {h}" for i, h in enumerate(heads, 1)))
    nums = []
    for k, v in sorted(style.items()):
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
    for m in mods:
        r = results.get(m["id"])
        if personal and analyses.get(m["id"]) and r and r.rules:
            tag, bullets = "measured", r.rules[:8]
        else:
            tag, bullets = "generic", ((r.rules[:3] if r else []) + _generic_bullets(m))[:3]
        if bullets:
            out.append(f"## {m['title']} ({tag})\n" + "\n".join(f"- {b}" for b in bullets))
    text = "\n\n".join(out) + "\n"
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n\n(Trimmed to fit a chat model's prompt.)\n"
    return text


def render_source(sname, personal, mods, analyses, results, answers):
    L = [f"# How {sname} was built", "", f"- Built: {time.strftime('%Y-%m-%d %H:%M')} by SkillBlend {__version__}",
         f"- Personal: {'yes' if personal else 'no (generic)'}", "", "| Module | Files | Answers | Warnings |", "|---|---|---|---|"]
    for m in mods:
        files = analyses.get(m["id"], [])
        r = results.get(m["id"])
        L.append(f"| {m['title']} | {', '.join(d['_submission']['file'] for d in files) or '-'} | "
                 f"{len(answers.get(m['id'], {}))} | {'; '.join(r.warnings) if r and r.warnings else ''} |")
    return "\n".join(L) + "\n"
