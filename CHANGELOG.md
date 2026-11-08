# Changelog

## 0.1.0 (2026-11-08)

First public release.

- **The SkillBlend app** (`python skillblend.py app`): point it at your Blender project and it learns how you model, in three steps: show it your work, see how you model, make your skill.
- **Learns from your project automatically.** It finds your `.blend` files, skips backups, autosaves, copies and `_` revision folders, reads each file once in Blender running in the background (read-only), and also reads your Python build scripts as plain text without running them.
- **13 parts of the workflow:** Python build scripts, scale/units/naming, parts and assemblies, blockout to final, bevels and shading (with bevel-size tiers), SubD modelling, booleans and cutters, modifier stacks, kitbash and insert library, materials, UVs and texture detail, game-ready and export, vehicles.
- **The skill it builds:** `SKILL.md` with a "How this project is built" overview, a style card, `style.py` to apply your style in Blender, `style_check.py` to check any model against it, and the full method for every part.
- **A built-in standard method** for anything your files don't show, written from SkillBlend's own measurements and Blender tests.
- **Install with one prompt** in Claude Code (`INSTALL_WITH_CLAUDE.md`), or use the command line (`learn`, `report`, `build`, `install`) or the optional guided interview.
- **A demo project** (`python skillblend.py demo`) to try it without your own files.
