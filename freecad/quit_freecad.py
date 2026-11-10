#!/usr/bin/env python3
"""Clean-stop helper: send QUIT to the FreeCAD API server on 127.0.0.1:9999."""
import socket, struct, sys
try:
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.settimeout(10)
    c.connect(('127.0.0.1', 9999))
    c.sendall(b'QUIT\n')
    hdr = b''
    while len(hdr) < 4:
        chunk = c.recv(4 - len(hdr))
        if not chunk:
            break
        hdr += chunk
    (n,) = struct.unpack('>I', hdr)
    buf = b''
    while len(buf) < n:
        chunk = c.recv(min(65536, n - len(buf)))
        if not chunk:
            break
        buf += chunk
    c.close()
    print('FreeCAD server said:', buf.decode('utf-8', 'replace').strip())
except Exception as e:
    print('server not reachable (%r) - nothing to stop' % (e,))
sys.exit(0)
