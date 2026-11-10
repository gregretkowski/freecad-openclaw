---
name: "freecad-remote-control"
description: "Operates the FreeCAD 1.1 API server on 127.0.0.1:9999 — hosted by the freecad-server systemd user unit (auto-restart, clean QUIT stop; background-exec hosting is a 30:00-capped fallback); drive via EXEC/SNAP/OPEN/QUIT; FreeCAD 1.1 gotchas (stdin EOF, hidden window, const TopoShape handles, revolve winding), the Assembly joint surface, TechDraw HLR line drawings as raster sheets OR pages embedded in the FCStd (GUI-init recipe, y-flip + silent-drop rules -> techdraw-hlr-drawings.md), FastenersWB headless install/API; shape-build validity rules (Y-rotate/extrude/loft broken — primitives+revolve+chamfer+PartDesign only), BOP quirks, render-probe build gates; session-state persistence, mirrored-Placement math, App::Link world shapes (ancestor-container transforms), reopen-error audits, per-part section renders, ShapeString text plates."
---

# FreeCAD remote control (optiplex)

Drive the FreeCAD GUI instance (1.1.4 AppImage under Xvfb) through a TCP API on
127.0.0.1:9999. Use for any FreeCAD task on this host: parametric modeling, edits,
screenshots, STL/STEP export, assemblies. Assets live in `/home/openclaw/freecad/`:
server `freecad_server_v4.py` (v3 retired 2026-10-17 — accept-loop hang, see
pitfalls), client `fc.py`, launcher `launch.sh`, stop helper
`quit_freecad.py`, logs `server.log` + `server_stdout.log`, unit
`~/.config/systemd/user/freecad-server.service`.

## Host it: systemd user unit (primary — verified 2026-10-11)

1. Check first: `systemctl --user status freecad-server` + `ss -ltn | grep 9999`
   (listening = already up, just PING) and `pgrep -x freecad`.
2. Control: `systemctl --user start|stop|restart freecad-server`.
   - stop/restart is clean: ExecStop runs `quit_freecad.py` (sends `QUIT` → FreeCAD
     exits while X is alive — no X11 spam; this replaced the Ctrl+C X11 flood).
   - `Restart=always` + 5s backoff: any FreeCAD death auto-revives the server.
     Verified: QUIT-killed mid-test → new PID in ~12s → PING PONG (NRestarts=1).
3. Readiness: poll `server.log` for `v4 event loop entering` (~10s), then PING.
4. Unit survives reboots: user manager + `Linger=yes` already set on this host.

Why not other hosting (all tried): foreground exec cells get timeout-killed and take
the process tree with them; tmux from exec gets reaped; **managed background exec
tasks are SIGTERM'd at exactly 30:00** (harness `overall-timeout` cap — runtimeMs
1800213 on the killed task), so they are only a <30min fallback:
```
cd /home/openclaw/freecad && : > server.log && : > server_stdout.log && tail -f /dev/null | xvfb-run -a ./FreeCAD_1.1.4-Linux-x86_64-py311.AppImage -c freecad_server_v4.py >> server_stdout.log 2>&1
```
(`background: true`). Connection refused later ⇒ relaunch — FreeCAD exits cleanly at
kill time, so a plain relaunch is safe; don't re-derive a crash.

The unit's launcher (`launch.sh`) matters: it feeds FreeCAD's stdin from a FIFO held
open by `sleep infinity` (console exits on EOF) and `exec`s xvfb-run so the tracked
main process dies with FreeCAD — a plain `tail -f | xvfb-run` pipeline leaves the unit
"active" with a dead server and Restart=never fires.

## Driving it

Client helper `/home/openclaw/freecad/fc.py` (copy to /tmp if needed):
- `cmd(b'PING')`, `cmd(b'SNAP:1400,1000,/tmp/out.png,White')`, `cmd(b'OPEN:/abs/path.FCStd')`,
  `cmd(b'QUIT')` (clean shutdown) — replies are one line.
- `execcode(code)`: runs arbitrary Python inside FreeCAD with `App/Gui/Part/doc/box` pre-seeded;
  returns captured stdout plus `repr(result)` if the code sets `result`; errors return whole tracebacks.
