---
name: freecad-tcp-assembly
description: >
  Build parametric CAD assemblies in FreeCAD 1.1.4 via a TCP API server on localhost:9999.
  Covers flanged collar assemblies, ASME fasteners, bellows, renders, and technical drawings.
  Includes server setup (systemd user unit), the off-screen rendering pipeline,
  FastenersWB integration, TechDraw workarounds, and every gotcha discovered
  building a refinery expansion joint from a spec spreadsheet. Verified modeling
  path for profile-based parts (nuts, brackets): PartDesign Sketcher + Pad/Pocket;
  avoid Part-extrude and Y-axis Shape.rotate() (both corrupt geometry here).
---

# FreeCAD TCP Assembly

Build parametric CAD assemblies in FreeCAD 1.1.4 (AppImage) via a TCP server on localhost:9999. Covers flanged collar assemblies, ASME fasteners, bellows, renders, and technical drawings.

## Server Setup

### systemd user unit

File: ~/.config/systemd/user/freecad-server.service

    [Unit]
    Description=FreeCAD API server v3 (xvfb, TCP 127.0.0.1:9999)
    After=network.target

    [Service]
    Type=simple
    WorkingDirectory=%h/freecad
    ExecStart=%h/freecad/launch.sh
    ExecStop=%h/freecad/quit_freecad.py
    Restart=always
    RestartSec=5
    TimeoutStopSec=30

    [Install]
    WantedBy=default.target

### launch.sh (stdin-EOF defense)

    #!/bin/sh
    cd /home/USER/freecad || exit 1
    FIFO=stdin_keepalive.fifo
    [ -p "$FIFO" ] || mkfifo "$FIFO"
    ( exec sleep infinity > "$FIFO" ) &
    exec xvfb-run -a ./FreeCAD_1.1.4-Linux-x86_64-py311.AppImage -c freecad_server_v3.py < "$FIFO" >> server_stdout.log 2>&1

The FIFO keeps FreeCAD from hitting stdin EOF (which kills the process).
The exec makes xvfb-run the tracked main process so systemd Restart=always works.

### quit_freecad.py (clean ExecStop)

    import socket, sys
    try:
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.settimeout(10)
        c.connect(('127.0.0.1', 9999))
        c.sendall(b'QUIT\n')
        c.close()
    except Exception:
        pass
    sys.exit(0)

### Deploy

    systemctl --user daemon-reload
    systemctl --user enable --now freecad-server

Linger must be on: loginctl show-user $(whoami) --property=Linger -> yes.

## TCP Protocol

Connect to 127.0.0.1:9999. Send command + newline.
Response = 4-byte big-endian length + UTF-8 payload.

Commands:
- PING -> PONG <version>
- EXEC:<base64(python)> -> Run arbitrary Python in FreeCAD namespace
- SNAP:<w>,<h>,<path>[,<bg>] -> Render active 3D view to PNG
- OPEN:<abs path> -> Open a .FCStd document
- QUIT -> Clean shutdown (no X11 spam)

### Python client (fc.py)

    import base64, socket, struct

    def cmd(raw, timeout=120.0):
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.settimeout(timeout)
        c.connect(("127.0.0.1", 9999))
        c.sendall(raw + b"\n")
        hdr = b""
        while len(hdr) < 4:
            chunk = c.recv(4 - len(hdr))
            if not chunk: raise RuntimeError("connection closed")
            hdr += chunk
        (n,) = struct.unpack(">I", hdr)
        buf = b""
        while len(buf) < n:
            chunk = c.recv(min(65536, n - len(buf)))
            if not chunk: break
            buf += chunk
        c.close()
        return buf.decode("utf-8", "replace")

    def execcode(code, timeout=180.0):
        return cmd(b"EXEC:" + base64.b64encode(code.encode()), timeout)

## Geometry Creation Patterns

### Collars (annular rings with bolt hole patterns)

