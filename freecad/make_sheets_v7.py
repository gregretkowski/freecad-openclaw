#!/usr/bin/env python3
# make_sheets_v7.py -- compose the 5-sheet V7 drawing package from views_v6 line art.
# Forked from v6 composer; v7 changes: REV/DATE bump, sheet5 balloon anchors
# world-corrected (v6 mapped recentred view coords as world coords -> all
# balloon targets ~222 px low), exploded-view label moved below the art with
# collision-checked placement.
import json, math, os
from PIL import Image, ImageDraw

DRW_IN = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v6/drawings"
DRW = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v7/drawings"
os.makedirs(DRW, exist_ok=True)
VIEWS = json.load(open(os.path.join(DRW, "views_extra", "views_merged.json")))
DIAG = json.load(open("/tmp/hlr_v7_diag.json"))
W, H = 2339, 1654
BLACK = (26, 26, 26)
BLUE = (28, 79, 156)
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DATE, REV = "2026-10-28", "V7"
PROJ = "TIED AXIAL EXPANSION JOINT - SCALE MODEL 1:4"
_fc = {}
def F(px, bold=True):
    k = (px, bold)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(FB if bold else FR, px)
    return _fc[k]
from PIL import ImageFont

class Sheet:
    def __init__(self):
        self.img = Image.new("RGB", (W, H), "white")
        self.d = ImageDraw.Draw(self.img)
        self.d.rectangle([26, 26, W-26, H-26], outline=BLACK, width=3)
        self.d.rectangle([38, 38, W-38, H-38], outline=BLACK, width=1)
    def paste_view(self, key, cx, cy, k=1.0, margin=8, rot180=False):
        m = VIEWS[key]
        img = Image.open(m["path"]).convert("RGB")
        x0, y0, x1, y1 = m["bbox"]
        x0 = max(0, x0-margin); y0 = max(0, y0-margin)
        x1 = min(img.width, x1+margin); y1 = min(img.height, y1+margin)
        crop = img.crop((x0, y0, x1, y1))
        if rot180:
            crop = crop.transpose(Image.ROTATE_180)
        if k != 1.0:
            crop = crop.resize((max(1, int(crop.width*k)), max(1, int(crop.height*k))), Image.LANCZOS)
        a = crop.convert("L").point(lambda v: 0 if v > 246 else 255)
        px, py = int(cx-crop.width/2), int(cy-crop.height/2)
        self.img.paste(crop, (px, py), a)
        S = m["pxmm"] * k
        bbox = (px+margin, py+margin, px+crop.width-margin, py+crop.height-margin)
        return S, bbox
    def arrow(self, x, y, dx, dy, size=11):
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx/L, dy/L
        self.d.polygon([(x, y),
                        (x - ux*size - uy*size*0.35, y - uy*size + ux*size*0.35),
                        (x - ux*size + uy*size*0.35, y - uy*size - ux*size*0.35)], fill=BLUE)
    def dot(self, x, y, r=4.5):
        self.d.ellipse([x-r, y-r, x+r, y+r], fill=BLUE)
    def line(self, pts, wd=2):
        self.d.line(pts, fill=BLUE, width=wd)
    def text_c(self, cx, y, s, size=26, bold=True, color=BLUE):
        f = F(size, bold); w = self.d.textlength(s, font=f)
        self.d.text((cx-w/2, y), s, font=f, fill=color)
    def fit_size(self, s, max_w, size, bold=True):
        while size > 12 and self.d.textlength(s, font=F(size, bold)) > max_w:
            size -= 1
        return size
    def dim_h(self, x1, x2, y, label, size=26):
        self.line([(x1, y), (x2, y)])
        self.arrow(x1, y, -1, 0); self.arrow(x2, y, 1, 0)
        self.text_c((x1+x2)/2, y - size - 10, label, size)
    def dim_v(self, x, y1, y2, label, size=24):
        if y1 > y2: y1, y2 = y2, y1
        self.line([(x, y1), (x, y2)])
        self.arrow(x, y1, 0, -1); self.arrow(x, y2, 0, 1)
        f = F(size)
        tw = int(self.d.textlength(label, font=f)) + 8
        th = size + 10
        tmp = Image.new("RGBA", (tw, th), (255, 255, 255, 0))
        ImageDraw.Draw(tmp).text((4, 3), label, font=f, fill=BLUE)
        rot = tmp.rotate(90, expand=True)
        self.img.paste(rot, (int(x - 12 - rot.width), int((y1+y2)/2 - rot.height/2)), rot)
    def leader(self, tx, ty, ex, ey, text, size=26, tail=22):
        self.arrow(tx, ty, tx-ex, ty-ey)
        self.line([(tx, ty), (ex, ey), (ex+tail, ey)])
        self.d.text((ex+tail+8, ey - size + 6), text, font=F(size), fill=BLUE)
    def balloon(self, bx, by, num, tx, ty, r=26):
        L = math.hypot(bx-tx, by-ty)
        ux, uy = (bx-tx)/L, (by-ty)/L
        sx, sy = bx - ux*r, by - uy*r
        self.arrow(tx, ty, bx-tx, by-ty)
        self.line([(tx, ty), (sx, sy)])
        self.d.ellipse([bx-r, by-r, bx+r, by+r], outline=BLUE, width=3)
        self.text_c(bx, by - 15, str(num), 28)
    def ext_v(self, x, y_from, y_to):
        self.line([(x, y_from), (x, y_to)], wd=1)
    def ext_h(self, y, x_from, x_to):
        self.line([(x_from, y), (x_to, y)], wd=1)
    def view_label(self, cx, y, s):
        self.text_c(cx, y, s, 30, bold=True, color=BLACK)
    def sheet_no(self, n):
        self.d.text((52, 48), "SHEET %d OF 5" % n, font=F(22), fill=BLACK)
    def title_block(self, part, qty, material):
        x0, y0 = W-38-920, H-38-200
        d = self.d
        d.rectangle([x0, y0, W-38, H-38], outline=BLACK, width=2)
        r1h = 58
        d.line([(x0, y0+r1h), (W-38, y0+r1h)], fill=BLACK, width=2)
        size = self.fit_size(PROJ, 890, 28)
        self.text_c((x0+W-38)/2, y0 + 12, PROJ, size)
        r2y = y0 + r1h; r2h = 50
        d.line([(x0, r2y+r2h), (W-38, r2y+r2h)], fill=BLACK, width=2)
        ps = self.fit_size("PART: "+part, 890, 26)
        d.text((x0+12, r2y+11), "PART: "+part, font=F(ps), fill=BLACK)
        r3y = r2y + r2h; r3h = 48
        d.line([(x0, r3y+r3h), (W-38, r3y+r3h)], fill=BLACK, width=2)
        c1 = x0+250; c2 = c1+400
        d.line([(c1, r3y), (c1, r3y+r3h)], fill=BLACK, width=1)
        d.line([(c2, r3y), (c2, r3y+r3h)], fill=BLACK, width=1)
        d.text((x0+10, r3y+11), "QTY: "+qty, font=F(24), fill=BLACK)
        d.text((c1+10, r3y+11), "MATERIAL: "+material, font=F(24), fill=BLACK)
        d.text((c2+10, r3y+11), "SCALE: NTS", font=F(24), fill=BLACK)
        r4y = r3y + r3h
        xs = [x0, x0+230, x0+400, x0+670, W-38]
        for x in xs[1:-1]:
            d.line([(x, r4y), (x, H-38)], fill=BLACK, width=1)
        for x, s2 in zip(xs[:-1], ["UNITS: MM", "REV: "+REV, "DATE: "+DATE, "DRAWN: RED"]):
            d.text((x+10, r4y+9), s2, font=F(22), fill=BLACK)
    def notes(self, lines, x, y0, lh=36, size=26):
        for i, s2 in enumerate(lines):
            bold = s2.startswith("NOTES")
            self.d.text((x, y0+i*lh), s2, font=F(size, bold), fill=BLACK)
    def save(self, name):
        p = os.path.join(DRW, name)
        self.img.save(p)
        print("[sheet]", p, os.path.getsize(p), "bytes")