- CLI: `__main__` EXECs **stdin only** (`execcode(sys.stdin.read())`) — `python3 fc.py cmd "OPEN:..."`
  puts the code on argv, which is ignored, and the empty-code EXEC replies `OK`: a silent
  no-op (verified 2026-10-27, cost a full diagnostic detour). Always feed code via heredoc/stdin
  (`python3 fc.py execcode <<'EOF'`) or call `cmd()` from a wrapper script.
- Wire format: 4-byte big-endian length + UTF-8 payload per response.
- Renders: server writes them chmod 644. **`view_image` rejects /tmp** ("not under an allowed
  directory") — copy renders into `~/.openclaw/workspace/freecad/renders/` before inspecting,
  and attach via MEDIA from the workspace copy (attachment procedure:
  attach-file-to-chat-reply).

## Pitfalls (evidenced 2026-10-11)

- **stdin EOF exits console mode.** `freecad -c script.py` ends in a REPL that quits on EOF —
  `< /dev/null` kills the server shortly after start (log shows
  `[FreeCAD Console mode <Use Ctrl-D (i.e. EOF) to exit.>]`). Always feed stdin via
  `tail -f /dev/null |` (background exec) or the unit's FIFO (systemd).
- **Never hide the main window.** `mw.hide()` before documents exist ⇒ no GUI documents/views ⇒
  `Gui.ActiveDocument` is None (`'NoneType' object has no attribute 'ActiveView'`). Leave the
  window shown; Xvfb hides it from humans anyway.
- **TopoShape handles are const in 1.1.** `obj.Shape` returns an immutable wrapper — non-const
  calls like `.reverse()` raise "This object is immutable, you can not set any attribute or call a
  non const method". Fix: `sh = obj.Shape.copy(); sh.reverse(); obj.Shape = sh`. Setting
  `obj.Shape` itself on an existing feature works fine.
- **Dark revolved solids.** A simple revolve can render near-black (normals inward); the clean
  fix is rebuilding the feature from the opposite polygon winding (`reversed(pts)`) — positive
  volume, lit render, same geometry (verified v1). LIMIT (verified expansion-joint v2
  2026-10-12): a boolean-cut thin-wall shell stayed near-black after envelope winding flips AND
  ShapeMaterial Ambient/Emissive boosts — treat deep-convolution darkness as a viewport lighting
  quirk: prove geometry via a section render + volume/mass, and hide occluding accessories
  (cover/shields) instead of fighting shading.
- **Blank renders.** Freshly added/modified objects need event pumps: 3-8× `Gui.updateGui()`
  between `fitAll()` and `saveImage()`, or simply re-snap after the scene settles.
- **pkill self-match**: `pkill -f freecad` from a command whose text contains "freecad" (paths do)
  SIGTERMs your own cell. Use `pkill -x freecad` — see test-local-server-in-exec.
- `App.Version()` returns a **list** in 1.1.4, not a dict (`['Version']` raises TypeError).
- **FeaturePython scripted objects don't render off-screen** (verified 2026-10-12: valid M20 bolt
  solid, invisible in saveImage) **and may not survive save/reopen** (the Proxy class can fail to
  restore if the module was modified during the session). Fix for both: copy the shape into a
  plain `Part::Feature` render proxy and hide the FeaturePython original. The proxy pattern was
  used for all 40 fasteners in the collar assembly render (all visible).
- **`doc.save()` on a `newDocument()` doc** raises "Object attribute 'FileName' is not set" —
  use `doc.saveAs(path)` first (verified 2026-10-12, cost a render cycle).
- **`App::Link.Shape` omits ancestor container placements.** The link shape carries only the
  link's own Placement; ancestor `App::Part` transforms (e.g. a mirrored top station) are NOT
  applied. Consuming `l.Shape` as world geometry silently uses local coords — duplicated
  overlapping solids make multiFuse drop parts with no error (half the v6 assembly vanished,
  2026-10-27). Fix: `s = l.Shape.copy()`; left-multiply the composed ancestor-Part placement
  (outermost ∘ … ∘ innermost) onto `s.Placement`; after that the fuse ran clean (1 solid,
  bbox = link-union bbox).
