# AI-Driven CAD: An LLM Agent Building a Parametric Expansion Joint in FreeCAD

**An overview of a 3-week trial (Oct 12 – Nov 1, 2026) letting a large-language-model
agent do real mechanical design work in FreeCAD — end to end, from a chat window.**

Audience: FreeCAD users and developers curious whether "AI can actually do CAD."
Short answer: yes, with the right harness — and the harness is the whole story.

---

## 1. What was built

A **tied axial bellows expansion joint** — bellows core, two flange pieces with
tie-rod lugs, spools, gaskets, data plate, M5 bolt sets, M3 tie rods with nuts —
modeled fully parametric in FreeCAD 1.1.4, with:

- a **SPEC spreadsheet** (70+ aliased cells) driving every dimension,
- **10 PartDesign master bodies** instanced as **92 App::Link objects** in a
  station-based App::Part tree,
- **5-sheet technical drawing package** (A4, orthographic views, exploded pictorial,
  dimensioned part views, BOM + balloons),
- **embedded TechDraw pages** inside the FCStd itself (5 DrawPages / 15 live
  DrawViewPart projections), so the savefile is self-contained,
- a frozen, checksummed release per version (sha256 manifest + tarball/zip).

It went through **8 versions** in 17 days. Nothing was drawn by hand, and no human
touched FreeCAD. The human's role was reviewing renders/PDFs in Telegram and
steering — more on that below.

## 2. Architecture

The core decision: **no GUI automation.** No screenshot-and-click bots. The agent
drives FreeCAD through its Python scripting API, headless.

```
 Greg (Telegram, phone/laptop)
   │  plain-English requests, review loops
   ▼
 OpenClaw gateway  (always-on agent runtime, Linux PC)
   │  agent = "Red Langosta" (main)
   ▼
 LLM: GLM-5.x (z.ai, via OpenRouter)   ← the reasoning engine
   │
   ▼
 shell/JS exec tool → python3 fc.py    ← thin TCP client helper (~30 lines)
   │
   ▼ TCP 127.0.0.1:9999 (length-prefixed JSON)
 ┌────────────────────────────────────────────────────────┐
 │ FreeCAD 1.1.4 AppImage (py311) under Xvfb              │
 │  └─ freecad_server_v4.py  — in-process EXEC loop       │
 │     runs arbitrary Python inside a live FreeCAD        │
 └────────────────────────────────────────────────────────┘
   launched by systemd --user (launch.sh: xvfb-run +
   stdin FIFO keepalive; clean QUIT on ExecStop)

 host-side drawing pipeline (plain python3 + Pillow):
   gen_*.py    → TechDraw HLR → edge geometry as JSON
   rasterize_*.py → edges → calibrated PNG line art
   make_sheets_*.py → compose A4 sheets: views, dims,
                     leaders, balloons, BOM, title block
```

### Why this shape

- **A persistent FreeCAD process** (not batch `freecad -c script.py` per command)
  preserves document state across hundreds of small operations, keeps the GUI
  objects alive (needed for TechDraw/view providers), and is far more reliable —
  batch AppImage runs proved flaky mid-project.
- **The TCP server is ~250 lines.** It exists only to `exec()` Python inside the
  live process and stream back stdout + results. Everything else — geometry,
  assembly, drawings — is ordinary FreeCAD scripting the agent writes on the fly.
- **Xvfb** because FreeCAD's GUI layer (Qt/coin3D view providers) must exist for
  several operations (renders, some TechDraw paths) even though nobody looks at
  the screen. The agent "sees" via rendered PNGs and numeric geometry probes
  instead.
- **The drawing annotation layer lives outside FreeCAD** (PIL composer). TechDraw
  annotations are possible headless but slow and finicky to lay out
  programmatically; a code-composed annotation layer regenerates instantly and is
  pixel-precise. Trade-off: the FCStd carries live geometry views, the PDF carries
  the finished annotation.

## 3. The approach (what made it work)

1. **Programmatic everything.** The agent never needed pixels to click. Every
   operation is a Python call; every question about the model ("is the plate
   clear of the spool?") is answered by geometry math (common() volumes,
   bounding boxes, isInside probes), not by looking.
2. **Versioned generations, freeze protocol.** v1→v8 directories; each frozen
   release is checksummed, made read-only, and copied forward. Model files are
   cheap; state discipline is what's expensive. Copy → verify → save-under-new-name
   → close the old document. Never edit a frozen version.
