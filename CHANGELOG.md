# Changelog

## 0.2.0 (2026-11-08)

Deeper analysis: SkillBlend now researches every modifier, every node tree and how you shade and light.

- **Every modifier, every setting.** The analyser records all settings of any modifier type (not just a fixed list), including Shrinkwrap targets, Edge Split, Geometry Nodes inputs, and Blender's own defaults. A new **modifier dictionary** in each skill lists every modifier type you use and every setting you change from the defaults; `style.modifier(obj, TYPE)` adds any modifier with your typical settings.
- **Shaders and node setups** (new): your whole material node trees - shader model, procedural or image texturing, the node chains you use for base colour, roughness, metallic and normals, image sizes and colour spaces, Bump/Normal Map/AO/shader-Bevel tricks, shared shader groups - and **shader recipes** per material name. `style.material(obj, name)` rebuilds your measured materials.
- **Geometry Nodes** (new): your node groups, what they're for and the input values you set.
- **Lighting, world and render** (new): render engine, colour management, world (HDRI, sky or colour), light rig and camera lenses. `style.setup_render()` sets up review renders the same way.
- Lights, cameras, constraints, animation, colour attributes, shape keys and particle systems are recorded per object.
- Works with Blender 5's new Geometry Nodes input API.
- Fixes: session copies (`*unsaved*`) are skipped; texture-detail ranges ignore extreme outliers; repeated nodes in a chain read "Math x4".

## 0.1.0 (2026-11-08)

First public release.

- **The SkillBlend app** (`python skillblend.py app`): point it at your Blender project and it learns how you model, in three steps: show it your work, see how you model, make your skill.
- **Learns from your project automatically.** It finds your `.blend` files, skips backups, autosaves, copies and `_` revision folders, reads each file once in Blender running in the background (read-only), and also reads your Python build scripts as plain text without running them.
- **13 parts of the workflow:** Python build scripts, scale/units/naming, parts and assemblies, blockout to final, bevels and shading (with bevel-size tiers), SubD modelling, booleans and cutters, modifier stacks, kitbash and insert library, materials, UVs and texture detail, game-ready and export, vehicles.
- **The skill it builds:** `SKILL.md` with a "How this project is built" overview, a style card, `style.py` to apply your style in Blender, `style_check.py` to check any model against it, and the full method for every part.
- **A built-in standard method** for anything your files don't show, written from SkillBlend's own measurements and Blender tests.
- **Install with one prompt** in Claude Code (`INSTALL_WITH_CLAUDE.md`), or use the command line (`learn`, `report`, `build`, `install`) or the optional guided interview.
- **A demo project** (`python skillblend.py demo`) to try it without your own files.