def sheet1():
    s = Sheet(); s.sheet_no(1)
    # layout: face view top, side view BELOW it at the SAME px/mm scale,
    # ISO mid-right to balance the sheet
    S, bb = s.paste_view("flange_face_r45", 640, 490)
    k = S / VIEWS["flange_side_r45"]["pxmm"]
    S2, bb2 = s.paste_view("flange_side_r45", 640, 1050, k=k)
    assert abs(S2 - S) < 0.01, "side view scale != face scale"
    s.paste_view("flange_iso", 1650, 760)
    # face callouts; hole dots from MEASURED HLR edge centers (face ctr 640,490)
    s.dot(434, 696)   # outer rim, lower-left diagonal
    s.leader(434, 696, 240, 820, "\u00d870")
    s.dot(480, 490)   # bore rim, left
    s.leader(480, 490, 270, 310, "ID \u00d838.5")
    s.dot(871, 394)   # bolt hole (measured center)
    s.leader(871, 394, 1130, 250, "8\u00d7 \u00d85.5 EQ.SP. ON \u00d860 BCD")
    s.dot(965, 490)   # tie-rod hole on right ear (measured center)
    s.leader(965, 490, 1170, 460, "4\u00d7 \u00d83.7 THRU (TIE) \u00d878 BC, EARS 84 ACROSS")
    # side view (below face): heights + stub
    sx0, sy0, sx1, sy1 = bb2
    sy_mid = sy1 - 7 * S2
    s.ext_h(sy0, sx1-30, sx1+150); s.ext_h(sy1, sx1-30, sx1+150); s.ext_h(sy_mid, sx1-10, sx1+150)
    s.dim_v(sx1+72, sy0, sy1, "27")
    s.dim_v(sx1+142, sy0, sy_mid, "20")
    s.dim_v(sx1+142, sy_mid, sy1, "7")
    sr = 21 * S2
    s.ext_v(640-sr, sy0-8, sy0-46); s.ext_v(640+sr, sy0-8, sy0-46)
    s.dim_h(640-sr, 640+sr, sy0-40, "\u00d842 STUB")
    s.view_label(640, 85, "TOP (FACE)")
    s.view_label(640, 1195, "SIDE")
    s.view_label(1650, 960, "ISO")
    s.title_block("FLANGE PIECE (INTEGRAL EARS)", "2", "PLA")
    s.save("sheet1_flange_piece.png")

