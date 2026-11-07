"""Measured rules: how the artist scripts models (from the project's bpy scripts, read as text)."""
from collections import Counter


def rules(ctx):
    L, r = ctx.lib, ctx.result
    every = [d["_script"] for d in ctx.files if "_script" in d]
    scripts = [s for s in every if s.get("role", "build") == "build"]
    tools = [s for s in every if s.get("role") == "tool"]
    kit_files = [s for s in every if s.get("role") == "kit"]
    r.extra["kit_files"] = [s["path"] for s in kit_files]
    if not scripts:
        if tools:
            r.rule(f"{len(tools)} helper scripts (checks, renders, exports) but no model-building scripts.")
        return r
    paired = [s for s in scripts if s.get("blends")]
    blends = {b for d in ctx.all_files for b in [d.get("_submission", {}).get("file")] if b}
    r.number("scripted_builds", True, f"{len(scripts)} bpy scripts")
    r.headline(f"Models are built from Python scripts ({len(scripts)} build script{'s' if len(scripts) != 1 else ''} in the project, "
               f"{len(paired)} next to the .blend {'it makes' if len(scripts) == 1 else 'they make'}).")
    if tools:
        r.rule(f"Besides the builders there are {len(tools)} tool scripts (checks, review renders, measuring, export), e.g. "
               + ", ".join(f"`{t['file']}`" for t in tools[:5]) + ": the artist verifies models with scripts too.")
    r.rule(f"{len(scripts)} model-building script(s); {len(paired)} sit next to a .blend with the same name "
           f"(e.g. {', '.join('`' + s['file'] + '`' for s in paired[:3]) or 'none'}).")
    kits = Counter(k for s in scripts for k in s.get("kits", []))
    if kits:
        top = [k for k, _ in kits.most_common(6)]
        r.number("helper_kits", top, "imported by the scripts")
        r.rule("Helper kits the scripts import: " + ", ".join(f"`{k}` ({c} script{'s' if c != 1 else ''})" for k, c in kits.most_common(6))
               + ". Build new models with the same kit instead of raw bpy calls.")
        if kit_files:
            r.rule("The kit itself is in the project: " + ", ".join(
                f"`{k['file']}` ({len(k.get('defs', []))} functions: " + ", ".join(f"`{d}`" for d in k.get("defs", [])[:12]) + ")"
                for k in kit_files) + ".")
        r.headline("They're assembled from the artist's own helper kit (" + ", ".join(f"`{k}`" for k in top[:3]) + ").")
    calls = Counter()
    for s in scripts:
        calls.update(s.get("calls", {}))
    defined = {d for s in scripts for d in s.get("defs", [])}
    vocab = [(c, n) for c, n in calls.most_common(80) if n >= 2][:24]
    if vocab:
        r.number("top_calls", [c for c, _ in vocab[:15]], "most-called functions in the build scripts")
        r.rule("The modelling vocabulary, most-called first: " + ", ".join(f"`{c}()` {n}" for c, n in vocab) + ".")
    ops = Counter()
    for s in scripts:
        ops.update(s.get("ops", {}))
    if ops:
        r.rule("Blender operators called directly: " + ", ".join(f"`{o}` {n}" for o, n in ops.most_common(10)) + ".")
    mods = Counter()
    for s in scripts:
        mods.update(s.get("modifiers", {}))
    if mods:
        r.rule("Modifiers created in code: " + ", ".join(f"{m} {n}" for m, n in mods.most_common(10)) + ".")
    docd = L.share(scripts, lambda s: s.get("doc"))
    args = L.share(scripts, lambda s: s.get("has_args"))
    r.rule(f"Scripts are about {L.fmt(L.median(s['lines'] for s in scripts))} lines; {L.percent(docd)} start with a docstring, "
           f"{L.percent(args)} take command-line arguments (`-- OUT_DIR ...`).")
    examples = [s for s in paired if s.get("doc")][:5]
    for s in examples:
        r.rule(f"`{s['file']}`: {s['doc']}")
    lib_dirs = sorted({p for s in scripts for p in s.get("lib_paths", [])})
    r.extra["lib_paths"] = lib_dirs
    r.extra["script_files"] = [s["path"] for s in scripts]
    if ctx.answers.get("script_notes"):
        r.rule(f"Artist's notes: {ctx.answers['script_notes']}.")
    return r