3. **Verification gates on every step.** HLR projections must match known mm spans
   within tolerance (catches silently dropped solids); forced recompute must
   produce zero invalid objects; cold-reopen must reproduce invariants; parametric
   edits are tested by changing a SPEC cell and measuring the result (8/8 test
   harness on v5), then reverted. "It rendered" is not acceptance; **numbers are**.
4. **Human-in-the-loop review.** Greg reviewed renders and PDFs in Telegram and
   caught things the numeric gates missed — most famously a **vertically mirrored
   assembly view** (near-symmetric parts hide mirrors). The loop: agent produces →
   human eyeballs → agent fixes → skill updated so the class of error can't recur.
5. **Skills as procedural memory.** Every hard-won lesson is written into skill
   files the agent re-reads before CAD work. The two skills in this zip
   (`freecad-remote-control`, `freecad-tcp-assembly` + the TechDraw HLR
   companion doc) accumulated ~40 documented gotchas over the project. At v7
   freeze, a dedicated pass rewrote wrong earlier rules (see §5) — the memory is
   versioned and self-correcting, not a pile of tips.
6. **Per-version docs.** SPEC_README.md (what the spec cells mean) and
   ERRORS_AND_FIXES.md (found problems + repairs) travel with each version.

## 4. Progression

| Version | Date | What happened |
|---|---|---|
| precursor | Oct 12 | Warm-up: Ø800 collar + ASME bolt/nut assembly via Fasteners workbench, driven from chat. First skill written same day. TCP server born here (v1→v2: stdin-EOF kill, FIFO fix). |
| v1 | Oct 15 | Single-piece expansion joint body. Headless build lessons: primitives + revolve + chamfer only (loft/extrude-rotate gave invalid solids). |
| v2 | Oct 16 | 3-part split: flange pieces + thin-wall bellows (envelope-minus-core). |
| v3 | Oct 16 | Full 87-object assembly: rods, 16 M5 bolt sets, gaskets, data plate with raised text. |
| v4 | Oct 16 | Spools + gaskets (91 obj), 3-state exploded views, first 5-sheet drawing package — initially render-based, then real TechDraw HLR. Server v3 accept-loop died during this push (see §5). |
| — | Oct 17 | Server v4: root-caused the event-loop hang; occlusion fix (fuse → one solid) for correct hidden lines. |
| v5 | Oct 22 | Full parametric rebuild: SPEC spreadsheet, PartDesign masters, 92 App::Links, everything expression-bound. 8/8 cold-file param test harness PASS. |
| v6 | Oct 27 | Error-archaeology pass on v5: fixed 19 invalid objects (unit-mismatch expressions, over-constrained sketch, dead zero-terms), GC'd 74 orphan objects (342→268). Found the App::Link world-transform trap. Regenerated drawings. |
| v7 | Oct 28 | TechDraw pages embedded in-file; 6 refinement rounds: BOM from link inventory, machinist-logic views (rotated projection frames), side-view orientation, data-plate remount (it had been buried inside the spool wall since v4), the mirror hunts. Frozen + checksummed. |
| v8 | Oct 28 | Clean copy forward, verified, opened as the new working doc. |

v7 final: 555 KB FCStd (self-contained drawings), 1.16 MB 5-sheet PDF, delivery zip
checksummed. Roughly 20 working sessions, most 30–90 minutes of wall-clock.

## 5. Lessons that cost blood (a selection)

**FreeCAD-specific, verified on 1.1.4:**

- **TechDraw HLR drops solids silently** from large compounds — a view can look
  plausible with half the assembly missing. Fix: gate every projection against
  expected mm extents; fuse the assembly into a single solid when you need true
  self-occlusion.
- **`DrawViewPart` needs an explicit XDirection** or the projection CS fails.
- **`getVisibleEdges()` returns Y-DOWN page coordinates.** We shipped mirrored
  views for three versions because a wrong "always negate y" rule paired with an
  opposite mapper cancelled out — until an asymmetric data plate exposed it.
  Corollary: **verify orientation with an asymmetric feature**, never with
  symmetric bolt rings.
- **`App::Link.Shape` omits ancestor App::Part placements** — fusing "world"
  shapes silently drops or duplicates half the parts. Must compose the container
  placement chain yourself.
- **FeaturePython objects (FastenersWB) don't render off-screen** — copy the shape
  into a plain `Part::Feature` wrapper; keep the parametric original hidden.
- **PartDesign**: PolarPattern only works as the final Tip feature; an
  over-constrained sketch (dof < 0) silently kills everything downstream;
  envelope-minus-core profiles must stagger inner faces axially or the revolve
  self-intersects.
