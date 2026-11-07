#!/usr/bin/env python
"""Trace a reference picture into real-size outlines and openings for a model script (numpy, Pillow, scipy only).

The structure of a replica comes from the picture, not from guesses: each part's silhouette is traced, scaled to
one known real dimension, simplified to a point list, and its openings (round holes, slots, the finger ring) are
measured. Paste the points into the model script's outlines; read the openings into hole/pocket calls.

  python ref_trace.py trace REF.png --part handle --rgb 40,140,40 --tol 70 --length-mm 195 --out knife_ref.json
  python ref_trace.py trace REF.png --part whole --bg auto --length-mm 195 --out knife_ref.json --preview trace.png
  python ref_trace.py pick REF.png 120,340 300,410        # print the colour at pixels (to choose --rgb / --hsv)
  python ref_trace.py check knife_ref.json                 # outlines valid? (self-crossing, winding, tiny edges)

Masks (combine to taste; every part is one run, all parts land in one JSON):
  --bg auto|R,G,B   everything that differs from the background (auto: the four corners' median colour)
  --rgb R,G,B       pixels near this colour (repeatable: union); --tol is the RGB distance (default 60)
  --hsv H0,H1,S0,V0,V1   hue range 0-360 (wraps if H0>H1), minimum saturation 0-1, value range 0-1
Scale and frame: the whole object's long side (--axis long, or x / y: its width / height in the picture) is
--length-mm; once a JSON has a scale, later parts reuse it (and its origin) so all parts share one frame.
Output units are metres, u to the picture's right and v up, origin at the object's bounding-box centre unless
--origin X,Y (pixels). --flip-u mirrors u (when the model's forward is the picture's left).
"""
import argparse, json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

NBR = [(0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1)]    # Moore ring, clockwise from west


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)


def rgb_arg(s):
    return np.array([float(x) for x in s.split(",")], np.float32)


def corner_colour(img, k=8):
    h, w, _ = img.shape
    patches = [img[:k, :k], img[:k, -k:], img[-k:, :k], img[-k:, -k:]]
    return np.median(np.concatenate([p.reshape(-1, 3) for p in patches]), axis=0)


def hsv_mask(img, spec):
    h0, h1, s0, v0, v1 = [float(x) for x in spec.split(",")]
    hsv = np.asarray(Image.fromarray(img.astype(np.uint8)).convert("HSV")).astype(np.float32) / 255.0
    hue = hsv[..., 0] * 360.0
    inh = (hue >= h0) & (hue <= h1) if h0 <= h1 else (hue >= h0) | (hue <= h1)
    return inh & (hsv[..., 1] >= s0) & (hsv[..., 2] >= v0) & (hsv[..., 2] <= v1)


def make_mask(img, bg=None, rgbs=(), tol=60.0, hsv=None, clean=1):
    m = np.zeros(img.shape[:2], bool)
    if bg:
        c = corner_colour(img) if bg == "auto" else rgb_arg(bg)
        m |= np.linalg.norm(img - c, axis=2) > tol
    for r in rgbs:
        m |= np.linalg.norm(img - rgb_arg(r), axis=2) < tol
    if hsv:
        m |= hsv_mask(img, hsv)
    if clean:
        m = ndi.binary_opening(m, iterations=clean)
        m = ndi.binary_closing(m, iterations=clean)
    return m


def largest(mask, keep=1):
    lab, n = ndi.label(mask)
    if n == 0:
        return mask
    sizes = ndi.sum(mask, lab, range(1, n + 1))
    order = np.argsort(sizes)[::-1][:keep]
    return np.isin(lab, order + 1)


