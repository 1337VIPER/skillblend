# How SkillBlend works

This document follows a project from folder to installed skill, and covers what each stage reads, decides and writes. For using the app, see the [README](../README.md).

- [1. Finding files](#1-finding-files)
- [2. Reading a .blend](#2-reading-a-blend)
- [3. Reading build scripts](#3-reading-build-scripts)
- [4. Sorting files by technique](#4-sorting-files-by-technique)
- [5. Turning files into rules](#5-turning-files-into-rules)
- [6. Building the skill](#6-building-the-skill)
- [7. Style checks](#7-style-checks)
- [8. The app](#8-the-app)
- [9. Workspace layout](#9-workspace-layout)

## 1. Finding files

`forge/project.py` walks each project folder. It:

- takes every `*.blend`;
- skips folders named `.git`, `__pycache__`, `node_modules` or `venv`, and any folder whose name starts with `.` or `_`. Artists keep revisions and scratch work in `_prev`, `_review`, `_stages` or `_render`, and those are not deliverables;
- skips files matching backup patterns: `*backup*`, `*autosave*`, `*recovered*`, `*_before_*`, `*.blend1`, `*_bak*`, `*_old*`, `*uvtest*`, `*_r###.blend`, and folders called `prev`, `old`, `archive`, `backup*` or `wip`;
- hashes every file (SHA-1) and drops exact duplicates.

Skipped files are listed in the app, so nothing disappears silently.

## 2. Reading a .blend

Each file is opened by Blender in the background:

```
blender -b --factory-startup FILE.blend --python forge/blender/analyse_blend.py -- OUT.json
```

`--factory-startup` keeps your add-ons and preferences out of the run, and the script never saves. Up to four files are read in parallel. The JSON is stored in `workspace/library/<sha1>.json`, so a file is only re-read when its content changes, or when the analyser version goes up.

An analysis document contains:

| Section | What's in it |
|---|---|
| `scene` | unit system, unit scale, length unit, render engine |
| `collections` | the collection tree, with object counts and asset marks |
| `objects[]` | per object: type, data name and users (for instancing), parent, collections, visibility, display type, location, rotation, scale, dimensions, where the origin sits in the bounding box, asset or fake-user status, material slots, and the **modifier stack** with the settings that carry style for each modifier type |
| `objects[].mesh` | vertex, face, triangle, quad and n-gon counts; quad ratio; surface area; sizes of n-gon caps (how many segments round parts get); poles; non-manifold edges; loose parts; edge-length spread (the 10th percentile against the median shows how tight support loops are); sharp, seam, crease and bevel-weight edges; custom normals; UV islands, seams, texel density, density spread, packing and UDIM tiles; triangle count after modifiers |
| `objects[].modifiers[]` | every modifier, any type: the curated fields plus **every** setting it has (`settings`), names of linked objects (Shrinkwrap targets, cutters, mirror objects), and for Geometry Nodes the group and the values set on its exposed inputs (works with both the Blender 4 and Blender 5 input APIs) |
| `modifier_rna_defaults` | Blender's own default for every setting of each modifier type in the file, so SkillBlend can tell your choices from untouched settings |
| `objects[].empty` | display type, size and child count: pivot and socket empties |
| `objects[].light`, `.camera` | light type, power, colour, size; camera type, lens, sensor, clipping, depth of field |
| extras per object | constraints, animation and drivers, colour attributes, shape keys, particle systems |
| `materials[]` | for every material: viewport values, render method, backface culling, displacement method, and the **whole node tree**: each node's type and settings (texture scales, Color Ramp stops, image size and colour space, projection), unlinked input values, every link (`TEX_NOISE.Fac>VALTORGB.Fac`), node groups followed inside, what feeds the material output, the Principled BSDF values, and for each Principled input that's driven by nodes, the chain that drives it |
| `world` | world colour, or its node tree: HDRI (environment texture), sky, gradient or flat colour, and strength |
| `render` | engine, samples, resolution, transparent film, colour management (view transform, look, exposure, gamma), and the compositor tree if used |
| `geometry_node_groups[]` | every Geometry Nodes group in use, with its full node tree |
| `images[]`, `libraries[]`, `node_groups[]` | what the file references |

Objects outside the scene are read too. Kit libraries often keep pieces in unlinked collections or as fake-user objects.

## 3. Reading build scripts

Many artists build or finish models with Python. `forge/scripts_scan.py` parses every `.py` file in the project folders **as text, using Python's `ast` module. It never runs them.** Scripts that don't use `bpy` or `bmesh` are ignored. For the rest it records:

- the imports, and which are your own helper kits (anything that isn't standard library, `bpy` or a common package);
- every function call, which becomes your modelling vocabulary (`box()`, `cyl()`, `cut()`, `bevel()`...);
- `bpy.ops` operators and `modifiers.new(..., "TYPE")` calls;
- the first docstring line, command-line arguments, and paths added to `sys.path` (where the kit lives).

Each script then gets a role:

| Role | When |
|---|---|
| **build** | it sits next to a `.blend` with the same name, or it isn't a tool |
| **kit** | another script imports it |
| **tool** | its name says check, render, shots, measure, review, export, bake and the like |

Only build scripts feed the vocabulary.

## 4. Sorting files by technique

Every module in `modules/` has a `detect(doc, L)` in its `rules.py`. It returns a short reason, or `None`:

```python
def detect(doc, L):
    n = sum(1 for o in L.meshes(doc) if L.is_subd_cage(o))
    return f"{n} live SubD cages" if n else None
```

A file can belong to several modules. Merged export files (`*_game`, `*_lods`) are kept out of the modules about authoring (setup, structure, bevels, materials), because merging erases those habits. A module can also look across the whole project with `detect_project(docs, L, picked)`. Game-ready uses this to add `x.blend` once it has found `x_low.blend` or `x_game.blend`.

Your overrides in the app are stored as `pinned` per file (force on or off) and `excluded`. They always win over detection.

## 5. Turning files into rules

`rules(ctx)` in each module gets:
- `ctx.files`: the analysis documents of the files picked for that module;
- `ctx.all_files`: every file;
- `ctx.answers`: optional details;
- `ctx.defaults`: the module's `defaults.json`;
- `ctx.lib`: the helpers in `forge/lib/doclib.py`.

It writes to `ctx.result`:

- `rule(text)`: a measured rule for the skill;
- `headline(text)`: one sentence for the skill's **How this project is built** overview;
- `number(key, value, note)`: a style number, with how it was measured;
- `warn(text)`: something to show you, such as a technique that didn't come through or an odd value.

Some measurements are more than a median:

- **Bevel tiers.** Bevel widths are usually continuous (0.25 to 35 mm in a real project), so splitting on gaps finds nothing. SkillBlend runs a 3-cluster k-means on log width and reports each tier with its share, for example 0.3 mm (23%), 0.5 mm (51%), 2 mm (26%).
- **Stack order.** For every pair of modifier types, it counts which comes first across every stack in the project, then sorts the types by those majority votes. Ties go to the average position, then to the generic order. Types it never saw keep their generic place.
- **Texel density.** It reports a median and the range across export meshes. When small assets are much denser than big ones (each asset on its own texture set), it says so instead of forcing one number.
- **High/low sets.** It pairs by object suffix inside a file (`_high` and `_low`), or by file name across files (`x.blend`, `x_low.blend`, `x_game.blend`, `x_lods.blend`). It compares triangles after modifiers.
- **Detail density.** Triangles per cm² after modifiers, in three size bands (under 5 cm, 5 to 50 cm, over 50 cm).
- **Round parts.** The most common n-gon cap sizes give the segment counts used on cylinders.
- **Vehicles.** A file counts as a vehicle only with at least three tyre- or wheel-named parts. A ship's `wheel_post` doesn't count.
- **Modifier dictionary.** For every modifier type in the project, every setting's typical value (median for numbers, most common for the rest) is compared with Blender's own default. The skill lists what you change, with how many instances agree (`references/modifier-dictionary.md`), and `style.modifier(obj, TYPE)` adds any modifier with those settings.
- **Shader recipes.** Materials are grouped by name across files: median base colour, metallic, roughness, emission, IOR and transmission, plus the node chain that drives each input. `style.material(obj, name)` rebuilds the material from its recipe, including a noise roughness break-up or a shader bevel when you use them.
- **Shading methods.** Counts of every texture node, the most common chain into each Principled input, image sizes and colour spaces, texture-coordinate outputs, and helpers such as Bump, Normal Map, Ambient Occlusion, Geometry, Color Ramp, Mapping and Attribute nodes.

## 6. Building the skill

`forge/build.py` merges the style numbers in order. Later sources win:

```
generic default (defaults.json)  <  measured (rules.py)  <  your answer (optional details)
```

`style.json` records which source each number came from.

`SKILL.md` is laid out as:

1. the frontmatter (`name`, `description`), written so Claude Code loads the skill for modelling requests;
2. **How this project is built**: every measured module's headline, numbered in workflow order (scripts, setup, structure, blockout, bevels, SubD, booleans, stacks, kit, materials, UVs, game-ready, vehicles);
3. **How to work**: build models as scripts, use your helper kit if one was found, load `style.py`, run `style_check.py`, render review shots;
4. the **style card**, a table of every number with its source;
5. one section per module, marked *measured* or *generic*: the measured rules, then the summary from `generic.md`, then a link to `references/<module>.md` for the full method.

The skill also gets `scripts/`:
- `style.py`, `style_check.py`, `analyse_blend.py` and `doclib.py`;
- each module's `check.py` (as `scripts/checks/<module>.py`);
- each module's helper scripts.

`examples/` gets your files and build scripts, plus your helper kit, only when you choose to include examples. `kit/` gets your kit library only when you've said it's yours to ship.

## 7. Style checks

```
blender -b --factory-startup MODEL.blend --python <skill>/scripts/style_check.py
```

This analyses the open file exactly as in step 2, then runs every `checks/*.py` against `style.json`. Checks compare against your measured ranges, not single values. A bevel is flagged only when it's outside both your width range and your width-to-part ratio range, so an artist's normal variety isn't reported as an error. The last line is `STYLE ok`, or `STYLE n warning(s), m note(s)`.

## 8. The app

`python skillblend.py app` starts a small HTTP server from Python's standard library (`forge/app.py`) and opens `forge/ui/index.html`, a single page with no external dependencies.

- It listens on `127.0.0.1` only. The page is served only to `localhost` or `127.0.0.1` Host headers, which blocks DNS rebinding.
- Every API call must send the `X-Forge-Token` header, a random token written into the page when the server starts. Other websites can't read it, so they can't call the API.
- API calls:

| Method and path | What it does |
|---|---|
| `GET /api/state` | the app's state |
| `GET /api/browse` | list folders, for the folder picker |
| `POST /api/scan` | scan the project, in a background thread |
| `POST /api/file` | exclude or override a file |
| `POST /api/answer` | save an optional detail |
| `POST /api/upload` | accept a dropped `.blend` |
| `POST /api/build` | build the skill |
| `POST /api/install` | install the skill |

## 9. Workspace layout

`workspace/` sits next to `skillblend.py` (set `FORGE_WORKSPACE` to move it) and is ignored by git:

```
workspace/
  config.json        Blender path, author, skill name
  project.json       folders, files found, detections, overrides, scripts, skipped files
  library/<sha>.json one analysis per file content
  answers.json       optional details
  uploads/           files dropped into the app
  submissions/       files submitted in the guided interview (and analysis/ for them)
  build/<skill>/     built skills
```
