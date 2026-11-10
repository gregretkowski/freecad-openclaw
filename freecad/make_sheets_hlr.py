import json, math, os
from PIL import Image, ImageDraw, ImageFont

OUT = "/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v4/drawings"
VIEWS = json.load(open(os.path.join(OUT, "views_hlr", "views_hlr.json")))
W, H = 2339, 1654
BLACK = (26, 26, 26)
BLUE = (28, 79, 156)
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DATE, REV = "2026-10-16", "V4"
PROJ = "TIED AXIAL EXPANSION JOINT - SCALE MODEL 1:4"
_fc = {}
def F(px, bold=True):
    k = (px, bold)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(FB if bold else FR, px)
    return _fc[k]

class Sheet:
    def __init__(self):
        self.img = Image.new("RGB", (W, H), "white")
        self.d = ImageDraw.Draw(self.img)
        self.d.rectangle([26, 26, W-26, H-26], outline=BLACK, width=3)
        self.d.rectangle([38, 38, W-38, H-38], outline=BLACK, width=1)
    def paste_view(self, key, cx, cy, k=1.0, margin=8):
        m = VIEWS[key]
        img = Image.open(m["path"]).convert("RGB")
        x0, y0, x1, y1 = m["bbox"]
        x0 = max(0, x0-margin); y0 = max(0, y0-margin)
        x1 = min(img.width, x1+margin); y1 = min(img.height, y1+margin)
        crop = img.crop((x0, y0, x1, y1))
        if k != 1.0:
            crop = crop.resize((max(1, int(crop.width*k)), max(1, int(crop.height*k))), Image.LANCZOS)
        a = crop.convert("L").point(lambda v: 0 if v > 246 else 255)
        self.img.paste(crop, (int(cx-crop.width/2), int(cy-crop.height/2)), a)
        pxmm = m["pxmm"].get("x") or m["pxmm"].get("y") or 0
        return pxmm * k
    def paste_png(self, path, cx, cy, target_w):
        img = Image.open(path).convert("RGB")
        kk = target_w / img.width
        crop = img.resize((int(img.width*kk), int(img.height*kk)), Image.LANCZOS)
        a = crop.convert("L").point(lambda v: 0 if v > 246 else 255)
        self.img.paste(crop, (int(cx-crop.width/2), int(cy-crop.height/2)), a)
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
    def ext_v(self, x, y_from, y_to):
        self.line([(x, y_from), (x, y_to)], wd=1)
    def ext_h(self, y, x_from, x_to):
        self.line([(x_from, y), (x_to, y)], wd=1)
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
        p = os.path.join(OUT, name)
        self.img.save(p)
        print("[sheet]", p, os.path.getsize(p), "bytes")

def sheet1():
    s = Sheet(); s.sheet_no(1)
    S = s.paste_view("flange_front", 640, 660)    # 7.381 px/mm, art x 330..950 y 560..760
    S2 = s.paste_view("flange_side", 1360, 660)   # 7.407 px/mm
    s.paste_view("flange_iso", 1930, 300)
    r = 35 * S
    s.ext_v(640-r, 552, 499); s.ext_v(640+r, 552, 499)
    s.dim_h(640-r, 640+r, 505, "\u00d870")
    s.ext_v(330, 764, 824); s.ext_v(950, 764, 824)
    s.dim_h(330, 950, 830, "84 ACROSS EARS")
    s.view_label(640, 884, "FRONT")
    hx = 640 + 30*math.cos(math.radians(22.5))*S
    hy = 660 - 30*math.sin(math.radians(22.5))*S
    s.dot(hx, hy)
    s.leader(hx, hy, 955, 445, "8\u00d7 \u00d85.5 EQ.SP. ON \u00d860 BCD")
    s.dot(640 + 39*S, 660)
    s.leader(640 + 39*S, 660, 1010, 780, "4\u00d7 \u00d83.7 THRU (TIE ROD)")
    sy_top, sy_bot = 560, 760
    sy_mid = sy_bot - 7 * S2
    s.ext_h(sy_top, 1712, 1772); s.ext_h(sy_bot, 1712, 1772); s.ext_h(sy_mid, 1746, 1772)
    s.dim_v(1720, sy_top, sy_bot, "27")
    s.dim_v(1760, sy_top, sy_mid, "20")
    s.dim_v(1760, sy_mid, sy_bot, "7")
    sr = 21 * S2
    s.ext_v(1360-sr, 552, 514); s.ext_v(1360+sr, 552, 514)
    s.dim_h(1360-sr, 1360+sr, 520, "\u00d842 STUB")
    s.dot(1430, 640)
    s.leader(1430, 640, 1560, 600, "ID \u00d838.5")
    s.view_label(1360, 816, "SIDE")
    s.view_label(1930, 520, "ISO")
    s.title_block("FLANGE PIECE (INTEGRAL EARS)", "2", "PLA")
    s.save("sheet1_flange_piece.png")

