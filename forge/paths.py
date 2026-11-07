import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(REPO, "forge")
LIB = os.path.join(PKG, "lib")
BLENDER = os.path.join(PKG, "blender")
TEMPLATES = os.path.join(PKG, "templates")
MODULES = os.path.join(REPO, "modules")
DEFAULT_WORKSPACE = os.environ.get("FORGE_WORKSPACE") or os.path.join(REPO, "workspace")
