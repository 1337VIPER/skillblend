## Blockout to Detail

- Structure before detail. A model reads right when its parts, proportions and silhouette are right; detail on the wrong structure still looks wrong.
- Before any geometry, write a `STRUCTURE:` block in the model script's docstring: object and anchor dimension, assembly tree, process per part, at least 5 measured proportions, the 3-5 silhouette curves, the feature tiers, calm areas and material zones.
- Sort every feature into a tier and build in tier order, rendering after each: primary (silhouette and mass, about 70% of the read), secondary (openings, joints, parts showing at the edges, about 20%), tertiary (fasteners, grind lines, print, texture, about 10%). Never fix a primary error with tertiary detail.
- Model from a reference by tracing it, not by eye: `scripts/ref_trace.py` turns the picture into real-size outlines and openings, `scripts/ref_compare.py` scores your orthographic render against it.
- Reference gate: silhouette IoU >= 0.90 with the same opening count. 0.85-0.90: fix the flagged slices. Below 0.85: the structure is wrong; go back to the trace and proportions, not to detail.
- Big models (a vehicle, weapon or machine) are never modelled straight from one concept image: split them into assemblies, get a close part reference for each, build each from its own reference, then fit them together. Count members against the picture.
- Shape gate: build the primary and secondary tiers, show the user side, top and 3/4 views next to the concept plus the overlay and 2-3 close-ups, and wait for approval before any production work (tertiary sweeps, LOW, bake, UVs, export).
- Each part follows the rules of the process that made it (machined, sheet metal, cast, moulded, ground, turned, extruded).
- Cluster detail at ends and joints; keep calm areas calm. Evenly spread detail reads as noise.

<!-- more -->

### The shape gate (get the shape approved before production)
The user verifies the shape before the long end-of-pipeline work starts. Work in two phases:
1. **Shape phase (HIGH only).** Build the primary and secondary tiers: silhouette, proportions, the parts and how they join, openings. Score against the reference (IoU, overlay). Then stop and show the user a small set:
   - the side, top and 3/4 views next to the concept;
   - the overlay;
   - 2-3 close-ups of the busiest areas.
   Ask whether they like the shape, and wait for an answer.
2. **Production phase, only after the user says yes.** This covers tertiary detail sweeps (print, stipple, screws, coil turns), the LOW build and cull, UVs, baking, LODs, export, game-mesh renders and engine import.

Before approval, skip all of that, including "just starting the bake in the background": a bake started before the user had seen the shape was stopped and thrown away. Keep shape-phase reviews lean: a few renders that answer "is the shape right?", not 12-view sweeps. Quick automatic checks on the HIGH are fine.

### Big models from a concept image: part sheets first
A whole vehicle, weapon or machine is never modelled straight from its one concept image. Detail invented part by part from a far-away 3/4 view reads as generic: a bull bar built that way came out as a plausible tube grid, not the bar in the picture.
1. **Break the main image into assemblies.** List them: front bumper + bull bar + winch, cab, bed, wheel, roof rack + lamps, cargo, and so on.
2. **Get a part reference for each.** The user provides close part images (or makes them). Each one is a close 3/4 view of that assembly alone, with every member visible. Save them next to the model script as `refs/NN_<part>.webp`, with the main image as `refs/00_concept_main.webp`.
3. **Build each assembly as its own detailed part.** It gets its own script, its own `STRUCTURE:` block read from its part reference (members, tube counts, where each brace runs, plates, holes, fixings), and its own review.
   - The review is a render from the part reference's camera, side by side with the picture, that checks each member.
   - Count tubes, uprights, braces, holes, shackles and chain links against the picture. The count must match.
4. **Fit the parts together on the main model.** Use the attach points (pivots at the real mounting faces). Then check the whole model against the main image.
5. **What isn't copied:** callout labels and part numbers drawn on a reference are presentation. Don't model them, and don't print them.

Each part keeps its own module(s) and pivots, so it exports as its own mesh in a modular kit.

### Brief: what it is and what every control does
Name the real class of object it imitates (era, maker class, size in mm). For anything with controls, list them and what each one does in the game; a label must say what the control really does (a menu station gets MENU / SELECT / arrows; a volume knob gets 0 and 10 at the right ends of its sweep, clockwise = up). Keep any anchors the game code relies on (screen offsets, knob seats, focus centre, hover box) and write them in the model script's docstring. If a better layout needs an anchor to move, change the code default in the same pass.

### Read the reference like the factory that made it
Write the answers in the model script's docstring as a `STRUCTURE:` block (template at the end).

**What it is.** Name the class, maker class and era ("folding karambit, 2010s tactical, CNC aluminium scales") and one anchor dimension you are sure of (see the setup-and-scale module). Every other size comes from the picture, scaled by this number.

