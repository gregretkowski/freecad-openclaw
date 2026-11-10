#!/usr/bin/env python3
"""FreeCAD TCP API client -- use with freecad-server v3 on localhost:9999."""
import base64, socket, struct

def cmd(raw, timeout=120.0):
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.settimeout(timeout)
    c.connect(("127.0.0.1", 9999))
    c.sendall(raw + b"\n")
    hdr = b""
    while len(hdr) < 4:
        chunk = c.recv(4 - len(hdr))
        if not chunk: raise RuntimeError("connection closed before response header")
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

if __name__ == "__main__":
    import sys
    print(execcode(sys.stdin.read()))
