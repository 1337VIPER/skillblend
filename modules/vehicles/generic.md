## Vehicles

- Cars are read by proportion first, then surface quality, then detail. Wheels are the unit: set the wheel diameter from the class ratio first and judge everything else against it.
- Build original designs. Never recreate a specific real, film or game car (or product) from its look, name or badges; use real cars only for class proportions.
- Frame: metres, car faces +X, Y left, Z up, ground at z 0, origin on the ground under the middle of the wheelbase.
- The body comes from four design curves (side top line, belt/shoulder, floor, plan half-width). The top line is straight between keys (flat windscreen and backlight), the others eased; plan corners are crisp (0.88 to 0.97 of the width within 3% of the length); tumblehome 0.72-0.80.
- Loft the body as one quad grid (about 40 stations, denser at the ends), creased at shoulder and rocker, then render side, front, top and 3/4 and judge proportion before any detail. Show the user the shape and wait for approval before the LOW, rig, bake or export.
- No slab panels: character line, rolled shoulder, crowned hood and roof, real radii everywhere (no knife edges on pressed steel), judged in a raking clay view.
- Glass is a separate skin sunk 12 mm behind a gasket recess, made from exact outlines (never by selecting faces). Panels are split with a real 4-5 mm gap. Lamps are recessed buckets with reflector rings and a lens. Arches are cut only to well depth and lined.
- Bolt-on assemblies (bull bar, roof rack, cages, wheels) are built as their own detailed parts from their own close references, then fitted.
- Rig with custom properties on a root (`steer`, `travel`, `door`) driving empties; export one skeletal mesh (root + four wheel bones) built in centimetres, last.
- Budgets: example coupe 61k tris; hero player car up to about 120k with interior; traffic 15-30k.
- The kit is `scripts/carkit.py`; start from `scripts/example_wedge_coupe.py`.

<!-- more -->

### What studying a production car .blend taught
A downloaded car .blend was studied for techniques, proportions and construction only; none of its meshes are used, and the kit is not for rebuilding that car or any other real or film car. It builds original cars.
- **Almost no live modifiers.** 49 meshes, about 790k triangles; stacks were only Mirror, Edge Split (30 deg + marked sharps, the old way of auto smooth) and a few Arrays (grille slats x9, vent louvres x85, radiator fins x129: one slat plus an Array, never 129 modelled fins). The body was subdivided and applied.
- **The body is a single-sided quad skin**, 12.9k quads with only about 100 poles, split into **84 separate shells**: every panel (hood, wings, sills, roof, door skins) is its own piece. Panels meet with a real gap, and each panel edge is **turned inward as a short return flange** with tight holding loops, so the gap shows depth and a clean highlight line. No panel line is a texture or a groove cut into one surface.
- **Loop flow follows the character lines:** long loops down the length of the car, an even grid on big flat panels (hood, roof), loops that wrap round the shoulder and sill.
- **Wheel arches** are rings of concentric loops. The arch edge rolls inward and continues as the inner arch wall, so there's no visible "cut" edge.
- **Glass is a separate panel** sitting behind a gasket ring that is part of the body opening. Windows never share a surface with the paint.
- **Lamps are recessed buckets** with concentric inset rings (reflector), a lens face, and a thin bezel.
- **Wheels:** about 8k quads each, a tire with modelled tread blocks (4.6k faces) and a separate rim, 54 islands (rim, spokes, nuts, valve).
- **Rig:** controls drive everything. One control handle per mechanism, limited to a range of travel; Transform constraints map that travel onto each wheel's slide and rotation, and each door's handle onto its hinge rotation. Hierarchy: master empty > slide > rotate > wheel.
- **Materials:** about 60, many near-duplicates (6 variants of one silver, separate glass colours per lamp); textured black plastic (a Voronoi bump) for trim and seats.

Proportions measured on it (side ortho render), now the `wedge_coupe` row in `carkit.KINDS`:

| | of overall length |
|---|---|
| wheelbase | 0.58 |
| wheel diameter | 0.143 |
| front overhang | 0.21 |
| rear overhang | 0.22 |
| width | about 0.465 |
| belt (window sill) from the ground | about 0.20 |