def sheet2():
    s = Sheet(); s.sheet_no(2)
    S, bb = s.paste_view("bellows_front", 680, 730)
    s.paste_view("bellows_iso", 1850, 700)
    bx0, by0, bx1, by1 = bb
    s.text_c(680, 312, "5 CONVOLUTIONS", 26, bold=True, color=BLACK)
    rh = 24 * S
    s.ext_v(680-rh, by0-8, by0-61); s.ext_v(680+rh, by0-8, by0-61)
    s.dim_h(680-rh, 680+rh, by0-55, "\u00d848")
    s.ext_h(by0, bx1-15, bx1-70); s.ext_h(by1, bx1-15, bx1-70)
    s.dim_v(bx1-24, by0, by1, "55", size=26)
    yA = by1 - 9.5 * S
    yB = by1 - 18.5 * S
    s.ext_h(yA, 931, 961); s.ext_h(yB, 931, 961)
    s.line([(967, yB), (967, yA)])
    s.arrow(967, yA, 0, -1); s.arrow(967, yB, 0, 1)
    s.d.text((979, (yA+yB)/2 - 16), "9", font=F(26), fill=BLUE)
    sr = 18.8 * S
    s.ext_v(680-sr, by1+8, by1+43); s.ext_v(680+sr, by1+8, by1+43)
    s.dim_h(680-sr, 680+sr, by1+49, "\u00d837.6 SPIGOT \u00d72, L5")
    s.view_label(680, by1+95, "FRONT")
    s.dot(905, 869)
    s.leader(905, 869, 1000, 780, "WALL 1.2 (3 PERIMETERS)")
    s.view_label(1850, 1060, "ISO")
    s.title_block("BELLOWS SECTION W/ SPIGOTS", "1", "PETG (REC.)")
    s.save("sheet2_bellows.png")

