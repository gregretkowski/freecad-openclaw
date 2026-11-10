#!/usr/bin/env python3
# rasterize_asm_v7.py -- asm_front + asm_left -> PNGs in views_extra/, updating
# views_merged.json. Scale matches the v6-era pxmm (700 px / 156 mm) so the
# sheet5 paste + balloon calibration in make_sheets_v7.py stays valid.
import json, os
from PIL import Image, ImageDraw

DRW7 = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v7/drawings"
OUTD = os.path.join(DRW7, "views_extra")
EDGES = json.load(open("/tmp/hlr_edges_v7_asm.json"))
MERGED = os.path.join(OUTD, "views_merged.json")

W, H = 1200, 900
CX, CY = 600.0, 450.0
INK = (26, 26, 26)
LW = 3
# getVisibleEdges returns y-DOWN page coords: map directly, NO pre-flip.
# (2026-10-28 bug: pre-flip mirrored the view; plate rendered at canvas top
#  while balloon anchors (world math) pointed at the bottom. Empirical proof:
#  plate world z -26..-11 -> edge v +60.5..+75.5, i.e. v = zc - z, y-down.)
FLIP_Y = False
# v6 asm_front calibration: 700 px tall over 156 mm
TARGET_PX = {"asm_front": 700, "asm_left": 700}
KNOWN = {"asm_front": (70.0, 156.0), "asm_left": (73.0, 156.0)}

merged = json.load(open(MERGED))
for key, rec in EDGES.items():
    lines = rec["lines"]
    assert lines, key + " has no lines"
    for span, kn in zip(("u_span", "v_span"), KNOWN[key]):
        assert abs(rec[span] - kn) < 1.5, (key, span, rec[span], kn)
    if FLIP_Y:
        lines = [[[p[0], -p[1]] for p in ln] for ln in lines]
    xs = [p[0] for ln in lines for p in ln]
    ys = [p[1] for ln in lines for p in ln]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = TARGET_PX[key] / max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    img = Image.new("RGB", (W, H), "white")
    drw = ImageDraw.Draw(img)
    def P(p):
        return (CX + (p[0] - cx) * s, CY + (p[1] - cy) * s)
    for ln in lines:
        pts = [P(p) for p in ln]
        if len(pts) >= 2:
            drw.line(pts, fill=INK, width=LW, joint="curve")
    path = os.path.join(OUTD, key + ".png")
    img.save(path)
    ix0 = min(P((x0, y0))[0], P((x0, y1))[0]); ix1 = max(P((x1, y0))[0], P((x1, y1))[0])
    iy0 = min(P((x0, y0))[1], P((x1, y0))[1]); iy1 = max(P((x0, y1))[1], P((x1, y1))[1])
    merged[key] = {"path": path, "bbox": [round(ix0), round(iy0), round(ix1), round(iy1)],
                   "pxmm": round(s, 6), "mm_span": [round(x1 - x0, 1), round(y1 - y0, 1)],
                   "center_mm": [0.0, 0.0]}
    print("[%s] %s pxmm=%.4f mm=%s" % (key, path, s, merged[key]["mm_span"]))

json.dump(merged, open(MERGED, "w"), indent=1)
print("[done] views_merged.json updated")
