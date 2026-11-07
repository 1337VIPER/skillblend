## Game-Ready Export

- Production work (LOW, bake, UVs, LODs, export) starts only after the user has approved the shape (see blockout-to-detail).
- Apply modifiers per object BEFORE joining; then mark sharp edges and add weighted normals LAST (auto smooth does nothing headless); merge duplicate material slots. Slot names are the engine's material mapping.
- The LOW follows the HIGH within 3 mm on every visible surface: build every feature that changes the surface (recesses, crowns, ridges, dents) into the LOW too, and measure it. The limit is 0.5% of a module's faces missing at 6 mm.
- Hidden-face removal on the LOW tests the whole face: sample every corner and edge midpoint, keep a face if ANY sample is outside.
- Never ship a render stack: drop or lower Subsurf, swap library inserts to `_lo`, and read the triangle table against the budget. A live-stack prop dropped from 68.9k to 9.8k triangles that way.
- Budgets: a hero interactive prop up to about 80k tris (non-Nanite); room pieces and set dressing can go Nanite. Vehicles: hero up to about 120k with interior, traffic 15-30k.
- Every glass slot keeps its own material in the game mesh.
- Review in Blender before any import: perspective and orthographic crop renders, every joint in close-up on the HIGH and the game mesh with backface culling on, from the rear, below and the user's seat, not only the hero angle.
- Then import with matching slots and check real-frame close-ups under the game's own lighting.
- Skeletal assets are built in centimetres (unit scale 0.01); static props stay in metres.

<!-- more -->

### HIGH, LOW and the bake
- **The LOW follows the HIGH within 3 mm on every visible surface.**
  - Why: a typical bake cage reaches about 6 mm out and 15 mm in. Where the low drifts further, the rays miss, and those pixels bake black and glossy: white streaks in the game render.
  - Where it drifts: a low cab skipped the high's recessed cowl vent and rounded the windscreen header off by 1-2.5 cm, and its cage rods didn't follow the high's pillow and dents.
  - So: build every feature that changes the surface (recesses, crowns, ridges, deformation) into the low too, then measure it per module with a ray-plus-nearest-distance check. Glass is excluded. The limit is 0.5% of a module's faces missing at 6 mm.
  - A long-reach fallback pass (about 4x the extrusion) that fills missed pixels is a safety net, not the fix.
- **Print bakes into the texture and is deleted before the AO and normal bakes** (see kit-library), so letters never show as relief.
- **Hidden-face removal on the low must test the whole face.** Sampling a face at its centre and three corners deleted a tail shell's whole end cap (one big n-gon whose samples sat inside a lamp housing) and a strip of a seat, leaving see-through holes. Sample every corner and edge midpoint, and keep a face if ANY sample is outside.
- **Every glass slot keeps its own material** (window glass, clear and amber lenses, tail lens, mirror). One copied glass material turned all of a truck's windows amber.
- **Small printed surfaces get more texels** (screens about 5x, labels about 4x; see uvs-and-texel-density).

### Bake down live stacks and SubD
- Live modifier stacks: `stackkit.game_down()` (Subsurf off, or level 1 on big curved heroes; curves to low resolution; inserts to `_lo`), then `stackkit.bake()` (applies stacks, deletes cutters). An exporter that joins every mesh joins hidden cutters too. See modifier-stacks.
- SubD cages: apply Subdivision 1 on primary forms, bake normals from level 2-3 for the rest (see subd-topology).
- Dense kitbash hardware becomes a normal-map bake or a cheaper `_lo` insert at game LOD.

### Export steps
1. Apply every modifier per object before the join (joining first throws away the other objects' stacks).
2. Apply scale and rotation; real metres for static meshes.
3. UVs: the origami unwrap (uvs-and-texel-density). Legend cards keep their own UVs.
4. Mark edges over the sharp angle as sharp in bmesh (auto smooth does nothing headless).
5. Weighted normals last, with Keep Sharp.
6. Merge duplicate material slots. Slot names are the material mapping, so a new slot name needs a material on the import side. Read the exported slot list before importing.
7. Triangulate before export so the baker and the engine see the same triangles.
8. Export FBX for the engine (smoothing by face); a GLB is handy for web or viewer review.

### Budgets
- Hero interactive prop (non-Nanite, for example one with a translucent hover overlay): up to about 80k tris.
- Room pieces and set dressing: Nanite (masked legends are fine on Nanite).
- Hero player vehicle: up to about 120k with an interior; traffic vehicles 15-30k (see vehicles).
- Read the triangle report (GAMEDOWN table, or your exporter's per-object count) against the budget every export.

### LODs
Build LODs from the LOW: fewer round segments, 1-segment bevels, `_lo` inserts, tertiary detail left to the normal map. Repeated module copies must stay vertex-identical (apply seeded irregularity before instancing) so they can share UVs and LODs.

### Review in Blender (before any import)
- Render perspective views plus orthographic front and crop views; legends render in their ink colour. Check each crop: every label on the right control, readable, not clipped by a bevel or another part; keys in the right order; nothing floating or buried. Fix and re-run; it takes seconds.
- **Review joints, not just the whole object.** Before calling a model done, render tight close-ups (lens 60-85 mm) of every place two parts meet (screen to cowl, seat to tail, light to fairing, mounts), for the HIGH AND the game mesh, with `use_backface_culling` on every material. A glTF or web viewer is single-sided, so flipped or missing faces show as holes there but not in a double-sided beauty render. Look from the rear, from below and from the user's seat, not only the hero angle.
- Glass in review renders: EEVEE screen-space refraction can turn objects behind glass into a white block, and without refraction glass reads opaque. Swap glass for a transparent material with a Fresnel gloss for reviews.
- A replica also passes the reference gate (IoU, openings, feature tiers; see blockout-to-detail), and the user sees the overlay with the renders.

### Import and check in the engine
- If any slot list changed, do a clean reimport with the exported slot list. Meshes the game code references by default can't be renamed aside: reimport them in place and check they resolved.
- If code anchors changed, rebuild and relaunch, re-run the placement, then take real-frame close-ups under the scene's lighting (not a high-res screenshot mode that drops volumetrics).
- Dark print on dark plastic and white print on a white surface are the usual failures.
- **Held items** (knives, tools, guns) hang from the hand bone (attach to the body's hand socket plus a relative transform), never placed in world space from the hand's IK target: the hand trails its target when the body moves fast, and the item floats off the fist.
- **Engine placement scripts:** don't build and compose engine transform structs in Python (in Unreal this crashed the editor on the next Play). A world yaw turn just adds to the rotator's yaw; do offsets in plain math.
- **Skeletal meshes** are built in centimetres (unit scale 0.01, every size x100) and exported with default FBX scaling; a metre scene gives a 100x root-bone scale.

### Done means
The user approved the shape before any of the following started. Then:
- every piece exported, previews reviewed crop by crop;
- every joint checked in close-up on the HIGH and the game mesh with back faces culled;
- the UV layout and a checker render reviewed (0 failed islands);
- a replica scored against its reference (IoU, openings, feature tiers) with the overlay shown;
- imported with matching slots, placed, and seen under the game's own lighting;
- the project's notes record the change (what changed, decisions, lessons).

### Credits
Export gotchas (apply modifiers before joining, weighted normals last, auto smooth is a no-op headless) are adapted (MIT) from garyhtou/claude-plugins, "building-3d-for-web": https://github.com/garyhtou/claude-plugins/blob/HEAD/plugins/high-fidelity-web/skills/building-3d-for-web/SKILL.md
