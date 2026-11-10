# gen_techdraw_v7.py -- embed native TechDraw pages INSIDE assembly_v7.FCStd.
# Run:  cd /home/openclaw/freecad && xvfb-run -a ./FreeCAD_1.1.4-Linux-x86_64-py311.AppImage -c gen_techdraw_v7.py
# Strategy: v6-proven HLR core (explicit XDirection, extents gates, pump loops),
# but DrawPage/DrawViewPart objects are created in the TARGET doc and saved with it.
# Incremental doc.save() after each page -> a killed run keeps finished pages.
import FreeCAD as App
import FreeCADGui as Gui
import Part
import json, os, glob, time, traceback

Gui.showMainWindow()
import TechDrawGui
for _ in range(10):
    Gui.updateGui()
time.sleep(1.0)
for _ in range(10):
    Gui.updateGui()

SRC = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v7/assembly_v7.FCStd"
OUT = "/home/openclaw/freecad/techdraw_v7_result.json"
diag = {}
def save_json():
    json.dump(diag, open(OUT, "w"), indent=1)

TMPLS = (glob.glob("/tmp/.mount_*/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True)
         or glob.glob("/tmp/squashfs-root/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True))
TMPL = None
for cand in sorted(TMPLS):
    base = os.path.basename(cand).lower()
    if "landscape" in base and "a4" in base and "blank" not in base:
        TMPL = cand  # editable title block preferred
        break
if TMPL is None:
    for cand in sorted(TMPLS):
        if "landscape" in os.path.basename(cand).lower():
            TMPL = cand
            break
if TMPL is None and TMPLS:
    TMPL = sorted(TMPLS)[0]
diag["template"] = TMPL
save_json()

d = App.openDocument(SRC)
diag["objects_on_open"] = len(d.Objects)

# ---- purge any prior partial run (idempotent reruns) ----
purged = 0
for o in list(d.Objects):
    if o.TypeId in ("TechDraw::DrawPage", "TechDraw::DrawSVGTemplate",
                    "TechDraw::DrawViewPart", "TechDraw::DrawViewAnnotation") \
       or o.Name.startswith(("DrawAsm", "DrawExp")):
        d.removeObject(o.Name)
        purged += 1
diag["purged"] = purged
save_json()

def world_shape(l):
    s = l.Shape.copy()
    chain, cur, seen = [], l, set()
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

def pump(n=5):
    for _ in range(n):
        Gui.updateGui()

# ---- masters ----
masters = {}
for name in ("FlangePiece", "Bellows", "Spool", "Gasket", "DataPlate"):
    o = d.getObject(name)
    assert o is not None, "missing master " + name
    sh = o.Shape
    assert sh is not None and not sh.isNull() and len(sh.Solids) > 0, name + " no solid"
    masters[name] = o  # keep OBJECT (live Source), not a shape copy
    diag["master_" + name] = [round(v, 1) for v in (
        sh.BoundBox.XMin, sh.BoundBox.XMax, sh.BoundBox.YMin,
        sh.BoundBox.YMax, sh.BoundBox.ZMin, sh.BoundBox.ZMax)]

# ---- assembled links: fuse into ONE occlusion-correct solid ----
links = [o for o in d.Objects if o.TypeId == "App::Link"]
shapes = []
for l in links:
    s = world_shape(l)
    if s is not None and not s.isNull() and len(s.Solids) > 0:
        shapes.append((l.LinkedObject.Name, s))
diag["links_with_solids"] = len(shapes)
xs = [v for _, s in shapes for v in (s.BoundBox.XMin, s.BoundBox.XMax)]
zs = [v for _, s in shapes for v in (s.BoundBox.ZMin, s.BoundBox.ZMax)]
asm_zmin, asm_zmax = min(zs), max(zs)
asm_yspan = max(v for _, s in shapes for v in (s.BoundBox.YMax,)) - min(v for _, s in shapes for v in (s.BoundBox.YMin,))
diag["asm_zspan"] = round(asm_zmax - asm_zmin, 1)

t0 = time.time()
fused = shapes[0][1].multiFuse([s for _, s in shapes[1:]])
diag["fuse_seconds"] = round(time.time() - t0, 1)
diag["fused_valid"] = bool(fused.isValid())
fb = fused.BoundBox
assert abs(fb.ZMin - asm_zmin) < 1.0 and abs(fb.ZMax - asm_zmax) < 1.0, "fuse lost parts vs link union"

asm_obj = d.addObject("Part::Feature", "DrawAsmFused")
asm_obj.Shape = fused
asm_obj.Label = "DrawAsmFused (occlusion source)"
asm_obj.Visibility = False

# ---- exploded capture, then RESTORE Explode_F=0 ----
spec = d.getObject("SPEC")
spec.set("Explode_F", "1")
d.recompute(None, True, True)
pump(10)
exp_shapes = []
for l in links:
    s = world_shape(l)
    if s is not None and not s.isNull() and len(s.Solids) > 0:
        exp_shapes.append(s)
ezs = [v for s in exp_shapes for v in (s.BoundBox.ZMin, s.BoundBox.ZMax)]
diag["exp_zspan"] = round(max(ezs) - min(ezs), 1)
exp_obj = d.addObject("Part::Feature", "DrawExploded")
exp_obj.Shape = Part.Compound(exp_shapes)
exp_obj.Label = "DrawExploded (pictorial source)"
exp_obj.Visibility = False

spec.set("Explode_F", "0")
d.recompute(None, True, True)
pump(10)
# gate: model actually collapsed back
back = []
for l in links:
    s = world_shape(l)
    if s is not None and not s.isNull() and len(s.Solids) > 0:
        back.append(s)
bzs = [v for s in back for v in (s.BoundBox.ZMin, s.BoundBox.ZMax)]
assert abs((max(bzs) - min(bzs)) - (asm_zmax - asm_zmin)) < 1.0, "Explode_F restore failed"
diag["explode_restored"] = True
diag["asm_yspan_front_known"] = round(asm_yspan, 1)
save_json()

# ---- projection math ----
def unit(v):
    m = v.Length
    return App.Vector(v.x / m, v.y / m, v.z / m)

def proj_axes(direction, xdir):
    D = unit(App.Vector(*direction)); X = unit(App.Vector(*xdir))
    U = D.cross(X)  # screen up (pre-flip)
    return X, U

def expected_spans(shape, direction, xdir):
    X, U = proj_axes(direction, xdir)
    bb = shape.BoundBox
    us, vs = [], []
    for px in (bb.XMin, bb.XMax):
        for py in (bb.YMin, bb.YMax):
            for pz in (bb.ZMin, bb.ZMax):
                p = App.Vector(px, py, pz)
                us.append(p.dot(X)); vs.append(p.dot(U))
    return max(us) - min(us), max(vs) - min(vs)

def fit_scale(bw, bh, su, sv):
    std = [1.0, 0.5, 0.4, 1.0/3.0, 0.25, 0.2, 0.15, 0.1, 0.05]
    lim = min(bw / max(su, 0.01), bh / max(sv, 0.01))
    for s in std:
        if s <= lim:
            return s
    return std[-1]

def edges_bbox(view):
    edges = []
    try:
        edges = view.getVisibleEdges()
    except Exception:
        return None, 0
    pts = []
    for e in edges:
        try:
            pts.extend(e.discretize(Deflection=0.03))
        except Exception:
            pass
    if not pts:
        return None, len(edges)
    xs = [p.x for p in pts]; ys = [p.y for p in pts]
    return (min(xs), min(ys), max(xs), max(ys)), len(edges)

XDIR = {
    (0, -1, 0): (1, 0, 0),
    (0, 0, 1): (1, 0, 0),
    (-1, 0, 0): (0, -1, 0),
    (1, 1, 1): (1, -1, 0),
}

def make_view(page, name, src, direction, box, known_axis=None, known_mm=None):
    xdir = XDIR.get(direction)
    assert xdir, "no XDirection for " + name
    view = d.addObject("TechDraw::DrawViewPart", "TDV_" + name)
    page.addView(view)
    view.Source = [src]
    view.Direction = App.Vector(*direction)
    view.XDirection = App.Vector(*xdir)
    su, sv = expected_spans(src.Shape, direction, xdir)
    scale = fit_scale(box[2], box[3], su, sv)
    try:
        view.ScaleType = "Custom"
    except Exception:
        pass
    view.Scale = scale
    view.X = box[0]; view.Y = box[1]
    view.ViewObject.show()
    bb, nedges = None, 0
    for attempt in range(25):
        try:
            view.touch(); view.recompute()
        except Exception:
            pass
        d.recompute()
        pump(5)
        bb, nedges = edges_bbox(view)
        if bb and nedges:
            break
        time.sleep(2.0)
        pump(5)
    rec = {"scale": scale, "edges": nedges,
           "exp_spans": [round(su, 1), round(sv, 1)],
           "got_spans": [round(bb[2] - bb[0], 1), round(bb[3] - bb[1], 1)] if bb else None}
    if bb and known_axis and known_mm:
        ext = (bb[2] - bb[0]) if known_axis == "x" else (bb[3] - bb[1])
        rec["gate"] = "OK" if abs(ext - known_mm) / known_mm < 0.10 else \
            "MISMATCH ext=%.1f known=%.1f" % (ext, known_mm)
    elif bb:
        # iso / pictorial: bbox-corner expected is generous -> warn only
        ok_u = abs((bb[2] - bb[0]) - su) / su < 0.35 if su > 2 else True
        ok_v = abs((bb[3] - bb[1]) - sv) / sv < 0.35 if sv > 2 else True
        rec["gate"] = "OK(warn-band)" if (ok_u and ok_v and nedges) else "CHECK"
    else:
        rec["gate"] = "NO-EDGES"
    diag["views"][name] = rec
    save_json()
    return rec

def make_page(idx, title, keep_left_clear=False):
    page = d.addObject("TechDraw::DrawPage", "Page%d" % idx)
    t = d.addObject("TechDraw::DrawSVGTemplate", "Tmpl%d" % idx)
    t.Template = TMPL
    page.Template = t
    try:
        page.KeepUpdated = True
    except Exception:
        pass
    page.ViewObject.show()
    pump(3)
    # title block texts: set by substring match on editable keys
    try:
        keys = list(t.EditableTexts.keys())
        vals = {}
        for k in keys:
            lk = k.lower()
            if "title" in lk:
                vals[k] = "EXPANSION JOINT - %s" % title
            elif "subtitle" in lk or "description" in lk:
                vals[k] = "REV V7 - EMBEDDED TECHDRAW"
            elif "scale" in lk:
                vals[k] = "AS NOTED"
            elif "sheet" in lk:
                vals[k] = "%d / 5" % idx
            elif "date" in lk:
                vals[k] = "2026-10-28"
            elif "author" in lk or "name" in lk:
                vals[k] = "RED LANGOSTA / OPENCLAW"
            elif "drawing" in lk or "number" in lk:
                vals[k] = "EJ-2026-V7-%d" % idx
        if vals:
            t.EditableTexts = vals
            diag["pages"][idx]["editable"] = vals
    except Exception as e:
        diag["pages"][idx]["editable_error"] = repr(e)[:120]
    ann = d.addObject("TechDraw::DrawViewAnnotation", "Ann%d" % idx)
    page.addView(ann)
    ann.X = 100.0; ann.Y = 195.0
    try:
        ann.Text = ["EXPANSION JOINT REV V7 - SHEET %d/5 - %s" % (idx, title)]
    except Exception:
        pass
    pump(3)
    return page

diag["views"] = {}
diag["pages"] = {}
save_json()
M = masters
pages_spec = [
    # (idx, title, [(viewname, source, direction, box(cx,cy,bw,bh), known_axis, known_mm)])
    (1, "FLANGE PIECE", [
        ("flange_front", M["FlangePiece"], (0, -1, 0), (85, 80, 130, 90), "x", 70.0),
        ("flange_top",   M["FlangePiece"], (0, 0, 1),  (225, 75, 110, 100), "x", 70.0),
        ("flange_iso",   M["FlangePiece"], (1, 1, 1),  (200, 140, 100, 50), None, None),
    ]),
    (2, "BELLOWS", [
        ("bellows_front", M["Bellows"], (0, -1, 0), (70, 85, 100, 120), "y", 55.0),
        ("bellows_side",  M["Bellows"], (-1, 0, 0), (160, 85, 100, 120), "y", 55.0),
        ("bellows_top",   M["Bellows"], (0, 0, 1),  (245, 60, 90, 90), "x", 48.0),
        ("bellows_iso",   M["Bellows"], (1, 1, 1),  (245, 135, 90, 80), None, None),
    ]),
    (3, "SPOOL", [
        ("spool_front", M["Spool"], (0, -1, 0), (85, 80, 130, 90), "x", 70.0),
        ("spool_side",  M["Spool"], (-1, 0, 0), (225, 80, 110, 90), "y", 27.0),
        ("spool_iso",   M["Spool"], (1, 1, 1),  (155, 140, 110, 70), None, None),
    ]),
    (4, "GASKET & DATA PLATE", [
        ("gasket_top",   M["Gasket"], (0, 0, 1),  (85, 60, 120, 100), "x", 44.0),
        ("plate_top",    M["DataPlate"], (0, 0, 1), (225, 60, 110, 100), "x", 40.0),
        ("gasket_front", M["Gasket"], (0, -1, 0), (85, 145, 120, 30), "y", 1.5),
    ]),
    (5, "ASSEMBLY", [
        ("asm_front", asm_obj, (0, -1, 0), (75, 95, 110, 150), "y", asm_zmax - asm_zmin),
        ("exp_iso",   exp_obj, (1, 1, 1),  (195, 95, 140, 140), None, None),
    ]),
]

for idx, title, views in pages_spec:
    diag["pages"][idx] = {"title": title}
    save_json()
    try:
        page = make_page(idx, title)
    except Exception as e:
        diag["pages"][idx]["page_error"] = traceback.format_exc()[-400:]
        save_json()
        continue
    for (vname, src, direction, box, kax, kmm) in views:
        t0 = time.time()
        try:
            rec = make_view(page, vname, src, direction, box, kax, kmm)
        except Exception:
            rec = {"gate": "EXC", "error": traceback.format_exc()[-400:]}
            diag["views"][vname] = rec
        diag["views"][vname]["seconds"] = round(time.time() - t0, 1)
        save_json()
    d.recompute()
    pump(10)
    d.save()   # incremental: finished pages survive a killed run
    diag["pages"][idx]["saved"] = True
    save_json()

d.recompute(None, True, True)
pump(10)
bad = [o.Name for o in d.Objects
       if o.TypeId.startswith("TechDraw::") and any(s in o.State for s in ("Invalid", "Error"))]
diag["techdraw_error_states"] = bad
d.save()
diag["final_objects"] = len(d.Objects)
diag["done"] = True
save_json()
os._exit(0)
