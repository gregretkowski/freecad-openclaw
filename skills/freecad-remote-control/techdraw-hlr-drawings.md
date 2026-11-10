# TechDraw HLR line drawings (off-screen 1.1.4) — verified 2026-10-16

Trigger: real 2D line drawings from FCStd geometry (deliverable sheets/PDF), or any
`getVisibleEdges()` / DrawViewPart work headless. Supersedes the 2026-10-12
"HLR returns 0 edges" finding: that was missing GUI init, not a build defect.
Delivered proof: expansion-joint-v4 5-sheet package regenerated end-to-end.
(assembly view occlusion-corrected 2026-10-17).

## Working recipe (standalone run — the proven batch path)

```
cd /home/openclaw/freecad && xvfb-run -a ./FreeCAD_1.1.4-Linux-x86_64-py311.AppImage -c gen_script.py
```

The 5-sheet package was delivered this way. Server-side HLR is available
again since the v4 fix (2026-10-17, smoke-verified in-server: cylinder
top-down → 1 visible edge, PING healthy afterward) — but a full sheet batch
is one grinding EXEC that blocks every other command (one-EXEC-at-a-time),
so prefer standalone for batches and reserve in-server HLR for small checks.
Batch flake fallback (verified 2026-10-28): if the standalone run dies with
FreeCAD's EMPTY `Exception while processing file: <script> []` (often with
doubled partial prints and no traceback), do not burn retries — run the same
generator inline via the fc.py `execcode` channel (doc already open →
`App.getDocument(...)`; still one fresh scratch doc per view). Identical view
code the batch dropped ran 4 s/view in-server; same-day sibling batch scripts
succeeded, so it is intermittent channel flake, not a code bug.
Init once per run, order matters: `Gui.showMainWindow()` THEN
`import TechDrawGui`, pump `Gui.updateGui()` a few times before any
TechDraw object.

Per view — the verified configuration is ONE FRESH document per view plus
explicit XDirection (all 17 views then succeeded). A doc-reuse variant with
cleanup between views had produced intermittent projection-CS failures, so
treat fresh-doc-per-view as part of the tested recipe:

1. Copy geometry into a plain `Part::Feature` in the new doc (solids only;
   skip null/empty shapes).
2. `TechDraw::DrawPage` + `TechDraw::DrawSVGTemplate` (any template SVG globbed
   from `/tmp/.mount_*/usr/share/Mod/TechDraw/Templates/**`); `page.Template = t`.
3. `TechDraw::DrawViewPart`: `page.addView(view)`, `view.Source = [feat]`,
   `view.Direction`, **explicit `view.XDirection`** (table below), `view.Scale`,
   `view.X/Y`.
4. `page.ViewObject.show()`, `view.ViewObject.show()`, `view.recompute()`,
   `doc.recompute()`, pump `Gui.updateGui()`.
5. `view.getVisibleEdges()` → Part edges in **page-mm (view Scale already applied)**,
   centered on the projection bbox. Divide by `view.Scale` before comparing to model
   extents — at Scale 0.5 an asm_front span read 78 against a 156 mm known and looked
   like a drop; it was exact (verified 2026-10-28).
   Empty → pump + retry (heavy shapes need several rounds), then the
   `TechDraw.project(compound, dir)` fallback (CS is transposed on front views —
   swap axes; it drops the same solids, see below).

XDirection table (missing/zero XDirection ⇒ "failed to create projection CS"
failures and 90°-rotated left/right views):

| view | Direction | XDirection |
|---|---|---|
| front | (0,-1,0) | (1,0,0) |
| top | (0,0,1) | (1,0,0) |
| left | (-1,0,0) | (0,-1,0) |
| iso | (1,1,1) | (1,-1,0) |

## Decision rules

- **Orientation (corrected 2026-10-28): `getVisibleEdges()` returns Y-DOWN
  page coords** — v = zc − z (proof: plate at world z −26..−11 surfaced at
  edge v +60.5..+75.5, view center zc=49.5). In a y-down raster (PIL) map
  `py = CY + (v − cy)·s` DIRECTLY; never pre-negate. The v6-era "negate y
  for every view" rule only worked because `rasterize_hlr_v6.py` paired the
  pre-negate with a `CY − y·s` mapper — two cancelling ops. Copying the
  pre-negate into a `CY + y·s` mapper double-flips = vertical MIRROR
  (2026-10-28: mirrored asm_front put the plate at canvas top while
  world-math balloon anchors pointed at the bottom). Same root behind the
  "ISO orientation bug" fixed via a 180° XDirection that day — mirror
  compensation in the projection frame. Never negate x (chiral text).