- **Expressions**: unit mismatches (unitless `0*sin(x)` vs mm) flag sketches
  invalid; `ExpressionEngine` is read-only (use `setExpression`); SPEC cell
  names lie (`Flange_T` = disc only, not the flange part) — probe live placements
  (set factor 0/1, recompute, read) instead of trusting transcribed expressions.

**Harness-specific:**

- **stdin EOF kills FreeCAD** — a console process exits when its stdin closes.
  Hence the FIFO keepalive in launch.sh.
- **The Qt event loop must actually run.** Server v3 relied on the console REPL to
  pump timers; importing TechDrawGui broke that and every PING/QUIT sat in the
  accept backlog for a day before anyone noticed. v4 ends with an explicit
  `QApplication.exec_()`.
- **Batch `freecad -c script.py` is flaky** (silent empty exceptions,
  double-execution). A persistent server you talk to over TCP is strictly better.
- **Numeric QA beats weak vision models.** Pixel-ink gap scans and VLM "looks
  fine" both failed on mirrored/busy views; measuring edges and extents in code
  never did. Vision is for the final human, and for targeted questions.

## 6. Honest assessment

**What worked:**

- A current-generation LLM, given a scripting API and verification gates, can do
  genuine multi-part parametric mechanical design — including the unglamorous
  parts: expression binding, constraint cleanup, drawing layout, BOM generation,
  and debugging broken inherited models (the v6 pass).
- Iteration speed is the superpower. Twenty build/debug cycles in an evening is
  normal; a human does not match that cadence in FreeCAD's GUI.
- Failure modes are mostly boring and recoverable: invalid solids, dropped
  projections, mirrored views — all caught by gates or by the human reviewer,
  all fixed the same session, all written into the skills so they don't recur.

**What to be skeptical about:**

- **Silent wrongness.** The scariest failures were plausible-looking: half an
  assembly missing from a view, a plate buried inside a wall for four versions,
  mirrored views nobody noticed because the part is symmetric. You need gates
  that assert, not eyeballs that approve.
- **The model doesn't "know" your design intent.** It follows the spec you give
  it. The SPEC spreadsheet discipline emerged because free-floating dimensions
  drift; make the parameters explicit and expression-bind everything.
- **Context limits.** Long sessions need memory hygiene (our agent compacts and
  keeps per-version docs) — this is an agent-harness problem, not a CAD problem,
  but it will bite you if you don't plan for it.
- **Annotation outside the file.** Our dimensioned sheets are code-composed, so
  the FCStd's embedded pages carry geometry but not the full annotation layer
  (native in-file TechDraw annotations are the known v8 work item).

**Cost shape:** the FreeCAD side is free; the LLM is metered. For us the whole
project rode an existing always-on agent subscription — no dedicated CAD tooling
budget. Your mileage will vary with model choice.

## 7. Try it yourself

This zip is everything needed to stand up the same harness (see README.txt for
install):

1. Install the server + systemd unit, drop the skills into your OpenClaw agent
   (or adapt them for any LLM harness that can run shell commands), and start
   with `python3 fc.py 'ping'`.
2. **Start small and gate everything**: one primitive body, one HLR view with an
   extents check. Grow complexity only when the gates pass.
3. Write your own spec file first (even 10 lines) and bind geometry to it. The
   parametric discipline is what makes AI-built models maintainable rather than
   landfill.
4. Version-freeze aggressively. Directories are cheap; redoing state is not.
5. Keep an asymmetric "tell-tale" feature in every assembly so orientation bugs
   can't hide.
6. If you use a different agent runtime (Claude Code, etc.), the portable parts
   are: freecad_server_v4.py, fc.py, the systemd unit, and the drawing pipeline
   scripts — all in this zip. The skills are OpenClaw-flavored markdown but the
   ~40 gotchas inside them apply to any harness.

## 8. Manifest of this zip

- `OVERVIEW.md` — this document
- `README.txt` — install guide for the server + unit + skills
- `freecad/` — server (v4, plus v3 for history), launch.sh, quit_freecad.py,
  fc.py client, and the workflow scripts (gen_hlr*, rasterize*, make_sheets*,
  gen_asm*, verify_techdraw*, capprobe, merge_asm, …) referenced by the skills
- `systemd/freecad-server.service` — user unit
- `skills/` — freecad-remote-control (SKILL.md + techdraw-hlr-drawings.md),
  freecad-tcp-assembly (SKILL.md + fc_client.py)

*Prepared 2026-11-05 by the agent that did the work (Red Langosta / OpenClaw,
GLM-5.3), at the direction of Greg Retkowski, who reviewed every render and
caught the mirrors.*
