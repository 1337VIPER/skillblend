## Kit Library

- Reuse before you model: search the project for an existing asset that fits, reuse it with its own materials, and leave it out of your own model (say so in a comment).
- Small hardware carries most of the detail read. Keep your own insert library of parts modelled from code (`scripts/build_inserts.py`): real ISO sizes in metres, origin on the mounting point, +Z out of the mount, modifiers applied, sharp edges over 30 degrees, plain slot names, and a `_lo` version of each.
- Place inserts with `insert(name, loc, normal=..., spin=..., scale=...)` (scale 0.75 turns an M8 part into M6). Instances share one mesh until bake.
- Every mounted part needs a load path: a mount runs from a structural part to the mounted part with fixings at BOTH ends. If you can't say what holds a part up, it's floating.
- Fit a part to the surface it sits on, never to its own curve, and measure the gap at 5+ points along the contact line: anything over about 1 mm open or buried fails. A part never overhangs what it sits on.
- Lights are assemblies (bore, reflector, lens, bezel, retaining ring), glowing parts sit inside hardware, screens show real information, seals follow the real edge and end flush.
- Text is texture, never geometry: every label, serial, warning and readout goes in the texture (base colour, roughness, emissive). The HIGH carries it as a flush print layer that bakes and is then deleted; the LOW never has it.
- Labels say what the control really does, at real cap heights (2-3 mm small print, 4-6 mm labels, 10+ mm signs), read upright from where the player stands.
- After any fix, survey the whole model with 8-10 close-ups and fix the weakest spot: one AI-looking part makes people distrust all of it.

<!-- more -->

### Reuse before you model
Search the project for an existing asset that fits (keyboards, mice, mugs, clocks, switches, extinguishers, chairs, clipboards). Reuse it with its own materials. Multi-part props keep their layout: read the parts' world transforms in the source level, then place each as `part * T(-anchor) * R(turn) * T(target)` (A then B). Leave the reused thing out of your own model and say so in a comment.

### What a primitives and detail kit should contain
Keep a small scripted kit so props are assembled from tested parts, not rebuilt each time. A good one has:
- **Primitives:** box, cylinder, ring, sphere, tube, plate, panel, louvres, hinge, handle, cable gland, conduit, screw, bolt, label, hazard plate, ring sector; an `export()` and a `render_preview()`.
- **Dials** set per model: minimum bevel segments, extra sides on round parts, the sharp angle marked before weighted normals, and orthographic review views (front plus crop boxes, with a top-view option).
- **Detail parts:** a face frame to build in (X right, Y up, Z out of the face), taper boxes, rounded slabs, boolean helpers (`cut` + pocket / slots / hole), dishes, keycaps, push buttons, rockers, toggles, LEDs, knurled knobs, speaker drivers (they need a hole cut first) and tweeters, jacks, BNC and IEC sockets, perforation, stickers, coil cords.
- **Print:** one list of every printed label, a glyph atlas built from it with stable cells (labels already in the atlas keep their cell, so only meshes using a new label need re-exporting), and a `legend()` placer.

### Your own insert library (scripts/build_inserts.py)
Every part is modelled from code (nothing downloaded):
```
blender -b --factory-startup --python scripts/build_inserts.py -- [library.blend] [--sheet out_dir]
```
The default library is `stackkit.INSERT_LIB` (`$BSF_INSERT_LIB`, or `~/blender_inserts/inserts.blend`). It writes the catalogue `inserts.json` next to the library and, with `--sheet`, contact sheets `inserts_sheet.png` and `inserts_sheet_lo.png`. Re-running rebuilds it.

Rules every part follows:
- real size in metres (ISO metric where a real part exists);
- origin on the mounting point, +Z out of the mount;
- modifiers applied, smooth with sharp edges over 30 degrees;
- plain slot names (Steel, SteelDark, PaintDark, Rubber, Brass, Plastic, Galvanized, WireBlack);
- built twice: full detail, and `NAME_lo` (half the round segments, 1-segment bevels, knurl and fine coil detail dropped). `stackkit.game_down()` swaps in the `_lo` version unless the object has `ob["hs_keep_hi"] = True`.