The other rows (hatchback, saloon, suv, pickup) are typical-class starting points, not measurements: check them against your own drawing.

**Not to copy:** 790k triangles with no LODs; a texture-mapped UV only on the seats; 60 near-duplicate materials; unapplied and negative object scales; single-sided panels (fine for renders, but back faces show in a game unless the material is two-sided or the panel gets a return flange all the way round).

### Frame, units and slots
Metres, car faces +X, Y left, Z up, ground at z 0, origin under the middle of the wheelbase. Rear is -X: a ray "from behind" starts at -20 m (a plate once landed on the nose).
Slots: CarPaint, Glass, Trim, Chrome, Gap, WheelWell, LampHousing, LampLens, TailLens, Grille, Tire, Rim, Brake, Plate (plus Steel/SteelDark from library inserts; map them in the engine import or swap the material in the insert call).

### Workflow
Start from the example (it runs start to FBX):
```
blender -b --factory-startup --python scripts/example_wedge_coupe.py -- OUT_DIR [--door 0.7] [--no-export]
```
Lug nuts come from the insert library (`$BSF_INSERT_LIB`, built by `scripts/build_inserts.py`, see kit-library) when it exists.

#### 0. From a concept image: part sheets
Body proportions come from the main image. Every bolt-on assembly (bull bar + bumper + winch, roof rack + lamps, bed rack, wheels, cages, cargo) is built as its own detailed part from its own close part reference, then fitted on (see "Big models from a concept image" in blockout-to-detail). Never invent an assembly's members from the far-away concept view.

#### 1. Brief and proportions
Name the class (wedge_coupe, hatchback, saloon, suv, pickup, or a new row in `KINDS`), the length, and what makes this car its own: two or three character ideas (a rising wedge belt, a short tail, a fastback). `proportions(kind, L, **over)` gives wheelbase, wheel radius, track, overhangs, ground clearance, belt height and where the cowl, roof and deck sit along the length; any key can be overridden. **Wheels are the unit**: set the wheel diameter from the class ratio first and judge everything else against it.

#### 2. The four design curves
`design(P, top, belt, floor, plan, tumblehome, shoulder, wedge)`: side top line (nose, hood, cowl, roof, deck, tail), belt/shoulder line, floor line, plan half-width, all as keys over t (0 nose, 1 tail). Rules that came out of testing:
- the hood sits **below** the belt at the nose and rises to meet the shoulder at the cowl;
- the top line is interpolated **straight** between keys (the windscreen and backlight are near-flat planes; an eased top line bows the windscreen into an S); the belt, floor and plan are eased;
- plan corners are **crisp**: 0.88 to 0.97 of the width within 3% of the length (eased 0.8 corners = a soap bar);
- tumblehome 0.72-0.80: the cabin leans in over the shoulder.

#### 3. Primary: lofted body, arches
`loft_body(D, stations=40, subd=2)`: cross-sections at 40 stations (denser at the ends), mirrored, capped, the shoulder and rocker loops creased (0.9, 0.6) and subdivided: long, clean loops. `wheel_arches(body, P)`: each arch cut from the outside only to the well depth (never through the car: a full-width cylinder makes a tunnel you can see through), walls in WheelWell, a thin Trim lip. **Render side, front, top and 3/4 now** (`render_views`) and judge proportion before any detail. Then the shape gate: show the user the body's side, top and 3/4 against the concept and wait for their OK before the LOW, rig, bake, game renders or export.

#### 3b. Surface depth: no slab panels
A flat slab side, a flat hood and ruler-straight tubes read as "AI made" even on the right proportions. Real pressed and fabricated metal always carries these. Build them into the section and the primary stage, never as decals or normal-map-only detail:
- **Character line (swage):** a crisp fold 10-15 mm proud, 80-100 mm under the belt, running unbroken from the front fender through every door and the cab (and bed) to the tail. It sits at the same z (within 2 mm) across every panel gap; measure it.
- **Shoulder** rolled at a 20-25 mm radius, not one knife crease. The side below has a slight 6-10 mm convex bow, a lower recessed moulding channel, and a rocker tuck-under.
- **Hood:**
  - crowned 15-20 mm across;
  - two stamped fore-aft ridges, each 8-12 mm high;
  - a raised centre with drafted walls;
  - a rolled front lip showing its thickness;
  - the fender tops sit 20-30 mm lower, with a visible step and valley, so the hood reads as its own panel.
