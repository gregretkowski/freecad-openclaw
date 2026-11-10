#!/usr/bin/env python3
# rasterize_hlr.py -- turn /tmp/hlr_edges.json (mm view-coords) into line-art PNGs
# matching the sheets' calibration, plus views_hlr.json for the composer.
import json, os
from PIL import Image, ImageDraw

DRW = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v4/drawings"
EDGES = json.load(open("/tmp/hlr_edges.json"))
OLD = json.load(open(os.path.join(DRW, "views", "views.json")))
OUT = os.path.join(DRW, "views_hlr")
os.makedirs(OUT, exist_ok=True)

W, H = 1200, 900
CX, CY = 600.0, 450.0
INK = (26, 26, 26)
LW = 3

# front-direction DVPs come out y-up = -z (verified vs renders: flange stub,
# bellows collar). Flip raw y so screen-up = +z. asm_front is pre-merged in
# world coords by merge_asm.py (flip baked in there).
# DVP raw output is y-flipped (screen-up = -world-up) for all view classes;
# verified by A/B composite (plate_comparison.png) and stub-direction checks.
# Y-only negation - x must NOT be touched (plate text is chiral).
# Note: plate text is a separate solid; TechDraw HLR does not occlude between
# source solids, so the iso pictorial shows the text - fixed by the same flip.
FLIP_Y = {"flange_front", "bellows_front", "spool_front", "gasket_front",
          "flange_side", "bellows_side", "spool_side",
          "plate_top", "plate_iso"}
# plate_top / plate_iso: DVP screen-y is -Y (same y-flip as all other views);
# verified by text-mirror iterations on sheet 4. Covered by FLIP_Y above.

# iso targets = old art max pixel dimension (pictorial size match)
ISO_TARGET = {k: max(OLD[k]["bbox"][2] - OLD[k]["bbox"][0],
                     OLD[k]["bbox"][3] - OLD[k]["bbox"][1])
              for k in ("flange_iso", "bellows_iso", "spool_iso", "plate_iso", "asm_iso")
              if k in OLD}

meta = {}
for key, rec in EDGES.items():
    lines = rec["lines"]
    if not lines:
        print("[skip] %s: no lines" % key)
        continue
    if key in FLIP_Y:
        lines = [[[p[0], -p[1]] for p in ln] for ln in lines]
    xs = [p[0] for ln in lines for p in ln]
    ys = [p[1] for ln in lines for p in ln]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if key in ISO_TARGET:
        s = ISO_TARGET[key] / max(x1 - x0, y1 - y0)
    elif key == "asm_front":
        s = OLD["asm_front"]["pxmm"]["y"]   # 4.2436: true z calibration
    else:
        pm = OLD[key]["pxmm"]
        s = pm.get("x") or pm.get("y")
    if key == "asm_front":
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0   # fused DVP: symmetric about z=49.5
    else:
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
    pm_new = dict(OLD[key]["pxmm"])
    if key == "asm_front":
        pm_new = {"x": s, "y": s}
    meta[key] = dict(path=p, bbox=[bx0, by0, bx1, by1], pxmm=pm_new,
                     part=OLD[key].get("part", ""), label=OLD[key].get("label", ""))
    print("[%s] %s scale=%.4f px/mm art %dx%d px" % (key, rec["method"], s, bx1 - bx0, by1 - by0))

with open(os.path.join(OUT, "views_hlr.json"), "w") as f:
    json.dump(meta, f, indent=1)
print("[done] %d line-art views -> %s" % (len(meta), OUT))
