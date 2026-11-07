## Modifier Stacks

- For a prop with no real-world reference (a sci-fi weapon, emitter, machine part) or a design that is still moving, keep every part as a short live modifier stack on a simple base mesh, so a change is a vertex or cutter move and the detail regenerates. Bake it down for the game at the end.
- The stack order is the technique; keep it:
  - turned hero forms: Bevel (angle 30, 3 segments, profile 0.7) > Subsurf 2 > Boolean > smooth by angle. The bevel's segments are the subsurf's support loops;
  - covers and armour plates: open outer surface > Mirror (clip) > Solidify (offset -1, even, rim) > Bevel > Boolean;
  - off-centre symmetric parts: Mirror with `mirror_object` set to the main body, not the world;
  - pipes and cage rails: vertex skeleton > Mirror > Skin > Subsurf;
  - glass vessels: Bevel > Subsurf > Mirror > Solidify (thin, about 0.6% of D);
  - Weighted Normal last of all at export.
- Booleans go AFTER the Subsurf, so cuts stay crisp in a smooth body.
- Take every width from the main body size D (`tiers(D)` in `scripts/stackkit.py`): three bevel widths for the whole prop.
- Never ship a render stack: Subsurf over a bevelled base multiplies fast. `game_down()` drops the Subsurf (keep level 1 only on big curved hero forms), then `bake()` applies stacks and deletes cutters before export. Read the GAMEDOWN triangle table against the budget.
- To learn from someone else's .blend, copy it, run `scripts/stack_audit.py` headless on the copy, and take techniques and ratios only, never their meshes.

<!-- more -->

### Why live stacks
A bake-as-you-go workflow applies each step (bevel applied before a cut, cutters deleted). A studied finished sci-fi prop .blend kept **every part as a short live modifier stack** on a simple base mesh (its main cylinder was 2.4k verts, a cover 153), so a shape change is a vertex move or a cutter move, and the detail regenerates. Few, simple bases; the modifiers do the work. Use the live way when a design is still moving (concept, hero props, sci-fi kit pieces), and bake it down for the game at the end.

### The stacks (order is the technique)
| Part type | Stack | Why that order |
|---|---|---|
| Turned hero forms (cylinders, tanks, caps) | Bevel (angle 30, 3 segs, profile 0.7) > Subsurf 2 > Boolean > smooth | The bevel's 3 segments are the subsurf's support loops: soft but tight edges, no hand-placed loops. The boolean runs **after** the subsurf, so cuts are crisp in a smooth body. |
| Covers, armour plates | open surface > Mirror (clip) > Solidify (offset -1, even, rim) > Bevel > Boolean | Model only the outer skin; thickness is constant and adjustable; the bevel runs round the solidified rim. |
| Off-centre symmetric parts | ... > Mirror with `mirror_object` = the main body | Tanks, canisters and holders are modelled once on one side and mirrored round the main body's axis, not the world's. |
| Pipes, cage rails | vertex skeleton > Mirror > Skin > Subsurf | Clean branching joints with no topology work; move a vertex to re-route. |
| Wire wraps, lashings | Bezier curve with a round bevel profile | A coil round a set of bolts; a circle bevel object or bevel depth gives the round section. |
| Glass vessels | Bevel > Subsurf > Mirror > Solidify (thin, ~0.6% of D) | Glass is a real wall (refraction reads); a liquid mesh sits inside, parented. |
| Small hardware (nuts, knurled collars, couplers, threads, flanges) | already-applied dense meshes, smooth by angle only | Kitbash inserts from a library, scaled into place (see kit-library). These carry most of the "detail" read at no modelling cost. |