| Insert | Real part | Mount / +Z | Tris (hi / lo) |
|---|---|---|---|
| hex_nut_m8 | ISO 4032 M8, 13 AF, chamfered both faces | bearing face | 1134 / 596 |
| washer_m8 | ISO 7089, 16 x 8.4 x 1.6 | bottom face | 512 / 256 |
| bolt_head_m8 | ISO 4017 head + washer face, grade dots | bearing face | 760 / 424 |
| socket_cap_m6 | ISO 4762 head, 5 mm hex socket, knurled side | bearing face | 1280 / 552 |
| pan_screw_m4 | ISO 1580 slotted pan | bearing face | 462 / 246 |
| rivet_dome_5 | dome rivet head d8 | bearing face | 384 / 192 |
| knurled_collar_30 | d30 x 20, bore 22, knurl band, M4 set screw | bottom face, along the shaft | 5068 / 1388 |
| coil_spring_12 | d12 x 25, 1.6 wire, squared ends | bottom end, along the axis | 2700 / 1016 |
| pipe_flange_25 | d60 flange, 25 mm socket, 4 x M5 studs + nuts | flange back, along the pipe | 4840 / 1968 |
| clevis_bracket_40 | 40 x 30 base, twin lugs, d8 pin + e-clip, 2 x M4 CSK | base bottom; pin along Y at z 22 | 2824 / 1304 |
| pipe_clamp_20 | saddle for a 20 mm pipe, 2 x M4 pan screws | mount face; pipe along Y at z 10.25 | 1440 / 776 |
| hose_coupler_12 | brass quick coupler, 14 AF hex, barbed tail | hex bottom, along the hose | 3654 / 1943 |
| cable_gland_m16 | M16 gland, 22 AF locknut, 8 mm cable stub | panel face, along the cable | 1184 / 608 |

**Placing:** `stackkit.insert("hex_nut_m8", loc, normal=(1, 0, 0), spin=a, scale=0.75)` puts it on a surface point facing along the normal (scale 0.75 = M6). Instances share the part's mesh (linked duplicates) until `bake()` makes them single-user.

**Adding a part:** write a `p_name()` builder in `build_inserts.py` that follows the rules (respect the `LO` flag), add it to `PARTS`, rebuild, check both contact sheets. `stackkit.insert_save()` still adds a one-off part made in a model script.

Check scale every time you place an insert: a nut that is 2x too big is the fastest way to make a model look fake.

