# add_plate_text_v7.py -- rebuild the v3 raised text on the v7 DataPlate master.
# v2: GUI init BEFORE Draft import; diag written immediately; fatal traceback captured.
import FreeCAD as App
import FreeCADGui as Gui
import Part
import json, os, time, traceback

DIAG = "/tmp/plate_text_v7_diag.json"
EDGES_OUT = "/tmp/hlr_edges_v7_extra2.json"
diag = {"started": True}
json.dump(diag, open(DIAG, "w"))

def dump():
    json.dump(diag, open(DIAG, "w"), indent=1)

def save_all():
    dump()
    try:
        cur = json.load(open(EDGES_OUT))
    except Exception:
        cur = {}
    for k, v in plate_view_rec.items():
        cur[k] = v
    json.dump(cur, open(EDGES_OUT, "w"))

plate_view_rec = {}

try:
    Gui.showMainWindow()
    import TechDrawGui
    import Draft
    for _ in range(10):
        Gui.updateGui()
    time.sleep(1.0)
    for _ in range(10):
        Gui.updateGui()
    diag["gui_up"] = True; dump()

    SRC = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v7/assembly_v7.FCStd"
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    assert os.path.exists(font), "font missing"

    PL, PW, PT = 40.0, 15.0, 2.0
    TEXT_UP, EMBED, MAXW = 0.6, 0.3, 38.0
    lines = [(2.4, "NPS 6  CL.150"), (1.9, "SCALE 1:4  TIED AXIAL BELLOWS EJ")]

    d = App.openDocument(SRC)
    diag["doc_open"] = True; dump()
    plate = d.getObject("DataPlate")
    assert plate is not None and plate.Shape.Solids, "DataPlate master missing"
    diag["plate_found"] = True; dump()

    helpers = []
    def make_text_solid(text, size):
        ss = Draft.makeShapeString(text, FontFile=font, Size=size)
        helpers.append(ss)
        d.recompute()
        face = Part.makeFace(ss.Shape.Wires, "Part::FaceMakerBullseye")
        s = face.extrude(App.Vector(0, 0, TEXT_UP + EMBED))
        assert s.isValid() and s.Volume > 0.5 * face.Area * (TEXT_UP + EMBED), "bad text solid"
        return s

    solids = []
    for i, (size, text) in enumerate(lines):
        for attempt in range(3):
            ss = Draft.makeShapeString(text, FontFile=font, Size=size)
            helpers.append(ss)
            d.recompute()
            w = ss.Shape.BoundBox.XLength
            if w <= MAXW:
                break
            size = size * (MAXW / w) * 0.98
        s = make_text_solid(text, size)
        bb = s.BoundBox
        s.translate(App.Vector(-(bb.XMin + bb.XMax) / 2.0,
                                (3.3 - i * 5.4) - (bb.YMin + bb.YMax) / 2.0,
                                PT - EMBED))
        solids.append(s)
        diag["line%d" % i] = [text, round(size, 2)]; save_all()

    final = plate.Shape
    for s in solids:
        final = final.fuse(s)
    final = final.removeSplitter()
    diag["fused"] = {"valid": bool(final.isValid()), "solids": len(final.Solids),
                     "volume": round(final.Volume, 1)}
    dump()
    assert final.isValid() and len(final.Solids) == 1 and 1200 < final.Volume < 1320, diag["fused"]

    feat = d.getObject("DataPlateText")
    if feat is None:
        feat = d.addObject("Part::Feature", "DataPlateText")
    feat.Shape = final
    feat.Label = "DataPlate (with raised text)"
    try:
        feat.Visibility = False
        feat.ViewObject.Visibility = False
    except Exception:
        pass
    for o in helpers:
        try:
            d.removeObject(o.Name)
        except Exception:
            pass
    d.recompute()
    diag["feature_created"] = True; dump()

    lnk = d.getObject("DataPlateAsm")
    if lnk is not None:
        try:
            lnk.LinkedObject = feat
            diag["link_repointed"] = True
        except Exception as e:
            diag["link_repointed"] = repr(e)[:120]
        dump()

    tdv = d.getObject("TDV_plate_top")
    if tdv is not None:
        try:
            tdv.Source = [feat]
            tdv.touch()
            d.recompute()
            for _ in range(5):
                Gui.updateGui()
            n = 0
            try:
                n = len(tdv.getVisibleEdges())
            except Exception:
                pass
            diag["embedded_tdv_plate_edges"] = n
        except Exception as e:
            diag["embedded_tdv_error"] = repr(e)[:120]
        dump()

    d.recompute(None, True, True)
    d.save()
    diag["saved"] = True
    save_all()

    import glob
    TMPLS = (glob.glob("/tmp/.mount_*/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True)
             or glob.glob("/tmp/squashfs-root/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True))
    TMPL = sorted(TMPLS)[0] if TMPLS else None

    def pump(n=5):
        for _ in range(n):
            Gui.updateGui()

    dd = App.newDocument("hlr_plate")
    obj = dd.addObject("Part::Feature", "Part")
    obj.Shape = final
    dd.recompute(); pump(3)
    page = dd.addObject("TechDraw::DrawPage", "DrawPage")
    view = dd.addObject("TechDraw::DrawViewPart", "DrawViewPart")
    if TMPL:
        t = dd.addObject("TechDraw::DrawSVGTemplate", "DrawSVGTemplate")
        t.Template = TMPL
        page.Template = t
    page.addView(view)
    view.Source = [obj]
    view.Direction = App.Vector(0, 0, 1)
    view.XDirection = App.Vector(1, 0, 0)
    view.Scale = 1.0
    view.X = 148.0; view.Y = 105.0
    page.ViewObject.show(); view.ViewObject.show()
    edges = []
    for attempt in range(20):
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
    gate = "OK" if (ext and abs(ext[0] - 40) / 40 < 0.10 and abs(ext[1] - 15) / 15 < 0.10
                    and len(lines_out) >= 12) else "FAIL ext=%s lines=%d" % (ext, len(lines_out))
    plate_view_rec["plate_top_text"] = {"lines": lines_out, "extents": ext, "gate": gate}
    diag["plate_view"] = [gate, ext, len(lines_out)]
    App.closeDocument(dd.Name)
    diag["done"] = True
    save_all()
except Exception:
    diag["fatal"] = traceback.format_exc()[-2500:]
    try:
        save_all()
    except Exception:
        dump()
    os._exit(1)
os._exit(0)