- **Expression-driven Placements: probe before rewriting.** Printed
  ExpressionEngine strings mislead about intent — a sign "fixed" from a
  misread moved the v7 data plate 20 mm until the bbox gate caught it
  (2026-10-28; SPEC names understate scope: `Flange_T`=7 is the disc only,
  the flange part spans 27 with its stub). Probe live semantics first (set
  driving cell → recompute → read placement → restore), then `setExpression`
  the new form and gate on the expected world bbox. `.Placement.Base`
  expressions bind the linked feature's sketch ORIGIN, not the shape
  centroid — rotations change which face a half-thickness offset lands on.
- **One EXEC at a time — literally.** A grinding op (TechDraw PolyAlgo HLR, heavy booleans)
  blocks every command; the client times out and the response is lost even though the work
  finishes server-side. Save the doc before risky ops; recovery =
  `systemctl --user restart freecad-server` + `OPEN:<saved path>` — in-memory-only changes
  (e.g. an unsaved TechDraw page) die with the restart (verified 2026-10-12).

## Saved-file restore-error audit (verified 2026-10-27, expansion-joint v5→v6)

Opening a delivered FCStd logs almost nothing real to stdout — ~700 lines of
`Requested non-existent style parameter token` are AppImage Qt cosmetics (grep them
out). Real restore errors live in object state, and they are silent: a sketch whose
constraint expressions fail still restores its saved geometry, so renders look fine
while every dependent is frozen out of recompute — the parametric chain is broken
until the driving parameter changes.

1. Baseline: list objects whose `State` contains `Touched`/`Invalid`/`Error`.
2. `doc.recompute(None, True, True)`, re-audit — still-flagged objects carry real
   defects; per-object error text prints to console during recompute (or call
   `o.recompute()` alone to surface it).
3. Diagnose per type: sketches via `o.solve()` (-4 = conflict) + `FullyConstrained`;
   features via the single-`o.recompute()` message.
4. Fix patterns (all verified):
   - **Unit mismatch** `mm - 0 * sin(...)`: the literal `0 *` term is unitless — drop
     dead zero terms. Bindings must go through `obj.setExpression(path, expr)`;
     assigning `obj.ExpressionEngine = [...]` raises "Property is read-only".
   - **Over-constrained sketch**: point-point `Symmetric` about an axis imposes TWO
     equations (coordinate-equality + mirror); if the equality duplicates an existing
     Vertical/Horizontal, replace it with a named directional Distance from the origin
     (`Sketcher.Constraint('DistanceY', -1, 1, geoId, 2, v)`) bound to an expression.
     Gate: `solve() == 0` and `FullyConstrained`.
   - **Orphan features** (empty `InList`, owned by no Body — superseded iteration
     debris): their stale shapes recompute to failures (e.g. multi-solid). Delete
     iteratively to fixpoint — each pass frees upstream sketches feeding only dead
     patterns (v6: 74 removed, master volumes/assembly extents byte-identical) — the
     file-level counterpart of the in-session purge rule below.
   - **Live vs debris before diagnosing**: flagged chains may be abandoned parallel
     builds — walk the owning Body's tip chain (`Tip` → `BaseFeature`…) and the
     App::Link targets to find the live feature before declaring a parametricity
     break (v6: debris sketches carried the unit bug; the in-body copies were clean
     and parametric). Diagonal features (ears at 45°) do NOT extend the axis-aligned
     bbox — confirm feature presence with `isInside` probes at mid-points, not extents.
5. Completion gate: 0 flagged objects after forced recompute AND after cold-reopen of
   the saved file; parametric spot-check (edit one driving cell → geometry follows
   exactly → revert exact).

Delivering FCStd over chat: OpenClaw's outbound media sniffing rewrites it to `.zip`
(zip magic bytes; the rewrite is in the mime/normalization layer before Telegram).
Ship CAD deliverables inside a real `.zip` (inner filename survives) or via scp.

## Shape API validity + build gates (verified 2026-10-16, expansion joint v1-v3)

