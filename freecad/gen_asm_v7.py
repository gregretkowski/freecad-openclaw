# gen_asm_v7.py -- regenerate assembly views for v7 after data-plate remount.
# asm_front: dir (0,-1,0)/X(1,0,0)  -- plate face (raised text) toward viewer
# asm_left : dir (1,0,0)/X(0,1,0)  -- the "rotate 90deg left" variant Greg asked
#            about; plate (y -38..-36) lands as a tab at the LEFT silhouette edge.
# Run: cd /home/openclaw/freecad && xvfb-run -a ./FreeCAD_1.1.4-Linux-x86_64-py311.AppImage -c gen_asm_v7.py
import FreeCAD as App
import FreeCADGui as Gui
import Part
import json, os, time, glob

Gui.showMainWindow()
import TechDrawGui
for _ in range(10):
    Gui.updateGui()
time.sleep(1.0)
for _ in range(10):
    Gui.updateGui()

SRC = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v7/assembly_v7.FCStd"
OUT = "/tmp/hlr_edges_v7_asm.json"
DIAG = "/tmp/hlr_v7_diag.json"
diag = {}

TMPLS = (glob.glob("/tmp/.mount_*/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True)
         or glob.glob("/tmp/squashfs-root/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True))
TMPL = sorted(TMPLS)[0] if TMPLS else None

d = App.openDocument(SRC)

def world_shape(l):
    s = l.Shape.copy()
    chain = []
    cur = l
    seen = set()
    while True:
        parents = [p for p in cur.InList if p.isDerivedFrom("App::Part")]
        if not parents or parents[0].Name in seen:
            break
        seen.add(parents[0].Name)
        chain.append(parents[0])
        cur = parents[0]
    pl = App.Placement()
    for anc in reversed(chain):
        pl = anc.Placement.multiply(pl)
    s.Placement = pl.multiply(s.Placement)
    return s

links = [o for o in d.Objects if o.TypeId == "App::Link"]
shapes = []
for l in links:
    s = world_shape(l)
    if s is not None and not s.isNull() and len(s.Solids) > 0:
        shapes.append((l.LinkedObject.Name, s))

# sanity: explode factor must be 0 (assembled)
spec = d.getObject("SPEC")
assert str(spec.get("Explode_F")) in ("0", "0.0"), spec.get("Explode_F")

# anchors (same format as hlr_v6_diag: per-master list of world bboxes)
by = {}
for tgt, s in shapes:
    bb = s.BoundBox
    by.setdefault(tgt, []).append([round(bb.XMin, 2), round(bb.XMax, 2), round(bb.YMin, 2),
                                   round(bb.YMax, 2), round(bb.ZMin, 2), round(bb.ZMax, 2)])
diag["anchors"] = by
pb = [b for b in by.get("DataPlate", [])][0]
print("[plate anchor]", pb, flush=True)
assert pb[0] == -20.0 and pb[2] == -38.0 and pb[3] == -36.0 and pb[4] == -26.0 and pb[5] == -11.0, pb

fused = d.getObject("DrawAsmFused").Shape
fb = fused.BoundBox
print("[fused]", len(fused.Solids), "solids bbox", [round(v, 1) for v in
      (fb.XMin, fb.XMax, fb.YMin, fb.YMax, fb.ZMin, fb.ZMax)], flush=True)
assert fb.YMin == -38.0 and fb.YMax == 35.0

def xdir_for(direction):
    return {(0, -1, 0): App.Vector(1, 0, 0),
            (1, 0, 0): App.Vector(0, 1, 0)}[direction]

def pump(n=5):
    for _ in range(n):
        Gui.updateGui()

def edges_via_dvp(comp, direction, tag):
    dd = App.newDocument("hlr_" + tag)
    obj = dd.addObject("Part::Feature", "Part")
    obj.Shape = comp
    dd.recompute()
    pump(3)
    page = dd.addObject("TechDraw::DrawPage", "DrawPage")
    view = dd.addObject("TechDraw::DrawViewPart", "DrawViewPart")
    if TMPL:
        t = dd.addObject("TechDraw::DrawSVGTemplate", "DrawSVGTemplate")
        t.Template = TMPL
        page.Template = t
    page.addView(view)
    view.Source = [obj]
    view.Direction = App.Vector(*direction)
    view.XDirection = xdir_for(direction)
    view.Scale = 1.0
    view.X = 148.0
    view.Y = 105.0
    page.ViewObject.show()
    view.ViewObject.show()
    edges = []
    for attempt in range(20):
        try:
            view.touch()
            view.recompute()
        except Exception:
            pass
        dd.recompute()
        pump(5)
        edges = view.getVisibleEdges()
        if edges:
            break
        time.sleep(2.0)
        pump(5)
    lines = []
    for e in edges:
        try:
            pts = e.discretize(Deflection=0.03)
            lines.append([[round(p.x, 4), round(p.y, 4)] for p in pts])
        except Exception:
            pass
    App.closeDocument(dd.Name)
    return lines

result = {}
JOBS = [
    # key, compound, direction, (u_span, v_span) gate at Scale=1 (page mm == model mm)
    ("asm_front", fused, (0, -1, 0), (70.0, 156.0)),
    ("asm_left",  fused, (1, 0, 0),  (73.0, 156.0)),  # y -38..35
]
for key, comp, direction, (gu, gv) in JOBS:
    t0 = time.time()
    lines = edges_via_dvp(comp, direction, key)
    xs = [p[0] for ln in lines for p in ln]
    ys = [p[1] for ln in lines for p in ln]
    u, v = max(xs) - min(xs), max(ys) - min(ys)
    assert lines, key + " no edges"
    assert abs(u - gu) < 1.5 and abs(v - gv) < 1.5, (key, u, v, gu, gv)
    result[key] = {"lines": lines, "u_span": round(u, 2), "v_span": round(v, 2),
                   "method": "drawviewpart", "seconds": round(time.time() - t0, 1)}
    print("[%s] %d edges, u=%s v=%s (%.1fs)" % (key, len(lines), round(u, 1), round(v, 1),
                                                time.time() - t0), flush=True)
    json.dump(result, open(OUT, "w"))

diag["views"] = {k: {kk: r[kk] for kk in ("u_span", "v_span")} for k, r in result.items()}
json.dump(diag, open(DIAG, "w"), indent=1)
print("[done] edges ->", OUT, "diag ->", DIAG, flush=True)