def sheet3():
    s = Sheet(); s.sheet_no(3)
    # layout: bottom face view top, side view BELOW it at the SAME px/mm scale,
    # ISO mid-right to balance the sheet
    S, bb = s.paste_view("spool_bottom", 640, 470)
    k = S / VIEWS["spool_side"]["pxmm"]
    # rot180: model has collar on top / stub below, but part is machined/dimensioned
    # collar-down (7mm bottom band, 20mm stub above) matching the 27/20/7 + stub dims
    S2, bb2 = s.paste_view("spool_side", 640, 970, k=k, rot180=True)
    assert abs(S2 - S) < 0.01, "side view scale != face scale"
    s.paste_view("spool_iso", 1650, 760)
    # face callouts; bolt-hole dot from MEASURED HLR edge center (ctr 640,470)
    s.dot(442, 668)   # outer rim, lower-left diagonal
    s.leader(442, 668, 250, 800, "\u00d870")
    s.dot(748, 578)   # bore rim, lower-right
    s.leader(748, 578, 950, 740, "ID \u00d838")
    s.dot(862, 378)   # bolt hole (measured center)
    s.leader(862, 378, 1120, 240, "8\u00d7 \u00d85.5 ON \u00d860 BCD")
    sx0, sy0, sx1, sy1 = bb2
    sy_mid = sy1 - 7 * S2
    s.ext_h(sy0, sx1-30, sx1+150); s.ext_h(sy1, sx1-30, sx1+150); s.ext_h(sy_mid, sx1-10, sx1+150)
    s.dim_v(sx1+72, sy0, sy1, "27")
    s.dim_v(sx1+142, sy0, sy_mid, "20")
    s.dim_v(sx1+142, sy_mid, sy1, "7")
    sr = 21 * S2
    s.ext_v(640-sr, sy0-8, sy0-46); s.ext_v(640+sr, sy0-8, sy0-46)
    s.dim_h(640-sr, 640+sr, sy0-40, "\u00d842 STUB")
    s.view_label(640, 120, "BOTTOM (FACE)")
    s.view_label(640, 1110, "SIDE")
    s.view_label(1650, 960, "ISO")
    s.title_block("PIPE SPOOL", "2", "PLA")
    s.save("sheet3_spool.png")

def sheet4():
    s = Sheet(); s.sheet_no(4)
    S, bb = s.paste_view("gasket_top", 560, 560)
    Sg, bbg = s.paste_view("gasket_front", 560, 1150)
    Sp, bbp = s.paste_view("plate_top_text", 1560, 1000)
    gx0, gy0, gx1, gy1 = bb
    r44 = 22 * S
    s.ext_v(560-r44, gy0-8, gy0-48); s.ext_v(560+r44, gy0-8, gy0-48)
    s.dim_h(560-r44, 560+r44, gy0-42, "\u00d844")
    r385 = 19.25 * S
    s.ext_v(560-r385, gy1+8, gy1+46); s.ext_v(560+r385, gy1+8, gy1+46)
    s.dim_h(560-r385, 560+r385, gy1+52, "\u00d838.5")
    s.view_label(560, gy1+100, "GASKET - FACE")
    fx0, fy0, fx1, fy1 = bbg
    s.ext_v(fx0, fy1+12, fy1+52); s.ext_v(fx1, fy1+12, fy1+52)
    s.line([(fx0-28, fy1+48), (fx0, fy1+48)]); s.line([(fx1, fy1+48), (fx1+28, fy1+48)])
    s.arrow(fx0, fy1+48, 1, 0); s.arrow(fx1, fy1+48, -1, 0)
    s.text_c(560, fy1+12, "1.5", 26)
    s.view_label(560, 1290, "GASKET - EDGE")
    px0, py0, px1, py1 = bbp
    s.ext_v(px0, py0-8, py0-48); s.ext_v(px1, py0-8, py0-48)
    s.dim_h(px0, px1, py0-42, "40")
    s.ext_h(py0, px1+25, px1+70); s.ext_h(py1, px1+25, px1+70)
    s.dim_v(px1+34, py0, py1, "15")
    s.dot(1560, py1-10)
    s.leader(1560, py1-10, 1560, py1+64, "TEXT RAISED 0.6")
    s.view_label(1560, 1290, "DATA PLATE - TOP")
    s.title_block("GASKET / DATA PLATE", "2 / 1", "TPU-FOAM / PLA")
    s.save("sheet4_small_parts.png")

