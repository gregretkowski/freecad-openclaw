#!/usr/bin/env python3
# merge_asm.py -- rebuild asm_front from: assembly-except-spools HLR (v3 DVP,
# front dir) + spool edges (from spool_v3 doc, worked) + gasket edges.
# All in world X/Z coords, z measured from bellows anchor (world z=0 at body bottom).
import json

EDGES = json.load(open("/tmp/hlr_edges.json"))

# guard: asm_front must be fresh DVP output, not a previous merged result
assert EDGES["asm_front"]["method"] == "drawviewpart", (
    "asm_front is %s - already merged; regenerate it first"
    % EDGES["asm_front"]["method"])

def flip(lines):
    return [[[p[0], -p[1]] for p in ln] for ln in lines]

def place(lines, dz, dx=0.0):
    return [[[p[0] + dx, p[1] + dz] for p in ln] for ln in lines]

# G1: assembly doc HLR (front dir). DVP recenters on source bbox center z=49.5.
# front views come out y-up=-z, so flip then offset.
g1 = flip(EDGES["asm_front"]["lines"])
g1 = place(g1, 49.5)

# spool doc front view (post-flip): flange y[-13.5..-6.5], stub y[-6.5..13.5].
# Top spool (world z100.5..127.5): flange mates gasket at 100.5 -> flange BELOW
# stub = flipped orientation, dz = 114. Bottom spool (-28.5..-1.5): flange at
# top (-8.5..-1.5) = raw orientation, dz = -15.
spool = flip(EDGES["spool_front"]["lines"])
spools = place(spool, 114.0) + place(EDGES["spool_front"]["lines"], -15.0)

# gasket doc front view: 1.5 thick strip, center z +-0.75
gk = flip(EDGES["gasket_front"]["lines"])
gaskets = place(gk, 99.75) + place(gk, -0.75)        # gaskets z -1.5..0 and 99..100.5

merged = g1 + spools + gaskets
xs = [p[0] for ln in merged for p in ln]
zs = [p[1] for ln in merged for p in ln]
print("merged asm_front: x[%.1f..%.1f] z[%.1f..%.1f] lines=%d" %
      (min(xs), max(xs), min(zs), max(zs), len(merged)))
assert max(zs) - min(zs) > 155, "assembly height must be ~156+, spools missing?"
assert abs(min(xs) + 42.4) < 2 and abs(max(xs) - 42.4) < 2

EDGES["asm_front"] = {"method": "merged(g1+spools+gaskets)", "lines": merged,
                      "world": [0.0, 49.5]}  # world anchor for rasterizer
EDGES.pop("asm_iso", None)  # shaded pictorial retained for iso slot; not used by composer
json.dump(EDGES, open("/tmp/hlr_edges.json", "w"))
print("[done] asm_front merged and asm_iso dropped")