Use Part.makeCylinder for outer, cut inner bore, cut N bolt holes at BC radius.
Hole angles must use the SAME formula as bolt placements (see gotcha #2).

### Thin-wall bellows (envelope-minus-core -- NEVER solid-of-revolution)

Solid envelopes are rigid slugs that defeat the entire purpose of a bellows.
Build outer envelope, build inner core, cut = thin-wall shell.

### Bolts (hex head + shank, plain Part::Feature)

Build as hex prism head + cylinder shank, fuse, place at BC radius.
Use plain Part::Feature -- NOT FeaturePython (invisible off-screen, see gotchas).

### Heavy hex nuts (hex prism with bore)

Hex prism extrude, cut cylinder bore, place on bolt tips above top collar.
(2026-10-16: shape extrude is unreliable in this build -- use the PartDesign
sketch+pad recipe in Critical Gotchas #10 instead.)

### PartDesign recipe (verified: nut test, 2026-10-16)

For profile-based parts, use PartDesign Body + fully constrained Sketcher + Pad + Pocket.
This is the RELIABLE path — Part.Face(polygon).extrude() is broken on this build.

Recipe (M3 nut, AF 5.5, H 2.4, bore Ø3.0):
- body.newObject("Sketcher::SketchObject") attached to Origin XY_Plane
- Hexagon = 6 LineSegments on construction circle R = AF/sqrt(3)
- Constraint web (27 DOF removed = FullyConstrained=True):
  6× Coincident closing loop + Coincident circle-center to origin (-1,1)
  + 6× PointOnObject vertex-on-circle + 5× Equal consecutive sides
  + PointOnObject first vertex on X-axis + 1× Radius datum
- Pad Length = H; bore sketch circle + Pocket Type=1 (ThroughAll) Reversed=True
- Gate: sketch.FullyConstrained == True; volume matches analytic to 3 decimals

### Capability probe (capprobe.py)

Run /home/openclaw/freecad/capprobe.py at project start and against any new
FreeCAD build. Tests 16 operations with validity gates and classifies each as
PASS, KNOWN-BROKEN, or REGRESSION. Results saved to capability_matrix/ as JSON.
Verified 2026-10-16 on 1.1.4: 9 PASS, 7 KNOWN-BROKEN, 0 REGRESSION.

## Critical Gotchas

### 1. FeaturePython objects do not render off-screen

FastenersWB FSScrewObject creates FeaturePython objects. Their shapes exist
(verified by volume) but are invisible in off-screen renders under Xvfb.

Fix: Copy the shape into a plain Part::Feature:

    sh = fp.Shape.copy()
    fp.ViewObject.Visibility = False
    g = doc.addObject('Part::Feature', name)
    g.Shape = sh

### 2. Bolt angles must match collar hole angles

Collar holes at 18.0*k degrees. Bolts at 18.0*k + 9.0 degrees = 9 degree offset.
Every bolt lands between holes instead of through them.
Use the SAME angle formula for both collar holes and bolt placements.

### 3. stdin EOF kills FreeCAD

FreeCAD's console mode exits on stdin EOF. Under systemd, stdin is /dev/null
which means instant exit.

Fix: FIFO keepalive in launch.sh:

    FIFO=stdin_keepalive.fifo
    mkfifo $FIFO
    ( exec sleep infinity > $FIFO ) &
    exec xvfb-run -a ./FreeCAD... -c server.py < $FIFO

### 4. TechDraw HLR returns zero edges in off-screen builds
SOLVED 2026-10-16 evening: Gui.showMainWindow() before import TechDrawGui,
template-on-page, and explicit view.XDirection. Full recipe in the
"TechDraw HLR line drawings" section below (run standalone, NOT via the TCP
server -- the server accept loop hangs with that init in its script).

TechDraw's HLR projection produces no geometry even for a Part::Box in the
1.1.4 AppImage running under Xvfb without a visible MDI window.

Workaround: Use the ortho camera + viewFront()/viewIso() + saveImage() for
drawing views. Compose sheets with dimensions drawn from CAD values via
PySide6 QPainter.

### 5. Deep convolutions render black under flat headlight

Self-shadowing on deep waves (44mm) with FreeCAD's single-headlight lighting.
The bellows will look nearly black from outside.

Fix: Boost material ambient/emissive, or accept it and use the section view
for geometry verification. The SECTION view shows the true geometry.

### 6. Polygon winding determines face normal direction

Reversed winding means inward-facing normals, which means black rendering.
If the revolve comes out dark, flip the point order:

    pts = list(reversed(pts))

### 7. Bellows must be thin-wall, not solid

Solid-of-revolution envelopes are rigid slugs. A bellows exists to flex --
model as thin-wall shell (envelope minus core).

### 8. Set FileName before doc.save()

If a doc was created via App.newDocument(name) and never saveAs(path),
then doc.save() raises: Object attribute FileName is not set.
Always saveAs(path) first, then use save() for subsequent saves.

### 9. Multiple Gui.updateGui() pumps after geometry changes

One pump is not enough. Use at least 8-10 pumps in a loop after creating
or modifying geometry, or the render will catch stale geometry.

### 10. Part-extrude and Y-axis Shape.rotate() corrupt geometry; PartDesign and Z-rotate verified (2026-10-16)

- Part.Face(polygon).extrude() yields solids flagged invalid AND with wrong
  volume, even for a simple closed hexagon on a fresh server (nut test:
  valid=False, 42.3 vs 62.9 mm3). Lofting two identical polygon wires gives the
  same invalid flag (volume correct). An invalid-flagged solid is SILENTLY
  DROPPED by later fuse/cut -- geometry vanishes without any error.
- Shape.rotate() about the Y axis (45 deg) corrupts geometry (misoriented
  chamfer edges, booleans returning the complement). Z-axis rotations on plain
  shapes are VALID (verified on a pad shape and a plain box). For placement,
  prefer doc-object Placements (Rotation(X,180) on the flipped top flange
  rendered correctly).
- VERIFIED RELIABLE PATH for profile-based parts (fully constrained nut test):
  PartDesign Body -> Sketcher sketch attached to Origin XY_Plane
  (AttachmentSupport, fallback Support, MapMode FlatFace) -> Pad -> Pocket.
  Recipe (M3 nut AF 5.5, H 2.4, bore 3.0): hexagon = 6 LineSegments with
  vertices on a construction circle R = AF/sqrt(3); constraints = 6x Coincident
  closing the loop + Coincident circle-center to origin (-1,1) + 6x
  PointOnObject vertex-on-circle + 5x Equal consecutive sides + PointOnObject
  first vertex on X-axis + 1x Radius datum = exactly 27 DOF removed ->
  solve()=0 and FullyConstrained=True, no redundancy. PartDesign::Pad
  Length=T; bore sketch + PartDesign::Pocket Type=1 (ThroughAll) with
  Reversed=True when the sketch sits on the bottom face. Volumes matched
  analytic values to 3 decimals (62.873 / 45.909 mm3). Requires
  import Sketcher; gate on sketch.FullyConstrained.

### 11. App::Link .Shape ignores ancestor container placements (2026-10-27)

- `l.Shape` on an App::Link returns the linked object's shape with ONLY the
  link's own placement applied. Placements of ancestor App::Part containers
  (e.g. a mirrored top-station container: Rotation(X,180) + translate) are NOT
  composed in.
- Symptom when assembling world geometry (fuse, HLR, section renders): links
  from transformed containers land at LOCAL coordinates, duplicating/overlapping
  other parts; multiFuse then silently drops a large fraction of solids (v6:
  half the 92-link assembly vanished with no error).
- Fix: for each link, walk InList for App::Part parents, compose their placements
  outermost×…×innermost, and apply to a shape copy:
  `s = l.Shape.copy(); s.Placement = chain.multiply(s.Placement)`.
  Gate: fused bbox must equal the world-union bbox of all link shapes.

## Exploded views and multi-state assemblies (verified 2026-10-16)

- **Compose placements, never replace them.** Building an exploded/state variant
  via po.Shape = o.Shape followed by po.Placement = App.Placement(offset)
  REPLACES each part's baked placement -- the top flange lost its X180 flip,
  z-offsets vanished, and placement-positioned hardware collapsed onto the
  axis. Correct: pl = App.Placement(o.Placement) then compose on the copy
  (pl.Base.z += dz*f for axial groups; for radial groups offset along the
  part's own radial direction: pl.Base.x += (bx/39)*RAD*f etc., where
  (bx,by) = pl.Base is the part's assembled position). Reading o.Placement.Base
  gives each part's assembled position for group-targeted offsets.
- **Section renders of multi-part assemblies: cut each part separately, never
  fuse.** fuse() over 20+ placed shapes failed and the boolean silently
  returned the cutting box instead of the intersection. Reliable: per object,
  piece = o.Shape.common(section_box) (each part is a simple valid shape ->
  clean BOP), then display Part.Compound(cutparts) as one Part::Feature.
  Renders as the sectioned assembly with zero fuse risk.
- **GUI visibility persists across runs.** A prior run's
  ViewObject.Visibility = False loop keeps objects invisible when the same
  document is reused in the long-lived server (in-memory state). Before beauty
  renders: for o in doc.Objects: o.ViewObject.Visibility = True.
- **Server document namespace persists across EXEC calls.** App.openDocument
  returns the in-memory doc if already open, including stale objects from
  failed attempts -- purge by name prefix before re-adding, and never use the
  pre-seeded `doc` global (a prior script's close-all loop leaves it a deleted
  wrapper; touching it raises "deleted object").
- Exploded scheme that worked (bellows anchored at z0): flange pieces +/-18,
  gaskets +/-30, spools +/-48, M5 hardware rides with its spool group (keeps
  the bolt/washer/nut stack clamped visually), tie rods + their nuts move
  radially outward. Render states f=0/0.5/1.0 as iso plus a front hero at f=1.

## Technical drawing sheets -- ortho renders + PIL composer (verified 2026-10-16, expansion joint project)

Full pipeline that delivered a complete 5-sheet A4 dimensioned drawing package
(4 part sheets + assembly sheet w/ balloons, BOM, notes) + bundled PDF. Has now
worked on two projects (collar job, expansion joint).

1. RENDER (in FreeCAD server): per part doc, per view -- viewFront / viewTop /
   viewLeft / viewIsometric, then fitAll + 10-12x updateGui, saveImage
   1200x900 white. Unhide ALL objects first (visibility persists across runs,
   see exploded-views section). One server pass can render ~15-17 views.
2. CALIBRATE: pixel-scan each PNG for the non-white bbox (sample every 2 px --
   fast enough), then compute px/mm from a KNOWN model dimension for that view
   axis (flange front width = 84 across ears, side height = 27, bellows height
   = 55, plate width = 40, assembly height = stack extent). Write per-view
   {path, bbox, pxmm} to a views.json sidecar -- this decouples rendering from
   sheet composition and lets the composer run OUTSIDE FreeCAD.
3. COMPOSE (system python3 + Pillow 12 -- NOT Qt inside the FreeCAD server:
   QPainter sheet composition segfaulted the server's EXEC handler twice on
   2026-10-16, even after a clean restart; it worked once for the collar job,
   so treat in-server Qt sheets as unreliable). A4 landscape 2339x1654 @200dpi;
   double border frame; title block bottom-right (project / part / qty /
   material / scale / rev / date / drawn-by); view labels; dimension style:
   blue (#1c4f9c) lines, extension ticks, filled arrowheads, label above line.
   Scale math: paste each view scaled by k = feat_px / (feat_mm * pxmm) so the
   KNOWN feature spans the target px. The feature is centered in its render
   bbox AND the bbox center equals the image center (fitAll behavior,
   verified) -- so page coords for a model point (x, y) relative to the view
   center = (x, y) * (pxmm * k). Draw dimensions from CAD values, never
   pixel measurements.
4. FURNITURE that reads well: extension-tick + arrow + text-above-line dims,
   dot-terminated leaders for hole callouts ("8X O5.5 EQ.SP. ON O60 BCD"),
   numbered balloons with leaders on the assembly view, BOM table
   (ITEM/PART/MATERIAL/QTY), notes bar with the display-model disclaimer.
5. PDF: Pillow multi-page -- pages[0].save(pdf, save_all=True,
   append_images=pages[1:], resolution=200). No Qt needed.
6. QA: view every sheet (view_image) before delivering; check spelling,
   legibility, overlaps, dims vs CAD values. A PIL auto-fit loop (measure text
   width, shrink font until it fits the plate/sheet) fixes overflow cheaply.
7. DELEGATION: an isolated subagent with the handoff doc + views.json + this
   section completed the entire 5-sheet package autonomously (3 QA iterations)
   without touching the FreeCAD server.

Reference implementation: /home/openclaw/freecad/make_sheets_pil.py and the
delivered sheets in /home/openclaw/.openclaw/workspace/freecad/expansion-joint-v4/drawings/.

## TechDraw HLR line drawings -- real geometry, standalone recipe (verified 2026-10-16 evening, expansion-joint-v4)

Replaces shaded ortho renders with true HLR line art on the PIL sheets.
Pipeline (all /home/openclaw/freecad/): gen_hlr_real.py -> merge_asm.py ->
rasterize_hlr.py -> make_sheets_hlr.py (latter two: system python3 + PIL).

Run generation STANDALONE, not through the TCP server:
    cd /home/openclaw/freecad && xvfb-run -a ./FreeCAD_1.1.4-Linux-x86_64-py311.AppImage -c gen_hlr_real.py
The server's QTimer accept loop stopped answering PINGs entirely once
Gui.showMainWindow()+import TechDrawGui init was added to its script -- keep
that init OUT of the server; do HLR in standalone -c scripts.

Forum recipe (per view, in a FRESH document each time -- re-adding Page/View
after removeObject in the same doc flakily triggers CS failures):
    Gui.showMainWindow()
    import TechDrawGui              # MUST come after showMainWindow()
    d = App.newDocument(...); obj = d.addObject("Part::Feature"); obj.Shape = ...
    page = d.addObject("TechDraw::DrawPage"); view = d.addObject("TechDraw::DrawViewPart")
    tmpl = d.addObject("TechDraw::DrawSVGTemplate"); tmpl.Template = <svg>
    page.Template = tmpl; page.addView(view)
    view.Source = [obj]; view.Direction = V; view.XDirection = XD; view.Scale = 1.0
    page.ViewObject.show(); view.ViewObject.show()
    view.recompute(); d.recompute(); Gui.updateGui()   # pump several times
    edges = view.getVisibleEdges()  # Part edges, mm, centered on source bbox

Hard-won rules (all reproduced 2026-10-16):
- view.XDirection is REQUIRED. Null/default gives "DVP - View - failed to
  create projection CS" (deterministic on some docs) or 90-deg rotated views.
  front (0,-1,0)->(1,0,0)   top (0,0,1)->(1,0,0)
  left  (-1,0,0)->(0,-1,0)  iso (1,1,1)->(-1,1,0)
- Raw edge coords are Y-DOWN page coords (2026-10-28 proof: part at world
  z -26..-11 -> edge v +60.5..+75.5, i.e. v = zc - z). Map py = CY + (v-cy)*s
  DIRECTLY in y-down rasters (PIL); pre-negating y mirrors the view (the old
  "negate y" rule only worked paired with a CY - y*s mapper -- copying the
  negate into a CY + y*s mapper double-flipped asm views 2026-10-28).
  Never negate x -- chiral features (plate text) would mirror. Do not trust
  eyeballing outline text at 1x (mirrored vs 180-rotated look alike): build a
  labeled A/B composite image and compare, and/or probe the edge JSON for an
  ASYMMETRIC feature's v-sign (symmetric parts pass mirrored QA).
- LinkPlacement rotation binds the linked object's LOCAL ORIGIN, not its
  centroid; .Placement.Base expressions bind that origin too (plate master
  local z 0..2 -> pos z -18.5 gave world -26..-11). Probe placements LIVE
  (Explode_F 0/1 -> recompute -> read) rather than transcribing
  ExpressionEngine strings -- one mis-transcribed sign silently moved a part
  20 mm. And verify expression mounts against ACTUAL adjacent geometry:
  a plate mounted tangent to Stub_OD sat buried inside the Flange_OD spool
  wall for four versions (v4-v7); check common() volume == 0 vs neighbors.
- Booleans AND HLR SILENTLY DROP solids: assembly_v3's spool/gasket shapes
  pass isValid() but vanish in fuse/HLR (projected 125 mm tall instead of
  156) with NO error -- the same poison poisons both paths. Gate every view:
  assert projected extent vs known mm span (<10 pct); gate fused bbox too.
  Workaround: rebuild poisoned parts from primitives at their assembly
  positions (same doctrine as geometry building), then multiFuse.
  NOTE: assembly_v3.FCStd contains NO spool/gasket objects at all (87 = 2
  flange pieces + bellows + 4 rods + 16 M3 nuts + M5 hardware); the 156mm
  stack with spools+gaskets = 91 solids only exists conceptually / in the v4
  exploded doc -- add rebuilt ones when fusing.
- NO inter-object occlusion between separate source solids: every part's
  full edge set is drawn (bolts through spools, text through plate). Single-
  object compound Source does NOT fix it. FIX: multiFuse everything into ONE
  solid first (0.8s for 91 solids, valid) -- intra-solid self-occlusion is
  correct, and the fuse also guarantees no solid gets dropped. Verified on
  the expansion-joint assembly front view (bolts correctly hidden behind
  spool flanges).
- print() is swallowed in -c mode and os._exit(0) drops buffered stdout:
  write results to a JSON file, never rely on console output.
- Fallback TechDraw.project/projectEx (needs "import TechDraw", not just
  TechDrawGui) returns a TRANSPOSED CS for front views (screen-x <- world z)
  and also drops solids -- the DVP path with explicit XDirection is preferred.
- Rasterize: edge.discretize(Deflection=0.03) -> polylines -> PIL at the
  sheet's px/mm calibration, centered on bbox (or world anchor for merged
  views); composer reads views_hlr/views_hlr.json, same schema as views.json.

## Assembly Pattern (Flanged Collar Pair)

1. Bottom collar at z=0, thickness t
2. Top collar at z=t (face-to-face, touching)
3. Bolts: heads below bottom collar (z=-head_h to 0),
   shanks through both collars (0 to 2t),
   tips protruding above top collar
4. Nuts: on top of top collar (z=2t to 2t+nut_h),
   threaded onto bolt tips

Bolt shank length = 2t + nut_h + 2 threads_proud

## Rendering Pipeline

    import FreeCADGui as Gui
    Gui.updateGui()
    v = Gui.activeDocument().activeView()
    v.viewIsometric(); v.fitAll()
    for _ in range(10): Gui.updateGui()  # multiple pumps needed
    v.saveImage('/tmp/render.png', 1600, 1200, 'White')

- Multiple Gui.updateGui() pumps required after geometry changes
- White background for clean renders
- 1600x1200 minimum for detail visibility
- Copy from /tmp to workspace immediately (tmp is volatile)

## Export

    import Import, Mesh
    doc.saveAs('/path/model.FCStd')
    Import.export([obj1, obj2], '/path/model.step')
    Mesh.export([obj], '/path/part.stl')