**Assembly tree.** List the real parts in build order, the way the object comes apart on a bench:
```
karambit
  frame:   liner L, liner R (steel, 1.2 mm), back spacer        <- the skeleton everything bolts to
  scales:  scale L, scale R (aluminium, 3.5 mm, unioned with the ring)
  blade:   blade (pivoting), its tang inside the frame
  pivot:   collar L, collar R, pivot screw
  fixings: 3 torx per side, clip + 2 screws
```
A part that would be a separate piece in the factory is a separate object (its own slab, bevel and material slot). Two things that are one piece (a moulded ring and its handle) are one solid: union them, don't stack them.

**How each part is made** sets its edges, thickness and details (table below). Write the process next to each part.

**Proportions table.** Measure, don't guess. Trace the silhouette and read off at least 5 ratios against the anchor: overall length : width, blade : handle, ring inner diameter : handle width, hole spacing, where the widest point sits (as % of the length). The review compares against this table.

**Silhouette edges.** Name the 3-5 curves that make the object recognisable from across a room (for a karambit: the blade's hook and how far it curls back, the ring, the finger choil under the pivot, the spine's line). These get traced points, the most points of any outline.

**Feature hierarchy.** Sort every feature into one tier before modelling any of them:
- primary (silhouette and mass): outline, thickness, the big forms; 70% of the read;
- secondary (structure): holes, slots, pivot collars, liners showing at the edge, inserts; 20%;
- tertiary (finish): screws, jimping, grind lines, etch, chamfers; 10%.

**Rest areas.** Real designs cluster detail (pivot hardware, the grip zone) and leave calm areas (a blade's flat, a scale between holes). Note where the calm areas are and keep them calm.

**Material zones.** One line per zone: material, finish, colour sampled from the picture (`ref_trace.py pick`), roughness and metallic. Coatings (anodising, ceramic coatings) are matte to satin; ground or polished edges are bright and smoother; fasteners are usually dark or bright steel, never the body colour.

### Trace, then build on the traced frame
1. `python scripts/ref_trace.py pick REF.png x,y ...` at a few pixels per material to get colours.
2. Trace the whole object against its background first (sets the scale from the anchor dimension and the origin), then each part by its colour into the same JSON:
   ```
   python scripts/ref_trace.py trace REF.png --part whole  --bg auto --length-mm 195 --out ref.json --preview t.png
   python scripts/ref_trace.py trace REF.png --part handle --rgb 40,140,40 --tol 70 --out ref.json --preview t.png
   python scripts/ref_trace.py trace REF.png --part blade  --hsv 0,360,0,0,0.18 --out ref.json --preview t.png
   ```
   Look at the preview: the traced outline must hug the part. Fix the mask (tolerance, colour) before going on. A dark part on a dark background can't be masked by colour: trace it as `whole` minus the other parts, or draw its points over the preview by hand.
3. The JSON gives each part's outline (metres, u right, v up, counter-clockwise) and its openings (round holes with centre and radius, slots with length, width and angle). The model script loads it rather than typing points in by eye:
   ```python
   REF = json.load(open(os.path.join(os.path.dirname(__file__), "knife_ref.json")))
   HANDLE = [tuple(p) for p in REF["parts"]["handle"]["outline"]]
   for h in REF["parts"]["handle"]["holes"]:          # one cutter at a time
       if h["kind"] == "round":
           cut_hole(handle, center=h["center"], r=h["r"])   # your own boolean hole helper
   ```
   Keep the JSON next to the model script, so a re-trace updates the model on the next run.
4. Photos are rarely square-on: a perspective picture shrinks the far end. When the object is turned, correct with the anchor measured at two places, or use a straight side photo for the outline and angled shots only for depth and detail.
5. `python scripts/ref_trace.py check ref.json` before building: a self-crossing outline builds a broken slab.

**Trace silhouettes from the mask, not by eye.** Read the mask row by row (the first and last pixel of each span). Reading a pistol grip off a gridded crop put the back strap 15 mm too far back (traced-frame IoU 0.916); re-traced from the rows, it scored 0.961. When a small shift matters, compare in the trace's own frame too: `ref_compare.py` normalises length, which can hide a shift.

### Manufacturing rules that make parts read as real
| Process | Thickness | Edges | Typical details |
|---|---|---|---|
| CNC-machined aluminium (scales, housings) | 3-6 mm | crisp chamfer 0.3-1 mm, catches light (bright on anodised parts) | pockets with corner radius = cutter radius (1-3 mm), through holes, flat floors |
| Sheet metal (liners, brackets, clips) | 0.8-2 mm, constant | bend radius about = thickness; cut edges square with a tiny break | bends, stamped holes, rolled edges |
| Ground steel (blades) | 3-4 mm spine | grind lines are sharp transitions, the edge bevel is narrow and bright | primary grind band, micro-bevel, swedge, jimping (small, regular) |
| Die-cast / cast | 2-4 mm walls | soft fillets 1-3 mm, draft | parting line, bosses, ribs |
| Injection-moulded plastic | 2-3 mm walls | fillets 0.5-2 mm, never razor-sharp | screw bosses, ribs, texture, parting line, sink marks near bosses |
| Turned parts (screws, pivots, knobs) | - | chamfered ends | knurling, a socket (hex, torx), a washer under the head |
| Extrusions | constant profile | sharp-ish | the profile repeats exactly along the length |

Fasteners have real sizes: M2 (head 3.8 mm), M2.5 (4.5 mm), M3 (5.5 mm), M4 (7 mm); torx on knives, hex or Phillips on electronics. Count them from the picture; don't add or drop screws.

Read as manufactured:
- mouldings: a front shell over a slightly smaller rear shell, with a dark band in the step (the parting line);
- screens sit 3-13 mm inside a chamfered opening over a smoked screen plate;
- fixings: screws in corners, feet under things, cables that go somewhere (glands, plugs, coil cords);
- nothing knife-sharp that a hand would touch.

### Build in tier order
Render after each tier: primary (outline, thickness, mass), then secondary (openings, parts showing at the edges, pivots and joints), then tertiary (fasteners, grind lines, texture, print). Never fix a primary error with tertiary detail. Each part follows its process's rules (machined: crisp chamfers and cutter-radius pocket corners; sheet metal: constant thickness and bend radius = thickness; moulded: fillets, bosses, parting line; ground steel: sharp grind transitions, a narrow bright edge).

**Tiers by visibility.** Hero objects get every control and label; set dressing gets silhouette, seams and the labels a person would read; anything behind or under stays simple.

### Detail on curved surfaces
A bevelled flat slab reads as sharp where the user wants something rounded, softer and detailed (a pistol grip, for example).
- Loft rounded sections (superellipse, exponent about 2.7, narrower at the front strap) between the traced front and back outlines, and give the width a palm swell.
- Put the detail ON the curve:
  - **textures** (checkering, stipple): a lattice of small pyramids in a 2D frame, each point raycast onto the surface and lifted along its normal;
  - **raised panels:** a constrained Delaunay grid (`mathutils.geometry.delaunay_2d_cdt`) inside the outline, dropped onto the surface, with a chamfer ring and walls sunk below it;
  - **dishes and notches:** ellipsoid or pocket cutters placed at the raycast surface point.
- Don't subdivide a flat, bevelled prism to bend it: that made 58k faces and non-manifold edges.
- Cut channels through a thin conformed panel, not into it: a cutter floor near its underside broke it.

### Offset outlines and bands
- Offset curves (edge bands, grind lines) flip side with the curve's direction. Render a new offset band in a loud colour once to see which side it landed on (one blade's edge band ended up hidden inside the blade).
- Inward-offset outlines (a panel inset from a grip) loop back on themselves at sharp corners. Drop offset points that come closer than the offset distance to the original outline.