def sheet2():
    s = Sheet(); s.sheet_no(2)
    S = s.paste_view("bellows_front", 680, 730)   # y 10.327, art x 433..927 y 446..1014
    s.paste_view("bellows_iso", 1850, 700)
    s.text_c(680, 312, "5 CONVOLUTIONS", 26, bold=True, color=BLACK)
    rh = 24 * (494/48.0)
    s.ext_v(680-rh, 438, 385); s.ext_v(680+rh, 438, 385)
    s.dim_h(680-rh, 680+rh, 391, "\u00d848")
    s.ext_h(446, 429, 374); s.ext_h(1014, 429, 374)
    s.dim_v(378, 446, 1014, "55", size=26)
    yA = 1014 - 9.5*10.327272727272728
    yB = 1014 - 18.5*10.327272727272728
    s.ext_h(yA, 931, 961); s.ext_h(yB, 931, 961)
    s.line([(967, yB), (967, yA)])
    s.arrow(967, yA, 0, -1); s.arrow(967, yB, 0, 1)
    s.d.text((979, (yA+yB)/2 - 16), "9", font=F(26), fill=BLUE)
    sr = 18.8 * (494/48.0)
    s.ext_v(680-sr, 1018, 1053); s.ext_v(680+sr, 1018, 1053)
    s.dim_h(680-sr, 680+sr, 1059, "\u00d837.6 SPIGOT \u00d72, L5")
    s.view_label(680, 1105, "FRONT")
    s.dot(905, 869)
    s.leader(905, 869, 1000, 780, "WALL 1.2 (3 PERIMETERS)")
    s.view_label(1850, 1060, "ISO")
    s.title_block("BELLOWS SECTION W/ SPIGOTS", "1", "PETG (REC.)")
    s.save("sheet2_bellows.png")

def sheet3():
    s = Sheet(); s.sheet_no(3)
    S = s.paste_view("spool_front", 640, 660)     # 8.7429, art x 334..946 y 541..779
    S2 = s.paste_view("spool_side", 1360, 660)    # 8.7407
    s.paste_view("spool_iso", 1980, 260)
    r = 35 * S
    s.ext_v(640-r, 533, 485); s.ext_v(640+r, 533, 485)
    s.dim_h(640-r, 640+r, 491, "\u00d870")
    hx = 640 + 30*math.cos(math.radians(22.5))*S
    hy = 660 - 30*math.sin(math.radians(22.5))*S
    s.dot(hx, hy)
    s.leader(hx, hy, 955, 445, "8\u00d7 \u00d85.5 ON \u00d860 BCD")
    sy_top, sy_bot = 542, 778
    sy_mid = sy_bot - 7 * S2
    s.ext_h(sy_top, 1706, 1766); s.ext_h(sy_bot, 1706, 1766); s.ext_h(sy_mid, 1740, 1766)
    s.dim_v(1714, sy_top, sy_bot, "27")
    s.dim_v(1754, sy_top, sy_mid, "20")
    s.dim_v(1754, sy_mid, sy_bot, "7")
    sr = 21 * S2
    s.ext_v(1360-sr, 534, 499); s.ext_v(1360+sr, 534, 499)
    s.dim_h(1360-sr, 1360+sr, 505, "\u00d842 STUB")
    s.dot(1430, 640)
    s.leader(1430, 640, 1560, 560, "ID \u00d838")
    s.view_label(640, 830, "FRONT")
    s.view_label(1360, 812, "SIDE")
    s.view_label(1980, 530, "ISO")
    s.title_block("PIPE SPOOL", "2", "PLA")
    s.save("sheet3_spool.png")

