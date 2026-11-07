## Bevels and Shading

- Nothing knife-sharp that a hand would touch. Every hard edge gets a bevel sized by its tier.
- Size bevels from a small set of widths, chosen by what the edge is (see the measured ladder below), never a fresh width per edge.
- On an invented or live-stack prop, use only three bevel widths for the whole model, taken as ratios of the main body size D: fine 0.36% of D, mid 0.82%, cutter chamfer 1.1% (about 1 : 2.25 : 3). One ladder everywhere is why parts look like they belong together.
- Bevel modifier defaults: limit method Angle at 30 degrees, 3 segments, profile 0.7 (a touch squarer than round), clamp overlap off (and keep every width under half the thinnest wall).
- Bevel BEFORE booleans: a bevel after a boolean clamps to the smallest gap and makes non-manifold corners where a cut leaves a hole inside a face.
- Shading in a script: `mesh.shade_smooth()` then `mesh.set_sharp_from_angle(angle)` writes smoothing straight into the mesh, so it survives export and every Blender version. Put the Weighted Normal modifier after the bevel (tested: flat faces bend 8.5 deg instead of 29 deg).
- SubD parts are the exception: no sharp edges and no bevel modifier on them; crispness comes from holding loops (see subd-topology).
- Metals reflect a dark scene and render near-black: judge shading under the scene's real lighting, not only in a bright preview.

<!-- more -->

### The width ladder (measured)
SkillBlend measured 649 live Bevel modifiers across a 23-asset hard-surface portfolio (props, weapons and vehicles). The widths are continuous, but they cluster into three groups, plus a few large chamfers:

| Group | Typical width | Share | What it was used on |
|---|---|---|---|
| Fine | about 0.3 mm | 23% | screws, lips, printed plates, tiny parts that only need a highlight |
| Mid | about 0.5 mm | 51% | most parts: covers, brackets, housings, rails |
| Heavy | about 2 mm | 26% | the outer edges of bodies and anything held |
| Chamfer | 5-35 mm | rare | one or two big design chamfers on the main body |

The common settings were 3 segments, an angle limit around 30-40 degrees and Clamp Overlap on. When your own files are learned, your measured ladder replaces this one.

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

### Shading: what we tested (Blender 5.2, headless, factory settings)
| Approach | Result |
|---|---|
| `mesh.shade_smooth()` + `mesh.set_sharp_from_angle(angle=30 deg)` | smooth faces, sharp edges written into the mesh (12 on a cube). Nothing to apply, nothing lost on export. **Use this in scripts.** |
| `bpy.ops.object.shade_auto_smooth(angle=30 deg)` | works headless in 5.2: it adds a "Smooth by Angle" geometry-nodes modifier. That modifier has to be applied before export, and older Blender versions behave differently, so prefer the mesh route. |
| Weighted Normal **after** the Bevel (Keep Sharp on) | the corner normals of big flat faces bend at most 8.5 deg: panels stay flat right up to the bevel. |
| Weighted Normal **before** the Bevel | the same faces bend up to 28.9 deg: the "putty" gradient across flat panels. |

So:
1. Shade smooth and mark sharp edges by angle on the mesh data (`stackkit.smooth()` does the bmesh version).
2. Put the Weighted Normal modifier after every Bevel and Boolean, with Keep Sharp on. That is what makes a 3-segment bevel read like a real fillet.
3. After applying modifiers and joining for export, mark sharps and add the weighted normals again (see game-ready-export).

Harden Normals on the bevel modifier is not needed when a Weighted Normal modifier runs last.

### Hard edges and UV seams
A hard (sharp) edge must also be a UV split, or the bake draws a line along it. Not every seam needs to be hard. With the usual unwrap angle of 48 degrees, 45-degree one-segment chamfers stay soft inside their faces' islands. See uvs-and-texel-density.

### Shading gotchas
- **Metals go black in dark scenes.** Brushed steel and other metals reflect a dark scene and render near-black, so black print on them vanishes in the engine even when it looks fine in a bright Blender preview. In dark scenes use dark panels with white print, or backlit (emissive) legends.
- **Glass in review renders.** EEVEE screen-space refraction turned an orb inside a glass tube into a white block, and without refraction the glass reads opaque. For review renders swap glass for a transparent material with a Fresnel gloss.
- **Judge in the scene's light.** Dark print on dark plastic and white print on a white surface are the usual failures, and only show under the game's own lighting.
- **Old pressed steel and car bodies** have no knife edges at all; their roll radii are in the vehicles module.

