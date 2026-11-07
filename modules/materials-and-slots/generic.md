## Materials and slots

- Material slot names are the material mapping in the engine: keep them short, stable and descriptive of the surface (`Steel`, `SteelDark`, `PaintDark`, `Rubber`, `Glass`, `Plastic`, `Trim`).
- Reuse one palette across assets instead of inventing names per model, so materials can be shared on import.
- One slot per part in the high poly; merge duplicate slots on the game mesh, and keep every glass slot its own material.
- Never rename a slot on a model that is already in the engine without re-importing with the new slot list.
<!-- more -->
### Palette first
Decide the surfaces before modelling: the base metal, a darker metal, paint, rubber, plastic, glass and any emissive parts. Assign them as you build each part, not at the end, so review renders already read correctly.

### Glass and emissives
Window glass, clear lenses, coloured lenses and mirrors each keep their own slot: a single shared glass material makes every lens the same colour. Emissive parts (LEDs, screens, lamps) sit inside real hardware and get their own slots so they can be driven in the engine.