def sheet5():
    s = Sheet(); s.sheet_no(5)
    S, bb = s.paste_view("asm_front", 620, 700)
    ax0, ay0, ax1, ay1 = bb
    # World anchor fix: HLR ink is centered on the projection bbox, so the
    # world coords of the ink center = midpoint of the assembled link-union
    # extents. (v6 bug: used center_mm=[0,0], the RECENTRED view coords, so
    # every balloon target sat (zc*S) ~222 px low. X was symmetric, survived.)
    A = DIAG["anchors"]
    wxs = [v for bbs in A.values() for b in bbs for v in (b[0], b[1])]
    wzs = [v for bbs in A.values() for b in bbs for v in (b[4], b[5])]
    xc = (min(wxs) + max(wxs)) / 2.0
    zc = (min(wzs) + max(wzs)) / 2.0
    def px(x): return 620 + (x - xc) * S
    def py(z): return 700 - (z - zc) * S
    # calibration sanity: world z-extent mapped to px must match pasted ink span
    assert abs((py(min(wzs)) - py(max(wzs))) - (ay1 - ay0)) < 15.0, "asm calibration off"
    Se, bbe = s.paste_view("exp_iso_v2", 1850, 1090, k=0.58)
    assert bbe[1] > 864, "exploded view hits parts list"  # parts list bottom = 340+10*52
    lab_y = bbe[3] + 34
    assert lab_y + 40 < 1416, "exploded label hits title block"  # tb y0 = H-38-200
    s.view_label(1850, lab_y, "EXPLODED VIEW (ISO)")
    s.view_label(620, ay1+40, "ASSEMBLED - FRONT")
    # balloon anchors: each balloon on the flank NEAREST its target, at the
    # target's height -> short leaders, fan pattern, no crossings.
    # Numbering follows the 9-item BOM (printed parts 1-5, hardware 6-9).
    def pick(tgt, want="low"):
        bbs = A[tgt]
        key = (lambda e: e[4]) if want == "low" else (lambda e: -e[5])
        return min(bbs, key=key)
    ctr = lambda b: ((b[0]+b[1])/2.0, (b[4]+b[5])/2.0)
    flg = max(A["FlangePiece"], key=lambda e: e[5])          # top flange
    flg_t = (ctr(flg)[0] - 31, ctr(flg)[1])                  # left rim
    bel = pick("Bellows"); bel_t = (ctr(bel)[0] + 23, ctr(bel)[1])   # right rim
    spo = pick("Spool");  spo_t = (ctr(spo)[0] - 21, ctr(spo)[1])   # left edge
    gak = pick("Gasket"); gak_t = (ctr(gak)[0] + 21, ctr(gak)[1])   # right rim
    plb = pick("DataPlate"); plb_t = ctr(plb)
    bolt = pick("BoltM5"); bolt_t = (ctr(bolt)[0] - 3, ctr(bolt)[1])
    rod = max(A["TieRod"], key=lambda e: e[1]); rod_t = ctr(rod)     # rightmost rod
    n3 = max(A["NutM3"], key=lambda e: (e[5], e[1])); n3_t = ctr(n3) # top, right
    n5 = max(A["NutM5"], key=lambda e: (e[1], -e[4])); n5_t = ctr(n5) # bottom, right
    # left flank (clear zone x ~100..450)
    s.balloon(430, py(flg_t[1]) - 10, 1, px(flg_t[0]), py(flg_t[1]))
    s.balloon(430, min(max(py(-18.5) + 90, 460), 950), 5, px(-20.0), py(-18.5))  # plate left-edge midpoint
    s.balloon(430, py(spo_t[1]) + 20, 3, px(spo_t[0]), py(spo_t[1]))
    # right flank (clear zone x ~800..1180), staggered to target heights
    s.balloon(810, py(n3_t[1]) - 5, 8, px(n3_t[0]), py(n3_t[1]))
    s.balloon(810, py(bel_t[1]) - 45, 2, px(bel_t[0]), py(bel_t[1]))
    s.balloon(810, py(rod_t[1]) + 50, 7, px(rod_t[0]), py(rod_t[1]))
    s.balloon(810, py(n5_t[1]) - 46, 9, px(n5_t[0]), py(n5_t[1]))
    s.balloon(810, py(bolt_t[1]) - 5, 6, px(bolt_t[0]), py(bolt_t[1]))
    s.balloon(810, py(gak_t[1]) + 40, 4, px(gak_t[0]), py(gak_t[1]))
    # data plate face lettering (matches the sheet4 raised-text legend;
    # HLR strokes alone are illegible at assembly scale)
    s.text_c(px(0.0), py(-14.5), "NPS 6  CL.150", size=11, color=BLACK)
    s.text_c(px(0.0), py(-20.5), "SCALE 1:4  TIED AXIAL BELLOWS EJ", size=8, color=BLACK)
    # parts list (9 items; moved up so the exploded view keeps clearance)
    bx, by, rh = 1201, 340, 52
    colw = [80, 620, 250, 130]
    s.d.text((bx, 300), "PARTS LIST:", font=F(24, True), fill=BLACK)
    header = ["ITEM", "DESCRIPTION", "MATERIAL", "QTY"]
    rows = [
        ("1", "FLANGE PIECE W/ INTEGRAL EARS", "PLA", "2"),
        ("2", "BELLOWS SECTION W/ SPIGOTS", "PETG (REC.)", "1"),
        ("3", "PIPE SPOOL", "PLA", "2"),
        ("4", "GASKET \u00d744/\u00d738.5 \u00d7 1.5", "TPU-OR-FOAM", "2"),
        ("5", "DATA PLATE (RAISED TEXT)", "PLA", "1"),
        ("6", "BOLT M5\u00d730 + NUT + 2 WASHERS", "STEEL", "8 SETS"),
        ("7", "TIE ROD M3\u00d7107", "STEEL", "4"),
        ("8", "NUT M3 (HEX)", "STEEL", "16"),
        ("9", "NUT M5 (HEX)", "STEEL", "16"),
    ]
    x = bx
    for j, cell in enumerate(header):
        s.d.rectangle([x, by, x+colw[j], by+rh], outline=BLACK, width=2)
        s.d.text((x+10, by+13), cell, font=F(24, True), fill=BLACK)
        x += colw[j]
    y = by + rh
    for row in rows:
        x = bx
        for j, cell in enumerate(row):
            s.d.rectangle([x, y, x+colw[j], y+rh], outline=BLACK, width=1)
            s.d.text((x+10, y+13), cell, font=F(24, False), fill=BLACK)
            x += colw[j]
        y += rh
    s.notes([
        "NOTES:",
        "1. DISPLAY MODEL - NOT A PRESSURE VESSEL.",
        "2. ALL DIMENSIONS MM. SCALE 1:4 OF NPS 6 / DN150 CLASS 150.",
        "3. PRINT: PLA FOR FLANGES/SPOOL/PLATE; PETG RECOMMENDED FOR BELLOWS.",
        "4. HARDWARE: 4\u00d7 M3\u00d7107 TIE RODS + 16\u00d7 M3 NUTS;",
        "   8\u00d7 M5\u00d730 + NUT + WASHERS PER JOINT SET.",
    ], x=60, y0=1330)
    s.title_block("ASSEMBLY - TIED AXIAL EXPANSION JOINT", "SEE BOM", "SEE BOM")
    s.save("sheet5_assembly.png")

sheet1(); sheet2(); sheet3(); sheet4(); sheet5()

names = ["sheet1_flange_piece.png", "sheet2_bellows.png", "sheet3_spool.png",
         "sheet4_small_parts.png", "sheet5_assembly.png"]
pages = [Image.open(os.path.join(DRW, n)).convert("RGB") for n in names]
for n, p in zip(names, pages):
    assert p.size == (W, H), (n, p.size)
pdf = os.path.join(DRW, "expansion_joint_v7_drawings.pdf")
pages[0].save(pdf, save_all=True, append_images=pages[1:], resolution=200.0)
print("[pdf]", pdf, os.path.getsize(pdf), "bytes")
print("[done] all 5 sheets + pdf generated")