### Review against the reference (every iteration)
Render the model orthographically from the picture's side, then:
```
python scripts/ref_compare.py REF.png renders/model_front.png --out cmp.png [--ref-rgb ...] [--no-rotate]
```
- IoU >= 0.90 means the structure matches; 0.85-0.90 is close (fix the slices it flags); below 0.85 the structure is off: go back to the tracing or the proportions table, not to detail.
- The thickness slices name where to fix (`<<` too thin, `>>` too thick). Red in the overlay is missing on the model, cyan is extra.
- Openings must match in count. A missing hole is a missing part of the structure.
- Then a side-by-side by eye, feature by feature down the tier list: every primary and secondary feature present, placed within about 2% of the length, the right size and the right material. Note each pass/fail.
- Record the IoU in the `STRUCTURE:` block's review line, and show the user the overlay with the renders.

Stop at "match" plus the feature list, then do the tertiary pass. Two or three iterations is normal.

### Mistakes this workflow has made (don't repeat them)
- A karambit blade came out a wide sickle when the picture's was a narrow hawkbill: modelled from memory of "a karambit", not traced. Trace first.
- An offset curve built on the wrong side hid the edge strip inside the blade: check the sign of an offset by rendering it in a bright colour once.
- A self-crossing outline near a tip broke the slab: run `ref_trace.py check`.
- Jimping that was too big read as teeth: tertiary details stay at real size (jimping notches 1-1.5 mm).
- Hole cutters gave the cut walls their own slot: pass the slot the wall should wear (see booleans-and-cutters).
- Overlapping cutters joined in one boolean wiped the target: cut one at a time.
- Parts too small to read in game: one blade was 15% short. Compare against the anchor, then make a first-person hero item read a touch big rather than small.

### Template for the docstring
```
STRUCTURE (from <reference file or description>)
  object      <class, maker class, era>; anchor: <dimension> = <mm> (<why it's certain>)
  assembly    <part>: <process>, <material>, <thickness>   (one line each, build order)
  proportions <ratio> = <value from the trace>              (5 or more)
  silhouette  <the 3-5 curves that make it recognisable>
  tiers       primary: ...; secondary: ...; tertiary: ...
  calm areas  <where detail stays out>
  materials   <zone>: <colour rgb>, metallic <m>, roughness <r>
  review      IoU <value> (<date>), openings <ref>/<model>, flagged slices: ...
```

### Credits
The prop tiers are adapted (MIT) from arjun988/blender-skills, "hard-surface" and "prop-artist": https://github.com/arjun988/blender-skills
