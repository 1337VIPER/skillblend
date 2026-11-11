# SkillBlend: instructions for AI coding assistants

This repository is SkillBlend: it learns how an artist builds Blender models and writes a skill their AI assistant follows. If a user asks you to run SkillBlend, learn their Blender project or make them a modelling skill, follow these steps. Run every command from the repository root. (Claude Code users can also run `python skillblend.py install-driver` to get these instructions as a skill.)

When you install the result, use `--for` with the assistant you are: `claude`, `codex` (OpenAI Codex and other AGENTS.md tools), `cursor`, `gemini`, `copilot` or `windsurf`, plus `--project-dir` for anything but Claude Code.

To work on SkillBlend's own code: the analyser is `forge/blender/analyse_blend.py` (runs inside Blender), technique modules are in `modules/<id>/` (`module.json`, `rules.py` with `detect()` and `rules()`, `check.py`, `generic.md`, `defaults.json`), and `python tests/run_tests.py` runs the full test suite (needs Blender). See docs/how-it-works.md.



The SkillBlend CLI is `python skillblend.py`. Every command below is that plus a subcommand. Add `--json` where offered when you need to parse output.

## 0. Pick the route
- **Default: learn the project.** If the artist has existing work (or doesn't want to be interviewed), don't interview them. Either:
  - **App:** start `app` in the background (`python skillblend.py app`), which opens http://127.0.0.1:4970. Tell them to add their project folder (plus any kit library folder), press "Learn how I model", check the cards, then "Make my skill" and "Install for Claude Code". Or
  - **CLI:** `learn "<project folder>" ["<kit folder>" ...]`, then `report`, then `build --name "..."` and `install "<dir>"`. Read the report critically before building (see 2.3), and tell them which techniques are measured and which stay generic.
- **Guided interview** only when the artist wants to make example models on purpose, or asks to be interviewed. Then follow sections 1-3.

You are the interviewer. The artist models; you request, measure, ask and build. Be brief and concrete: one module at a time.

## 1. Start
1. `status --json`. If `blender` is null, ask the artist for the path to blender.exe (or the Blender app) and run `config --blender PATH`. If no author is set, ask what name the skill should credit and run `config --author "NAME"` (they may decline; that's fine).
2. Explain the deal in two or three lines. There are 16 technique modules (build scripts are read from the project, the rest can be requested). Each asks for one specific model that shows that technique. Every module they submit makes the skill more like them. Anything they skip falls back to the generic workflow. They can stop at any time and build.
3. Ask whether they want to go through every module, pick some, or build the generic skill straight away.

## 2. Each module
1. `request <module> --json`. Present the brief, the must-include list and the ideas in your own short words. Ask them to model it (or pick an existing file that already fits) and give you the path when it's ready. If they want to skip, run `skip <module>` and move on.
2. When they give a path: `submit <module> "PATH" --note "what it is"`. The submit runs a headless Blender analysis and prints what the file shows.
3. Read the result critically, the way a senior artist would:
   - Lines starting with `!` are warnings. The usual meaning is that the file doesn't show the technique: no live bevels in the bevel module, no Blockout collection, no high/low pair. Tell the artist plainly, and offer to take another file, record how they really work in an answer, or skip.
   - Look for numbers that seem off (a 5 m crate, 40 bevel segments) and ask whether they're intended.
4. Interview: `questions <module> --json`. Ask the unanswered ones. Questions with options are a good fit for AskUserQuestion. Store each answer with `answer <module> KEY "VALUE"` (true/false and numbers are typed automatically).
5. Show what you learned in two to four lines (`report <module>`), then move to the next module (`request next --json`).

The artist can submit more than one file per module; more files make the medians more reliable. A non-.blend file (a reference picture, for example) is stored and shipped with the examples but not analysed.

## 3. Build
- When they're done (or want to stop): `build --json` (add `--name "..."` if they named the skill, or `--exclude vehicles` if they don't model vehicles and don't want that section).
- **Exit code 2 / "No models have been submitted"**: ask whether they want the generic skill. Only on a yes, run `build --generic --json`. The generic skill is SkillBlend's built-in workflow. It's complete and tested, but it isn't personalised; say so.
- Summarise the result: which modules are measured, which are generic, and any warnings.
- The kit-library module copies kit files into the skill only if `kit_redistribute` was answered true. Never change that answer for them. Their files are copied into `examples/` only with `--examples`. Ask first, and suggest leaving it off if the files are private or large or the skill will be shared.
- Install with `install "<dir>"` for Claude Code (add `--force` to replace an earlier build, after they agree). For other assistants add `--for codex,cursor,gemini,copilot,windsurf` and `--project-dir <their project>`; for a plain chat model give them `exports/system-prompt.md` from the built folder. It installs to `~/.claude/skills/`; use `--scope project --project-dir DIR` to install into one project instead. Tell them to start a new Claude Code session to load it.

## Rules
- Never invent measurements or answers. The skill's rules come only from the files, the answers and the generic modules.
- Don't open, edit or save the artist's .blend files. SkillBlend works on copies in its workspace.
- If an analysis fails, show the last lines of the error. Common causes: the file was saved by a newer Blender than the one configured, or the path is wrong.
- To redo a module: `remove <module> <n>`, then submit again. `analyse` re-runs every analysis (after a SkillBlend update, for example).
