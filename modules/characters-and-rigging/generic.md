## Characters and rigging

- Build a character as an assembly: a body form and skeleton first, then head, garments and gear as separate parts fitted over it.
- Model at the target engine's scale and proportions (Unreal mannequin about 1.8 m; about 7.5 heads tall for a realistic adult) and in the engine's rest pose (A-pose with arms about 45 degrees down is the safer default).
- Name bones the engine's way from the start (Unreal: `pelvis`, `spine_01`, `upperarm_l`...), so retargeting just works.
- Keep the body and head all-quad, with closed edge loops round the neck, limbs, eyes and mouth: those loops are what bend cleanly.
- Garments are cages wrapped over the body at a real clearance (a few millimetres), with Subdivision and Solidify; they must never dip inside the body.
- Hard gear (helmets, armour plates, weapons) rides rigidly on one bone; only soft parts get painted weights.
- At most 4 weights per vertex, every vertex weighted, weights normalised; test with poses before export.
<!-- more -->
### Order of work
1. Body form and skeleton from one spec (height, proportions, pose).
2. Head base mesh on measured head proportions; face loops round eyes and mouth.
3. Garments: cages over the form at clearance; gear on bones.
4. Weights, then pose tests (bend each joint to its limit and look for tearing and collapse).
5. Game-ready: retopology where needed, bake, export with the engine's skeleton.

### Face shape keys
For facial animation in engines that use them, name shape keys with the ARKit set (`jawOpen`, `eyeBlinkLeft`...), so tools that drive faces can find them.