- **Verify orientation with an ASYMMETRIC feature, never symmetric spans.**
  Near-symmetric assemblies, uniform hole rings and 45°-ear faces are
  mirror-invariant and pass eyeball QA. Probe the edge JSON: a unique
  part's world z vs the sign of its edge v settles it in one query; or
  row-scan the PNG for a unique rectangle's y-position.
- **Settle orientation with one A/B composite, not flip iterations.** Render
  as-is next to the candidate transform, content-cropped, labeled, one image
  (view_image). Eyeballing mirrored-vs-rotated outline text at sheet scale
  misreads repeatedly — the composite ended four failed guess-flip rounds.
- **Silent solid drop -- booleans and HLR agree on which shapes are poison:**
  the v3 spool/gasket solids pass isValid() yet vanish in multiFuse AND in
  HLR (assembly projected 125 mm tall instead of 156) with NO error. Gate
  every view on extents: assert projected-vs-known-mm within 10% per axis;
  gate the fused bbox too. **`getVisibleEdges()` returns PAGE mm — divide the
  got-span by `view.Scale` before comparing** (verified 2026-10-28: asm_front
  78 raw at Scale 0.5 = exact 156 known; raw comparison false-MISMATCHes
  every scaled view). Recovery (verified 2026-10-17): rebuild poisoned
  parts from primitives at their assembly positions, then multiFuse
  everything.
- **Census the source doc before assuming a drop:** assembly_v3.FCStd has NO
  spool or gasket objects (87 solids = 2 flange pieces + bellows + 4 rods +
  16 M3 nuts + M5 hardware); the 156 mm stack with spools/gaskets = 91
  solids is the v4 conceptual assembly. Count objects first.
- **No inter-object occlusion between separate Source solids:** every part's
  full edge set draws as visible (bolts through spool flanges; separate-solid
  text shows through its plate). A single-object compound Source does NOT fix
  it. FIX (verified 2026-10-17): multiFuse all solids into ONE solid (91
  solids, 0.8 s, valid) -- intra-solid self-occlusion is exact. Fuse before
  projecting; never layer separate projections (layering is what produced the
  show-through Greg flagged on sheet 5).
- **Standalone runs swallow stdout** (FreeCAD console redirect; `os._exit`
  drops buffers). Write results to a JSON file incrementally and treat the
  artifact as truth — do not grep logs. Write `{"started": true}` to
  the diag JSON as the FIRST statement and wrap the whole script in
  try/except that dumps the traceback there — otherwise an early crash
  leaves zero evidence. Init order kills scripts silently (verified
  2026-10-28): `import Draft` at module top BEFORE `Gui.showMainWindow()`
  dies with no output — GUI init first, THEN `import TechDrawGui`/`import
  Draft`. The exec harness's "service child cleanup did not complete"
  warning on xvfb-run exit is noise; the JSON artifact is truth.

## Embedded TechDraw pages inside the model file — verified 2026-10-28

Trigger: drawings must live INSIDE the FCStd (single-file delivery; pages
re-project on recompute) instead of raster sheets. Proven end-to-end on the
v7 expansion joint: 15 DrawViewPart views + 5 pages created directly in the
268-object assembly doc, gates exact, cold-reopen + forced recompute clean,
per-page PDF export OK. Working scripts: `/home/openclaw/freecad/gen_techdraw_v7.py`
(embed) and `verify_techdraw_v7.py` (cold reopen + `TechDrawGui.exportPageAsPdf` proof).

- The fresh-doc-per-view rule above is for standalone edge-extraction batches.
  Creating each view ONCE in the target doc — explicit XDirection, extents gate,
  pump/retry loop per view — succeeded first-try on all views (0.2–5 s each).
  Sizing: `view.ScaleType='Custom'` + `view.Scale=…`, `page.KeepUpdated=True`.
- Extents-gate calibration (both false alarms verified):
  - `getVisibleEdges()` is page-mm — divide by Scale (see the Decision-rules
    extents-gate bullet).
  - ISO/pictorial views: axis-aligned bbox corners projected onto iso axes
    OVERESTIMATE true spans (flange 99×79 projected vs 84×58 actual). Gate iso
    against previously measured spans (views_*.json) with a warn-band, or no
    hard gate.
