## UVs and Texel Density

- Unwrap every low or game mesh the way a papercraft net is cut ("origami"), never by angle buckets: Smart UV Project left one vehicle in about 7,000 islands at 33% of the atlas.
- Every hard edge is a seam; not every seam is hard. Hard = over the angle (48 degrees) AND a UV split. Log "hard edges without a UV split: 0".
- Cut each chart only as much as it needs to lie flat: a tube gets one straight seam, a ring two, a closed dome a pole-to-pole cut, a box a net joining every corner to the cut.
- Seams go where nobody looks: creases (concave first), undersides and edges boxed in by other parts are cheap to cut; long, flat, open, upward-facing edges are expensive.
- Unwrap Angle Based (ABF++), not Minimum Stretch. Measure every island: area distortion (mean |ln area ratio|) under 0.2, shape anisotropy under 1.35, no flips. Fix failures with relief slits, not by re-projecting.
- Keep islands packable: none longer than about a fifth of the atlas side, quad strips laid out straight, spiky islands (under 30% fill) split again. Pack with a skyline packer that finds the largest uniform scale, with 8 px gaps at 4K.
- Identical parts (fan blades, mirrored lamps, bolts) share UV space, unless they carry print or bake from different high-poly surfaces.
- Texel density: about 500-650 px/m for a third-person hero asset; aim for 30-40 m2 of surface per 4K set. Boxed-in islands get half density; readable print gets more (screens about 5x, labels about 4x). Report the area-weighted median density, not the average.
- Review every unwrap: the UV layout picture, a checker render of the low (squares even and square, seams off hero surfaces), and the log (islands, seams, relief rounds, coverage, density).

<!-- more -->

### Results this method gave
On a vehicle it gave 1,060 islands, 46% coverage and 755 px/m (Smart UV Project: about 7,000 islands, 567 px/m); on a coilgun prop 3018 px/m (was 2577). Both came in under 5% area distortion with shape distortion 1.05-1.11, and 0 islands failed.

### 1. Hard edges and seams
Every hard edge is a seam; not every seam is hard. Hard edges are the edges over the angle (48 degrees by default, so 45-degree one-segment chamfers stay soft inside their faces' islands) that are ALSO UV splits. A hard edge without a split bakes a line, so the final normals pass only hardens split edges. Log the count: "hard edges without a UV split: 0".

### 2. Cut each chart only as much as it needs to lie flat
Along the cheapest edges:
- a tube gets one straight seam between its ends;
- a ring gets two;
- a closed smooth dome gets a pole-to-pole cut;
- a box (or any chart with corners) gets a net: every corner (angle defect summed over two rings of neighbours, so bevelled corners count) is joined to the cut.

One way to find the cuts: a tree-cotree cut graph (a dual maximum spanning tree on cost-to-cut, complement pruned), with end-to-end cuts re-routed as the cheapest path so they run straight along edge loops.

### 3. Cut cost decides where seams go
So seams land where nobody looks:
- long, flat, open, upward-facing edges cost most;
- creases (concave first), undersides and edges boxed in by other parts cost least (find "boxed in" with short raycasts).

### 4. Unwrap and measure
- Unwrap **Angle Based (ABF++)**, not Minimum Stretch. SLIM collapsed a prop's small millimetre bands (shape distortion 2.0 against ABF's 1.12).
- Measure every island:
  - area distortion: mean |ln| of the 3D-to-UV area ratio, limit 0.2;
  - shape anisotropy: area-weighted sigma1/sigma2 of the 3D-to-UV map, limit 1.35;
  - flipped triangles: none.
- Use real triangulation for n-gons when measuring: fans over concave n-gons fake huge distortion.

### 5. Fix failures with relief slits
Cut from the most stretched vertex to the nearest existing cut and unwrap again (2 rounds). A slit doesn't add an island. Only then split by face direction.

Scripting gotchas:
- `bpy.ops.uv.smart_project` ignores the face selection from a script and re-projects the whole mesh, so never use it per chart.
- Selecting faces in Object Mode must also set their edges and verts, or a stale vertex selection flushes back to every face.

### 6. Keep islands packable
- No island longer than about a fifth of the atlas side: long tubes get extra evenly spaced cuts, and any long island is cut across at even surface distances.
- Quad-grid strips are laid out straight (each row its true length, centred), because curved arcs pack badly.
- **Compact pass:** islands filling under 30% of their smallest rectangle are split by face direction and unwrapped again. These are the spiky ones: a panel with a band hanging off it at an angle, or a fan cap with arms. Mean fill comes back at about 0.6.
- **Packing:** don't trust `bpy.ops.uv.pack_islands` for this. In Blender 5.2 it would not scale up one vehicle's islands (one island packed alone stayed at 0.13 x 0.26, leaving 2-8% coverage), though a plain plane packs fine. A skyline packer that turns each island to its smallest rectangle, lays it wider than tall, and binary-searches the largest uniform scale that fits (8 px gaps at 4K) is deterministic, keeps the texel tiers, and beat the operator (48.9% against 46.5% coverage).
- **Texture sets for big assets:** give each group of modules its own texture set and material.
  - A vehicle has about 150 m2 of unique surface, which one 4K sheet caps at about 250 px/m.
  - Aim for about 30-40 m2 per 4K set, which gives about 500-650 px/m (third-person hero vehicle). Put the biggest hero shell alone in its set.
  - Stacked copies never cross sets.
- **Very long parts** (hulls, guard rails, rub rails): an 18 m hull side or a 40 m rail won't be cut by an automatic seam finder, and one such island limits the whole set (2.6-25% coverage). Cut the LOW in the model script where nobody looks: a hull at plate butts, rails at every post (under the collar), bands every 2.5 m, and split a big hull into port and starboard modules with a set each. If the pipeline welds vertices within 0.02 mm, leave a 0.06 mm gap at these splits. Drop hidden inner skins (a solidified hull's inside, a deck underside) from the LOW: they take as much texture as the outside.

### 7. Identical parts share UV space
- **Which:** parts with the same topology whose vertices map onto each other by a rotation or a mirror (fan blades, mirrored lamps, struts, bolts, wheels).
- **How:** they're stacked on the master's island, left out of the pack, and removed from the bake copy, so each shared island bakes once.
- **When not:** a group is NOT shared when any member carries print (text would repeat or mirror), or when the high-poly surface each member bakes from differs. Check that within bake reach of the part, not its bounding box, which wrongly includes neighbours.

### 8. Texel tiers
- Islands boxed in by other parts (inside a core, under a seat, an inner shell behind armour) get half density, about 12% of the surface.
- Readable print gets more: about 5x for screens and 4x for labels. At a uniform 560 px/m a 13 cm screen got about 70 px and blurred.
- Report the main tier's density (area-weighted median), not the average.

### 9. Review, every time
- a picture of the UV layout;
- a checker (color grid) render of the low: squares even and square, seams off the hero surfaces;
- the log lines: shared instances, seams, relief rounds, final islands, coverage and texel density.
Iterate on the unwrap alone (stop before the bake) until those pass.