Cutters live in a hidden collection, displayed as wire, and **carry their own bevel** (wider than the body's): that bevel becomes the chamfer round the opening. A cutter can transfer its material, so a ring groove's walls glow. See booleans-and-cutters.

### Edge and thickness language (ratios of the main body size D)
The studied prop used **three bevel widths only**: 0.0077 / 0.0173 / 0.0231 on a 2.11-unit main cylinder, roughly 1 : 2.25 : 3. One ladder everywhere is why the parts look like they belong together. `tiers(D)` gives: fine 0.36% of D (small parts, lips), mid 0.82% (plates, rails), cutter 1.1% (chamfer of a cut), shell 3.1% (plate thickness), glass 0.56%, gap 0.8%. All with profile 0.7, 3 segments, angle limit 30.

### Design language (why it reads as finished)
- **Primary:** one or two big forms (a main cylinder and a wrap-around cover). Read from across the room.
- **Secondary:** cover panels with a rib row along the bottom, rounded slots and vents, a graded run of repeats (small, medium, large: rhythm with variation, not three copies), a cage of rails round the body.
- **Tertiary:** hex nuts, screws, springs on the joints, a knurled collar, wire lashing. Detail **clusters at ends and joints** (the business end, mounts, pivots); the long sides stay calm.
- **Value and material:** a near-black body (black metal base 0.023, roughness 0.26; black plastic 0.013, roughness 0.28), light grey parts as contrast (aluminium 0.53, roughness 0.15), one cool accent (a teal-grey metal), a **single emissive colour** (strength about 24) in grooves and glass, one warm accent (copper wire). Seven flat materials, no textures: the shapes and values carry it.

### Building an invented prop with scripts/stackkit.py
1. Pick D (the main body's diameter or width, in metres) and take every width from `tiers(D)`: three bevel widths on the whole prop, profile 0.7, 3 segments, angle 30.
2. Primary forms first, one `hybrid` or `shell` each. Render.
3. Secondary: `cutter`s for slots, vents and grooves (after the subsurf), graded repeats, parts mirrored round the main axis with `mirror_about`, a cage or pipe run with `skin_cable`.
4. Tertiary at the ends and joints only: `insert`s from your library (nuts, knurl, springs, couplers), a wire lashing with `curve_wire` + `helix`. Keep the long faces calm.
5. Materials: near-black body, light grey contrast parts, one cool accent, ONE emissive colour, one warm accent.
6. `game_down()` (subsurf off; 1 only for big curved heroes via `ob["hs_game_subd"] = 1`), `bake()`, then export. Check the GAMEDOWN table against the budget.

The kit's functions:
- `tiers(D)`: the width ladder.
- `bevel`, `subsurf`, `smooth` (Smooth by Angle node, or sharp marks when headless has no asset library).
- `hybrid(ob, width)`: Bevel > Subsurf > smooth.
- `shell(ob, thickness, width)`: Mirror > Solidify > Bevel > smooth.
- `cutter(cut_ob, targets, width, slot)`: live boolean, cutter to the hidden `Cutters` collection.
- `mirror_about(ob, pivot)`: mirror round another object's axes.
- `skin_cable(points, radius, m, edges=)`: skeleton > Skin > Subsurf.
- `curve_wire(points, r, m)` and `helix(...)`: wires and coils.
- `glass_shell(ob, wall, width, liquid=)`: a glass vessel with an optional inner liquid.
- `insert_save` / `insert`: your own kitbash library (see kit-library).
- `game_down`, `curves_to_mesh`, `bake`, `drop_cutters`: the game bake-down.

### What not to copy from a render file
The studied file was a render piece, not a game asset: **907k triangles** evaluated (the main cylinder alone 344k: 4.8k base x Subsurf 2), no UVs at all, unapplied and negative object scales, arbitrary units (about 17 units tall), an old float boolean solver. For a game:
- `game_down(subd=0)`: drop the subsurf; the bevel's 3 segments plus weighted normals give nearly the same edge. Keep Subsurf 1 only on large curved hero forms. A test prop went from 68.9k to 9.8k triangles that way.
- `bake()` applies stacks and deletes cutters before export.
- Real metres, scale applied, Exact solver, UVs from the unwrap; dense kitbash hardware becomes a normal-map bake or a cheaper `_lo` insert at game LOD.

### Gotchas
- An exporter that joins EVERY mesh in the scene joins hidden cutters too. Always `stackkit.bake()` first (applies the stacks, deletes the Cutters collection).
- A Subsurf at level 0 counts as disabled and can't be applied: `game_down` removes it instead.
- Subsurf over a bevelled base multiplies fast (a 4.8k-tri cylinder became 344k at level 2): never ship a render stack; read the GAMEDOWN table.
- Headless `--factory-startup` has no Essentials asset library, so `stackkit.smooth()` falls back to marking sharp edges on the base mesh (fine: export re-marks sharps and adds weighted normals).
- Inserts share their part's mesh until `bake()` makes them single-user.

### Studying how another .blend was built
1. Copy the file to a scratch folder (never open the original for editing).
2. Run the audit headless on the copy:
   ```
   blender -b --factory-startup copy.blend --python scripts/stack_audit.py -- audit.json
   ```
   It prints each object's stack in order with the settings that matter, base vs evaluated triangles, the bevel width ladder, stack patterns, materials (base colour, metallic, roughness), sharp/seam/UV use, and flags cutters, unapplied and negative scale.
3. Turn the report into rules: the stack patterns, the width ladder as ratios of the main size, the material values, the triangle cost of each stack.
4. Take techniques and ratios only, never the meshes. Build every asset yourself.
