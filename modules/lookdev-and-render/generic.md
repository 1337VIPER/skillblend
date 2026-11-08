## Lighting, world and render

- Review models in EEVEE with AgX colour management, a soft sky or neutral HDRI world, and a simple key light (sun or large area light) so shapes and bevels read.
- Keep one review camera per model with a normal lens (about 50 mm) plus orthographic front, side and top views for checking against the reference.
- Judge shading under the lighting it will be seen in: a dark scene turns metal near-black and hides dark print.
- Don't bake the review lighting into anything; it is only for judging the model.
<!-- more -->
### A quick review rig
Sky Texture world at strength 0.5-1.0, one sun at 3-4 W/m2 from above and to the side, and one area light opposite at low power to lift the shadows. Render 1920x1080 for full views and tighter crops (60-85 mm lens) for joints and details.

### What `style.setup_render()` does
It sets the measured render engine, colour management view transform and look, and builds the measured kind of world (sky or flat colour, at the measured strength), so review renders match the artist's own.
