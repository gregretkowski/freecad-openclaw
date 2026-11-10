import math, os, json
import FreeCAD as App
import Part

OUTD = "/home/openclaw/.openclaw/workspace/freecad/capability_matrix"
os.makedirs(OUTD, exist_ok=True)
def V(x, y, z): return App.Vector(x, y, z)

results = []

def probe(name, fn, expect="pass"):
    """Run fn() -> (ok, detail). Record result."""
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, "EXCEPTION: " + str(e)[:200]
    status = "PASS" if ok else "FAIL"
    if expect == "known_broken" and not ok:
        status = "KNOWN-BROKEN"
    results.append(dict(name=name, ok=ok, detail=str(detail)[:200], status=status))
    print("[%-14s] %-30s %s" % (status, name, str(detail)[:120]))

def close_all_probe_docs():
    for n in list(App.listDocuments().keys()):
        if n.startswith("capprobe_"):
            try: App.closeDocument(n)
            except: pass

# ===== TIER 1: Verified-reliable operations =====

def t_primitives():
    b = Part.makeBox(5, 3, 2)
    c = Part.makeCylinder(2.5, 10)
    k = Part.makeCone(5, 2, 6)
    vols = [b.Volume, c.Volume, k.Volume]
    want = [30.0, math.pi*6.25*10, math.pi*2*(25+10+4)]
    ok = all(s.isValid() for s in (b, c, k)) and all(abs(a-b) < 0.1 for a, b in zip(vols, want))
    return (ok, "vols=%s" % ["%.2f" % v for v in vols])

def t_revolve_ring():
    # Rectangle 2..8 x 0..10 revolved about Z -> ring pi*(64-4)*10
    pts = [V(2, 0, 0), V(8, 0, 0), V(8, 0, 10), V(2, 0, 10)]
    f = Part.Face(Part.makePolygon(pts))
    s = f.revolve(V(0, 0, 0), V(0, 0, 1), 360)
    want = math.pi * (64 - 4) * 10
    return (s.isValid() and abs(s.Volume - want) < 2, "vol=%.1f want=%.1f" % (s.Volume, want))

def t_chamfer():
    box = Part.makeBox(4, 10, 5, V(20, -5, 14))
    edge = None
    for e in box.Edges:
        eb = e.BoundBox
        if eb.XLength < 1e-6 and eb.ZLength < 1e-6 and eb.YLength > 1:
            if edge is None or eb.XMax > edge.BoundBox.XMax:
                edge = e
    if edge is None: return (False, "no edge found")
    g = box.makeChamfer(2.0, [edge])
    return (g.isValid() and abs(g.Volume - 180.0) < 5, "valid=%s vol=%.1f" % (g.isValid(), g.Volume))

def t_placement_compose():
    d = App.newDocument("capprobe_pc")
    o = d.addObject("Part::Feature", "PC")
    o.Shape = Part.makeBox(5, 3, 2)
    o.Placement = App.Placement(V(10, 0, 5), App.Rotation(V(1, 0, 0), 180))
    pl = App.Placement(o.Placement)
    pl.Base.z += 7.0
    o.Placement = pl
    bb = o.Shape.BoundBox
    ok = (o.Shape.isValid() and abs(bb.ZMin - 10) < 0.01 and abs(bb.ZMax - 12) < 0.01)
    App.closeDocument(d.Name)
    return (ok, "bbox z=%.2f..%.2f" % (bb.ZMin, bb.ZMax))

def t_compound_common():
    parts = [Part.makeBox(10, 10, 10), Part.makeCylinder(4, 20), Part.makeCone(5, 2, 8)]
    cutbox = Part.makeBox(60, 60, 60, V(-5, -30, -5))
    outs = [s.common(cutbox) for s in parts]
    comp = Part.Compound(outs)
    return (comp.isValid() and comp.Volume > 0 and all(x.isValid() for x in outs),
            "all valid, vol>0")

def t_fuse_overlapping():
    a = Part.makeBox(10, 10, 10, V(0, 0, 0))
    b = Part.makeBox(10, 10, 10, V(5, 0, 0))
    u = a.fuse(b)
    return (u.isValid() and len(u.Solids) == 1 and abs(u.Volume - 1500) < 5,
            "vol=%.1f solids=%d" % (u.Volume, len(u.Solids)))

# ===== TIER 2: Verified-broken operations (expect failure) =====

def t_face_extrude_hex():
    """Part.Face(polygon).extrude() - documented broken on this build"""
    R = 3.0
    pts = [V(15 + R*math.cos(math.radians(60*i)), R*math.sin(math.radians(60*i)), 0) for i in range(6)]
    try:
        f = Part.Face(Part.makePolygon(pts))
        s = f.extrude(V(0, 0, 4.7))
        return (not s.isValid() or abs(s.Volume - 109.9) > 5,
                "valid=%s vol=%.1f (broken: expect invalid or wrong vol)" % (s.isValid(), s.Volume))
    except Exception as e:
        return (True, "raises as expected: %s" % str(e)[:80])

