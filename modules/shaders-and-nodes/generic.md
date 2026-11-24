## Shaders and node setups

- Start every material from a Principled BSDF and set real values first: metals are Metallic 1 with their colour in Base Color; painted, plastic and rubber surfaces are Metallic 0.
- Give flat surfaces life with a cheap procedural break-up before any texturing: a Noise Texture into a Color Ramp into Roughness, scaled to the object (Texture Coordinate > Object).
- Use a shader Bevel node into Normal for small rounded edges that don't need geometry, and keep real bevels for silhouettes and anything that bakes.
- Name materials for the surface (`SteelDark`, `PaintGreen`, `Rubber`) and reuse the same names and values across assets.
- Image textures: colour maps in sRGB, everything else (roughness, metallic, normal) as Non-Color; use Box projection with a blend for quick triplanar mapping on unwrapped-later parts.
- Check materials under the lighting they will be seen in: dark metals reflect a dark scene and go near-black.
<!-- more -->
### A review material in four nodes
Texture Coordinate (Object) > Noise Texture (scale 15-30) > Color Ramp (two greys around the target roughness) > Principled Roughness. It reads as real surface variation in review renders and costs nothing, and the final texture pass replaces it.

### Edge wear without textures
A Geometry node's Pointiness (Cycles) or an Ambient Occlusion node, through a Color Ramp, gives an edge mask for wear and dirt. Keep it subtle in review renders; the baked texture set does the real job.

### What `style.material()` does
`style.material(obj, "SteelDark")` builds the Principled values for that name (base colour, metallic, roughness, emission) and sets the viewport colour to match. It takes them from the artist's measured recipe when their files showed one, adding the noise break-up if they drive roughness procedurally. For a name their files didn't show it uses the standard palette (`Steel`, `SteelDark`, `Paint`, `PaintDark`, `Rubber`, `Plastic`, `Glass`, `Trim`, `Emissive`), by exact name or by what the name says (`RubberGrip` is rubber). For anything else, say the colour yourself: `style.material(obj, "CrateGreen", color=(0.2, 0.27, 0.19))`. A material left at Blender's default grey fails the style check.
