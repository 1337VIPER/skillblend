## Structure and assemblies

- One real part = one object: anything that would be a separate piece in the factory gets its own object, bevel and material slot.
- Group parts into assemblies (one collection per assembly, or a parent empty), named so the asset reads in the outliner.
- Give every model the parts a real one has: fasteners, seams, joints and mounts carry most of the detail read, so model them rather than painting them.
- Put pivots where things turn or mount (hinges, wheel centres, trigger pivots) and add empties for sockets the engine will use.
- Spend triangles where they are seen: round parts get enough segments to read round at the camera distance, small hidden parts get fewer.
<!-- more -->
### Breaking an object down
Write the assembly tree before modelling: the main body, then each bolt-on assembly, then the parts inside each. Count members against the reference (bolts on a flange, slats in a vent, rungs on a ladder). Missing or extra members are the most common thing that makes a model read as "not quite right".

### Detail density
Small parts are dense relative to their size; big panels are light. A model that has the same triangle density everywhere either wastes triangles on flat panels or starves the small parts that carry the read.

### Round parts
Pick a segment count per size band and keep to it across the model (for example 12 for a screw head, 24-32 for a knob, 48-64 for a wheel or lens). Mixed segment counts on parts of the same size read as careless.