def trace_boundary(mask):
    """Moore-neighbour trace of the outer boundary of the (single) component, as (row, col) pixels, clockwise."""
    m = np.pad(mask, 1)
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        return []
    start = (int(ys[0]), int(xs[0]))
    pts, p, back = [start], start, 0                  # entered the start pixel from its west neighbour (background)
    for _ in range(m.size):
        for k in range(1, 9):
            i = (back + k) % 8
            q = (p[0] + NBR[i][0], p[1] + NBR[i][1])
            if m[q]:
                prev = (p[0] + NBR[(i - 1) % 8][0], p[1] + NBR[(i - 1) % 8][1])
                back = NBR.index((prev[0] - q[0], prev[1] - q[1]))
                p = q
                break
        else:
            break                                     # a lone pixel
        if p == start and len(pts) > 2:
            break
        pts.append(p)
    return [(y - 1, x - 1) for y, x in pts]


def smooth(pts, n=2):
    a = np.array(pts, np.float64)
    for _ in range(n):
        a = (np.roll(a, 1, 0) + 2 * a + np.roll(a, -1, 0)) / 4.0
    return a


def rdp(a, eps):
    """Douglas-Peucker on a closed loop: split at the two farthest points, simplify each half."""
    if len(a) < 4:
        return a
    i0 = 0
    i1 = int(np.argmax(np.linalg.norm(a - a[0], axis=1)))

    def simp(p):
        if len(p) < 3:
            return p
        s, e = p[0], p[-1]
        d = e - s
        L = np.hypot(*d)
        dist = np.abs(d[0] * (p[:, 1] - s[1]) - d[1] * (p[:, 0] - s[0])) / L if L > 0 else np.linalg.norm(p - s, axis=1)
        k = int(np.argmax(dist))
        if dist[k] > eps:
            return np.vstack([simp(p[:k + 1])[:-1], simp(p[k:])])
        return np.vstack([s, e])
    first = simp(a[i0:i1 + 1])
    second = simp(np.vstack([a[i1:], a[:1]]))
    return np.vstack([first[:-1], second[:-1]])


def openings(filled, mask, min_px):
    """the holes: inside the filled silhouette, not part of the mask. Round ones get a radius, long ones a slot."""
    lab, n = ndi.label(filled & ~mask)
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if len(ys) < min_px:
            continue
        cy, cx = ys.mean(), xs.mean()
        cov = np.cov(np.vstack([xs - cx, ys - cy]))
        ev, evec = np.linalg.eigh(cov)
        major, minor = 4 * math.sqrt(max(ev[1], 1e-9)), 4 * math.sqrt(max(ev[0], 1e-9))    # full lengths (ellipse fit)
        ang = math.degrees(math.atan2(-evec[1, 1], evec[0, 1]))                               # major axis, v up
        out.append({"px": (cx, cy), "area_px": int(len(ys)), "major_px": major, "minor_px": minor, "angle": ang,
                    "boundary": trace_boundary(lab == i)})
    return out


class Frame:
    def __init__(self, scale_m_per_px, origin, flip_u=False):
        self.s, self.o, self.f = scale_m_per_px, origin, -1.0 if flip_u else 1.0

    def uv(self, x, y):
        return (round(self.f * (x - self.o[0]) * self.s, 5), round((self.o[1] - y) * self.s, 5))