- **No knife edges anywhere on old pressed steel** ("too sharp and squared" is the failure):
  - roof edges roll at 50-80 mm, cab and bed corners at 80-120 mm, window openings at 40-60 mm;
  - door and panel edges are hemmed at 6-10 mm;
  - character creases are soft (15-30 mm radius), not 0.95-weight knife creases;
  - a fender wraps its front corner at 250-350 mm in plan;
  - panels are wavy and dented, 4-10 mm over 15-40 cm.
  Judge it in a raking clay view beside the reference, never in a flat-lit render.
  How, in `carkit.py` (all opt-in):
  - Blender's crease is sharpness 10 c squared: at subd 2, 0.45+ is a knife. Use 0.1-0.3 for soft lines; `D["crease_fn"](k, t, c)` varies a line along the length.
  - `D["round_ends"] = [(t_end, dir, ax, by, az, bz)]` (truck section) rounds a part's end as a quarter ellipse tangent to the end face (cab back, bed corners). Don't use plan keys for it: their cosine ease makes S-bends.
  - `loft_body(cap_crease=(front, rear))` and `bed_box(cap_crease=...)` soften one end only.
  - Hems on a booleaned skin: thicken the skin piece safely after the cuts; never use `inset_region` for a hem.
  - Waviness: long (0.5-0.9 m) waves of 1 mm or less. Short sines read as corrugation.
- **Every fabricated part at hero level:** window cages and guards get the same treatment as the bull bar.
  - Round-tube frames standing off the glass, with thick rods (10-16 mm, not wire).
  - Welded crossings, rod ends welded into the frame, and stand-off tabs.
  - Bent and unevenly spaced bars, and the same weathering.
  - Window cages are a bent round-tube hoop at a big corner radius (windscreen 35 mm OD at R 200, doors 20 mm OD at R 75-85), with bars clipped to it in touching layers and seeded waves and sag. Draw HIGH-only randoms (welds) from their own random generator, so the HIGH and LOW stay the same cage.
  - The glass behind them is dirty, and maybe cracked, as texture.
  - Flat thin-mesh cages read weak next to a detailed bull bar.
- **Hoods are layered pressings, never a squared slab:**
  - a rolled bullnose lip over the grille, with a ledge line behind it;
  - a raised centre bulge with soft radiused ledges along its edges;
  - lower side flats stepping down from it;
  - a big rounded shoulder (60-100 mm) rolling into the side edge;
  - fenders lower, with their own shoulders and an eyebrow swell over the lamp and arch.
  Read every ledge off the reference crop before modelling, and compare a raking clay view beside it.
  - **Build the front clip as its own part** (hood, fenders, grille surround, headlamp buckets, core support) with surfaces you control ledge by ledge (subdivision cages with creases, or curve networks). A body loft with one cross-section can't make a layered hood: two passes on one truck stayed slab-like. On real trucks the clip bolts on at the cowl and firewall anyway.
- **Front end slope and taper:** even square-body trucks are not boxes in plan or side view. The hood line drops about 100-130 mm (3-4 degrees) from the cowl to the nose, and the fender shoulder eases down with it. The hood and fenders narrow to about 0.90-0.92 of the width at the fascia, while the nose corners stay crisp. Check both in top and side ortho views.
- **Fenders:** an eyebrow crease rising over the arch, a 12-20 mm swell around it, and a rolled return flange at the opening.
- **Roof:** crowned 20-25 mm, with low stamped stiffening ribs. Cab corners and A-pillars are rounded at a 50-70 mm radius. Bed rail caps roll over to the inside.
- **Tubes:**
  - mandrel bends at 2.5-3x the OD, with slight ovality in the bend;
  - a 2-6 mm/m sag or bow on long spans;
  - on bars that take hits, a few dents (15-25% flattening) and one kink;
  - coped joints with weld beads, and capped ends.