Broken in 1.1.4 headless — produces invalid-flagged solids that poison later
BOPs (fuse SILENTLY DROPS an invalid argument; cut no-ops or removes
everything):
- `Shape.rotate()` — Y-axis rotations corrupt geometry (verified); Z-axis
  rotations on plain shapes are VALID (nut test 2026-10-16), and doc-object
  Placements are always safe. Still prefer native positioning
  (makeCylinder/makeCone take a `dir` argument; for 90° multiples build
  axis-aligned boxes by swapping coordinates).
- Polygon `Part.Face(...).extrude(...)` — invalid at BOTH windings.
- `Part.makeLoft` — correct volume but valid=False.

Verified-good: primitives (makeBox/makeCylinder/makeCone), polygon-face
`revolve` (try both windings, keep the valid positive-volume result),
fuse/cut/common of validated inputs, `makeChamfer`. BOP rules: `cut()` takes
ONE shape (loop it — varargs raise "at most 2 arguments"); there is no
`.union`, use `.fuse`; validate every ingredient (isValid + Volume>0) BEFORE
any BOP. Chamfer/feature edges must be found by measuring (edge lies in the
target face plane, max midpoint planar radius) — assuming axes mis-orients
half the features at 90° multiples (Greg caught exactly this in the renders).

Gates that actually work: `valid=True` + a volume window do NOT catch
orientation or zero-wall bugs — add `isInside` probes at discriminating
asymmetric points (mid-wall on each wall type, just-beyond-hypotenuse).
Cut results partition at face contacts, so multi-solid compounds are normal
(6-solid and 2-solid verified) — gate on all sub-solids valid + volume window
+ STL solid=True with matching meshvol, NOT solids==1; fuse() of
volume-overlapping valid pieces does merge to 1 solid. If identical code gives
different BOP results between runs, the long-lived server's OCC state is bad:
`systemctl --user restart freecad-server` (verified fix).

Deliverable versioning (standing practice): each design rev gets new
`*_vN.FCStd/.stl` files; never overwrite a prior rev in place.

## Session state, mirrored Placements, and section renders (verified 2026-10-16, v2/v3 hardware rounds)

- The server session persists EVERYTHING between EXEC calls: document
  contents, namespace variables, and GUI visibility. A failed attempt that
  placed objects leaves them in memory even when the file was never saved
  (asserts fire before saveAs). Purge added objects by name prefix
  (doc.removeObject) before re-placing, and make count asserts equal the
  real per-pass delta (64 M5 pieces, not the BOM's 48 -- the mismatch cost
  three round trips).
- GUI visibility persists too: a section render that hides objects makes the
  next beauty render show only newly added objects (v3 iso showed 16 bare
  bolt stacks, no body). Unhide-all (o.ViewObject.Visibility = True) before
  any render.
- Any script that closes all documents turns the pre-seeded doc global into
  a deleted-object zombie -- reference only documents created in the same
  EXEC (docN.recompute(), never bare doc.recompute()).
- Section renders of placed assemblies: NEVER fuse the placed hardware then
  common() -- the 23-shape fuse BOP fails and common() returns the tool box
  itself. Cut EACH placed shape with the half-space box
  (shape.common(cutbox)) and display Part.Compound(cutparts) -- verified
  correct on the 87-object assembly.
- Mirrored joints: Placement(point, Rotation(X,180)) maps local z to t - z --
  the translate t is the TOP of the desired stack position (nut t=86.3
  landed 81.6-86.3 floating; t=91 seated it 86.3-91 against the flange
  underside at 92). Greg caught the resulting floating nuts in the section
  render.
- Text on plates (verified): Draft.makeShapeString +
  Part.makeFace(wires, "Part::FaceMakerBullseye") + face.extrude works
  (extrude corruption is construction-dependent, not universal). Auto-fit
  letter size to the plate width, sink letters 0.3 into the plate and fuse
  (volumetric -> single solid), and REMOVE discarded fit-attempt
  ShapeStrings before rendering -- they render as stray text fragments
  outside the plate.
