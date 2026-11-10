# exp_iso_v7.py -- regenerate the exploded ISO with the data plate moved BELOW the
# lower spool (clear gap, not attached). Probes exploded z-ranges first, computes
# the drop, translates the plate shape, projects D=(1,1,1)/X=(1,-1,0).
import FreeCAD as App
import FreeCADGui as Gui
import Part
import json, os, time, traceback

DIAG = "/tmp/exp_iso_v7_diag.json"
EDGES_OUT = "/tmp/hlr_edges_v7_extra2.json"
diag = {"started": True}
json.dump(diag, open(DIAG, "w"))

try:
    Gui.showMainWindow()
    import TechDrawGui
    for _ in range(10):
        Gui.updateGui()
    time.sleep(1.0)
    for _ in range(10):
        Gui.updateGui()

    SRC = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v7/assembly_v7.FCStd"
    d = App.openDocument(SRC)

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

    links = [o for o in d.Objects if o.TypeId == "App::Link"]
    spec = d.getObject("SPEC")
    spec.set("Explode_F", "1")
    d.recompute(None, True, True)
    for _ in range(10):
        Gui.updateGui()

    exp = {}
    for l in links:
        s = world_shape(l)
        if s is None or s.isNull() or not s.Solids:
            continue
        bb = s.BoundBox
        tgt = l.LinkedObject.Name
        exp.setdefault(tgt, []).append(
            {"name": l.Name, "zmin": round(bb.ZMin, 1), "zmax": round(bb.ZMax, 1),
             "xmin": round(bb.XMin, 1), "xmax": round(bb.XMax, 1),
             "ymin": round(bb.YMin, 1), "ymax": round(bb.YMax, 1), "shape": s})
    diag["exploded"] = {k: [{kk: v[kk] for kk in ("name", "zmin", "zmax")}
                            for v in vs] for k, vs in exp.items()}
    json.dump(diag, open(DIAG, "w"), indent=1)

    plate = exp["DataPlateText"][0] if "DataPlateText" in exp else exp["DataPlate"][0]
    spools = sorted([v for v in exp.get("Spool", [])], key=lambda e: e["zmin"])
    lower = spools[0]
    GAP = 30.0  # world-z gap; ISO v-projection shrinks z-gaps (~x0.82, minus the
                # plate's y-offset effect), so use 30 for a clearly visible break
    delta = (plate["zmax"] - lower["zmin"]) + GAP  # drop so plate top sits GAP below spool bottom
    if delta <= 0:
        delta = GAP
    diag["plate"] = {k: plate[k] for k in ("zmin", "zmax")}
    diag["lower_spool"] = {k: lower[k] for k in ("zmin", "zmax")}
    diag["drop_mm"] = round(delta, 1)
    json.dump(diag, open(DIAG, "w"), indent=1)

    # build compound with plate translated down
    parts = []
    for tgt, vs in exp.items():
        for v in vs:
            s = v["shape"]
            if v is plate:
                s.translate(App.Vector(0, 0, -delta))
            parts.append(s)
    comp = Part.Compound(parts)
    cb = comp.BoundBox
    diag["compound"] = [round(v, 1) for v in (cb.XMin, cb.XMax, cb.YMin, cb.YMax, cb.ZMin, cb.ZMax)]
    json.dump(diag, open(DIAG, "w"), indent=1)

    # restore explode BEFORE projecting (compound is a static copy)
    spec.set("Explode_F", "0")
    d.recompute(None, True, True)
    diag["explode_restored"] = True
    json.dump(diag, open(DIAG, "w"), indent=1)
    # no save: model untouched

    import glob
    TMPLS = (glob.glob("/tmp/.mount_*/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True)
             or glob.glob("/tmp/squashfs-root/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True))
    TMPL = sorted(TMPLS)[0] if TMPLS else None

    def pump(n=5):
        for _ in range(n):
            Gui.updateGui()

    dd = App.newDocument("hlr_exp2")
    obj = dd.addObject("Part::Feature", "Part")
    obj.Shape = comp
    dd.recompute(); pump(3)
    page = dd.addObject("TechDraw::DrawPage", "DrawPage")
    view = dd.addObject("TechDraw::DrawViewPart", "DrawViewPart")
    if TMPL:
        t = dd.addObject("TechDraw::DrawSVGTemplate", "DrawSVGTemplate")
        t.Template = TMPL
        page.Template = t
    page.addView(view)
    view.Source = [obj]
    view.Direction = App.Vector(1, 1, 1)
    # X negated vs v6: proper 180-deg in-plane rotation. The up-vector of the
    # (1,1,1)/(1,-1,0) frame carries -0.82 z, so the rasterizer's y-flip
    # (right for front/side/top) inverted the ISO: world-top rendered at image
    # bottom ( unnoticed v4-v7, symmetric part). With X=( -1,1,0): U_z>0, z-up
    # renders at image top, plate-below-spool shows image-below. No mirror.
    view.XDirection = App.Vector(-1, 1, 0)
    view.Scale = 1.0
    view.X = 148.0; view.Y = 105.0
    page.ViewObject.show(); view.ViewObject.show()
    edges = []
    for attempt in range(25):
        try:
            view.touch(); view.recompute()
        except Exception:
            pass
        dd.recompute(); pump(5)
        try:
            edges = view.getVisibleEdges()
        except Exception:
            edges = []
        if edges:
            break
        time.sleep(2.0); pump(5)
    lines_out = []
    for e in edges:
        try:
            pts = e.discretize(Deflection=0.03)
            lines_out.append([[round(p.x, 4), round(p.y, 4)] for p in pts])
        except Exception:
            pass
    xs = [p[0] for ln in lines_out for p in ln]
    ys = [p[1] for ln in lines_out for p in ln]
    ext = [round(max(xs) - min(xs), 1), round(max(ys) - min(ys), 1)] if xs else None
    plate_view = {"lines": lines_out, "extents": ext,
                  "gate": "OK" if (ext and len(lines_out) > 100) else "FAIL lines=%d" % len(lines_out)}
    diag["view"] = [plate_view["gate"], ext, len(lines_out)]
    json.dump(diag, open(DIAG, "w"), indent=1)
    App.closeDocument(dd.Name)

    cur = json.load(open(EDGES_OUT))
    cur["exp_iso_v2"] = plate_view
    json.dump(cur, open(EDGES_OUT, "w"))
    diag["done"] = True
    json.dump(diag, open(DIAG, "w"), indent=1)
except Exception:
    diag["fatal"] = traceback.format_exc()[-2500:]
    json.dump(diag, open(DIAG, "w"), indent=1)
    os._exit(1)
os._exit(0)