- **Mesh guards:** the panel pillows 6-12 mm, with one or two dents and 1-2 mm rod waviness. The rod layers touch at every crossing, and the rod ends are welded to the frame.
- **Seeding:** all irregularity is deterministic and seeded per module, and applied before instancing, so repeated module copies stay vertex-identical (UV stacking and modular export depend on it).
- **LOW mesh:** the LOW keeps all of this as geometry; only welds, rivets and print bake.
- **Review:** use raking light (sun 10-15 degrees grazing along the side, and a raking 3/4 of the hood). Flat-lit renders hide every one of these.

#### 4. Secondary: glass, panels, lamps
- `dlo(D)` works out the daylight openings from the curves (side glass, optional B pillar, windscreen, backlight). `window(body, poly, "XZ"|"XY"|"YZ")` makes each one: a separate glass skin keeping the body's curvature, sunk 12 mm, in a recess whose walls are the gasket. Never select faces to make glass: it steps along the grid.
- `split_panel(body, outline, "XZ"|"XY"|"YZ", gap=0.005)`: doors, hood, boot, fuel flap as separate objects with a real gap (walls in Gap). Parent them to hinges in the rig.
- `lamp(body, y, z, w, h, "front"|"rear")`: a recessed bucket along the surface normal, reflector rings, lens. `grille(...)`, `plate(...)`.

