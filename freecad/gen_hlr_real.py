# gen_hlr_real.py v2 -- standalone TechDraw HLR of the REAL expansion-joint geometry.
# Run:  cd /home/openclaw/freecad && xvfb-run -a ./FreeCAD_1.1.4-Linux-x86_64-py311.AppImage -c gen_hlr_real.py
# v2: ONE FRESH DOC PER VIEW (exactly the proven forum recipe), explicit retries,
#     TechDraw fallback imported properly. Geometry copied in as Part::Feature.
import FreeCAD as App
import FreeCADGui as Gui
import Part
import TechDraw
import json, math, os, glob, time

Gui.showMainWindow()
import TechDrawGui
for _ in range(10):
    Gui.updateGui()
time.sleep(1.0)
for _ in range(10):
    Gui.updateGui()

V2 = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v2"
V3 = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v3"
OUT = "/tmp/hlr_edges.json"

TMPLS = (glob.glob("/tmp/.mount_*/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True)
         or glob.glob("/tmp/squashfs-root/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True))
TMPL = sorted(TMPLS)[0] if TMPLS else None
print("[init] template:", TMPL, flush=True)

JOBS = [
    ("flange_front", V2 + "/flange_piece_v2.FCStd", (0, -1, 0), "x", 84.0),
    ("flange_top",   V2 + "/flange_piece_v2.FCStd", (0, 0, 1),  "x", 84.0),
    ("flange_side",  V2 + "/flange_piece_v2.FCStd", (-1, 0, 0), "y", 27.0),
    ("flange_iso",   V2 + "/flange_piece_v2.FCStd", (1, 1, 1),  None, None),
    ("bellows_front", V2 + "/bellows_v2.FCStd", (0, -1, 0), "y", 55.0),
    ("bellows_top",   V2 + "/bellows_v2.FCStd", (0, 0, 1),  "x", 48.0),
    ("bellows_side",  V2 + "/bellows_v2.FCStd", (-1, 0, 0), "y", 55.0),
    ("bellows_iso",   V2 + "/bellows_v2.FCStd", (1, 1, 1),  None, None),
    ("spool_front", V3 + "/spool_v3.FCStd", (0, -1, 0), "x", 70.0),
    ("spool_side",  V3 + "/spool_v3.FCStd", (-1, 0, 0), "y", 27.0),
    ("spool_iso",   V3 + "/spool_v3.FCStd", (1, 1, 1),  None, None),
    ("gasket_top",   V3 + "/gasket_v3.FCStd",   (0, 0, 1),  "x", 44.0),
    ("gasket_front", V3 + "/gasket_v3.FCStd",   (0, -1, 0), "x", 44.0),
    ("plate_top",    V3 + "/data_plate_v3.FCStd", (0, 0, 1),  "x", 40.0),
    ("plate_iso",    V3 + "/data_plate_v3.FCStd", (1, 1, 1),  None, None),
    ("asm_front", V3 + "/assembly_v3.FCStd", (0, -1, 0), "y", 156.0),
    ("asm_iso",   V3 + "/assembly_v3.FCStd", (1, 1, 1),  None, None),
]

_shapecache = {}

def doc_solids(path):
    if path in _shapecache:
        return _shapecache[path]
    d = App.openDocument(path)
    solids = []
    for o in d.Objects:
        try:
            s = o.Shape
            if s is not None and not s.isNull() and len(s.Solids) > 0:
                solids.append(s)
        except Exception:
            pass
    App.closeDocument(d.Name)
    _shapecache[path] = solids
    return solids

def xdir_for(direction):
    if direction == (0, -1, 0):
        return App.Vector(1, 0, 0)    # front: screen right = +X, up = +Z
    if direction == (0, 0, 1):
        return App.Vector(1, 0, 0)    # top: screen right = +X, up = +Y
    if direction == (-1, 0, 0):
        return App.Vector(0, -1, 0)   # left: screen right = -Y, up = +Z
    if direction == (1, 1, 1):
        return App.Vector(1, -1, 0)   # iso: negated - previous sign gave mirrored text
    return App.Vector(0, 0, 0)

def pump(n=5):
    for _ in range(n):
        Gui.updateGui()

def edges_via_dvp(comp, direction, tag):
    d = App.newDocument("hlr_" + tag)
    obj = d.addObject("Part::Feature", "Part")
    obj.Shape = comp
    d.recompute()
    pump(3)
    page = d.addObject("TechDraw::DrawPage", "DrawPage")
    view = d.addObject("TechDraw::DrawViewPart", "DrawViewPart")
    if TMPL:
        t = d.addObject("TechDraw::DrawSVGTemplate", "DrawSVGTemplate")
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
    import time as _t
    for attempt in range(20):
        try:
            view.touch()
            view.recompute()
        except Exception:
            pass
        d.recompute()
        pump(5)
        edges = view.getVisibleEdges()
        if edges:
            break
        _t.sleep(2.0)
        pump(5)
    lines = []
    for e in edges:
        try:
            pts = e.discretize(Deflection=0.03)
            lines.append([[round(p.x, 4), round(p.y, 4)] for p in pts])
        except Exception:
            pass
    App.closeDocument(d.Name)
    return lines, "drawviewpart"

def edges_via_project(comp, direction):
    vec = App.Vector(*direction)
    lines = []
    try:
        res = TechDraw.project(comp, vec)
        shapes = list(res[:2]) if isinstance(res, (tuple, list)) else [res]
    except Exception:
        res = TechDraw.projectEx(comp, vec)
        shapes = [s for s in res[:5] if s is not None]
    for sh in shapes:
        try:
            if sh is None or sh.isNull() or len(sh.Edges) == 0:
                continue
            for e in sh.Edges:
                pts = e.discretize(Deflection=0.03)
                lines.append([[round(p.x, 4), round(p.y, 4)] for p in pts])
        except Exception:
            pass
    # observed: fallback CS maps screen-x <- world z (transposed vs GUI) for front
    # views; swap axes to the standard X-right/Y-up convention.
    if direction == (0, -1, 0):
        lines = [[[p[1], p[0]] for p in ln] for ln in lines]
    return lines, "techdraw.project+swap"

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

for key, path, direction, axis, known in JOBS:
    if key in result and result[key].get("lines"):
        print("[skip] %s already done" % key, flush=True)
        continue
    solids = doc_solids(path)
    comp = Part.Compound(solids) if len(solids) > 1 else solids[0]
    t0 = time.time()
    try:
        lines, method = edges_via_dvp(comp, direction, key)
        if not lines:
            lines, method = edges_via_project(comp, direction)
    except Exception as e:
        print("  [%s] DVP path exception: %s" % (key, e), flush=True)
        lines, method = edges_via_project(comp, direction)
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
result_out = dict(views=len(result))
print("[result] %s" % result_out)
os._exit(0)
