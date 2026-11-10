#!/usr/bin/env python3
# rasterize_hlr_v6.py -- /tmp/hlr_edges_v6.json (mm view coords) -> line-art PNGs
# + views_v6.json for the composer. Self-calibrated target art sizes (px).
import json, os
from PIL import Image, ImageDraw

DRW = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v6/drawings"
EDGES = json.load(open("/tmp/hlr_edges_v6.json"))
OUT = os.path.join(DRW, "views_v6")
os.makedirs(OUT, exist_ok=True)

W, H = 1200, 900
CX, CY = 600.0, 450.0
INK = (26, 26, 26)
LW = 3

# DVP raw output is y-flipped for EVERY view class (v4-verified A/B composite);
# y-only negation -- x must never be touched (chiral plate text).
FLIP_Y = True

# target art max dimension in px (v4-sheet-like sizing)
TARGET_PX = {
    "flange_front": 620, "flange_side": 518, "flange_iso": 470,
    "bellows_front": 568, "bellows_iso": 450,
    "spool_front": 616, "spool_side": 518, "spool_iso": 420,
    "gasket_top": 638, "gasket_front": 638,
    "plate_top": 842,
    "asm_front": 700, "exp_iso": 740,
}
# views whose scale is driven by a specific mm span instead (keeps px/mm round
# for the composer's dimension math):
FORCED_PXMM = {
    "bellows_front": 494.0 / 48.0,   # v4 calibration, dims hardcode against it
    "asm_front": None,               # set from measured z-span below
}

meta = {}
for key, rec in EDGES.items():
    lines = rec["lines"]
    if not lines:
        print("[skip] %s: no lines" % key)
        continue
    if FLIP_Y:
        lines = [[[p[0], -p[1]] for p in ln] for ln in lines]
    xs = [p[0] for ln in lines for p in ln]
    ys = [p[1] for ln in lines for p in ln]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if key == "asm_front":
        zspan = y1 - y0
        s = 700.0 / zspan
    elif key in FORCED_PXMM and FORCED_PXMM[key]:
        s = FORCED_PXMM[key]
    else:
        s = TARGET_PX.get(key, 500) / max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    pxs, pys = [], []
    for ln in lines:
        pts = [(CX + (x - cx) * s, CY - (y - cy) * s) for x, y in ln]
        if len(pts) == 1:
            pts = pts * 2
        d.line(pts, fill=INK, width=LW, joint="curve")
        pxs += [p[0] for p in pts]
        pys += [p[1] for p in pts]
    bx0, bx1 = int(min(pxs)) - LW, int(max(pxs)) + LW
    by0, by1 = int(min(pys)) - LW, int(max(pys)) + LW
    p = os.path.join(OUT, key + ".png")
    img.save(p)
    meta[key] = {"path": p, "bbox": [bx0, by0, bx1, by1], "pxmm": s,
                 "mm_span": [round(x1 - x0, 2), round(y1 - y0, 2)],
                 "center_mm": [round(cx, 2), round(cy, 2)]}
    print("[%s] %s scale=%.4f px/mm art %dx%d px (mm %s)" % (
        key, rec["method"], s, bx1 - bx0, by1 - by0, meta[key]["mm_span"]))

with open(os.path.join(OUT, "views_v6.json"), "w") as f:
    json.dump(meta, f, indent=1)
print("[done] %d line-art views -> %s" % (len(meta), OUT))
