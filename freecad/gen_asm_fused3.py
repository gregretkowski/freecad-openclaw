import FreeCAD as App
import FreeCADGui as Gui
import Part
import json, os, time, glob, math, traceback

V3 = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v3/assembly_v3.FCStd"
DIAG = "/tmp/asm_fused3_diag.json"
OUT = "/tmp/asm_fused3.json"
diag = {}
def save_diag():
    json.dump(diag, open(DIAG, "w"))
def V(x, y, z):
    return App.Vector(x, y, z)

try:
    Gui.showMainWindow()
    import TechDrawGui
    for _ in range(10):
        Gui.updateGui()
    time.sleep(1.0)
    for _ in range(10):
        Gui.updateGui()

    d = App.openDocument(V3)
    # assembly_v3 has NO spool/gasket objects (those only exist in v4 exploded):
    # 87 objects = 2 flange pieces + bellows + 4 rods + 16 M3 nuts + M5 hardware.
    keep = []
    for o in d.Objects:
        try:
            s = o.Shape
            if s is None or s.isNull() or len(s.Solids) == 0:
                continue
            keep.append(s)
        except Exception:
            pass
    App.closeDocument(d.Name)
    diag["kept"] = len(keep)
    save_diag()
    assert len(keep) == 87, "expected 87 assembly solids, got %d" % len(keep)

    def spool(zstub, zfl):
        # stub cylinder zstub..zstub+20 (OD21/ID19), flange zfl..zfl+7 (R35, bore 19.25, 8xO2.75 on BCD30 @22.5+45k)
        stub = Part.makeCylinder(21, 20, V(0, 0, zstub)).cut(Part.makeCylinder(19, 20, V(0, 0, zstub - 0.5)))
        fl = Part.makeCylinder(35, 7, V(0, 0, zfl)).cut(Part.makeCylinder(19.25, 7, V(0, 0, zfl - 0.5)))
        for k in range(8):
            a = math.radians(22.5 + 45 * k)
            hole = Part.makeCylinder(2.75, 9, V(30 * math.cos(a), 30 * math.sin(a), zfl - 1))
            fl = fl.cut(hole)
        return stub.fuse(fl)

    rebuilt = [
        spool(-28.5, -8.5),    # bottom spool: stub down, flange up
        spool(107.5, 100.5),   # top spool: flange down, stub up
        Part.makeCylinder(22, 1.5, V(0, 0, -1.5)).cut(Part.makeCylinder(19.25, 1.5, V(0, 0, -1.5))),
        Part.makeCylinder(22, 1.5, V(0, 0, 99.0)).cut(Part.makeCylinder(19.25, 1.5, V(0, 0, 99.0))),
    ]
    for i, s in enumerate(rebuilt):
        assert s.isValid(), "rebuilt %d invalid" % i
        assert len(s.Solids) > 0, "rebuilt %d no solid" % i

    allsolids = keep + rebuilt
    t0 = time.time()
    fused = allsolids[0].multiFuse(allsolids[1:])
    diag["fuse_seconds"] = round(time.time() - t0, 1)
    bb = fused.BoundBox
    diag["bbox"] = [round(v, 1) for v in (bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax)]
    diag["fused_valid"] = bool(fused.isValid())
    diag["fused_nsolids"] = len(fused.Solids)
    save_diag()
    assert bb.ZMin < -25 and bb.ZMax > 122, "fused bbox missing spool range: %s" % diag["bbox"]
    assert abs(bb.XMin + 42.2) < 1 and abs(bb.XMax - 42.2) < 1, "x extent wrong"

    doc = App.newDocument("hlr_asm_f3")
    obj = doc.addObject("Part::Feature", "Part")
    obj.Shape = fused
    doc.recompute()
    for _ in range(3):
        Gui.updateGui()

    page = doc.addObject("TechDraw::DrawPage", "DrawPage")
    view = doc.addObject("TechDraw::DrawViewPart", "DrawViewPart")
    tmpls = glob.glob("/tmp/.mount_*/usr/share/Mod/TechDraw/Templates/**/*.svg", recursive=True)
    if tmpls:
        t = doc.addObject("TechDraw::DrawSVGTemplate", "DrawSVGTemplate")
        t.Template = sorted(tmpls)[0]
        page.Template = t
    page.addView(view)
    view.Source = [obj]
    view.Direction = App.Vector(0, -1, 0)
    view.XDirection = App.Vector(1, 0, 0)
    view.Scale = 1.0
    view.X = 148.0
    view.Y = 105.0
    page.ViewObject.show()
    view.ViewObject.show()

    edges = []
    for attempt in range(40):
        try:
            view.touch()
            view.recompute()
        except Exception:
            pass
        doc.recompute()
        for _ in range(5):
            Gui.updateGui()
        edges = view.getVisibleEdges()
        diag["hlr_attempts"] = attempt + 1
        if edges:
            break
        time.sleep(2.0)
    lines = []
    for e in edges:
        try:
            pts = e.discretize(Deflection=0.03)
            lines.append([[round(p.x, 4), round(p.y, 4)] for p in pts])
        except Exception:
            pass
    xs = [p[0] for ln in lines for p in ln]
    ys = [p[1] for ln in lines for p in ln]
    diag["hlr_edges"] = len(edges)
    diag["edge_bbox"] = [round(min(xs),1), round(max(xs),1), round(min(ys),1), round(max(ys),1)] if xs else None
    diag["n_lines"] = len(lines)
    json.dump({"method": "fused3-dvp", "lines": lines}, open(OUT, "w"))
    diag["written"] = True
    save_diag()
except Exception:
    diag["error"] = traceback.format_exc()[-1500:]
    save_diag()
os._exit(0)