- Assembly-build procedures (PartDesign hex recipe, BOM, exploded/drawing
  plan): freecad-tcp-assembly skill (workspace, operator-edited).

## Thin-wall shells of revolution (verified: expansion joint v2, 2026-10-12)

A bellows-style part (thin wall following a wave contour) does NOT survive a direct revolve of
the closed thin profile — winding/validity flakiness: one order gives an invalid negative-volume
solid, the other a self-intersecting bowtie with garbage volume (both tried 2026-10-12).
Reliable construction (verified: 1,033,062 mm3, isValid True):
1. Envelope solid: revolve `[(bore_r, 0)] + [outer contour (r, z)] + [(bore_r, L)]`
   (winding that yields positive volume; v1-proven).
2. Core solid: revolve `[(0, 0)] + [(contour_r - wall_t, z)] + [(0, L)]` (a profile touching the
   axis revolves fine).
3. `shell = envelope.cut(core)`.
Verify `isValid()` and positive Volume after the cut.

## Model mechanisms at rest (user QA expectation)

Greg QA-renders assemblies and flags floating/frozen geometry. Stop collars butt their lug
faces at cold position (the +/-travel gap opens only under motion); mating sleeves sit flush
to the bore minus running clearance; every component attaches to something. A liner 3 mm off
the bore reads as "floating in space" in a section render. Also verified
2026-10-16: Greg reviews renders and catches orientation errors (half the
gussets chamfered on the wrong face) — keep orientation `isInside` probes in
the build gates, not just volume checks.

## CAD builds with subagents (verified: expansion joint, 2026-10-11)

Split so parallelizable work runs on isolated subagents while the parent holds the single
FreeCAD writer seat (one TCP server — no concurrent writers):
- Subagent A: spec sheet (xlsx) → mm parameter table as an importable python file
  (stdlib zipfile+ElementTree parsing; include unit conversions and discrepancy notes).
- Subagent B: profile/geometry math as an importable python file with a `__main__` self-test.
- The spawn objective must state the hard constraint: **no TCP connections / no
  localhost:9999**; files only under the project dir. `sessions_spawn` takes the objective
  as `task` (an `objective` field fails schema validation).
- Parent imports the delivered files via importlib and executes the build through EXEC.
- Relay subagent findings (spec conflicts, ambiguities) into the final user report — they
  are often the most valuable output.

## Assembly workbench (1.1.4) — verified surface

- Registered doc types: `Assembly::AssemblyObject`, `Assembly::JointGroup`,
  `Assembly::AssemblyLink`, `Assembly::BomGroup`, `Assembly::SimulationGroup`, `Assembly::ViewGroup`.
  Gui workbench: `AssemblyWorkbench` (activates fine).
- **Joints are Python scripted objects, not doc types**: `addObject('Assembly::Joint')` and
  `Assembly::FixedJoint` etc. all fail. Create via `Mod/Assembly/JointObject.py`:
  `Joint(joint_docobj, type_index)` (enum: Fixed, Revolute, Cylindrical, Slider, Ball, Distance,
  Parallel, Perpendicular, Angle, RackPinion, Screw, Gears, Belt), grounding via
  `GroundedJoint(joint_docobj, obj_to_ground)`, joints container `UtilsAssembly.getJointGroup(asm)`,
  solver `assembly.solve()`.
- Open issue (partially resolved): wrapping a joint whose doc object is not yet inside the
  assembly's group tree raises `setJointConnectors ... 'NoneType' object has no attribute 'Type'`.
  Creating via `asm.newObject('App::FeaturePython', ...)` gets past the wrap, and
  `fj.Proxy.setJointConnectors(fj, [(part, ['FaceN']), ...])` sets references — but the solver
  still did not reposition the part from console (2026-10-11). Element-map reference formatting
  the GUI normally provides is the suspected gap; deterministic Placement positioning avoids
  the solver entirely for box-style assemblies.

## TechDraw HLR line drawings (off-screen) — WORKING; verified 2026-10-16

