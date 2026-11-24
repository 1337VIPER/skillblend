"""Tests that need no Blender: the builder's text and safety rules, the installer, and the pure-Python helpers.

    python -m unittest discover -s tests -p "test_*.py"

The end-to-end suite (tests/run_tests.py) covers everything that measures a .blend file.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from forge import build as buildlib, modules as modlib  # noqa: E402
from forge import evalkit as E  # noqa: E402
from forge import targets as T  # noqa: E402
from forge.project import find_blends  # noqa: E402
from forge.workspace import Workspace  # noqa: E402


def write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="skillblend-unit-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)

    def generic(self, **kw):
        return buildlib.build(Workspace(self.path("ws")), generic=True, **kw)


class FrontMatter(Temp):
    def test_plain_values_stay_plain(self):
        self.assertEqual(T.yaml_scalar("Model in Blender the way Ana does."), "Model in Blender the way Ana does.")

    def test_risky_values_are_quoted_and_read_back(self):
        for s in ("Studio: Nine #1", 'He said "hi": ok', "- leading dash", "trailing colon:", "true", "42", "a #hash"):
            y = T.yaml_scalar(s)
            self.assertTrue(y.startswith('"'), s)
            meta, _ = T.parse_skill(f"---\nname: x\ndescription: {y}\n---\n\nbody\n")
            self.assertEqual(meta["description"], s)

    def test_newlines_collapse(self):
        self.assertEqual(T.yaml_scalar("two\nlines"), "two lines")

    def test_slug_fits_the_agent_skills_name_rules(self):
        for raw in ("My Style!!", "--x--", "A" * 200, "Ünïcode näme", "a -- b"):
            s = buildlib.slug(raw)
            self.assertRegex(s, r"^[a-z0-9]+(-[a-z0-9]+)*$")
            self.assertLessEqual(len(s), 64)

    def test_description_never_exceeds_the_limit(self):
        titles = ", ".join(m["title"].lower() for m in modlib.load_modules())
        for who in ("Ana", "A" * 150, "B" * 600):
            self.assertLessEqual(len(buildlib.description(who, titles, True)), 1024)
        self.assertIn("Ana", buildlib.description("Ana", titles, True))


class GenericBuild(Temp):
    def test_skill_is_a_valid_short_agent_skill(self):
        res = self.generic()
        text = read(os.path.join(res["dir"], "SKILL.md"))
        meta, body = T.parse_skill(text)
        self.assertEqual(meta["name"], os.path.basename(res["dir"]))
        self.assertTrue(0 < len(meta["description"]) <= 1024)
        self.assertLess(text.count("\n"), 200)       # the Agent Skills guide: under 500 lines
        self.assertLess(len(text), 20000)            # ... and about 5000 tokens
        for m in modlib.load_modules():
            self.assertIn(f"references/{m['id']}.md", body)
            self.assertTrue(os.path.isfile(os.path.join(res["dir"], "references", m["id"] + ".md")))
        self.assertTrue(os.path.isfile(os.path.join(res["dir"], "references", "style-card.md")))

    def test_exports(self):
        res = self.generic()
        ex = os.path.join(res["dir"], "exports")
        self.assertLess(len(read(os.path.join(ex, "AGENTS.md"))), 2000)
        self.assertIn(".agents/skills/blender-modelling/SKILL.md", read(os.path.join(ex, "AGENTS.md")))
        self.assertIn("## Style card", read(os.path.join(ex, "system-prompt.md")))

    def test_manifest_lists_what_was_built(self):
        res = self.generic()
        man = T.read_manifest(res["dir"])
        self.assertIn("SKILL.md", man["files"])
        self.assertIn("scripts/style.py", man["files"])
        self.assertFalse(any(f.startswith("exports/") for f in man["files"]))
        self.assertIn("How to work", man["headings"])

    def test_out_dir_with_someone_elses_files_is_refused(self):
        out = self.path("documents")
        write(os.path.join(out, "thesis.txt"), "years of work")
        with self.assertRaises(buildlib.UnsafeOutput):
            self.generic(out_dir=out)
        self.assertEqual(read(os.path.join(out, "thesis.txt")), "years of work")
        self.assertFalse(os.path.exists(os.path.join(out, "SKILL.md")))

    def test_out_dir_empty_or_an_earlier_build_is_fine(self):
        out = self.path("out")
        os.makedirs(out)
        self.generic(out_dir=out)
        write(os.path.join(out, "stale.txt"), "left by the last build")
        self.generic(out_dir=out)
        self.assertFalse(os.path.exists(os.path.join(out, "stale.txt")))
        self.assertTrue(os.path.isfile(os.path.join(out, "SKILL.md")))

    def test_out_dir_that_is_an_installed_skill_is_refused(self):
        res = self.generic()
        inst = self.path("home", ".claude", "skills", res["name"])
        T.sync_skill(res["dir"], inst, self.path("backups"))
        write(os.path.join(inst, "NOTES.md"), "mine")
        with self.assertRaises(buildlib.UnsafeOutput):
            self.generic(out_dir=inst)
        self.assertEqual(read(os.path.join(inst, "NOTES.md")), "mine")


class Install(Temp):
    def setUp(self):
        super().setUp()
        self.src = self.generic()["dir"]
        self.name = os.path.basename(self.src)
        self.home = self.path("home")
        self.backups = self.path("backups")

    def install(self, tools, **kw):
        return T.install_skill(self.src, tools, home=self.home, backup_root=self.backups, **kw)

    def test_fresh_install_leaves_exports_out(self):
        rep = self.install(["claude"])["claude"]
        self.assertTrue(rep["new"])
        self.assertTrue(os.path.isfile(os.path.join(rep["path"], "SKILL.md")))
        self.assertFalse(os.path.exists(os.path.join(rep["path"], "exports")))
        self.assertEqual(rep["path"], os.path.join(self.home, ".claude", "skills", self.name))

    def test_update_keeps_what_was_made_by_hand(self):
        dst = self.install(["claude"])["claude"]["path"]
        write(os.path.join(dst, "references", "footwear.md"), "# Footwear\n")
        write(os.path.join(dst, "scripts", "shoekit.py"), "x = 1\n")
        with open(os.path.join(dst, "SKILL.md"), "a", encoding="utf-8") as fh:
            fh.write("\n## Footwear and soft goods (measured)\n\n- Build shoes from panels.\n")
        with open(os.path.join(dst, "scripts", "style.py"), "a", encoding="utf-8") as fh:
            fh.write("\n# my tweak\n")
        rep = self.install(["claude"])["claude"]
        self.assertFalse(rep["new"])
        self.assertEqual(rep["kept"], ["NOTES.md", "references/footwear.md", "scripts/shoekit.py"])
        self.assertEqual(rep["notes"], ["Footwear and soft goods"])
        self.assertEqual(sorted(rep["edited"]), ["SKILL.md", "scripts/style.py"])
        self.assertIn("Build shoes from panels", read(os.path.join(dst, "NOTES.md")))
        skill = read(os.path.join(dst, "SKILL.md"))
        self.assertNotIn("Build shoes from panels", skill)
        self.assertIn("## Your additions", skill)
        self.assertIn("[references/footwear.md](references/footwear.md)", skill)
        self.assertNotIn("# my tweak", read(os.path.join(dst, "scripts", "style.py")))
        self.assertIn("# my tweak", read(os.path.join(rep["backup"], "scripts", "style.py")))
        # and again: nothing is treated as edited, nothing doubles up
        rep = self.install(["claude"])["claude"]
        self.assertEqual((rep["edited"], rep["notes"], rep["backup"]), ([], [], None))
        self.assertEqual(read(os.path.join(dst, "SKILL.md")).count("## Your additions"), 1)
        self.assertEqual(read(os.path.join(dst, "NOTES.md")).count("Build shoes from panels"), 1)

    def test_update_of_a_skill_installed_before_the_manifest(self):
        dst = os.path.join(self.home, ".claude", "skills", self.name)
        write(os.path.join(dst, "SKILL.md"), f"---\nname: {self.name}\ndescription: old\n---\n\n# Old\n\n## How to work\n\n- old\n\n"
              "## Bevels and shading (measured)\n\n- old rule\n\n## SubD topology (generic)\n\n- old\n\n## My own section\n\n- mine\n")
        write(os.path.join(dst, "style.json"), "{}")
        write(os.path.join(dst, "THIRD_PARTY.md"), "old credits")
        write(os.path.join(dst, "references", "mine.md"), "kept")
        rep = self.install(["claude"])["claude"]
        self.assertEqual(rep["notes"], ["My own section"])          # the old generated sections are not "yours"
        self.assertEqual(rep["kept"], ["NOTES.md", "references/mine.md"])
        self.assertEqual(rep["removed"], ["THIRD_PARTY.md"])
        self.assertIn("# Old", read(os.path.join(rep["backup"], "SKILL.md")))

    def test_a_folder_that_is_not_a_skill_is_left_alone(self):
        dst = os.path.join(self.home, ".claude", "skills", self.name)
        write(os.path.join(dst, "holiday.txt"), "photos")
        with self.assertRaises(ValueError):
            self.install(["claude"])
        self.assertEqual(os.listdir(dst), ["holiday.txt"])

    def test_every_other_tool_shares_one_folder(self):
        self.assertEqual(T.canonical(["codex", "cursor", "gemini", "copilot", "windsurf", "claude"]), ["agents", "claude"])
        done = self.install(["codex", "cursor"])
        self.assertEqual(list(done), ["agents"])
        self.assertEqual(done["agents"]["path"], os.path.join(self.home, ".agents", "skills", self.name))
        proj = self.path("proj")
        os.makedirs(proj)
        done = self.install(["gemini"], project_dir=proj)
        self.assertEqual(done["agents"]["path"], os.path.join(proj, ".agents", "skills", self.name))

    def test_agents_md_pointer_and_legacy_cleanup(self):
        proj = self.path("proj")
        old = (f"<!-- skillblend:{self.name}:start -->\nThe style's files are in `.skillblend/{self.name}/`.\n"
               + "old rule\n" * 300 + f"<!-- skillblend:{self.name}:end -->\n")
        write(os.path.join(proj, "AGENTS.md"), "# Mine\n\n" + old + "\n## After\n")
        write(os.path.join(proj, "GEMINI.md"), old)
        write(os.path.join(proj, ".github", "copilot-instructions.md"), "# Copilot rules\n\n" + old)
        write(os.path.join(proj, ".cursor", "rules", self.name + ".mdc"), old)
        write(os.path.join(proj, ".cursor", "rules", "other.mdc"), "not ours")
        write(os.path.join(proj, ".skillblend", self.name, "SKILL.md"), f"---\nname: {self.name}\ndescription: o\n---\n")
        write(os.path.join(proj, ".skillblend", self.name, "style.json"), "{}")
        write(os.path.join(proj, ".skillblend", self.name, "references", "mine.md"), "kept")
        done = self.install(["codex", "agents-md"], project_dir=proj)
        agents = read(os.path.join(proj, "AGENTS.md"))
        self.assertTrue(agents.startswith("# Mine"))
        self.assertIn("## After", agents)
        self.assertNotIn("old rule", agents)
        self.assertEqual(agents.count(":start -->"), 1)
        self.assertIn(f".agents/skills/{self.name}/SKILL.md", agents)
        self.assertFalse(os.path.exists(os.path.join(proj, "GEMINI.md")))
        self.assertEqual(read(os.path.join(proj, ".github", "copilot-instructions.md")).strip(), "# Copilot rules")
        self.assertFalse(os.path.exists(os.path.join(proj, ".cursor", "rules", self.name + ".mdc")))
        self.assertTrue(os.path.exists(os.path.join(proj, ".cursor", "rules", "other.mdc")))
        self.assertFalse(os.path.exists(os.path.join(proj, ".skillblend")))
        shared = done["agents"]["path"]
        self.assertTrue(os.path.isfile(os.path.join(shared, "references", "mine.md")))
        self.assertIn("## How to work", read(os.path.join(shared, "SKILL.md")))
        with self.assertRaises(ValueError):
            self.install(["agents-md"])  # needs a project

    def test_merge_block_replaces_only_its_own_block(self):
        p = self.path("AGENTS.md")
        write(p, "# Mine\n")
        T.merge_block(p, "a", "one")
        T.merge_block(p, "b", "other")
        T.merge_block(p, "a", "two")
        text = read(p)
        self.assertTrue(text.startswith("# Mine"))
        self.assertIn("two", text)
        self.assertNotIn("one", text)
        self.assertIn("other", text)
        self.assertTrue(T.remove_block(p, "a"))
        self.assertFalse(T.remove_block(p, "a"))
        self.assertIn("other", read(p))


class Helpers(Temp):
    def test_find_blends_skips_backups_and_revision_folders(self):
        for rel in ("radio.blend", "radio.blend1", "radio_backup.blend", "_prev/radio.blend", "kit/bolts.blend",
                    "wip/try.blend", "old/radio.blend", "untitled.blend", ".git/x.blend", "notes.txt"):
            write(self.path("proj", rel))
        found, skipped = find_blends(self.path("proj"))
        rels = sorted(os.path.relpath(p, self.path("proj")).replace("\\", "/") for p in found)
        self.assertEqual(rels, ["kit/bolts.blend", "radio.blend"])
        self.assertIn("radio_backup.blend", skipped)

    def test_bevel_tiers_find_the_ladder(self):
        spec = importlib.util.spec_from_file_location("bevel_rules", os.path.join(REPO, "modules", "bevels-and-shading", "rules.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        widths = [0.0005] * 30 + [0.00052] * 5 + [0.002] * 40 + [0.0021] * 4 + [0.01] * 12
        tiers = [round(t, 4) for t, _ in mod.bevel_tiers(widths)]
        self.assertEqual(tiers, [0.0005, 0.002, 0.01])
        self.assertEqual(mod.bevel_tiers([]), [])

    def test_every_module_is_complete(self):
        mods = modlib.load_modules()
        self.assertGreaterEqual(len(mods), 19)
        for m in mods:
            self.assertTrue(m["title"] and m["summary"], m["id"])
            self.assertTrue(os.path.isfile(os.path.join(m["dir"], "generic.md")), m["id"])
            self.assertTrue(os.path.isfile(os.path.join(m["dir"], "rules.py")), m["id"])
            self.assertIn(m["title"], T.LEGACY_HEADINGS | {m["title"]})
            json.dumps(m["defaults"])

    def test_docs_do_not_hard_code_the_module_count(self):
        import re
        for rel in ("AGENTS.md", os.path.join("driver-skill", "SKILL.md")):
            hit = re.search(r"\b\d+ technique modules", read(os.path.join(REPO, rel)))
            self.assertIsNone(hit, f"{rel} states a module count that will go stale: {hit.group(0) if hit else ''}")


def model_row(name, warnings=0, notes=0, built=True, module="setup-and-scale"):
    """A score as evalkit.summarise makes one, for the tests of the totals."""
    doc = {"analysis": {"file": name, "objects": [{"type": "MESH", "mesh": {"tri_count": 12}}] if built else []},
           "findings": [{"module": module, "severity": "warn", "message": f"Cube: bevel {i} mm is too wide."} for i in range(warnings)]
           + [{"module": module, "severity": "info", "message": "a note"} for _ in range(notes)]}
    return E.summarise(name, doc)


class Eval(Temp):
    def test_built_in_tasks(self):
        tasks = E.load_tasks()
        self.assertGreaterEqual(len(tasks), 6)
        self.assertEqual(len({t["id"] for t in tasks}), len(tasks))
        self.assertEqual(len({t["file"] for t in tasks}), len(tasks))
        for t in tasks:
            self.assertTrue(t["prompt"] and t["title"] and t["file"].endswith(".blend"), t["id"])
        ids = [t["id"] for t in tasks]
        self.assertEqual([t["id"] for t in E.load_tasks(only=f"{ids[3]},{ids[0]}")], [ids[0], ids[3]])  # the file's order
        with self.assertRaises(ValueError):
            E.load_tasks(only="no-such-task")

    def test_own_tasks_file(self):
        p = self.path("tasks.json")
        write(p, json.dumps([{"id": "kettle", "prompt": "Model  a\nkettle."}]))  # a plain list is fine
        self.assertEqual(E.load_tasks(p), [{"id": "kettle", "title": "kettle", "prompt": "Model a kettle.", "file": "kettle.blend"}])
        for bad in ([], [{"id": "Kettle", "prompt": "x"}], [{"id": "a", "prompt": ""}], [{"id": "models", "prompt": "x"}],
                    [{"id": "a", "prompt": "x"}, {"id": "a", "prompt": "y"}],
                    [{"id": "a", "prompt": "x", "file": "same.blend"}, {"id": "b", "prompt": "y", "file": "Same.blend"}],
                    [{"id": "a", "prompt": "x", "file": "a.fbx"}]):
            write(p, json.dumps({"tasks": bad}))
            with self.assertRaises(ValueError, msg=str(bad)):
                E.load_tasks(p)

    def test_runner_command_keeps_paths_and_prompts_whole(self):
        blender = r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
        prompt = 'Model a "crate",\nabout 0.8 m long & 50% taller. Save it to {out}.'
        vals = {"blender": blender, "out": r"D:\My Work\run 1\model.blend", "skill_dir": "", "arm": "without",
                "task": "crate", "prompt": prompt, "prompt_file": r"D:\My Work\run 1\PROMPT.md", "workdir": r"D:\My Work\run 1"}
        argv = E.render_command(r'"{blender}" -b --python "C:\My Tools\build it.py" -- {arm} "{skill_dir}" {out} {prompt}', vals)
        self.assertEqual(argv, [blender, "-b", "--python", r"C:\My Tools\build it.py", "--", "without", "",
                                r"D:\My Work\run 1\model.blend", prompt])  # backslashes kept, spaces kept, {out} in the prompt not expanded
        self.assertEqual(E.split_command("a  'b c'\t\"\" d"), ["a", "b c", "", "d"])
        with self.assertRaises(ValueError):
            E.render_command("tool {nope}", vals)
        with self.assertRaises(ValueError):
            E.render_command('tool "unclosed', vals)
        with self.assertRaises(ValueError):
            E.render_command("   ", vals)

    def test_presets_are_well_formed(self):
        vals = dict.fromkeys(("prompt", "prompt_file", "workdir", "out", "skill_dir", "blender", "arm", "task"), "x")
        for name, p in E.PRESETS.items():
            for arm in E.ARMS:
                self.assertTrue(E.render_command(p[arm], vals), name)
            self.assertIn(p["isolation"], ("flag", "none"))
        claude = E.PRESETS["claude"]
        self.assertIn("Skill", E.render_command(claude["with"], vals)[E.render_command(claude["with"], vals).index("--allowedTools") + 1])
        without = E.render_command(claude["without"], vals)
        self.assertIn("--safe-mode", without)
        self.assertNotIn("Skill", without[without.index("--allowedTools") + 1])
        rn = E.resolve_runner(runner="mytool {out}", runner_without="mytool --bare {out}")
        self.assertEqual((rn["with"], rn["without"], rn["isolation"]), ("mytool {out}", "mytool --bare {out}", "unknown"))
        self.assertEqual(E.resolve_runner(runner="t", isolated=True)["isolation"], "confirmed")
        self.assertEqual(E.resolve_runner(agent="codex")["isolation"], "none")
        with self.assertRaises(ValueError):
            E.resolve_runner(agent="hal9000")

    def test_one_model_score(self):
        self.assertEqual(E.summarise("a.blend", None, exists=False)["why"], "no model file")
        self.assertIn("could not open", E.summarise("a.blend", None, detail="Blender quit")["why"])
        # Blender fell back to its own start-up scene: that is not the model
        self.assertFalse(E.summarise("a.blend", {"analysis": {"file": "", "objects": [{"type": "MESH"}]}, "findings": []})["built"])
        empty = E.summarise("a.blend", {"analysis": {"file": "a.blend", "objects": [{"type": "CAMERA"}]}, "findings": []})
        self.assertEqual((empty["built"], empty["why"]), (False, "the file has no mesh in it"))
        row = E.summarise(os.path.join("some", "dir", "A.blend"), {"analysis": {"file": "a.blend", "objects": [{"type": "MESH", "mesh": {"eval_tri_count": 40}}]},
                          "findings": [{"module": "bevels", "severity": "warn", "message": "m"}, {"module": "bevels", "severity": "error", "message": "m"},
                                       {"module": "names", "severity": "info", "message": "m"}]})
        self.assertEqual((row["built"], row["warnings"], row["notes"], row["tris"], row["style_ok"]), (True, 2, 1, 40, False))
        self.assertEqual(row["modules"], {"bevels": {"warnings": 2, "notes": 0}, "names": {"warnings": 0, "notes": 1}})
        self.assertTrue(model_row("b.blend")["style_ok"])

    def test_totals_keep_models_that_were_not_built(self):
        with_rows = [model_row("a.blend", 1), model_row("b.blend", 0, 2), model_row("c.blend", 2)]
        without_rows = [model_row("a.blend", 9, 3), E.summarise("b.blend", None, exists=False), model_row("c.blend", 10)]
        w, wo = E.aggregate(with_rows), E.aggregate(without_rows)
        self.assertEqual((w["prompts"], w["built"], w["warnings_per_model"], w["notes_per_model"], w["no_warnings"], w["style_ok"]),
                         (3, 3, 1.0, 0.67, 1, 0))
        self.assertEqual((wo["prompts"], wo["built"], wo["warnings_per_model"], wo["no_warnings"]), (3, 2, 9.5, 0))  # mean over the 2 built
        self.assertEqual(wo["modules"]["setup-and-scale"], {"warnings": 19, "notes": 3, "warnings_per_model": 9.5})
        self.assertEqual(E.paired(with_rows, without_rows), {"both_built": 2, "with_fewer": 2, "same": 0, "without_fewer": 0})
        head = E.headline({"with": w, "without": wo})
        self.assertEqual(head, "Warnings per model: 9.5 without the skill, 1 with it (3 prompts; built 3 of 3 with the skill, 2 of 3 without).")
        none = E.aggregate([E.summarise("a.blend", None, exists=False)])
        self.assertEqual((none["built"], none["warnings_per_model"]), (0, None))
        self.assertIn("n/a (nothing built)", E.headline({"with": E.aggregate([model_row("a.blend", 2)]), "without": none}))
        self.assertIn("nothing to compare", E.headline({"with": none, "without": none}))
        self.assertIn("1 prompt and one attempt", E.small_n_note(1))
        self.assertIn("not as a statistically reliable difference", E.small_n_note(6))

    def test_report_text(self):
        run_dir = E.new_run_dir(self.path("ws"), "My Run!")
        tasks = [{"id": "a", "title": "Crate", "prompt": "p", "file": "a.blend"}, {"id": "b", "title": "Radio", "prompt": "p", "file": "b.blend"}]
        models = {"with": [model_row("a.blend", 1), model_row("b.blend", 0)],
                  "without": [model_row("a.blend", 8), E.summarise("b.blend", None, exists=False)]}
        doc = E.finish(run_dir, {"run": os.path.basename(run_dir), "dir": run_dir, "mode": "score", "date": "2026-01-01 10:00",
                                 "skillblend": "0", "blender": "Blender 5.3.0", "tasks": tasks,
                                 "skill": {"name": "my-style", "dir": "D:/skills/my-style", "personal": True, "built": "2026-01-01"},
                                 "dirs": {"with": "W", "without": "WO"},
                                 "caveats": ["The without arm may have seen user-level skills."]}, models)
        self.assertEqual(os.path.basename(run_dir), "My-Run")
        md = read(os.path.join(run_dir, "report.md"))
        self.assertIn("**Warnings per model: 8 without the skill, 0.5 with it (2 prompts; built 2 of 2 with the skill, 1 of 2 without).**", md)
        self.assertIn("This rests on 2 prompts", md)
        self.assertIn("> **Caveat.** The without arm may have seen user-level skills.", md)
        self.assertIn("| Radio (`b.blend`) | 0 / 0 | not built (no model file) |", md)
        self.assertIn("| Models built | 2 of 2 | 1 of 2 |", md)
        self.assertIn("8x setup-and-scale: Cube: bevel 0 mm is too wide. (`a.blend`)", md)   # the same complaint counted once
        self.assertIn("SkillBlend did not build these models", md)
        saved = json.loads(read(os.path.join(run_dir, "report.json")))
        self.assertEqual(saved["headline"], doc["headline"])
        self.assertEqual(saved["summary"]["without"]["built"], 1)

    def test_a_run_folder_is_never_reused(self):
        ws = self.path("ws")
        dirs = [E.new_run_dir(ws, "nightly") for _ in range(3)]
        self.assertEqual([os.path.basename(d) for d in dirs], ["nightly", "nightly-2", "nightly-3"])
        write(os.path.join(dirs[0], "report.json"), "{}")
        self.assertEqual(E.list_runs(ws), ["nightly"])               # only finished runs are listed
        stamped = [E.new_run_dir(ws) for _ in range(2)]               # the same second: still two folders
        self.assertEqual(len(set(stamped)), 2)
        self.assertRegex(os.path.basename(stamped[0]), r"^\d{8}-\d{6}$")

    def test_isolation_caveat_is_said_plainly(self):
        home = self.path("home")
        write(os.path.join(home, ".claude", "skills", "hard-surface-props", "SKILL.md"), "x")
        write(os.path.join(home, ".claude", "skills", "not-a-skill", "notes.txt"), "x")
        write(os.path.join(home, ".agents", "skills", "cars", "SKILL.md"), "x")
        hs = E.home_skills(home)
        self.assertEqual(hs, {"~/.claude/skills": ["hard-surface-props"], "~/.agents/skills": ["cars"]})
        flag = E.isolation_caveat(E.resolve_runner(agent="claude"), hs)   # Claude Code reads ~/.claude/skills only
        self.assertIn("The without arm may have seen user-level skills. 1 skill folder exists in the home folder (1 in ~/.claude/skills)", flag)
        self.assertIn("--safe-mode", flag)
        self.assertIn("has not verified", flag)
        codex = E.isolation_caveat(E.resolve_runner(agent="codex"), hs)    # Codex reads ~/.agents/skills
        self.assertIn("1 in ~/.agents/skills", codex)
        self.assertNotIn(".claude", codex)
        self.assertIn("nothing hid them", codex)
        self.assertIsNone(E.isolation_caveat(E.resolve_runner(agent="codex"), {"~/.claude/skills": ["x"]}))
        own = E.isolation_caveat(E.resolve_runner(runner="t"), hs)         # your own command could read either
        self.assertIn("2 skill folders exist", own)
        self.assertIn("can't tell what your command lets the without arm see", own)
        self.assertIsNone(E.isolation_caveat(E.resolve_runner(runner="t", isolated=True), hs))
        self.assertIsNone(E.isolation_caveat(E.resolve_runner(agent="codex"), E.home_skills(self.path("empty-home"))))

    def test_signs_of_a_skill_in_what_a_run_left(self):
        wd = self.path("run")
        write(os.path.join(wd, "runner.log"), r'read C:\Users\me\.claude\skills\hard-surface-props\SKILL.md' + '\n{"type":"tool_use","name": "Skill"}')
        write(os.path.join(wd, "PROMPT.md"), "skills/cars")                                  # the harness's own file
        write(os.path.join(wd, ".claude", "skills", "cars", "SKILL.md"), "skills/cars")      # the installed copy
        write(os.path.join(wd, "build_model.py"), "import style\n")
        self.assertEqual(E.skill_signs(wd, ["hard-surface-props", "cars"]), ["hard-surface-props", "the Skill tool"])
        self.assertEqual(E.skill_signs(wd, [], also=("import style",)), ["import style", "the Skill tool"])
        self.assertEqual(E.skill_signs(self.path("empty"), ["cars"]), [])

    def test_one_run_end_to_end_without_blender(self):
        # a stand-in runner in plain Python: it saves what it was piped as the "model", unless told to hang
        runner = self.path("my tools", "fake agent.py")
        write(runner, "import sys, time, os\n"
                      "arm, out, skill = sys.argv[1:4]\n"
                      "if os.environ['SKILLBLEND_EVAL_TASK'] == 'slow': time.sleep(60)\n"
                      "text = sys.stdin.read()\n"
                      "assert os.path.isfile('PROMPT.md') and os.environ['SKILLBLEND_EVAL_ARM'] == arm\n"
                      "assert (arm == 'with') == os.path.isfile(os.path.join(skill, 'SKILL.md')) if skill else arm == 'without'\n"
                      "open(out, 'w', encoding='utf-8').write(text)\nprint('saved by the fake agent')\n")
        skill = E.skill_info(self.generic()["dir"])
        rn = E.resolve_runner(runner=f'"{sys.executable}" "{runner}" {{arm}} "{{out}}" "{{skill_dir}}"')
        run_dir = E.new_run_dir(self.path("ws"), "r")
        task = {"id": "crate", "title": "Crate", "prompt": "Model a crate.", "file": "crate.blend"}
        recs = {arm: E.run_one(task, arm, rn, run_dir, r"C:\Program Files\Blender\blender.exe", skill, timeout=120) for arm in E.ARMS}
        for arm in E.ARMS:
            self.assertTrue(recs[arm]["saved"], recs[arm])
            wd = os.path.join(run_dir, "crate", arm)
            self.assertEqual(read(os.path.join(run_dir, "models", arm, "crate.blend")), read(os.path.join(wd, "PROMPT.md")))  # the prompt arrived on stdin
            self.assertIn("saved by the fake agent", read(os.path.join(wd, "runner.log")))
        self.assertEqual(read(os.path.join(run_dir, "crate", "with", "PROMPT.md")), read(os.path.join(run_dir, "crate", "without", "PROMPT.md")))
        self.assertIn("Model a crate.", read(os.path.join(run_dir, "crate", "with", "PROMPT.md")))
        for tool in (".claude", ".agents"):
            self.assertTrue(os.path.isfile(os.path.join(run_dir, "crate", "with", tool, "skills", skill["name"], "SKILL.md")))
            self.assertFalse(os.path.exists(os.path.join(run_dir, "crate", "without", tool)))
        slow = E.run_one(dict(task, id="slow", file="slow.blend"), "without", rn, run_dir, "blender", skill, timeout=2)
        self.assertEqual((slow["saved"], slow["error"]), (False, "stopped after 2 s (the time limit)"))
        gone = E.run_one(task, "without", E.resolve_runner(runner="no-such-tool-anywhere {out}"), E.new_run_dir(self.path("ws"), "r"), "blender", skill, 10)
        self.assertFalse(gone["saved"])
        self.assertIn("could not start no-such-tool-anywhere", gone["error"])
        with self.assertRaises(ValueError):
            E.skill_info(self.path("ws"))                                  # not a built skill

    def test_command_line_is_wired_in(self):
        from forge import cli
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["--workspace", self.path("ws"), "eval", "tasks", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual([t["id"] for t in json.loads(buf.getvalue())], [t["id"] for t in E.load_tasks()])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["--workspace", self.path("ws"), "eval", "report"])
        self.assertEqual(code, 1)
        self.assertIn("No runs yet", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
