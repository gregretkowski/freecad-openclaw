#!/bin/sh
# FreeCAD API server launcher (systemd unit main process).
# FreeCAD's console exits on stdin EOF, so stdin is fed from a FIFO held
# open by a sleep writer. exec makes xvfb-run the tracked main process:
# FreeCAD death == unit death == Restart=always kicks in.
cd /home/openclaw/freecad || exit 1
FIFO=stdin_keepalive.fifo
[ -p "$FIFO" ] || mkfifo "$FIFO"
( exec sleep infinity > "$FIFO" ) &
exec xvfb-run -a ./FreeCAD_1.1.4-Linux-x86_64-py311.AppImage -c freecad_server_v4.py < "$FIFO" >> server_stdout.log 2>&1