HLR works when TechDraw gets GUI init: `Gui.showMainWindow()` then
`import TechDrawGui` (that order), one fresh doc per view, a template on the
page, view shown + recomputed + `Gui.updateGui()` pumped. The 2026-10-12
"0 visible edges for everything" finding was the missing init, not a build
defect. Still true: never set `ProjectionAlgorithm = 'PolyAlgo'` in-server on
big models (grounds the single-threaded server >15 min).

Full procedure + decision rules: **`techdraw-hlr-drawings.md`** (this dir) —
XDirection table, y-down raw edge coords mapped direct (never negate x — chiral text), silent
solid-drop gates + census + primitives-rebuild recovery, the single-solid
multiFuse occlusion fix (separate Source solids never occlude each other),
A/B-composite orientation checks, the standalone
`xvfb-run -c` runner, Pillow sheet composition (verified: 5-sheet A4
PDF delivered 2026-10-16; assembly view occlusion-corrected 2026-10-17),
embedded live TechDraw pages inside the target FCStd + the scale-applied
`getVisibleEdges()` gate + world-anchor balloon mapping (verified 2026-10-28).

Shaded ortho renders (bbox px/mm scan + known feature span) remain the method
for pictorial/exploded views. In-server QtGui sheet composition SEGFAULTS the
EXEC handler (2026-10-16, 3x incl. fresh server) — compose outside the server
in system Python.

## Placement expressions, reopen asserts, version freeze (verified 2026-10-28, v7 plate remount)

- A link `.Placement.Base` expression binds the LINKED OBJECT's local
  ORIGIN, not its centroid (plate master spans local z 0..2 → pos z −18.5
  gave world −26..−11). With LinkPlacement rotation, derive the expected
  world bbox from master bbox × placement, and assert with TOLERANCE —
  fresh-reopen BoundBoxes carry fp jitter; exact `==` fails.
- Probe expression behavior LIVE (set Explode_F 0/1 → recompute → read the
  placement) instead of transcribing ExpressionEngine strings — a
  mis-transcribed sign silently moved a part 20 mm. Read SPEC cell values
  too; names lie (Flange_T=7 is the disc only; the 27 mm flange part =
  7 mm disc + 20 mm stub).
- Expression mounts can BURY a part inside another solid for generations
  (v4→v7 data plate: mounted tangent to Ø42 Stub_OD, sat inside the Ø70
  spool wall — hidden lines on every sheet). After any mount edit:
  `common()` volume vs adjacent solids == 0, and at Explode_F=1 the part's
  bbox must clear every link (bbox-overlap scan), plus a sane world gap.
- Version freeze (v7→v8 verified): close the old doc in the server (freeze),
  cp the FCStd to `<vN+1>/assembly_vN+1.FCStd`, open, verify invariants
  (object count, 0 Invalid/Error after forced recompute, key bboxes, page
  count, Explode_F=0), save — internal Name/Label follow the new filename.
  Append checksums to `EXPANSION_JOINT_SHA256SUMS.txt` (ships chmod 444 —
  `chmod u+w` before appending). Delivery zip = FCStd + drawings PDF.
- Batch `AppImage -c script.py` is flaky (silent empty "Exception while
  processing file", doubled top-level prints; 2026-10-28). The fc.py EXEC
  server channel runs the same HLR view-gen fine (~4 s/view, same session
  that edited the model). Prefer the server channel; batch only when a
  cold process is required.

**Accept-loop hang (fixed 2026-10-17, v4).** v3 fell off the end of the
script into the console REPL and relied on the REPL's stdin hook to pump Qt
events (the only thing that ever fired the QTimer). Once the TechDraw init
(`Gui.showMainWindow()` + `import TechDrawGui`) ran at module scope, fresh
instances still bound/listened and printed `>>>`, but the REPL stopped
pumping — QTimer never fired, PING/QUIT sat in the accept backlog forever
(every ExecStop logged 'server not reachable'; ~5s CPU over 9h = blocked, not
busy). Fix in `freecad_server_v4.py`: end the script with an explicit
`QtWidgets.QApplication.instance().exec_()` — the event loop runs itself, the
REPL is never reached, QUIT still exits via `os._exit(0)`. Never again depend
on the console REPL to pump Qt timers in a `-c` server script.

#
