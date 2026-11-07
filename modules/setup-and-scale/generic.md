## Setup and Scale

- Work in metres (Metric, unit scale 1.0) at real-world size. Settle one anchor dimension you are sure of before modelling anything, and size everything else from it.
- Every prop faces +X at its origin, Z is up. Vehicles also face +X, with Y to the left and the ground at z 0.
- Put the origin (pivot) at the contact point: on the desk for a desk prop, on the wall for a wall prop, on the hinge line for a door or lid, under the middle of the wheelbase for a car, on the mounting face for a kitbash insert.
- Apply rotation and scale before export, booleans and bevels. Unapplied or negative object scale is a fault, not a style.
- Name objects for what they are, in lower snake case (`hex_nut_m8`, `door_l`). Material slot names are the material mapping in the engine, so keep them stable and descriptive (`Steel`, `CarPaint`, `Glass`). Exported assets take the engine's prefix (`SM_` static, `SK_` skeletal).
- One real part = one object. A part that would be a separate piece in the factory gets its own object, bevel and material slot; two things made as one piece are one solid.
- Animated (skeletal) props are the exception to the metre rule: build them in centimetres (unit scale 0.01, every size x100).
- Parts smaller than about 2 mm import as degenerate polygons: model tiny props 10x and scale them in the engine.
- Script the model so a fix is an edit and a re-run, and keep the script clean (no scratch code left in it).

<!-- more -->

### Units and the anchor dimension
Model in metres with Blender's Metric unit system and a unit scale of 1.0. Real dimensions are not optional: a prop at the wrong size breaks texel density, physics, bevel widths (which are ratios of size) and how it reads next to everything else.

Pick one **anchor dimension** you are certain of and write it down before you build: an overall length, a screen diagonal, or a standard part whose size is fixed. Good anchors:
- a 9 V battery, a 3.5 mm jack, a USB-A plug;
- an M3 screw head (5.5 mm across), M2 (3.8 mm), M2.5 (4.5 mm), M4 (7 mm);
- a finger ring that has to fit a gloved finger (about 25 mm inside);
- a wheel diameter for a vehicle (wheels are the unit of a car).
Every other size comes from the reference, scaled by this one number. When the only reference is a steep perspective view, ask for a straight side view first; a perspective picture shrinks the far end.

### Axes and facing
- Props: +X is the front, Z up, origin at the contact point. Write the facing in the model script's docstring.
- Vehicles: the car faces +X, Y is left, Z up, the ground is z 0, and the origin sits on the ground under the middle of the wheelbase. Rear is -X: a ray cast "from behind" starts at a large negative X (one plate landed on the nose because the ray started at +X).
- Inserts (screws, nuts, clamps): origin on the mounting point, +Z pointing out of the mount (a nut's +Z points away from the face it sits on), so placing one is "surface point + surface normal".
- Detail built on a face: build in a local frame (X across the face, Y up the face, Z out of the face), then place the frame. A box's size in that frame is (across, up, out): a display that should be wide across a sloped top is `(wide, short, thick)`.

### Origins and pivots
The pivot is where the object touches the world or turns:
- on the desk or floor (bottom centre of the contact face) for anything that stands;
- on the wall plane for wall-mounted props;
- on the hinge line for doors, lids, flaps, levers;
- at the real mounting face for every part of a modular kit, so assemblies snap together;
- under the centre of the wheelbase, on the ground, for vehicles.
Parts of a big model keep their own pivots at their real mounting faces, so each part can export as its own mesh in a modular kit.

### Applied transforms
- Apply rotation and scale before any boolean, bevel or export. Bevel widths, solidify thickness and boolean results all go wrong on scaled objects.
- Negative scale flips normals on export. Find and fix it (a study tool such as `scripts/stack_audit.py` flags `[neg-scale]` and `[unapplied-scale]`).
- Rig empties: give an empty its location in its parent's space and no parent inverse. Empties created with `matrix_parent_inverse = parent.matrix_world.inverted()` before a depsgraph update get a stale inverse and double their offset (wheels landed beyond the bumpers that way).

### Naming
- Objects: lower snake case named for what they are (`hex_nut_m8`, `door_l`, `arch_liner`). Never `Cube.017`.
- One object per real part; name it for the part.
- Material slots: short, stable, PascalCase names that describe the surface (`Steel`, `SteelDark`, `PaintDark`, `Rubber`, `Glass`, `CarPaint`, `Trim`, `Gap`). The slot name is the material mapping in the engine: a new slot name needs a material on the import side, and duplicate slots are merged at export.
- Low-poly variants of library parts: `NAME_lo`.
- Rig and helper objects carry a role prefix (`CAR_root`, `WHL_FL_steer`, `HINGE_door_l`).
- Exported assets take the engine's convention: `SM_` for static meshes, `SK_` for skeletal meshes.

### Animated and tiny props
- **Skeletal (animated) props:** build the scene in centimetres (unit scale 0.01, every size x100) and export with default FBX scaling. A metre scene gives a 100x root-bone scale in Unreal, and animation compression then zeroes small bone moves. Static props keep the metre workflow.
- **Tiny props:** parts under about 2 mm import as degenerate polygons. Model tiny props (insects, small electronics) 10x and scale them in the engine.

### Scripted, repeatable builds
Build models from a script so every fix is an edit and a re-run that takes seconds. Keep the facts the build depends on in the script's docstring (anchor dimension, facing, pivots, any positions the game code relies on). Never leave scratch code (`if False else ...`) in a model script; re-read a block before running it.

### Credits
The pivot conventions are adapted (MIT) from arjun988/blender-skills, "hard-surface" and "prop-artist": https://github.com/arjun988/blender-skills