def cmd_trace(a):
    img = load(a.image)
    data = json.load(open(a.out)) if a.out and os.path.exists(a.out) else {"image": os.path.abspath(a.image), "parts": {}}
    mask = make_mask(img, a.bg, a.rgb or (), a.tol, a.hsv, a.clean)
    mask = largest(mask, a.keep)
    if not mask.any():
        sys.exit("empty mask: pick colours with `ref_trace.py pick` or loosen --tol")
    if mask[0].any() and mask[-1].any() and mask[:, 0].any() and mask[:, -1].any():
        sys.exit("the mask touches all four edges: it caught the background. Pick the part's colour with "
                 "`ref_trace.py pick`, or use a picture where the part stands out from the background")
    filled = ndi.binary_fill_holes(mask)
    if "scale_m_per_px" not in data or a.rescale:
        whole = ndi.binary_fill_holes(largest(make_mask(img, "auto", (), a.tol, None, a.clean), 1)) if a.whole_bg else filled
        ys, xs = np.nonzero(whole)
        w, h = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
        span = {"long": max(w, h), "x": w, "y": h}[a.axis]
        data["scale_m_per_px"] = a.length_mm / 1000.0 / float(span)
        data["origin_px"] = [float(x) for x in a.origin.split(",")] if a.origin else [float(xs.min() + xs.max()) / 2.0, float(ys.min() + ys.max()) / 2.0]
        data["flip_u"] = a.flip_u
        data["size_mm"] = [round(float(w) * data["scale_m_per_px"] * 1000, 1), round(float(h) * data["scale_m_per_px"] * 1000, 1)]
    F = Frame(data["scale_m_per_px"], data["origin_px"], data.get("flip_u", False))
    eps = a.eps_mm / 1000.0 / F.s
    loop = rdp(smooth(trace_boundary(filled)), eps)
    outline = [F.uv(x, y) for y, x in loop]
    if F.f < 0:
        outline.reverse()                              # mirroring flips the winding: keep it counter-clockwise
    if signed_area(outline) < 0:
        outline.reverse()
    holes = []
    for o in openings(filled, mask, a.min_hole_px):
        c = F.uv(*o["px"])
        maj, mnr = o["major_px"] * F.s, o["minor_px"] * F.s
        h = {"center": c, "area_mm2": round(o["area_px"] * F.s * F.s * 1e6, 1)}
        if mnr / maj > 0.7:
            h.update(kind="round", r=round(math.sqrt(o["area_px"] / math.pi) * F.s, 5))
        else:
            h.update(kind="slot", length=round(maj, 5), width=round(mnr, 5), angle_deg=round(o["angle"] * F.f, 1))
        b = rdp(smooth(o["boundary"]), eps)
        if len(b) < 3:
            continue                                   # a speck, not an opening
        h["outline"] = [F.uv(x, y) for y, x in b]
        holes.append(h)
    holes.sort(key=lambda h: (-h["center"][1], h["center"][0]))
    data["parts"][a.part] = {"outline": outline, "holes": holes, "points": len(outline),
                             "area_mm2": round(float(mask.sum()) * F.s * F.s * 1e6, 1),
                             "mask": {"bg": a.bg, "rgb": a.rgb, "tol": a.tol, "hsv": a.hsv}}
    if a.out:
        json.dump(data, open(a.out, "w"), indent=1)
    print("part %s: %d points, %d openings, size %s mm (whole), scale %.4f mm/px" % (
        a.part, len(outline), len(holes), data["size_mm"], F.s * 1000))
    for i, h in enumerate(holes):
        print("  opening %d: %s at (%.4f, %.4f) %s" % (i, h["kind"], h["center"][0], h["center"][1],
              "r %.4f" % h["r"] if h["kind"] == "round" else "%.4f x %.4f at %.0f deg" % (h["length"], h["width"], h["angle_deg"])))
    problems = outline_problems(outline)
    print("  outline check:", "ok" if not problems else "; ".join(problems))
    if a.preview:
        preview(a.image, data, a.preview)
        print("  preview:", a.preview)


def preview(image, data, out):
    im = Image.open(image).convert("RGB")
    im = Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), 0.45)
    d = ImageDraw.Draw(im)
    s, o, f = data["scale_m_per_px"], data["origin_px"], -1.0 if data.get("flip_u") else 1.0
    px = lambda p: (o[0] + f * p[0] / s, o[1] - p[1] / s)
    cols = [(255, 60, 220), (60, 230, 255), (255, 220, 40), (120, 255, 90), (255, 120, 60)]
    for k, (name, part) in enumerate(data["parts"].items()):
        c = cols[k % len(cols)]
        pts = [px(p) for p in part["outline"]]
        d.line(pts + pts[:1], fill=c, width=2)
        for p in pts:
            d.ellipse([p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2], fill=c)
        d.text((pts[0][0] + 4, pts[0][1]), name, fill=c)
        for i, h in enumerate(part["holes"]):
            hp = [px(p) for p in h["outline"]]
            d.line(hp + hp[:1], fill=(255, 255, 255), width=1)
            cx, cy = px(h["center"])
            d.text((cx + 3, cy - 6), str(i), fill=(255, 255, 255))
    d.line([(o[0] - 6, o[1]), (o[0] + 6, o[1])], fill=(255, 0, 0)); d.line([(o[0], o[1] - 6), (o[0], o[1] + 6)], fill=(255, 0, 0))
    im.save(out)