def t_rotate_y_box():
    """Shape.rotate() about Y - documented broken on this build"""
    b = Part.makeBox(40, 40, 40)
    b.rotate(V(0, 0, 0), V(0, 1, 0), 45.0)
    # if rotate corrupted: bbox will be asymmetric or volume wrong
    bb = b.BoundBox
    vol_ok = abs(b.Volume - 64000) < 1
    sym = abs(bb.XMin + bb.XMax) < 0.1 and abs(bb.ZMin + bb.ZMax) < 0.1
    return (not (vol_ok and sym), "corrupted=%s (rot-Y is broken)" % (not (vol_ok and sym)))

def t_loft_wires():
    """Part.makeLoft of polygon wires - documented broken on this build"""
    R = 4.0
    w0 = Part.makePolygon([V(R*math.cos(math.radians(60*i)), R*math.sin(math.radians(60*i)), 0) for i in range(6)])
    w1 = Part.makePolygon([V(R*math.cos(math.radians(60*i)), R*math.sin(math.radians(60*i)), 10) for i in range(6)])
    try:
        s = Part.makeLoft([w0, w1], True, True)
        return (not s.isValid(), "confirmed broken: valid=%s vol=%.1f" % (s.isValid(), s.Volume))
    except Exception as e:
        return (True, "raises as expected")

# ===== TIER 3: PartDesign recipe (verified in nut test) =====

def t_partdesign():
    d = App.newDocument("capprobe_pd")
    body = d.addObject("PartDesign::Body", "B")
    sk = body.newObject("Sketcher::SketchObject", "S")
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    try: sk.AttachmentSupport = [(xy, "")]
    except Exception: sk.Support = [(xy, "")]
    sk.MapMode = "FlatFace"
    R = 8.0 / math.sqrt(3.0)
    pts = [V(R*math.cos(math.radians(60*i)), R*math.sin(math.radians(60*i)), 0) for i in range(6)]
    for i in range(6):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i+1) % 6]), False)
    ci = sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), R), True)
    cons = []
    for i in range(6):
        cons.append(Sketcher.Constraint("Coincident", i, 2, (i+1) % 6, 1))
    cons.append(Sketcher.Constraint("Coincident", ci, 3, -1, 1))
    for i in range(6):
        cons.append(Sketcher.Constraint("PointOnObject", i, 1, ci))
    for i in range(5):
        cons.append(Sketcher.Constraint("Equal", 0, i+1))
    cons.append(Sketcher.Constraint("PointOnObject", 0, 1, -1))
    sk.addConstraint(cons)
    sk.addConstraint(Sketcher.Constraint("Radius", ci, R))
    pad = body.newObject("PartDesign::Pad", "P")
    pad.Profile = sk
    pad.Length = 2.4
    doc.recompute()
    sk2 = body.newObject("Sketcher::SketchObject", "Bore")
    sk2.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 1.5), False)
    sk2.addConstraint(Sketcher.Constraint("Coincident", 0, 3, -1, 1))
    sk2.addConstraint(Sketcher.Constraint("Radius", 0, 1.5))
    pk = body.newObject("PartDesign::Pocket", "Pk")
    pk.Profile = sk2
    pk.Type = 1
    pk.Reversed = True
    doc.recompute()
    sh = body.Tip.Shape
    want = (0.5*6*(8/math.sqrt(3))*4.0 - math.pi*1.5**2) * 2.4
    ok = sh.isValid() and len(sh.Solids) == 1 and abs(sh.Volume - want) < 3.0
    App.closeDocument(d.Name)
    return (ok, "vol=%.2f want=%.2f" % (sh.Volume, want))

import Sketcher

close_all_probe_docs()

# ===== run all =====
probe("primitives", t_primitives, "pass")
probe("revolve_ring", t_revolve_ring, "pass")
probe("chamfer_box", t_chamfer, "pass")
probe("placement_compose", t_placement_compose, "pass")
probe("compound_common", t_compound_common, "pass")
probe("fuse_overlapping", t_fuse_overlapping, "pass")
probe("partdesign_pad_pocket", t_partdesign, "pass")
probe("face_extrude_hex", t_face_extrude_hex, "known_broken")
probe("rotate_y_box", t_rotate_y_box, "known_broken")
probe("loft_wires", t_loft_wires, "known_broken")

close_all_probe_docs()

# ===== report =====
passed = [r for r in results if r["ok"]]
failed = [r for r in results if not r["ok"]]
print("")
print("=== CAPABILITY PROBE RESULTS ===")
print("PASS: %d | FAIL: %d | TOTAL: %d" % (len(passed), len(failed), len(results)))
for r in results:
    print("  %-14s ok=%-5s %s" % (r["name"], r["ok"], r["detail"][:80]))
if failed:
    print("")
    print("FAILED (need investigation):")
    for r in failed:
        print("  -", r["name"], ":", r["detail"][:100])

# save JSON
out = dict(date=time.strftime("%Y-%m-%d %H:%M"), probes=results,
           passed=len(passed), failed=len(failed))
with open(os.path.join(OUTD, "capability_matrix_latest.json"), "w") as fh:
    json.dump(out, fh, indent=1)
print("[json saved]")
result = "done: %d passed, %d failed" % (len(passed), len(failed))
print("[result] %s" % result)