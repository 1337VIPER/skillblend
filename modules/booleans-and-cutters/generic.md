## Booleans and Cutters

- Openings, wells, vents and holes are boolean cuts with a chamfer, never a box floating in front of the surface.
- Use the Exact solver. Cutters must overshoot the surface, and never sit coplanar with a face: offset them by a fraction of a millimetre.
- Bevel the target before cutting. A bevel after a boolean clamps to the smallest gap and breaks at corners the cut leaves behind.
- The cutter's own bevel is the chamfer of the opening: give cutters a wider bevel than the body.
- Cut overlapping cutters one at a time. Several overlapping cutters joined into one object can make the Exact solver wipe the whole target.
- Cutters give the walls they cut their own material slot (Transfer mode): always pass the slot the wall should wear, and read the exported slot list.
- Never trust `recalc_face_normals` on thin flat cutters; build their winding outward from a counter-clockwise outline. Audit every opening afterwards by raycasting into it from outside, on both sides.
- Tidy after every boolean: weld, dissolve degenerate, limited dissolve at 0.05 degrees with the Material delimit.
- Live cutters (still moving design) live in a hidden `Cutters` collection, displayed as wire, with the boolean after the Subsurf; apply them and delete the collection before export.
- Never boolean or merge into a SubD part; intersect separate meshes instead (see subd-topology).

<!-- more -->

### Openings the manufactured way
- **Openings and wells:** cut a pocket into the target with a chamfer. Never put a box in front of the surface to fake a recess.
- **Vents and grilles:** cut slots with material transfer, so the slot walls take the dark cutter slot and read as depth.
- **Speakers:** cut a hole, then build the driver inside it (a concave cone, a surround, a dust cap) and a tweeter.
- **Machined pockets:** inside corners take the cutter radius (1-3 mm), floors are flat.

### Solver and cutter rules
- Use the **Exact** solver. Float/Fast solvers from older files fail on modern geometry.
- **Overshoot.** Pocket, slot and hole cutters must pass through the surface they cut, past it on the outside.
- **No coplanar faces.** Booleans with coplanar faces fail quietly; offset cutters by a fraction of a millimetre.
- **Bevel first, then cut.** Applying the target's bevel before the cut keeps cut edges crisp and the big bevel intact. A bevel after the boolean clamps to the smallest gap.
- **One cutter at a time when they overlap.** A helper that joins all its cutters into one object can wipe the target with the Exact solver when those cutters overlap each other (an optic housing vanished that way). Cut overlapping cutters one at a time.
- **Material slot of the cut walls.** With material Transfer the cut walls wear the cutter's slot. A hole cutter that defaulted to "Plastic" leaked an unmapped slot into a knife's holes. Pass the slot the wall should wear, and read the exported slot list before importing.
- **Winding on thin cutters.** Never trust `bmesh.ops.recalc_face_normals` on thin flat plates (cutters, panels): it turned window cutters inside out, and the Exact boolean then only imprinted the outline, with no hole and no error. Build the winding outward from a counter-clockwise outline and flip only when the placement matrix mirrors. Then audit every opening by raycasting into it from outside, on both sides of the model.
- **Hole-tolerant mode** (`use_hole_tolerant`) is needed when cutting an open skin (a single-sided shell); see "Cutting an open skin" below.

### Cuts that leave holes inside a face
A cut that leaves a hole inside a face (a light-guide channel, rib grooves, or a seam that stops short of the edge), followed by a bevel, makes non-manifold corners: Blender bridges the hole with an edge to a corner, and a bevel modifier run after the cut breaks at that 4-edge corner (90 bad edges on 5 parts of one pistol). Three fixes:
- bevel the part first (then cut), or run the groove out through an edge;
- tidy after every boolean: weld, dissolve degenerate, `dissolve_limit` at 0.05 degrees with the MATERIAL delimit;
- keep a cutter's bevelled edges clear of the faces they meet. A slot cutter whose floor sat 0.5 mm under a window's ceiling gave 20 bad edges.

Check every boolean result for non-manifold edges before moving on.

### Live cutters (non-destructive)
When a design is still moving, keep cuts live (see modifier-stacks):
- the cutter moves to a hidden collection named `Cutters`, displayed as wire, hidden in renders;
- the Boolean modifier (named `Cut_<cutter>`) goes AFTER the target's Subsurf, so cuts stay crisp in a smooth body, and before the smoothing step, which stays last;
- the cutter carries its own bevel (the "cutter" tier, 1.1% of the main body size), which becomes the chamfer round the opening;
- a cutter can transfer its material, so a ring groove's walls glow (`stackkit.cutter(..., slot="Light")`).

Before export, apply every stack and delete the Cutters collection (`stackkit.bake()`). An exporter that joins every mesh in the scene will otherwise join the hidden cutters too.

### Cutting an open skin
Single-sided body skins (sheet-metal shells with an interior) need hole-tolerant cuts made before thickening, with the cutter's own faces deleted after each cut. The method is in the vehicles module (`carkit.SKIN_CUT`, `carkit.BOOL_HOLES`).