#### 5. Tertiary and wheels
`wheel(P, side, spokes)`: tire (sidewall bulge, two grooves, tread blocks), rim barrel and dished face, tapered spokes, brake disc and caliper, lug nuts from the insert library. Then mirrors, wipers, handles, badges (your own, never a real maker's), exhaust: small parts built the hard-surface way (kit-library, modifier-stacks).

#### 6. Rig
`rig_car(body, P, wheels, hinges)`: custom properties on `CAR_root` drive everything, the same idea as one control handle per mechanism: `steer` (-1..1, front wheels +-0.6 rad), `travel` (metres rolled, every wheel spins travel / radius), `door` (0..1, each hinge (panel, pivot, axis, max deg)). Hierarchy root > WHL_xx_steer > WHL_xx_spin > wheel. Test with door 0.7 and steer 0.5 in a render.

#### 7. Export to the engine
`export_unreal_vehicle(path, body_parts, wheels, P)`: one skeletal mesh, bones `root` + `wheel_fl/fr/rl/rr` at the wheel centres, body weighted to root, each wheel to its bone, built in **centimetres** (a metre scene gives a 100x root bone). Destructive, so run it last. In Unreal: import as Skeletal Mesh, make a Physics Asset (wheels as spheres, body as boxes), and a vehicle Blueprint (Chaos wheeled vehicle movement) with those bone names. Verify the import on your first real car and record what it needed.

### Budgets and review
Measured: the example wedge coupe is 61k tris (body 23k, each wheel about 8k with lug nuts); a traffic hatchback with `loft_body(stations=24, subd=1)` and `wheel(segs=32, tread=False, lug=False)` is about 14k (body 4.4k, wheel 1.9k) and still reads. For a game: hero player car up to about 120k with an interior, traffic 15-30k. The body is a closed volume, so glass is opaque tinted (fine for traffic); a hero car needs an interior and two-sided or backed glass. Review every change on the same five renders (3/4 front, 3/4 rear, side, front, top); record shape decisions in the car's script docstring.

### Gotchas
- UVs for any game mesh: the origami unwrap (uvs-and-texel-density). Seams sit on hidden edges, corners lie on cuts, identical wheels, lamps and mirrored panels share UV space unless they carry print, and every island is checked for stretch.
- Anything mounted ON the body (screens, spoilers, mirrors, light pods) takes its contact line from the body's real surface and has a mount with fixings at both ends. Measure the gap along the whole contact line, and check every joint in close-up with back faces culled (see kit-library: a windscreen once floated 60 mm off its cowl at the corners).
- Selecting faces for windows steps along the grid: use `window()` outlines.
- Eased top lines bow the windscreen into an S; eased plan corners make a soap bar.
- An arch cylinder through the full width makes a tunnel you can see through; cut each side only to well depth.
- Rig empties created with `matrix_parent_inverse = parent.matrix_world.inverted()` before a depsgraph update get a stale inverse and double their offset (the wheels landed beyond the bumpers): give rig empties their location in the parent's space and no inverse.
- Rear is -X: a ray "from behind" starts at -20 m.
- Known issue: where the windscreen (XY) and side glass (XZ) cuts meet at the A pillar a small paint sliver can stick out (seen on the hatchback); widen `dlo(pillar=)` or `a_tip` until it closes.
- Library inserts bring Steel/SteelDark slots; map them in the engine import or swap the material in the insert call.

### Pickups, trucks and off-road builds
Kit additions, all in `carkit.py`:
- **Class row `pickup`** (crew cab + separate bed, 37 in tyres); `proportions(kind, L, **over)` overrides any key (`wheel_r`, `track` for tyres that sit out under flares). `PICKUP["bed_t"]` = where the bed starts.
- **Sections:** `D["profile"]` = `"slab"` (`station_slab`, 12 points: flat square-body side, crisp shoulder) or `"truck"` (`station_truck`, 27 points, creases `TRUCK_CREASES`, `glass_pt` 21): rocker tuck, recessed moulding channel, bowed side with an optional stamped rib (`side_rib` keys, e.g. bed only), a swage that stands `swage_out` proud `swage_drop` under the belt with a return under it, a rolled shoulder, the fender top, and a hood that steps `hood_step_h` above the fenders (`hood_step` keys) and crowns to its centre line; a crowned roof; stamped ribs (`ribs` height keys, `hood_rib_y` keys, `roof_rib_y`). Hooks: `swage_fn(x)` (an eyebrow over the arch), `side_fn(x, z)` (a swell round the arches). `D["hood_levels"]` makes a multi-level pressed hood. The point count is fixed, so the loft stays one quad grid, and the swage lands at one height across every panel gap (measured within 2 mm on a test truck).
- **Taper and slope:** the hood line is the `top` keys' centre line, straight-interpolated (drop it toward the nose with a short convex roll into the lip); ease `belt` down over the fender; narrow `plan` from the cowl forward, keeping the corners crisp inside the last ~1% of the length. Hold full width a little ahead of the door gap, or coarse LOW quads tilt there and the thickened door touches the body.
- **Sheet-metal shell:** `loft_body(..., t0, t1, cap_crease, cap_fill="tri")` (a concave section folds an n-gon cap), then `hollow(body, t, thicken_now=False)`; cut every window, panel, arch and fascia opening on the OPEN skin with `carkit.SKIN_CUT = carkit.BOOL_HOLES = True` (the cutter's own faces are dropped after each cut), then `thicken(piece, t, "Gap")` each piece. Solidifying first and cutting after wiped the shell (the offset folds at tiny creased cap corners); hole-tolerant cuts without SKIN_CUT left the cutter walls inside (a door became a box).
- **Panels and glass:** `split_panel` / `window` take plane `"YZ"` (back windows, tailgates); put a seam on a flat floor, never on a sloped step wall (the thickened skins overlap under it); keep panel shells thinner than half the gap; overlap adjacent panel cuts so no sliver of body is left between two gaps. `gasket(glass)` beads the step between sunk glass and the opening. Window outlines must sit inside their door outline (check the sign of every edge: one front window first ran 35 mm past the door's rear edge).
- **Bed and arches:** `bed_box(D, t0, t1, floor_z, wall, rail=...)` (double-wall sides, load box and underside cut out, rear wall ready for a `YZ` tailgate split); `wheel_arches(..., axles, outline, liner, z_cut)` cuts a box arch and builds closed wheel-house liners (an earlier liner closed back across the arch bottom, through the tyre).
- **Wheels:** `offroad_tyre` (carcass + mud-terrain blocks with draft; shoulder blocks wrap into sidewall lugs) and `steel_wheel` (barrel, dished face with lug and vent holes, beadlock ring); a lathe section must never cross itself or every hole boolean leaves its cutter standing. Build one wheel and place copies (a spare too); keep the hub and rotor on the axle so the spare stays the same mesh.
- **Checks:** `contact_gap(mounted, support)` (signed gaps on contact faces, ok = share within +-1 mm) and `min_clearance` (tyre in arch, flare over tyre). A full joint check samples whole faces, measures only over the support, skips parts resting on the mount's own parts, leaves batched hardware out, has a "drape" rule for straps and pressed panels (may bridge, may not cut in), and tests clearances with exact triangle overlap. It caught every fault the eye missed.