### Joints, mounts and what reads as "AI made"
People spot these at once. Each rule came from a real build that got it wrong.
- **Fit a part to the surface it sits on, never to its own curve.** A windscreen built from its own Bezier touched the cowl only on the centreline: 5 mm buried there and 60 mm in the air at the corners. Take the contact line from the other part's real surface (project each edge point onto it, or BVH raycast for meshes), stand the edge a gasket's height above it, and blend the correction out up the part. Then MEASURE the gap at 5+ points along the whole contact line (centre, quarter, corners), not one: anything over about 1 mm open or buried is a fail.
- **A part never overhangs what it sits on.** The screen's corners were 7 mm wider than the cowl and hung in the air. Check the width against the support at the contact line.
- **Everything mounted needs a load path.** Brackets were tabs on the glass with nothing under them. A mount runs from a structural part to the mounted part, with fixings at BOTH ends: pad screwed to the body, stay tube, rubber grommet against the glass, bolt through it.
- **Seals, trims and gaskets follow the real edge and end flush.** A gasket was a straight rod whose ends stuck out past the glass. Sample the gasket from the finished edge itself, inset its ends by its radius, seat it about 1 mm into the surface below, and make the side trims start where it ends.
- **Lights are assemblies, not glowing shapes.** A box with flat discs and red bars floating off its corners, and a tail light of three flat glow rectangles, read as AI made at once. Build a lamp the way real ones are: a bore in the housing, a chrome reflector bowl, a projector barrel with lens and retaining ring (or a domed lens), a chamfered bezel proud of the face, a halo ring. LED signatures are light guides sitting in a dark channel let into the face, never bars stuck on top. LED bars are separate cells in a recessed channel (amber end cells for indicators). Then add what real lamps come with: a visor hood, side markers, a sensor or camera, mounting plates and bolts, a parting line on the housing, and a plate bracket with plate and plate lamp at the rear.
- **Screens and displays carry real information.** A generic "000" with a rising bar chart and the model name is filler. Show what the machine would show (speed, a segmented gauge for its main system, charge, a status line), give the screen a sun hood, and give small printed surfaces more texels (see uvs-and-texel-density).
- **Glowing parts sit inside hardware.** A solid glowing cylinder in a cage of plain rods read as a toy. Show glow THROUGH something built: windows machined in a sleeve, gaps between coil windings, vents. Put real hardware round it: tie-rods with nuts, washers and spacers, sensors with screws, coils as separate windings with cheeks. A plain rod or bar with no fixing at its ends is a tell.
- **Fabricated steel reads lived-in, not machined.** Bend tubes on a mandrel radius of 2.5-3x the OD (tighter reads as a CAD fillet) with 4-6% ovality in the bend plane; sag long spans 2-6 mm per metre, seeded per part (never noise); add a few dents (15-25% of the OD over 40-80 mm) where things hit; cope every tube end onto the tube it meets, with a weld bead, and cap open ends. Mesh guards pillow 6-12 mm and take a dent; rod waviness goes IN the mesh plane so the two rod layers keep touching. Parts that sit on a sagged bar are placed on the bar's measured top.
- **Survey the whole model for low-detail spots.** After the fix you were asked for, render 8-10 close-ups round the model (lights, dash, controls, core, nozzles, pegs, skids) and fix the weakest; one AI-looking part makes the user distrust all of it.

### Legends and labels
- A label says what the control really does (a volume knob gets 0 and 10 at the right ends of its sweep, clockwise = up).
- Cap heights at real size: 2-3 mm small print, 4-6 mm labels, 10+ mm signs.
- Ink slots: dark print on light or metal, light print on dark, red for warnings (REC, CLR), and a backlit (unlit emissive) slot for keypads.
- Print quads are cut to the text width and lifted 0.3 mm off the surface.
- **Reading direction:** vertical faces read upright from outside the face; horizontal faces default to text-up = -X; set the up direction explicitly when the reader stands elsewhere (work out where the player sits and point up away from them).
- Glyphs on a part that tilts (a rocker paddle) are built with it and tilted with it.
- **Metals swallow black print.** Brushed steel reflects a dark scene and renders near-black, so black print on it vanishes in the engine though it looks fine in a Blender preview. In dark scenes use dark panels with white print, or backlit legends.
- Check every label in a crop render: on the right control, readable, not clipped by a bevel or another part, keys in the right order (1 2 3 on the top row).

### Text is texture, never geometry
Every piece of visual text and print (names, serials, warnings, stencils, hazard chevrons, ID plates, screen readouts and gauges) goes in the TEXTURE: base colour, roughness and emissive. It is never modelled, extruded or embossed, and never exists on the low or game mesh, so the game asset stays clean and cheap at any LOD.
- On the HIGH, print is a flush layer (glyph meshes lifted 0.3 mm) in "Print*" slots only (PrintDark, PrintLight, PrintGlow).
- The bake turns that layer into colour, roughness and emissive, then deletes the Print faces before the AO and normal bakes, so letters never show as relief or AO outlines.
- The LOW never builds text.
- Real recesses (screw sockets) are not print: give them a normal slot.
- Give readable print enough texels (boost screens about 5x and labels about 4x; see uvs-and-texel-density).
- Check it on the game mesh under a raking light: the print must look painted on, with no edges catching light.
- A flat print card (legend quads textured from a glyph atlas) is already texture and is fine for engine props, but the rule holds: no letter shapes in the mesh.
