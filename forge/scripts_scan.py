"""Read the Python build scripts in a project (pure Python, no Blender).

Many artists build or finish models with bpy scripts. A script's imports and calls are the artist's own
modelling vocabulary: which helper kit they use and which operations they reach for most.
"""
import ast
import os
import re
import sys
from collections import Counter

STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"bpy", "bmesh", "mathutils", "bpy_extras", "gpu", "blf",
                                                          "addon_utils", "numpy", "PIL", "scipy"}
BORING = {"print", "len", "range", "min", "max", "abs", "int", "float", "str", "list", "dict", "set", "tuple", "zip",
          "enumerate", "sorted", "sum", "round", "isinstance", "getattr", "setattr", "hasattr", "open", "format",
          "append", "extend", "get", "items", "keys", "values", "join", "split", "replace", "format", "copy",
          "Vector", "Matrix", "Euler", "Quaternion", "radians", "degrees", "sin", "cos", "tan", "sqrt", "atan2",
          "exists", "dirname", "basename", "abspath", "insert", "index", "pop", "update", "strip", "lower", "upper",
          "startswith", "endswith", "add", "remove", "load", "dump", "loads", "dumps", "new", "link", "unlink",
          "select_set", "normalized", "cross", "dot", "lerp", "to_mesh", "free", "ensure_lookup_table",
          "argv", "exit", "write", "read", "makedirs", "listdir", "walk", "time", "sleep", "super", "type", "any",
          "all", "map", "filter", "next", "iter", "reversed", "bool", "repr", "id", "hash", "vars", "Counter",
          "defaultdict", "OrderedDict", "namedtuple", "deepcopy", "partial", "wraps", "seed", "random", "uniform",
          "randint", "choice", "pi", "floor", "ceil", "hypot", "acos", "asin", "fmod", "copysign", "isclose",
          "Translation", "Rotation", "Scale", "from_mesh", "ray_cast", "transform", "evaluated_get", "to_mesh_clear",
          "inverted", "to_euler", "to_quaternion", "to_matrix", "freeze", "calc_normals", "from_pydata", "validate",
          "temp_override", "mode_set", "ensure", "verify", "resize", "render", "save_as_mainfile", "open_mainfile"}
MODIFIER_TYPES = {"BEVEL", "SUBSURF", "WEIGHTED_NORMAL", "BOOLEAN", "MIRROR", "ARRAY", "SOLIDIFY", "SKIN", "SCREW",
                  "WELD", "TRIANGULATE", "DECIMATE", "DISPLACE", "SHRINKWRAP", "DATA_TRANSFER", "EDGE_SPLIT", "CURVE",
                  "SIMPLE_DEFORM", "LATTICE", "WIREFRAME", "REMESH", "SMOOTH", "CORRECTIVE_SMOOTH", "CAST", "NODES",
                  "ARMATURE", "MULTIRES", "TRIANGULATE", "EDGE_SPLIT", "UV_PROJECT", "NORMAL_EDIT", "SUBDIVISION"}
TOOL_NAME = re.compile(r"(check|render|shot|measure|review|compare|test|lookdev|beauty|audit|qa|preview|export|"
                       r"import|bake|origami|gameready|reassemble|probe|watch|capture)", re.I)


def _bpy_ops(node):
    """'mesh.primitive_cube_add' for bpy.ops.mesh.primitive_cube_add(...)."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    parts.reverse()
    if len(parts) >= 4 and parts[0] == "bpy" and parts[1] == "ops":
        return ".".join(parts[2:4])
    return None


def read_script(path, max_bytes=2_000_000):
    if os.path.getsize(path) > max_bytes:
        return None
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
        tree = ast.parse(src)
    except (SyntaxError, ValueError, OSError):
        return None
    imports, calls, ops, modifiers, defs = Counter(), Counter(), Counter(), Counter(), []
    lib_paths = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports[a.name.split(".")[0]] += 1
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports[node.module.split(".")[0]] += 1
        elif isinstance(node, ast.FunctionDef):
            defs.append(node.name)
        elif isinstance(node, ast.Call):
            f = node.func
            op = _bpy_ops(f)
            if op:
                ops[op] += 1
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            if name and name not in BORING and not name.startswith("_") and len(name) > 2:
                calls[name] += 1
            # modifiers.new("Name", "TYPE")
            if isinstance(f, ast.Attribute) and f.attr == "new" and len(node.args) >= 2:
                a1 = node.args[1]
                if isinstance(a1, ast.Constant) and isinstance(a1.value, str) and a1.value in MODIFIER_TYPES:
                    modifiers[a1.value] += 1
            # sys.path.insert(0, "...") tells where a helper kit lives
            if isinstance(f, ast.Attribute) and f.attr in ("insert", "append") and node.args:
                last = node.args[-1]
                if isinstance(last, ast.Constant) and isinstance(last.value, str) and ("/" in last.value or "\\" in last.value):
                    lib_paths.append(last.value)
    uses_bpy = "bpy" in imports or "bmesh" in imports or bool(ops)
    doc = ast.get_docstring(tree) or ""
    return {"uses_bpy": uses_bpy, "lines": src.count("\n") + 1,
            "imports": dict(imports), "kits": sorted(k for k in imports if k not in STDLIB),
            "calls": dict(calls.most_common(60)), "ops": dict(ops.most_common(30)),
            "modifiers": dict(modifiers), "defs": defs[:200], "lib_paths": lib_paths[:10],
            "doc": doc.strip().splitlines()[0][:200] if doc.strip() else "",
            "has_args": "argv" in src or "argparse" in imports}


def find_scripts(roots, skip_dir, max_files=3000):
    out = []
    for root in roots:
        for d, dirs, files in os.walk(root):
            dirs[:] = sorted(x for x in dirs if not skip_dir(x))
            for f in sorted(files):
                if f.endswith(".py") and not re.search(r"(_before_|backup|_old|_bak)", f):
                    out.append((root, os.path.join(d, f)))
                    if len(out) >= max_files:
                        return out
    return out