def sheet4():
    s = Sheet(); s.sheet_no(4)
    S = s.paste_view("gasket_top", 560, 560)      # 14.4545, art x 242..878 y 242..878
    s.paste_view("gasket_front", 560, 1150)       # strip x 242..878 y 1139..1161
    s.paste_view("plate_top", 1560, 1000)         # 21.05, art x 1139..1981 y 842..1158
    r44, r385 = 22*S, 19.25*S
    s.ext_v(560-r44, 234, 186); s.ext_v(560+r44, 234, 186)
    s.dim_h(560-r44, 560+r44, 192, "\u00d844")
    s.ext_v(560-r385, 884, 922); s.ext_v(560+r385, 884, 922)
    s.dim_h(560-r385, 560+r385, 928, "\u00d838.5")
    s.view_label(560, 990, "GASKET - FACE")
    s.ext_v(242, 1174, 1218); s.ext_v(878, 1174, 1218)
    s.line([(214, 1212), (242, 1212)]); s.line([(878, 1212), (906, 1212)])
    s.arrow(242, 1212, 1, 0); s.arrow(878, 1212, -1, 0)
    s.text_c(560, 1176, "1.5", 26)
    s.view_label(560, 1290, "GASKET - EDGE")
    pw = 421
    s.ext_v(1560-pw, 834, 786); s.ext_v(1560+pw, 834, 786)
    s.dim_h(1560-pw, 1560+pw, 794, "40")
    s.ext_h(842, 1985, 2030); s.ext_h(1158, 1985, 2030)
    s.dim_v(2026, 842, 1158, "15")
    s.dot(1560, 1160)
    s.leader(1560, 1160, 1560, 1206, "TEXT RAISED 0.6")
    s.view_label(1560, 1290, "DATA PLATE - TOP")
    s.title_block("GASKET / DATA PLATE", "2 / 1", "TPU-FOAM / PLA")
    s.save("sheet4_small_parts.png")

def sheet5():
    s = Sheet(); s.sheet_no(5)
    s.paste_view("asm_front", 620, 700)           # y 4.2436, x 5.2638; art x 397..843 y 369..1031
    PY = 4.243589743589744; PX = PY  # true ortho HLR: uniform scale, balloons land exactly
    def py(z): return 700 - (z-49.5)*PY
    def px(x): return 620 + x*PX
    s.paste_png("/home/openclaw/.openclaw/workspace/freecad/expansion-joint-v4/v4_exploded_100_front.png", 1700, 1080, 600)
    s.view_label(1700, 1330, "EXPLODED VIEW (100%)")
    s.view_label(620, 1080, "ASSEMBLED - FRONT")
    s.balloon(940, 470, 1, px(6.5), py(95.5))
    s.balloon(930, 640, 2, px(1.5), py(49.5))
    s.balloon(930, 990, 3, px(1.5), py(-5))
    s.balloon(300, 480, 4, px(1.5), py(99.75))
    s.balloon(1010, 760, 5, px(6.5), py(50))
    s.balloon(1030, 560, 6, px(6.5), py(88))
    s.balloon(1010, 900, 7, px(3), py(10.35))
    bx, by, rh = 1201, 420, 52
    colw = [80, 620, 250, 130]
    s.d.text((bx, 382), "PARTS LIST:", font=F(24, True), fill=BLACK)
    header = ["ITEM", "DESCRIPTION", "MATERIAL", "QTY"]
    rows = [
        ("1", "FLANGE PIECE (INTEGRAL EARS)", "PLA", "2"),
        ("2", "BELLOWS SECTION W/ SPIGOTS", "PETG (REC.)", "1"),
        ("3", "PIPE SPOOL", "PLA", "2"),
        ("4", "GASKET \u00d844/\u00d838.5 \u00d7 1.5", "TPU-OR-FOAM", "2"),
        ("5", "TIE ROD M3\u00d7110", "STEEL", "4"),
        ("6", "NUT M3 (HEX)", "STEEL", "16"),
        ("7", "BOLT M5\u00d730 + NUT + 2 WASHERS", "STEEL", "8 SETS"),
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
        "4. HARDWARE: 4\u00d7 M3\u00d7110 TIE RODS + 16\u00d7 M3 NUTS;",
        "   8\u00d7 M5\u00d730 + NUT + WASHERS PER JOINT SET.",
    ], x=60, y0=1330)
    s.title_block("ASSEMBLY - TIED AXIAL EXPANSION JOINT", "SEE BOM", "SEE BOM")
    s.save("sheet5_assembly.png")

sheet1(); sheet2(); sheet3(); sheet4(); sheet5()

names = ["sheet1_flange_piece.png", "sheet2_bellows.png", "sheet3_spool.png",
         "sheet4_small_parts.png", "sheet5_assembly.png"]
pages = [Image.open(os.path.join(OUT, n)).convert("RGB") for n in names]
for n, p in zip(names, pages):
    assert p.size == (W, H), (n, p.size)
pdf = os.path.join(OUT, "expansion_joint_v4_drawings.pdf")
pages[0].save(pdf, save_all=True, append_images=pages[1:], resolution=200.0)
print("[pdf]", pdf, os.path.getsize(pdf), "bytes")
print("[done] all 5 sheets + pdf generated");
