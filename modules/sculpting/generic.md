## Sculpting

- Keep the sculpt as its own object and stage; the clean quad mesh is what gets rigged, unwrapped and baked to.
- Block out with voxel remesh or dynamic topology, then move detail onto a clean quad base with Multires, so detail stays stable and bakes cleanly.
- Use face sets to separate regions and masks to protect them; keep symmetry on until the asymmetric pass.
- Sculpt at real-world scale so brush sizes and detail sizes mean the same on every model.
- Never ship the sculpt: bake its detail into normal and occlusion maps on the game mesh.
<!-- more -->
### Detail size
Measure how fine a sculpt goes by its median edge length as a share of the object's size: a full head sculpt at about 0.15% holds pores and wrinkles; 1% holds forms and big folds.

### From sculpt to game mesh
Retopologise by building quad loops over the sculpt (not by decimating), keep the loops a deforming character needs, then bake the sculpt onto it.
