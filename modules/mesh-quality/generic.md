## Mesh quality

- Keep quads close to square where the surface curves; long thin faces belong only on flat strips and chamfers.
- Keep quad corners near 90 degrees on curved surfaces: skewed quads shade unevenly once subdivided or baked.
- Keep quads flat: a bent quad (one corner off its plane) triangulates differently in the engine and the bake shows a crease.
- Triangles and n-gons are fine on flat, hard-surface faces with a bevel or weighted normals; keep them off curved and subdivided surfaces.
- No non-manifold edges, zero-area faces or stray loose vertices in anything you ship.
- Put poles (3- and 5+-edge vertices) on flat areas or hard edges, never in the middle of a smooth curve, where they pinch.
<!-- more -->
### Reading the measurements
- **Aspect**: a face's longest edge over its shortest. 1 is square; chamfer strips are naturally 10:1 or more.
- **Skew**: how far the worst corner of a quad is from 90 degrees.
- **Bent quads**: the fourth corner sits more than 5% of the face size off the plane of the other three.
- **Pinching**: on the subdivided result, a pole whose shading bends much more than its neighbours'.
- **Edge profile**: the share of edges that are flat, smooth, soft, hard or sharp (by the angle between their faces). Hard-surface base meshes are mostly flat and sharp, and the bevel modifier rounds them; SubD cages are mostly soft.