def signed_area(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def _cross(p, q, r, s):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return orient(p, q, r) * orient(p, q, s) < 0 and orient(r, s, p) * orient(r, s, q) < 0


def outline_problems(pts, min_edge=0.0002):
    """what would break a slab built from this loop: self-crossings, repeated points, edges under 0.2 mm"""
    n, out = len(pts), []
    if n < 3:
        return ["fewer than 3 points"]
    if abs(signed_area(pts)) < 1e-9:
        out.append("zero area")
    short = [i for i in range(n) if math.dist(pts[i], pts[(i + 1) % n]) < min_edge]
    if short:
        out.append("%d edges under %.1f mm (first at point %d)" % (len(short), min_edge * 1000, short[0]))
    crossings = []
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _cross(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n]):
                crossings.append((i, j))
    if crossings:
        out.append("crosses itself %d times (edges %s)" % (len(crossings), crossings[:4]))
    return out


def cmd_check(a):
    data = json.load(open(a.json))
    parts = data["parts"] if "parts" in data else {"outline": {"outline": data}}
    bad = 0
    for name, part in parts.items():
        loops = [("outline", part["outline"])] + [("opening %d" % i, h["outline"]) for i, h in enumerate(part.get("holes", []))]
        for what, pts in loops:
            p = outline_problems([tuple(x) for x in pts])
            bad += bool(p)
            print("%s %s: %s (%d points, %s)" % (name, what, "ok" if not p else "; ".join(p), len(pts),
                                                 "ccw" if signed_area(pts) > 0 else "cw"))
    sys.exit(1 if bad else 0)


def cmd_pick(a):
    img = load(a.image)
    for xy in a.xy:
        x, y = [int(v) for v in xy.split(",")]
        r, g, b = img[y, x]
        hsv = Image.fromarray(np.uint8([[img[y, x]]])).convert("HSV").getpixel((0, 0))
        print("(%d,%d) rgb %d,%d,%d  hsv %.0f,%.2f,%.2f" % (x, y, r, g, b, hsv[0] / 255 * 360, hsv[1] / 255, hsv[2] / 255))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trace")
    t.add_argument("image"); t.add_argument("--part", default="whole"); t.add_argument("--out", default="")
    t.add_argument("--bg"); t.add_argument("--rgb", action="append"); t.add_argument("--hsv"); t.add_argument("--tol", type=float, default=60.0)
    t.add_argument("--clean", type=int, default=1); t.add_argument("--keep", type=int, default=1)
    t.add_argument("--length-mm", type=float, default=100.0); t.add_argument("--axis", choices=["long", "x", "y"], default="long")
    t.add_argument("--whole-bg", action="store_true", help="scale from the whole object against the background, not this part")
    t.add_argument("--rescale", action="store_true", help="recompute the scale and origin even if the JSON has them")
    t.add_argument("--origin"); t.add_argument("--flip-u", action="store_true")
    t.add_argument("--eps-mm", type=float, default=0.4, help="simplification tolerance (smaller = more points)")
    t.add_argument("--min-hole-px", type=int, default=30); t.add_argument("--preview", default="")
    c = sub.add_parser("check"); c.add_argument("json")
    p = sub.add_parser("pick"); p.add_argument("image"); p.add_argument("xy", nargs="+")
    a = ap.parse_args()
    {"trace": cmd_trace, "check": cmd_check, "pick": cmd_pick}[a.cmd](a)


if __name__ == "__main__":
    main()
