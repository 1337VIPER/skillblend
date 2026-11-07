## Build scripts

- Build every model from a Python script run in headless Blender: `blender -b --factory-startup --python build_model.py -- OUT.blend`. A fix is an edit and a re-run, never a hand edit to a generated file.
- Keep one script per model, named like the .blend it writes (`radio.py` writes `radio.blend`).
- Put the facts the build depends on in the script's docstring: what it is, the anchor dimension, which way it faces, pivots, and any positions game code relies on.
- Assemble models from a small helper kit of tested primitives and detail parts, imported at the top of every script, instead of re-writing geometry code each time.
- Keep scripts clean: no scratch branches (`if False else ...`), no dead code; re-read a block before running it.
<!-- more -->
### Why scripts
A scripted model is reproducible and reviewable: every change is a diff, the model rebuilds in seconds, and proportions live as named numbers instead of being buried in vertex positions. It also lets Claude work the way the artist does: by editing the build, not by poking a saved file.

### A good script layout
1. Docstring with the brief and the facts above.
2. Imports: `bpy`, then the helper kit (`sys.path.insert(0, KIT_DIR)`).
3. Reset the scene and set units.
4. Build assembly by assembly, in tier order (primary, secondary, tertiary).
5. Finish: modifiers, shading, naming, collections.
6. Save, and optionally render review shots and export.
