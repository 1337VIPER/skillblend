## Bevels and Shading

- Nothing knife-sharp that a hand would touch. Every hard edge gets a bevel sized by its tier.
- Bevel tiers by edge: primary edges 5-20 mm with 3+ segments, panel edges 1-3 mm, micro edges 0.5-1 mm.
- On an invented or live-stack prop, use only three bevel widths for the whole model, taken as ratios of the main body size D: fine 0.36% of D, mid 0.82%, cutter chamfer 1.1% (about 1 : 2.25 : 3). One ladder everywhere is why parts look like they belong together.
- Bevel modifier defaults: limit method Angle at 30 degrees, 3 segments, profile 0.7 (a touch squarer than round), clamp overlap off (and keep every width under half the thinnest wall).
- Bevel BEFORE booleans: a bevel after a boolean clamps to the smallest gap and makes non-manifold corners where a cut leaves a hole inside a face.
- Shading: smooth shading with edges over 30 degrees marked sharp, then a Weighted Normal modifier LAST, with Keep Sharp on.
- Auto smooth does nothing in headless Blender: mark sharp edges in bmesh (or with a Smooth by Angle node) instead of relying on it.
- SubD parts are the exception: no sharp edges and no bevel modifier on them; crispness comes from holding loops (see subd-topology).
- Metals reflect a dark scene and render near-black: judge shading under the scene's real lighting, not only in a bright preview.

<!-- more -->

### Bevel tiers (real sizes)
| Tier | Width | Segments | Where |
|---|---|---|---|
| Primary | 5-20 mm | 3+ | the big outer edges of the body, anything a hand holds |
| Panel | 1-3 mm | 2-3 | panel edges, covers, plates, lids |
| Micro | 0.5-1 mm | 1-2 | small parts, lips, edges that only need to catch a highlight |

Process sets the edge too (see blockout-to-detail): machined aluminium gets a crisp 0.3-1 mm chamfer that catches light; moulded plastic gets 0.5-2 mm fillets, never razor-sharp; cast parts get soft 1-3 mm fillets; sheet metal has square cut edges with a tiny break and a bend radius about equal to its thickness; ground steel has sharp grind transitions and a narrow bright edge bevel.

### The ratio ladder (one edge language for a whole prop)
For an invented prop, pick D (the main body's diameter or width, in metres) and take every width from it. These ratios were measured on a finished hard-surface prop that used only three bevel widths in total (0.0077 / 0.0173 / 0.0231 on a 2.11-unit main cylinder, roughly 1 : 2.25 : 3):

| Name | Fraction of D | Use |
|---|---|---|
| fine | 0.36% | small parts, lips, caps |
| mid | 0.82% | plates, rails, covers |
| cutter | 1.1% | the bevel ON a boolean cutter, which becomes the chamfer round the opening |
| shell | 3.1% | plate / cover thickness (solidify) |
| glass | 0.56% | glass wall thickness |
| gap | 0.8% | parting gap between a plate and the body |

All with profile 0.7, 3 segments and an angle limit of 30 degrees. `tiers(D)` in `scripts/stackkit.py` returns this table.

### Bevel modifier settings
- `limit_method = "ANGLE"`, `angle_limit = 30` degrees.
- `segments = 3` (the segments double as support loops when a Subsurf follows; see modifier-stacks).
- `profile = 0.7`.
- `miter_outer = "MITER_SHARP"`.
- `use_clamp_overlap = False`, so every edge gets the same width. Then keep every width under half the thinnest wall, or the bevel folds.
- Small library parts (screws, nuts) use 1-2 segments at 35-40 degrees; their low versions use 1 segment.

### Bevel order with booleans
- Bevel the target first, then cut. A bevel run after a boolean clamps to the smallest gap the cut created, so the big bevel collapses; applying the target's bevel before the cut keeps cut edges crisp and the big bevel intact.
- A cut that leaves a hole inside a face (a groove or channel that stops short of an edge) makes Blender bridge the hole with an edge to a corner. A bevel modifier run after the cut breaks at that 4-edge corner and gives non-manifold edges (90 bad edges on 5 parts of one pistol). Fixes: bevel first, or run the groove out through an edge; tidy after every boolean (see booleans-and-cutters); keep a cutter's bevelled edges clear of the faces they meet.
- The cutter's own bevel is the chamfer the opening gets. Give cutters a wider bevel than the body (the "cutter" tier).

### Shading: sharp edges and weighted normals
1. Shade smooth.
2. Mark edges over the sharp angle (30 degrees) as sharp. Do it in bmesh:
   ```python
   for e in bm.edges:
       e.smooth = not (e.is_manifold and e.calc_face_angle(0.0) > math.radians(30))
   ```
   Auto smooth is a no-op in headless Blender, so never rely on it in a script. A Smooth by Angle geometry-nodes modifier works in the UI, but headless `--factory-startup` has no Essentials asset library, so a script must fall back to marking sharp edges on the base mesh (`stackkit.smooth()` does this).
3. Add a Weighted Normal modifier LAST in the stack (after every bevel and boolean) with Keep Sharp on. It makes large flat faces shade flat right up to the bevel, which is what makes a 3-segment bevel read like a real fillet.
4. At export, re-mark sharps and re-apply weighted normals after modifiers are applied and parts joined (see game-ready-export).

Harden Normals on the bevel modifier is not needed when a Weighted Normal modifier runs last.

### Hard edges and UV seams
A hard (sharp) edge must also be a UV split, or the bake draws a line along it. Not every seam needs to be hard. With the usual unwrap angle of 48 degrees, 45-degree one-segment chamfers stay soft inside their faces' islands. See uvs-and-texel-density.

### Shading gotchas
- **Metals go black in dark scenes.** Brushed steel and other metals reflect a dark scene and render near-black, so black print on them vanishes in the engine even when it looks fine in a bright Blender preview. In dark scenes use dark panels with white print, or backlit (emissive) legends.
- **Glass in review renders.** EEVEE screen-space refraction turned an orb inside a glass tube into a white block, and without refraction the glass reads opaque. For review renders swap glass for a transparent material with a Fresnel gloss.
- **Judge in the scene's light.** Dark print on dark plastic and white print on a white surface are the usual failures, and only show under the game's own lighting.
- **Old pressed steel and car bodies** have no knife edges at all; their roll radii are in the vehicles module.

### Credits
Adapted (MIT) from two published skills:
- arjun988/blender-skills, "hard-surface" and "prop-artist" (bevel tiers, wear via roughness): https://github.com/arjun988/blender-skills
- garyhtou/claude-plugins, "building-3d-for-web" (weighted normals last, auto smooth is a no-op headless): https://github.com/garyhtou/claude-plugins/blob/HEAD/plugins/high-fidelity-web/skills/building-3d-for-web/SKILL.md
