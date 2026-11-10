# freecad_server v3 -- Greg's QTimer event-loop design + full API surface.
# Run:  xvfb-run ./FreeCAD_1.1.4-Linux-x86_64-py311.AppImage -c freecad_server_v3.py
#
# Commands (one per connection, newline-terminated recommended):
#   PING                          -> PONG <version>
#   EXEC:<base64(python)>         -> arbitrary python, persistent NS (App/Gui/Part loaded),
#                                    returns stdout + repr(result) if code sets 'result'
#   SNAP:<w>,<h>,<path>[,<bg>]    -> isometric+fitAll render to <path> (abs path!)
#   OPEN:<abs path .FCStd>        -> open document
#   UPDATE_AND_SNAP:l,w,h,<path>  -> compat: reshape MyCube, snap 1280x720 White
# Responses: 4-byte big-endian length + UTF-8 payload (tracebacks arrive whole).

import FreeCAD as App
import FreeCADGui as Gui

# --- TechDraw HLR initialization (verified 2026-10-16) ---
# These two lines are REQUIRED for TechDraw HLR to work when called via Python API.
# Without them, getVisibleEdges() silently returns 0 edges.
Gui.showMainWindow()
import TechDrawGui  # must be after showMainWindow()
# --- end TechDraw init ---
import Part
import base64
import io
import os
import socket
import struct
import traceback
from contextlib import redirect_stdout
from PySide import QtCore

PORT = 9999
DOC_NAME = "VisualAutomation"
_QUIT = {"flag": False}  # set by QUIT command; honored after the reply is sent

# --- socket up first (proven design: non-blocking accept inside Qt timer) ---
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(("127.0.0.1", PORT))
server_socket.listen(4)
server_socket.setblocking(False)
print("v3 listening on 127.0.0.1:%d ..." % PORT, flush=True)

# --- GUI up, then LET IT FINISH INITIALIZING before creating documents ---
Gui.showMainWindow()
mw = Gui.getMainWindow()
# NOTE: do NOT hide the main window before documents exist -- a hidden main
# window prevents GUI document/View3D creation entirely (root cause of the
# original 'NoneType' ActiveView failure). Keep it visible; under xvfb-run
# nobody sees it anyway.
for _ in range(5):
    Gui.updateGui()   # pump the event loop: let the GUI finish initializing

doc = None
box = None
NS = {}

LOGF = open("/home/openclaw/freecad/server.log", "a", buffering=1)

def log(msg):
    line = "[fc-v3] " + msg
    print(line, flush=True)
    try:
        LOGF.write(line + "\n")
    except Exception:
        pass

def build_doc():
    global doc, box
    doc = App.newDocument(DOC_NAME)
    box = doc.addObject("Part::Feature", "MyCube")
    box.Shape = Part.makeBox(10, 10, 10)
    doc.recompute()

def recover():
    """Heal any state where the App doc lost its GUI doc (the ActiveView killer)."""
    global doc, box
    try:
        mw2 = Gui.getMainWindow()
        if mw2 is not None and not mw2.isVisible():
            mw2.show()
            Gui.updateGui()
        if Gui.ActiveDocument is None or App.ActiveDocument is None:
            log("recovery: GUI doc missing, rebuilding")
            try:
                App.closeDocument(DOC_NAME)
            except Exception:
                pass
            build_doc()
            for _ in range(3):
                Gui.updateGui()
    except Exception:
        build_doc()

build_doc()
log("document '%s' ready (GUI doc: %s)" % (DOC_NAME, Gui.ActiveDocument is not None))

def do_exec(code):
    NS.pop("result", None)
    NS.update(App=App, Gui=Gui, Part=Part, doc=doc, box=box)  # fresh refs every call
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            exec(compile(code, "<EXEC>", "exec"), NS)
        Gui.updateGui()
    except Exception:
        out = buf.getvalue()
        return out + ("\n" if out else "") + traceback.format_exc()
    out = buf.getvalue()
    result = NS.get("result")
    if result is not None:
        try:
            out += ("\n" if out else "") + "result = " + repr(result)
        except Exception:
            pass
    return out or "OK"

def do_snap(path, w, h, bg="White"):
    recover()
    Gui.updateGui()
    gd = Gui.ActiveDocument
    if gd is None:
        return "ERROR: no GUI document after recovery"
    view = gd.ActiveView
    if view is None:
        return "ERROR: no 3D view available"
    view.viewIsometric()
    view.fitAll()
    for _ in range(3):
        Gui.updateGui()  # freshly created objects need several event pumps to draw
    path = os.path.abspath(path)
    view.saveImage(path, int(w), int(h), bg)
    try:
        os.chmod(path, 0o644)
    except OSError:
        pass
    return "SNAPPED " + path

def handle(cmd):
    if cmd == "QUIT":
        _QUIT["flag"] = True
        return "BYE"
    if cmd == "PING":
        try:
            ver = ".".join(str(x) for x in App.Version()["Version"][:3])
        except Exception:
            ver = "freecad"
        return "PONG " + ver
    if cmd.startswith("EXEC:"):
        return do_exec(base64.b64decode(cmd[5:]).decode("utf-8"))
    if cmd.startswith("SNAP:"):
        p = cmd[5:].split(",")
        bg = p[3] if len(p) > 3 else "White"
        return do_snap(p[2], p[0], p[1], bg)
    if cmd.startswith("OPEN:"):
        recover()  # flush automation doc if it would shadow
        d = App.openDocument(cmd[5:].strip())
        Gui.updateGui()
        return "OPENED " + d.Name
    if cmd.startswith("UPDATE_AND_SNAP:"):
        parts = cmd[len("UPDATE_AND_SNAP:"):].split(",")
        l, w, h, path = float(parts[0]), float(parts[1]), float(parts[2]), parts[3]
        recover()
        d = App.ActiveDocument            # fresh refs -- module globals go stale
        b = d.getObject("MyCube")
        b.Shape = Part.makeBox(l, w, h)
        d.recompute()
        Gui.updateGui()
        return do_snap(path, 1280, 720, "White")
    return "ERR unknown command (PING/EXEC/SNAP/OPEN/UPDATE_AND_SNAP)"

def check_network_commands():
    try:
        conn, addr = server_socket.accept()
    except BlockingIOError:
        return
    try:
        conn.setblocking(True)
        conn.settimeout(0.5)
        data = b""
        while not data.endswith(b"\n"):
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            data += chunk
        cmdstr = data.decode("utf-8", "replace").strip()
        log("req %s: %s" % (addr[0], cmdstr[:60]))
        try:
            resp = handle(cmdstr)
        except Exception:
            resp = "ERROR:\n" + traceback.format_exc()
        payload = resp.encode("utf-8")
        conn.settimeout(30)
        conn.sendall(struct.pack(">I", len(payload)) + payload)
        log("resp: %s" % resp.splitlines()[0][:80] if resp else "resp: <empty>")
        if _QUIT["flag"]:
            log("QUIT: clean exit")
            os._exit(0)
    except Exception as e:
        try:
            conn.sendall(("ERROR: %r" % (e,)).encode("utf-8"))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

timer = QtCore.QTimer()
timer.timeout.connect(check_network_commands)
timer.start(50)