- Assembly occlusion source = fused Part::Feature copy in the doc
  (`DrawAsmFused`, Visibility=False); exploded pictorial = unfused compound
  copy (`DrawExploded`). Capture exploded shapes via `SPEC.Explode_F=1`, then
  RESTORE `0` + forced recompute + assert the assembled z-span returned before
  saving (gate proved the collapse back).
- Part views should Source the live in-doc masters (re-project on model edits);
  the fused/exploded copies are snapshots by nature.
- Snapshot sources go STALE after model edits: `DrawAsmFused`/`DrawExploded`
  re-project their saved shapes, so embedded asm/exploded views silently keep
  OLD geometry (2026-10-28: after remounting the data plate, DrawExploded
  still held the buried copy). After any model change, rebuild both from
  current world shapes (assembled multiFuse / `Explode_F=1` compound, restore
  F=0, gate fuse bbox = link-union). An EXTRA fuse solid can be correct — a
  part deliberately mounted proud/standoff no longer merges; gate on bbox,
  not solids==1.
- Save incrementally after each finished page — a killed run keeps completed
  sheets; the script purges `TechDraw::*`/`DrawAsm*`/`DrawExp*` objects first so
  reruns are idempotent.
- Completion gate: fresh-process cold reopen → 0 objects in
  Invalid/Error/Touched after `doc.recompute(None, True, True)` → export every
  page to PDF as visual proof.
- `Default_Template_A4_Landscape.svg` has NO editable title-block fields
  (EditableTexts empty). Sheet identity via DrawViewAnnotation, or glob for a
  `a4`+`landscape` `_TD`/ISO template (skip `blank`) for a fillable title block.

## Compose the sheets (system Python + Pillow — verified)

Rasterize edges (`edge.discretize(Deflection=0.03)`) at the target sheet's
existing px/mm calibration and centering so dimension/balloon code stays valid.
An assembly view whose balloons map model z→page needs a fixed world anchor,
NOT `center_mm` — that field is the RECENTRED content center (≈[0,0]); mapping
through it shipped v6 balloons ~222 px low (2026-10-28). World→page:
`xc,zc = midpoint of the link-union bbox extremes` (gen diag `anchors`),
`px(x)=cx_page+(x−xc)·S`, `py(z)=cy_page−(z−zc)·S`, and assert
`abs((py(zmin)−py(zmax))−(ay1−ay0)) < ~15px` — note the sign: page y
inverts, so `py(zmax) < py(zmin)`. When view_image is unavailable, verify
annotations deterministically instead: sample the rendered sheet PNG at each
computed balloon target (nearest dark pixel within ~30 px = on-part) and
collision-assert label bands (below the pasted-art bbox, clear of the title
block). Machinist-drawing rules (user-directed, 2026-10-28 review rounds):
- Near-axisymmetric parts: front and side profiles are duplicates — ship ONE
  profile + the FACE view (top; for a spool, bottom = the open/bore end) +
  ISO. Every hole/bore callout must live on the view where that feature is
  drawn as a CIRCLE; a dot on a profile view points at nothing.
- Align diagonal features H/V by rotating the projection frame, not the
  model: Direction (0,0,1) + XDirection (1,1,0) puts 45° ears/holes at
  horizontal/vertical (how the machinist clocks the part). Gate against the
  ROTATED-frame spans — ears horizontal read 84×84, not 70×70 (exact on v7).
- Hole-callout dots from measured edge data, not formulas: extract small
  closed loops from the edges JSON (center+radius); for top/bottom views
  page = paste_center + (u,v)·pxmm (+y draws DOWN after the flip). A dot at
  a hole CENTER cannot see ring ink within a small scan radius — verify
  rim/bore dots against black art ink, trust measured centers for holes.
- Balloons: place on the flank NEAREST the target AT the target's height
  (leaders ≤~200 px, fan pattern, no crossings, circles ≥~56 px apart).
  Same-side balloon columns whose leaders cross the whole view were
  rejected by the user (2026-10-28).
- BOM completeness: census link-union target names (gen diag `anchors`) —
  every printed part AND hardware item gets a row, printed parts first;
  renumber balloons to match the final BOM order (v6 BOM shipped without
  the flange pieces).
- Cross-view frame consistency: every view of a part on one sheet shares ONE
  orientation frame. If the face view is rotated (X=(1,1,0)/√2), the side
  view must use the same-rotated frame — front (0,-1,0)/(1,0,0) → D=(1,-1,0)/√2,
  X=(1,1,0)/√2 — else ears project at cos45 offsets and dims stop matching
  (v7 sheet-1 catch). Diagnose orientation with a row-extent scan (narrow
  band height) before re-projecting. A 180° raster transpose in the composer
  ≡ a 180°-rotated ortho projection — cheap flip of a part to its machining
  orientation (v7 sheet-3: modeled collar-up, machined collar-down).
