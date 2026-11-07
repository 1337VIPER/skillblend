"""Check a .blend against this skill's style.

    blender -b --factory-startup MODEL.blend --python scripts/style_check.py [-- --json OUT.json]

Measures the open file with analyse_blend.py, runs every check in scripts/checks/,
and prints one line per finding. The last line is "STYLE ok" when nothing needs
attention, or "STYLE n warning(s), m note(s)". Fix warnings, or say why they're intended.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyse_blend  # noqa: E402

with open(os.path.join(HERE, "..", "style.json"), encoding="utf-8") as fh:
    STYLE = json.load(fh)["numbers"]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    doc = analyse_blend.analyse()
    findings = []
    cdir = os.path.join(HERE, "checks")
    for fn in sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []:
        if not fn.endswith(".py"):
            continue
        spec = importlib.util.spec_from_file_location("check_" + fn[:-3].replace("-", "_"), os.path.join(cdir, fn))
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            for sev, msg in mod.check(doc, STYLE):
                findings.append({"module": fn[:-3], "severity": sev, "message": msg})
        except Exception as exc:
            findings.append({"module": fn[:-3], "severity": "error", "message": f"check failed: {exc!r}"})
    for f in findings:
        print(f"[{f['severity']}] {f['module']}: {f['message']}")
    warns = sum(1 for f in findings if f["severity"] in ("warn", "error"))
    notes = len(findings) - warns
    print("STYLE ok" if not findings else f"STYLE {warns} warning(s), {notes} note(s)")
    if "--json" in argv:
        out = argv[argv.index("--json") + 1]
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"findings": findings, "analysis": doc}, fh, indent=1)


main()
