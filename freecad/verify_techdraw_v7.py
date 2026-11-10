# verify_techdraw_v7.py -- cold reopen of the saved v7, audit + PDF export proof.
# Run: cd /home/openclaw/freecad && xvfb-run -a ./FreeCAD_1.1.4-...AppImage -c verify_techdraw_v7.py
import FreeCAD as App
import FreeCADGui as Gui
import json, os

Gui.showMainWindow()
import TechDrawGui
for _ in range(10):
    Gui.updateGui()
import time
time.sleep(1.0)
for _ in range(10):
    Gui.updateGui()

SRC = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v7/assembly_v7.FCStd"
OUT = "/home/openclaw/freecad/techdraw_v7_verify.json"
res = {}

d = App.openDocument(SRC)
for _ in range(5):
    Gui.updateGui()

pages = [o for o in d.Objects if o.TypeId == "TechDraw::DrawPage"]
views = [o for o in d.Objects if o.TypeId == "TechDraw::DrawViewPart"]
res["pages"] = len(pages)
res["views"] = len(views)
res["open_states_bad"] = [o.Name for o in d.Objects
                          if o.TypeId.startswith("TechDraw::")
                          and any(s in o.State for s in ("Invalid", "Error", "Touched"))]

d.recompute(None, True, True)
for _ in range(10):
    Gui.updateGui()
res["after_recompute_bad"] = [o.Name for o in d.Objects
                              if o.TypeId.startswith("TechDraw::")
                              and any(s in o.State for s in ("Invalid", "Error", "Touched"))]
# also whole-doc audit (model must be untouched by page recompute)
res["doc_bad_any"] = [o.Name + ":" + ",".join(o.State) for o in d.Objects
                      if any(s in o.State for s in ("Invalid", "Error"))][:20]

pdfs = []
for p in sorted(pages, key=lambda p: int(p.Name.replace("Page", ""))):
    path = "/home/openclaw/freecad/v7_%s.pdf" % p.Name
    try:
        TechDrawGui.exportPageAsPdf(p, path)
        pdfs.append([p.Name, os.path.getsize(path) if os.path.exists(path) else 0])
    except Exception as e:
        pdfs.append([p.Name, "ERR:" + repr(e)[:100]])
res["pdf_export"] = pdfs
json.dump(res, open(OUT, "w"), indent=1)
os._exit(0)
