## Geometry Nodes

- Use Geometry Nodes where a setup is repeated or must stay editable: cables and pipes swept from curves, parts instanced along edges or on bolt circles, scattered surface detail.
- Expose the numbers an artist would tweak (radius, count, spacing, seed) as group inputs, with sensible defaults and limits.
- Realize instances before export and apply the modifier on the game mesh; keep the live setup on the high-poly source.
- Name node groups for what they make (`CableFromCurve`, `BoltCircle`), and reuse them across assets instead of rebuilding.
<!-- more -->
### A cable from a curve
Group Input (curve) > Curve to Mesh, with a Curve Circle (12-16 segments) as the profile whose Radius is a group input. Add Set Curve Radius if the cable should taper, and Set Material for the jacket.

### Instancing hardware
Mesh Line or the points of a circle > Instance on Points with an Object Info (the bolt) > Realize Instances. Align instances to the surface normal so heads sit flat.
