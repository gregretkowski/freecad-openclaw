# gen_hlr_v6.py -- standalone TechDraw HLR of the REAL v6 geometry.
# Run:  cd /home/openclaw/freecad && xvfb-run -a ./FreeCAD_1.1.4-Linux-x86_64-py311.AppImage -c gen_hlr_v6.py
# Adapts the proven v4 recipe (fresh doc per view, explicit XDirection, extents gates)
# to the single-file v6 model: masters for part views, fused links for the assembly,
# link shapes at Explode_F=1 for the exploded pictorial.
import FreeCAD as App
import FreeCADGui as Gui
import Part
import TechDraw
import json, math, os, glob, time, traceback

Gui.showMainWindow()
import TechDrawGui
for _ in range(10):
    Gui.updateGui()
time.sleep(1.0)
for _ in range(10):
    Gui.updateGui()

SRC = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v6/assembly_v6.FCStd"
OUT = "/tmp/hlr_edges_v6.json"
DIAG = "/tmp/hlr_v6_diag.json"
diag = {}
def save_diag():
    json.dump(diag, open(DIAG, "w"), indent=1)

TMPLS = (glob.glob("/tmp/.mount_*/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True)
         or glob.glob("/tmp/squashfs-root/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True))
TMPL = sorted(TMPLS)[0] if TMPLS else None

d = App.openDocument(SRC)
diag["objects"] = len(d.Objects)

def world_shape(l):
    # App::Link .Shape carries only the link's own placement; nest inside
    # ancestor App::Part containers (e.g. mirrored StationTop) by composing
    # their placements (outermost * ... * innermost) onto the local shape.
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

# ---- masters (part views) ----
masters = {}
for name in ("FlangePiece", "Bellows", "Spool", "Gasket", "DataPlate"):
    o = d.getObject(name)
    assert o is not None, "missing master " + name
    sh = o.Shape
    assert sh is not None and not sh.isNull() and len(sh.Solids) > 0, name + " no solid"
    masters[name] = sh
    bb = sh.BoundBox
    diag["master_" + name] = [round(v, 1) for v in (bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax)]

# ---- links (assembled) ----
links = [o for o in d.Objects if o.TypeId == "App::Link"]
shapes = []
for l in links:
    s = world_shape(l)
    if s is not None and not s.isNull() and len(s.Solids) > 0:
        shapes.append((l.LinkedObject.Name, s))
diag["links_total"] = len(links)
diag["links_with_solids"] = len(shapes)

xs = [v for _, s in shapes for v in (s.BoundBox.XMin, s.BoundBox.XMax)]
zs = [v for _, s in shapes for v in (s.BoundBox.ZMin, s.BoundBox.ZMax)]
asm_bbox = [min(xs), max(xs), min(zs), max(zs)]
diag["asm_bbox_xy_xz"] = [round(v, 1) for v in asm_bbox]

t0 = time.time()
fused = shapes[0][1].multiFuse([s for _, s in shapes[1:]])
diag["fuse_seconds"] = round(time.time() - t0, 1)
diag["fused_valid"] = bool(fused.isValid())
diag["fused_solids"] = len(fused.Solids)
fb = fused.BoundBox
diag["fused_bbox"] = [round(v, 1) for v in (fb.XMin, fb.XMax, fb.YMin, fb.YMax, fb.ZMin, fb.ZMax)]
assert abs(fb.ZMin - asm_bbox[2]) < 1.0 and abs(fb.ZMax - asm_bbox[3]) < 1.0, "fuse lost parts vs link union"
save_diag()

# ---- exploded link shapes (Explode_F=1, no save) ----
spec = d.getObject("SPEC")
spec.set("Explode_F", "1")
d.recompute(None, True, True)
exp_shapes = []
for l in links:
    s = world_shape(l)
    if s is not None and not s.isNull() and len(s.Solids) > 0:
        exp_shapes.append((l.LinkedObject.Name, s))
ezs = [v for _, s in exp_shapes for v in (s.BoundBox.ZMin, s.BoundBox.ZMax)]
eys = [v for _, s in exp_shapes for v in (s.BoundBox.YMin, s.BoundBox.YMax)]
exs = [v for _, s in exp_shapes for v in (s.BoundBox.XMin, s.BoundBox.XMax)]
diag["exp_bbox"] = [round(min(exs), 1), round(max(exs), 1), round(min(eys), 1), round(max(eys), 1), round(min(ezs), 1), round(max(ezs), 1)]
exp_comp = Part.Compound([s for _, s in exp_shapes])
save_diag()

# ---- balloon anchors: assembled link bboxes by target ----
by = {}
for tgt, s in shapes:
    bb = s.BoundBox
    by.setdefault(tgt, []).append([round(bb.XMin,2), round(bb.XMax,2), round(bb.YMin,2), round(bb.YMax,2), round(bb.ZMin,2), round(bb.ZMax,2)])
diag["anchors"] = by

# ---- view jobs ----
M = masters
JOBS = [
    ("flange_front", M["FlangePiece"], (0, -1, 0), "x", 70.0),
    ("flange_top",   M["FlangePiece"], (0, 0, 1),  "x", 70.0),
    ("flange_side",  M["FlangePiece"], (-1, 0, 0), "y", 27.0),
    ("flange_iso",   M["FlangePiece"], (1, 1, 1),  None, None),
    ("bellows_front", M["Bellows"], (0, -1, 0), "y", 55.0),
    ("bellows_top",   M["Bellows"], (0, 0, 1),  "x", 48.0),
    ("bellows_side",  M["Bellows"], (-1, 0, 0), "y", 55.0),
    ("bellows_iso",   M["Bellows"], (1, 1, 1),  None, None),
    ("spool_front", M["Spool"], (0, -1, 0), "x", 70.0),
    ("spool_side",  M["Spool"], (-1, 0, 0), "y", 27.0),
    ("spool_iso",   M["Spool"], (1, 1, 1),  None, None),
    ("gasket_top",   M["Gasket"], (0, 0, 1),  "x", 44.0),
    ("gasket_front", M["Gasket"], (0, -1, 0), "y", 1.5),
    ("plate_top",    M["DataPlate"], (0, 0, 1),  "x", 40.0),
    ("asm_front",    fused,       (0, -1, 0), "y", asm_bbox[3] - asm_bbox[2]),
    ("exp_iso",      exp_comp,    (1, 1, 1),  None, None),
]

def xdir_for(direction):
    if direction == (0, -1, 0):
        return App.Vector(1, 0, 0)
    if direction == (0, 0, 1):
        return App.Vector(1, 0, 0)
    if direction == (-1, 0, 0):
        return App.Vector(0, -1, 0)
    if direction == (1, 1, 1):
        return App.Vector(1, -1, 0)
    return App.Vector(0, 0, 0)

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
    return lines, "drawviewpart"

def bbox_mm(lines):
    xs = [p[0] for ln in lines for p in ln]
    ys = [p[1] for ln in lines for p in ln]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None

result = {}
if os.path.exists(OUT):
    try:
        result = json.load(open(OUT))
    except Exception:
        result = {}

def save():
    with open(OUT, "w") as f:
        json.dump(result, f)

for key, comp, direction, axis, known in JOBS:
    if key in result and result[key].get("lines"):
        print("[skip] %s already done" % key, flush=True)
        continue
    t0 = time.time()
    try:
        lines, method = edges_via_dvp(comp, direction, key)
    except Exception as e:
        diag["exc_" + key] = repr(e)[:200]
        save_diag()
        lines, method = [], "exception"
    bb = bbox_mm(lines)
    ok = ""
    if bb and axis and known:
        ext = (bb[2] - bb[0]) if axis == "x" else (bb[3] - bb[1])
        ok = "OK" if abs(ext - known) / known < 0.10 else "MISMATCH ext=%.1f known=%.1f" % (ext, known)
    if lines:
        result[key] = {"method": method, "lines": lines}
        save()
    print("  [%s] %s lines=%d bbox=%s %s (%.1fs)" % (
        key, method, len(lines),
        tuple(round(v, 1) for v in bb) if bb else None, ok, time.time() - t0), flush=True)

save()
print("[done] views=%d/%d -> %s" % (len([k for k in result if result[k]["lines"]]), len(JOBS), OUT))
save_diag()
os._exit(0)
