## SubD Topology

- Use SubD cages for smooth, flowing hard-surface forms (hulls, pods, fins, nozzles, helmets, vehicle bodies, sculpted weapon shells). Use bevels and booleans for machined boxes and printed panels, and live modifier stacks for kitbash pieces. Never mix sharps or booleans into a SubD part.
- All quads (98-100%), interior poles under 1-2%, and poles hidden on axis tips where nobody looks.
- No sharp edges and no bevel modifier on SubD parts: every crisp lip, step and rim comes from a pair of holding loops at about 1/10 (0.1-0.12) of the local quad size.
- Even, square quads at 2-3.5% of the part's size; density follows curvature (flat boxes stay low with one chamfer).
- Every lathed part of an assembly uses one segment count (cage 16 x Subdivision 2 = 64 around) so loops line up where parts meet.
- Intersect, never merge or boolean: fins, frames, rings and panel-line strips are separate meshes pushed into the body.
- Panel lines are raised strips that follow the surface, not cuts.
- Gate every part with `subdkit.qa()`: primary forms quads >= 98%, poles <= 2%, 0 sharps, median edge 1-5% of size; detail parts quads >= 95%, poles <= 3%, 0 sharps.
- For a game: keep the cage, apply Subdivision 1 on primary forms, bake normals from level 2-3 for the rest, and give it UVs.

<!-- more -->

### The reference standard
These rules were measured from a studied hand-built SubD model (a retro rocket: 73 objects, 0 modifiers, 458k triangles) with a stack audit, a topology probe and isolated wireframe renders, not guessed. `scripts/subdkit.py` reproduces the techniques from code and `subdkit.qa()` checks a model against them.

| Part | Faces | Quads | Interior poles | Sharp edges | Median edge / size |
|---|---|---|---|---|---|
| Hull (lathe, 1.35 m x 1.0 m) | 7,656 | 100% | 0.37% | 0 | 2.2% (~30 mm, near-square) |
| Glass dome (lathe) | 7,232 | 100% | 0.06% | 0 | 1.7% |
| Swept fins (slabs) | 816 each | 100% | 0 | 0 | 2.2% |
| Triangular frames | 1,280 each | 100% | 0 | 0 | 3.6% |
| Seam ring, panel-line strips | 1.7k-3.3k | 100% | 0-0.6% | 0 | strips 9-16 mm wide |
| Whole model | 458k tris | ~98-100% | | 0 everywhere | |

### The techniques
1. **Holding loops, never sharps.** No edge marked sharp, no bevel modifier, no weighted normals: every crisp lip, step and rim comes from a pair of tight loops (about 1/10 of the local quad size; 1-3.5 mm edges on a 1 m hull) and smooth shading over Subdivision. `subdkit.hold_profile` and `lathe(crisp=...)` put them in for you (`hold=0.12` of the neighbouring segment).
2. **Even, square quads.** Primary forms sit at about 2-3.5% of their size per quad, about square, so highlights flow without pinching. `lathe(square=True)` resamples a profile so the spans along it match the spacing round it.
3. **Lathes share one segment count.** Hull, dome, seam ring and nozzles all use 64 around, so their loops line up where the parts meet (cage 16 x Subdivision 2 = 64). Poles go on the axis tips where nobody sees them.
4. **Never merge, intersect.** Fins, frames, strips and rings are separate meshes pushed into the body:
   - swept fins sit about 88 mm into a 1 m hull with the root flared like a fillet;
   - panel-line strips are sunk 6-8 mm and show 2-3 mm;
   - a ring over a dome joint stands 36 mm proud and hides the joint.
   Booleans and merges are what break quad flow; the reference has none. (`fin(embed=, flare=)`, `trim_strip(embed=)`, `seam_ring()`.)
5. **Panel lines are raised strips, not cuts.** A thin strip following the surface reads as a seam with a real highlight and costs no topology on the body (`trim_strip`).
6. **Sections swept along paths.** Frames are a rounded rectangle swept round a rounded triangle; cables are circles swept along curves (the hull, dome and strips were also curves converted to mesh). `sweep`, `rounded_rect`, `rounded_polygon`, `circle`.
7. **Density follows curvature.** Flat boxy housings are a handful of faces with a single chamfer; curved parts are dense. Don't spend a SubD grid on a flat box.
8. **Mechanisms from primitives.** Landing legs are cylinders + UV-sphere joints + collars + coil springs + a lathed foot pad; nozzles are lathes with stepped ribs (`ribs()`).

### The kit: scripts/subdkit.py
- `lathe(profile, m, segs=16, crisp=(...), hold=0.12, square=True)`: a profile `[(r, z)]` lathed round +Z; crisp point indices get two holding loops; start and end at r = 0 for a closed solid (poles on the axis), or `closed=True` for a ring section.
- `ribs(r0, r1, z0, z1, n, depth)`: a ribbed-bell profile segment and its crisp indices, to splice into a lathe profile.
- `fin(root, tip, thickness, m, embed=, flare=)`: a quad-grid slab from root chord to tip chord, rim holding loops, root sunk and flared into the body.
- `sweep(section, path, m, closed_path=, up_fn=, scale_fn=)` with `rounded_rect`, `rounded_polygon`, `circle`.
- `trim_strip(target, pts, w, h, m, embed=0.6)`: a raised seam strip snapped to a surface, sunk by `embed` of its height.
- `seam_ring(r, width, proud, z0, m)`: a lathed band over the joint between two lathed parts.
- `subd(ob, levels)`: Subdivision with smooth shading and no sharp edges.
- `topology_report(ob)` and `qa(objs, "primary" | "detail")`: the measures and the gate.

Finish every build with `subdkit.qa(primary_parts, "primary")` and `qa(details, "detail")`; all must PASS.

Worked example: `blender -b --factory-startup --python scripts/example_subd_probe.py -- OUT_DIR` builds an original probe (lathed hull, dome, seam ring, ribbed nozzle, three fins, a frame, two strips, a cable), runs QA and writes shaded and wire renders. It passes every gate at 100% quads and 0 sharps.

### The gate (calibrated on the reference)
- **Primary forms:** quads >= 98%, interior poles <= 2% (a small lathe's two axis tips alone give 2 x (segs + 1) poles), 0 sharp edges, median edge 1-5% of the part's longest dimension.
- **Detail parts** (strips, cables, frames): quads >= 95%, poles <= 3%, 0 sharps; density is not judged (a long strip's edge is tiny against its length; the reference's own strips are 0.11%).

### Creases
Edge creases are not sharps: a SubD body may use them to tighten a loop without adding geometry (the vehicles module lofts car bodies with creased shoulder and rocker loops). Blender maps crease c to sharpness 10 c squared, so at Subdivision 2 a crease of 0.45 or more is a knife edge, and 0.1-0.3 gives a soft roll. Prefer holding loops on hard-surface props; use creases sparingly and softly.

### What not to copy for a game
The reference is a render model: Subdivision was applied high on small parts (a 28 cm pod is 31k faces, a leg assembly 79k), so the whole thing is 458k tris with no UVs. For a game, keep the cage, apply Subdivision 1 on primary forms, bake normals from level 2-3 for the rest, and give it UVs (see game-ready-export and uvs-and-texel-density).
