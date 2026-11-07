#!/usr/bin/env python
"""Score a model's silhouette against the reference picture: does the structure match? (numpy, Pillow, scipy only)

Both silhouettes are masked, turned so their long axis is level, scaled to the same length and laid over each other
(every mirror is tried; the best fit wins). Proportion errors then show as numbers instead of impressions:

  IoU            overlap of the two silhouettes (1 = identical). Aim for >= 0.90 on a replica, 0.85 is "close".
  aspect         height / length of each; a fat or skinny part shows here first.
  openings       holes through the part in each (a missing hole or ring shows here).
  thickness      the silhouette's height in 12 slices along the length, model vs reference, as % of the length;
                 the slices marked << or >> are where to fix the outline (too thin / too thick).
  overlay PNG    grey = both, red = in the reference only (missing on the model), cyan = on the model only (extra).

  python ref_compare.py REF.png RENDER_f.png --out cmp.png [--ref-bg auto | --ref-rgb R,G,B ... | --ref-hsv ...]
                 [--model-bg auto] [--tol 60] [--no-rotate] [--mirror auto|none|x|y|xy]

The render is the model's orthographic view from the same side as the picture (an orthographic front render, or a
crop view). Use --no-rotate when both are already posed the same way (it keeps a curved part's own orientation).
"""
import argparse, math, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ref_trace import load, make_mask, largest

W = 800    # the common length in pixels


def principal_angle(m):
    ys, xs = np.nonzero(m)
    cov = np.cov(np.vstack([xs - xs.mean(), ys - ys.mean()]))
    ev, evec = np.linalg.eigh(cov)
    return math.degrees(math.atan2(evec[1, 1], evec[0, 1]))


def normalise(m, rotate=True):
    """level the long axis, crop, scale to length W; returns the mask (bool)"""
    if rotate:
        m = ndi.rotate(m.astype(np.uint8), principal_angle(m), reshape=True, order=0) > 0
    ys, xs = np.nonzero(m)
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = m.shape
    if not rotate and h > w:
        s = W / h
    else:
        s = W / max(w, 1)
    img = Image.fromarray(m.astype(np.uint8) * 255).resize((max(1, round(w * s)), max(1, round(h * s))), Image.NEAREST)
    return np.asarray(img) > 127


def place(a, b):
    """both masks centred on one canvas"""
    H, Wd = max(a.shape[0], b.shape[0]) + 4, max(a.shape[1], b.shape[1]) + 4
    out = []
    for m in (a, b):
        c = np.zeros((H, Wd), bool)
        y0, x0 = (H - m.shape[0]) // 2, (Wd - m.shape[1]) // 2
        c[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] = m
        out.append(c)
    return out


def iou(a, b):
    return (a & b).sum() / max((a | b).sum(), 1)


def count_openings(m):
    filled = ndi.binary_fill_holes(m)
    lab, n = ndi.label(filled & ~m)
    sizes = ndi.sum(filled & ~m, lab, range(1, n + 1)) if n else []
    return int(sum(1 for s in sizes if s > 0.0004 * m.sum()))


def profile(m, along_x, n=12):
    """the silhouette's thickness per slice along its length, as % of that length"""
    if not along_x:
        m = m.T
    L, out = m.shape[1], []
    for i in range(n):
        rows = np.nonzero(m[:, int(i * L / n):int((i + 1) * L / n)].any(axis=1))[0]
        out.append(100.0 * (rows.max() - rows.min() + 1) / L if len(rows) else 0.0)
    return out


def aspect(m, along_x):
    return m.shape[0] / m.shape[1] if along_x else m.shape[1] / m.shape[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ref"); ap.add_argument("model"); ap.add_argument("--out", default="")
    ap.add_argument("--ref-bg", default=None); ap.add_argument("--ref-rgb", action="append"); ap.add_argument("--ref-hsv")
    ap.add_argument("--model-bg", default="auto"); ap.add_argument("--model-rgb", action="append"); ap.add_argument("--model-hsv")
    ap.add_argument("--tol", type=float, default=60.0); ap.add_argument("--model-tol", type=float, default=30.0)
    ap.add_argument("--no-rotate", action="store_true"); ap.add_argument("--mirror", default="auto", choices=["auto", "none", "x", "y", "xy"])
    a = ap.parse_args()
    if not (a.ref_bg or a.ref_rgb or a.ref_hsv):
        a.ref_bg = "auto"
    ref = ndi.binary_fill_holes(largest(make_mask(load(a.ref), a.ref_bg, a.ref_rgb or (), a.tol, a.ref_hsv), 1)) & \
        largest(make_mask(load(a.ref), a.ref_bg, a.ref_rgb or (), a.tol, a.ref_hsv), 1)
    mod = largest(make_mask(load(a.model), a.model_bg, a.model_rgb or (), a.model_tol, a.model_hsv), 1)
    rot = not a.no_rotate
    rn, mn = normalise(ref, rot), normalise(mod, rot)
    flips = {"none": lambda m: m, "x": lambda m: m[:, ::-1], "y": lambda m: m[::-1, :], "xy": lambda m: m[::-1, ::-1]}
    tried = flips if a.mirror == "auto" else {a.mirror: flips[a.mirror]}
    best = max(((iou(*place(rn, f(mn))), k) for k, f in tried.items()))
    score, mk = best
    R, M = place(rn, flips[mk](mn))
    along_x = R.shape[1] >= R.shape[0]
    pr, pm = profile(R, along_x), profile(M, along_x)
    ra, ma = aspect(rn, along_x), aspect(mn, along_x)
    print("IoU %.3f  (%s)   mirror %s" % (score, "match" if score >= 0.9 else "close" if score >= 0.85 else "structure differs", mk))
    print("aspect (thickness / length): reference %.3f  model %.3f  (%+.0f%%)" % (ra, ma, 100 * (ma / ra - 1)))
    print("openings: reference %d  model %d" % (count_openings(ref), count_openings(mod)))
    print("thickness per slice along the length (% of length), reference -> model:")
    for i, (x, y) in enumerate(zip(pr, pm)):
        d = (y - x) / max(x, 0.5)
        flag = " >>" if d > 0.12 else " <<" if d < -0.12 else ""
        print("  slice %2d (%3d-%3d%%): %5.1f -> %5.1f%s" % (i, i * 100 // len(pr), (i + 1) * 100 // len(pr), x, y, flag))
    if a.out:
        rgb = np.zeros(R.shape + (3,), np.uint8)
        rgb[R & M] = (150, 150, 150)
        rgb[R & ~M] = (235, 50, 50)
        rgb[M & ~R] = (40, 220, 235)
        Image.fromarray(rgb).save(a.out)
        print("overlay:", a.out, "(grey both, red reference only = missing, cyan model only = extra)")


if __name__ == "__main__":
    main()