- Census the FEATURE before flipping/regenerating a view: "text/holes not
  visible" is usually ABSENT geometry, not occlusion (v6/v7 DataPlate had
  no text solid; its top view gated 4 edges = plain rectangle). Check
  master solid count + projection edge count first.
- A part drawing only hidden/dashed lines INSIDE another solid's silhouette
  in every view orientation is inside the material (bad mount), not occluded.
  Confirm with `common()` volume against the containing solid, then fix the
  mount in the MODEL (v7 data plate: expression-mounted tangent to the Ø42
  stub, inside the Ø70 spool wall since v4 — hidden lines on every sheet).
- Fix scope: presentation flaws (exploded placement, view orientation) are
  fixed at the DRAWING layer — translate shape copies inside the view
  compound / rotate the raster; model untouched, no save. Design features
  (plate text) belong in the MODEL — rebuild + fuse + re-point the assembly
  link so CAD/print consumers keep them.
- Exploded ISO gaps: v=(x+y−2z)/√6 — world z-gaps shrink ~×0.82 and a part's
  y-offset eats further into them (15 mm gap → ~10 px once offsets land);
  gate on the PROJECTED separation in the raster (ink-free band under the
  part), not the world-z gap.
- **Lettering at two scales:** part-view lettering = modeled Draft
  `makeShapeString` raised text projected as its own HLR overlay view
  (`add_plate_text_v7.py` → `plate_top_text`); assembly-view lettering =
  PIL text in the composer ON the projected face — HLR strokes of 0.6 mm
  raised text are illegible at assembly px/mm (2026-10-28: plate read
  "blank" until overlaid). When a face carries lettering, point its balloon
  at the feature EDGE, not the center, so the leader doesn't spear text.
- **BOM is generated from the link inventory, never hand-typed** — diff the
  parts list against App::Link groups by master name (2026-10-28: both
  flanges and the data plate were missing from a 7-item BOM; truth was 9).
- **Numeric edge/pixel checks beat the vision model for detail QA.** Search
  the edge JSON for expected geometry (4-segment rect, N text strokes,
  lines beyond a silhouette) and ink-count PNG regions; weak VLMs misread
  technical linework (two wrong reads on the same day). view_image crops
  must live under the workspace root — /tmp paths are rejected.
Keep shaded
renders only for pictorial/exploded views. Multi-page PDF: Pillow
`save(pdf, save_all=True, append_images=rest, resolution=…)` (A4 verified).
Working scripts (current, v7 single-file model, 2026-10-28):
`/home/openclaw/freecad/gen_hlr_v6.py` (base views from in-doc masters +
fused assembly front + exploded iso at `Explode_F=1`), `gen_hlr_v7_extra*.py` + `add_plate_text_v7.py` + `exp_iso_v7.py`
(r45-consistent frames, plate text rebuild, repositioned exploded iso),
`rasterize_v7_extra*.py` (self-calibrated px/mm;
merges old+new into `views_extra/views_merged.json`), `make_sheets_v7.py`
(sheets/BOM/balloons: measured world anchors, flank-adjacent balloons,
pixel-verified callout dots) plus `gen_asm_v7.py` + `rasterize_asm_v7.py`
(regenerate single views after a model edit, reusing the sheet's px/mm and
anchors diag so composer calibration survives). The v4 trio (`gen_hlr_real.py`, `gen_asm_fused3.py`,
`rasterize_hlr.py`, `make_sheets_hlr.py`) covers the separate-part-files variant.
Assembly Source solids must be WORLD shapes — `App::Link.Shape` omits ancestor App::Part
placements (see SKILL.md pitfall; the first v6 run lost half the fuse until container
transforms were composed). Exploded pictorial as HLR line art (links at `Explode_F=1`,
unfused — spread parts don't occlude) avoids the 3D-view render fight entirely; HLR
extents gates were exact on all 16 v6 views.

## Server accept-loop hang — RESOLVED 2026-10-17 (v4)

Symptom was: after the TechDraw-init lines landed at module top, the TCP
server listened but never answered PING/QUIT. Root cause and fix live in the
freecad-remote-control SKILL.md pitfalls entry ("Accept-loop hang, fixed
v4"): v3 depended on the console REPL stdin hook to pump the QTimer; v4
closes the script with an explicit `QApplication.exec_()`. No standalone
workaround needed anymore.

