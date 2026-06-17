# -*- coding: utf-8 -*-
"""Generate locAIte thesis diagrams as high-res PNGs using Pillow."""
import os, math
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "diagrams")
os.makedirs(OUT, exist_ok=True)
S = 2  # supersampling

# brand palette
NAVY = (10, 26, 53)
BLUE = (28, 129, 217)
GREEN = (126, 199, 72)
GREY = (188, 194, 199)
LGREY = (236, 240, 245)
DGREY = (90, 100, 115)
WHITE = (255, 255, 255)
RED = (211, 47, 47)
INK = (26, 26, 26)

def _font(size, bold=False):
    names = ([r"C:\Windows\Fonts\arialbd.ttf"] if bold else [r"C:\Windows\Fonts\arial.ttf"])
    names += ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, size * S)
        except Exception:
            continue
    return ImageFont.load_default()

def canvas(w, h, bg=WHITE):
    img = Image.new("RGB", (w * S, h * S), bg)
    return img, ImageDraw.Draw(img)

def save(img, name):
    w, h = img.size
    img = img.resize((w // S, h // S), Image.LANCZOS)
    p = os.path.join(OUT, name)
    img.save(p, "PNG")
    print("wrote", p)

def _wrap(draw, text, font, maxw):
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if draw.textlength(t, font=font) <= maxw * S:
            cur = t
        else:
            if cur: lines.append(cur)
            cur = wd
    if cur: lines.append(cur)
    return lines

def text_center(draw, cx, cy, lines, font, fill, lh=None):
    if isinstance(lines, str): lines = [lines]
    asc, desc = font.getmetrics()
    fh = asc + desc
    lh = (lh or (fh + 4 * S))
    total = lh * len(lines)
    y = cy * S - total / 2
    for ln in lines:
        w = draw.textlength(ln, font=font)
        draw.text((cx * S - w / 2, y), ln, font=font, fill=fill)
        y += lh

def box(draw, x, y, w, h, title, fill=WHITE, outline=NAVY, tcolor=INK,
        sub=None, fsz=15, ow=2, radius=12):
    draw.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S],
                           radius=radius * S, fill=fill, outline=outline, width=ow * S)
    f = _font(fsz, bold=True)
    if sub:
        sf = _font(fsz - 3)
        lines = _wrap(draw, title, f, w - 16)
        slines = []
        for s in (sub if isinstance(sub, list) else [sub]):
            slines += _wrap(draw, s, sf, w - 16)
        asc, desc = f.getmetrics(); fh = asc + desc + 3 * S
        sasc, sdesc = sf.getmetrics(); sfh = sasc + sdesc + 2 * S
        total = fh * len(lines) + sfh * len(slines) + 4 * S
        yy = (y + h / 2) * S - total / 2
        for ln in lines:
            wln = draw.textlength(ln, font=f)
            draw.text(((x + w / 2) * S - wln / 2, yy), ln, font=f, fill=tcolor); yy += fh
        yy += 4 * S
        for ln in slines:
            wln = draw.textlength(ln, font=sf)
            draw.text(((x + w / 2) * S - wln / 2, yy), ln, font=sf, fill=DGREY); yy += sfh
    else:
        lines = _wrap(draw, title, f, w - 16)
        text_center(draw, x + w / 2, y + h / 2, lines, f, tcolor)

def diamond(draw, cx, cy, w, h, text, fill=(255, 244, 219), outline=(214, 158, 46), tcolor=INK, fsz=13):
    pts = [(cx * S, (cy - h / 2) * S), ((cx + w / 2) * S, cy * S),
           (cx * S, (cy + h / 2) * S), ((cx - w / 2) * S, cy * S)]
    draw.polygon(pts, fill=fill, outline=outline)
    draw.line(pts + [pts[0]], fill=outline, width=2 * S)
    f = _font(fsz, bold=True)
    text_center(draw, cx, cy, _wrap(draw, text, f, w - 24), f, tcolor)

def ellipse_uc(draw, cx, cy, w, h, text, fill=(234, 244, 252), outline=BLUE, tcolor=NAVY, fsz=13):
    draw.ellipse([(cx - w / 2) * S, (cy - h / 2) * S, (cx + w / 2) * S, (cy + h / 2) * S],
                 fill=fill, outline=outline, width=2 * S)
    f = _font(fsz, bold=True)
    text_center(draw, cx, cy, _wrap(draw, text, f, w - 22), f, tcolor)

def arrow(draw, p1, p2, color=NAVY, width=2, head=10, label=None, lcolor=DGREY, dashed=False):
    x1, y1 = p1[0] * S, p1[1] * S
    x2, y2 = p2[0] * S, p2[1] * S
    if dashed:
        _dash(draw, (x1, y1), (x2, y2), color, width)
    else:
        draw.line([x1, y1, x2, y2], fill=color, width=width * S)
    ang = math.atan2(y2 - y1, x2 - x1)
    hs = head * S
    draw.polygon([(x2, y2),
                  (x2 - hs * math.cos(ang - 0.45), y2 - hs * math.sin(ang - 0.45)),
                  (x2 - hs * math.cos(ang + 0.45), y2 - hs * math.sin(ang + 0.45))], fill=color)
    if label:
        f = _font(11, bold=True)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        tw = draw.textlength(label, font=f)
        pad = 5 * S
        draw.rectangle([mx - tw/2 - pad, my - 11*S, mx + tw/2 + pad, my + 11*S], fill=WHITE)
        draw.text((mx - tw / 2, my - 8 * S), label, font=f, fill=lcolor)

def line(draw, p1, p2, color=NAVY, width=2):
    draw.line([p1[0]*S, p1[1]*S, p2[0]*S, p2[1]*S], fill=color, width=width*S)

def _dash(draw, p1, p2, color, width, dash=10):
    x1, y1 = p1; x2, y2 = p2
    tot = math.hypot(x2 - x1, y2 - y1); dx = (x2 - x1) / tot; dy = (y2 - y1) / tot
    d = 0
    while d < tot:
        a = (x1 + dx * d, y1 + dy * d)
        b = (x1 + dx * min(d + dash * S, tot), y1 + dy * min(d + dash * S, tot))
        draw.line([a[0], a[1], b[0], b[1]], fill=color, width=width * S)
        d += dash * S * 2

def title(draw, w, text, sub=None):
    f = _font(24, bold=True)
    tw = draw.textlength(text, font=f)
    draw.text((w / 2 * S - tw / 2, 22 * S), text, font=f, fill=NAVY)
    if sub:
        sf = _font(13)
        sw = draw.textlength(sub, font=sf)
        draw.text((w / 2 * S - sw / 2, 54 * S), sub, font=sf, fill=DGREY)
    draw.line([60*S, 78*S, (w-60)*S, 78*S], fill=GREEN, width=3*S)

def actor(draw, cx, cy, label):
    c = NAVY; r = 11
    draw.ellipse([(cx-r)*S, (cy-28)*S, (cx+r)*S, (cy-28+2*r)*S], outline=c, width=3*S)
    line(draw, (cx, cy-6), (cx, cy+18), c, 3)
    line(draw, (cx-16, cy+2), (cx+16, cy+2), c, 3)
    line(draw, (cx, cy+18), (cx-14, cy+40), c, 3)
    line(draw, (cx, cy+18), (cx+14, cy+40), c, 3)
    f = _font(14, bold=True)
    for i, ln in enumerate(label.split("\n")):
        tw = draw.textlength(ln, font=f)
        draw.text((cx*S - tw/2, (cy+48 + i*20)*S), ln, font=f, fill=NAVY)

# =========================================================================
# 1. SYSTEM ARCHITECTURE
# =========================================================================
def architecture():
    W, H = 1180, 900
    img, d = canvas(W, H)
    title(d, W, "locAIte - System Architecture", "Single Flask app serves the static frontend and the REST API")

    # Presentation tier
    box(d, 90, 120, 1000, 90, "PRESENTATION TIER  -  Browser (locAIte static site)", fill=LGREY, outline=BLUE,
        sub="HTML / CSS / Bootstrap / vanilla JS  -  app.js (window.LOCAITE)  -  JWT in localStorage", fsz=16)
    # Application tier container
    box(d, 90, 270, 1000, 250, "", fill=(247, 250, 253), outline=NAVY, ow=2, radius=14)
    f = _font(13, bold=True); d.text((110*S, 280*S), "APPLICATION TIER  -  Flask (Python)", font=f, fill=NAVY)
    box(d, 120, 320, 430, 70, "REST API Blueprints", fill=WHITE, outline=BLUE,
        sub="auth  -  cases  -  admin  -  stream  -  fb", fsz=15)
    box(d, 120, 410, 430, 80, "AI Engine  (Singleton FaceModel)", fill=(240, 248, 236), outline=GREEN,
        sub="MTCNN detect  +  FaceNet embed  +  L2 match", fsz=15)
    box(d, 600, 320, 470, 70, "NLP Analyzer  (fb_analyzer)", fill=WHITE, outline=BLUE,
        sub="rapidfuzz name match  +  spaCy / regex location", fsz=15)
    box(d, 600, 410, 470, 80, "Static file serving", fill=WHITE, outline=GREY,
        sub="catch-all route -> new_front_end/  (one port: 5000)", fsz=15)
    # Data tier
    box(d, 90, 580, 560, 95, "DATA TIER  -  SQLite via SQLAlchemy", fill=LGREY, outline=NAVY,
        sub=["User  -  MissingPerson", "MatchAlert  -  FacebookSighting"], fsz=16)
    box(d, 700, 580, 390, 95, "Periodic FB Scan Runner", fill=(255, 248, 236), outline=(214, 158, 46),
        sub=["fb_scan_runner.py (separate process)", "every 600s -> writes sightings"], fsz=15)

    arrow(d, (590, 210), (590, 270), BLUE, 3, label="HTTP  (JSON / MJPEG)")
    arrow(d, (370, 520), (370, 580), NAVY, 3, label="ORM")
    arrow(d, (835, 580), (835, 520), NAVY, 3)
    arrow(d, (650, 627), (700, 627), DGREY, 3)
    save(img, "01_architecture.png")

# =========================================================================
# 2. ERD
# =========================================================================
def entity(d, x, y, w, name, rows, accent=BLUE):
    rh = 26
    h = 34 + rh * len(rows)
    d.rounded_rectangle([x*S, y*S, (x+w)*S, (y+h)*S], radius=8*S, fill=WHITE, outline=NAVY, width=2*S)
    d.rounded_rectangle([x*S, y*S, (x+w)*S, (y+34)*S], radius=8*S, fill=accent, outline=accent)
    d.rectangle([x*S, (y+20)*S, (x+w)*S, (y+34)*S], fill=accent)
    f = _font(14, bold=True)
    tw = d.textlength(name, font=f); d.text(((x+w/2)*S - tw/2, (y+8)*S), name, font=f, fill=WHITE)
    rf = _font(11); rfb = _font(11, bold=True)
    yy = y + 34
    for label, typ, pk in rows:
        if pk: d.rectangle([x*S, yy*S, (x+w)*S, (yy+rh)*S], fill=(240, 246, 252))
        d.text((x*S + 10*S, yy*S + 6*S), label, font=(rfb if pk else rf), fill=INK)
        tw = d.textlength(typ, font=rf); d.text((x+w)*S - tw - 10*S, yy*S + 6*S, ) if False else None
        d.text(((x+w)*S - tw - 10*S, yy*S + 6*S), typ, font=rf, fill=DGREY)
        d.line([x*S, (yy+rh)*S, (x+w)*S, (yy+rh)*S], fill=GREY, width=1*S)
        yy += rh
    return (x, y, w, h)

def erd():
    W, H = 1180, 860
    img, d = canvas(W, H)
    title(d, W, "locAIte - Entity Relationship Diagram", "SQLite (SQLAlchemy ORM)")

    entity(d, 90, 120, 300, "User", [
        ("PK  id", "Integer", True), ("username", "String", False), ("email", "String", False),
        ("first_name / last_name", "String", False), ("middle_name", "String", False),
        ("password_hash", "String", False), ("role", "String", False)], accent=DGREY)

    mp = entity(d, 440, 120, 330, "MissingPerson", [
        ("PK  id", "Integer", True), ("name", "String", False), ("national_id", "String", False),
        ("last_location", "String", False), ("identifiers", "Text", False), ("status", "String", False),
        ("created_at", "DateTime", False), ("embedding_blob", "PickleType", False),
        ("photo_path", "String", False), ("last_location_updated_at", "DateTime", False),
        ("last_location_source", "String", False)], accent=BLUE)

    entity(d, 830, 120, 260, "MatchAlert", [
        ("PK  id", "Integer", True), ("FK  missing_person_id", "Integer", True),
        ("timestamp", "DateTime", False), ("confidence", "Float", False),
        ("status", "String", False)], accent=GREEN)

    entity(d, 830, 430, 260, "FacebookSighting", [
        ("PK  id", "Integer", True), ("FK  missing_person_id", "Integer", True),
        ("post_id", "String", False), ("post_url", "String", False), ("post_text", "Text", False),
        ("matched_name", "String", False), ("match_score", "Float", False),
        ("previous_location", "String", False), ("new_location", "String", False),
        ("applied", "Boolean", False), ("created_at", "DateTime", False)], accent=(214, 158, 46))

    # relationships (crow's-foot-ish: 1 .. N)
    def rel(p1, p2, label):
        line(d, p1, (p2[0], p1[1]), NAVY, 2)
        line(d, (p2[0], p1[1]), p2, NAVY, 2)
        f = _font(12, bold=True)
        d.text((p1[0]*S + 8*S, p1[1]*S - 18*S), "1", font=f, fill=NAVY)
        d.text((p2[0]*S - 16*S, p2[1]*S - 18*S), "N", font=f, fill=NAVY)
        tw = d.textlength(label, font=_font(11))
        d.text(((p1[0]+p2[0])/2*S - tw/2, p1[1]*S - 18*S), label, font=_font(11), fill=DGREY)
    rel((770, 200), (830, 200), "has")
    rel((770, 470), (830, 470), "logs")
    save(img, "02_erd.png")

# =========================================================================
# 3. USE CASE
# =========================================================================
def usecase():
    W, H = 1180, 820
    img, d = canvas(W, H)
    title(d, W, "locAIte - Use Case Diagram")
    # system boundary
    d.rounded_rectangle([300*S, 110*S, 880*S, 770*S], radius=16*S, outline=NAVY, width=2*S)
    f = _font(13, bold=True); d.text((320*S, 120*S), "locAIte System", font=f, fill=NAVY)

    actor(d, 130, 360, "Public\nUser")
    actor(d, 1050, 360, "Administrator")

    ucs_user = [("Register / Login", 200), ("Report Missing Person", 280),
                ("Browse Case Directory", 360), ("View Case Details", 440), ("View Live Stream", 520)]
    for t, y in ucs_user:
        ellipse_uc(d, 470, y, 230, 56, t)
        line(d, (175, 360), (355, y), DGREY, 2)

    ucs_admin = [("View Dashboard & Stats", 200), ("Review / Resolve Matches", 300),
                 ("Manage Case Status", 400), ("Run Facebook Scan", 500), ("View FB Sightings Log", 600)]
    for t, y in ucs_admin:
        ellipse_uc(d, 710, y, 250, 56, t, fill=(240, 248, 236), outline=GREEN, tcolor=NAVY)
        line(d, (1005, 360), (835, y), DGREY, 2)

    # AI engine as secondary actor
    actor(d, 470, 700, "AI Engine\n(MTCNN+FaceNet)")
    arrow(d, (470, 548), (470, 652), GREEN, 2, label="auto-detect")
    save(img, "03_usecase.png")

# =========================================================================
# 4. FACE-MATCHING FLOWCHART
# =========================================================================
def flowchart():
    W, H = 1180, 1180
    img, d = canvas(W, H)
    title(d, W, "Real-Time Face-Matching Algorithm", "backend/routes/stream.py  -  gen_frames()")

    cx = 360
    def term(y, t, fill): box(d, cx-120, y, 240, 48, t, fill=fill, outline=NAVY, radius=24, fsz=14)
    def proc(y, t, sub=None): box(d, cx-150, y, 300, 56, t, fill=WHITE, outline=BLUE, sub=sub, fsz=14)

    term(110, "START  /  open camera", (240, 248, 236))
    arrow(d, (cx, 158), (cx, 180))
    proc(180, "Capture frame")
    arrow(d, (cx, 236), (cx, 262))
    diamond(d, cx, 300, 240, 78, "frame_count % 10 == 0 ?")
    # No branch loops back
    arrow(d, (cx+120, 300), (760, 300), DGREY, 2, label="No")
    line(d, (760, 300), (760, 208), DGREY, 2)
    arrow(d, (760, 208), (cx+150, 208), DGREY, 2)
    arrow(d, (cx, 339), (cx, 365), label="Yes")
    proc(365, "Detect faces (MTCNN)")
    arrow(d, (cx, 421), (cx, 447))
    proc(447, "For each face: crop 160x160, embed (FaceNet)")
    arrow(d, (cx, 503), (cx, 529))
    proc(529, "Compare to all active cases", sub="min Euclidean (L2) distance")
    arrow(d, (cx, 585), (cx, 611))
    diamond(d, cx, 655, 250, 84, "min distance < 0.65 ?")

    # Yes -> match
    arrow(d, (cx-125, 655), (170, 655), GREEN, 2, label="Yes")
    box(d, 40, 700, 260, 84, "MATCH", fill=(240, 248, 236), outline=GREEN, tcolor=(60,120,40),
        sub=["Green box + label", "Create MatchAlert (pending)"], fsz=14)
    # No -> unknown
    arrow(d, (cx+125, 655), (560, 655), RED, 2, label="No")
    box(d, 560, 700, 250, 84, "UNKNOWN", fill=(252, 236, 236), outline=RED, tcolor=(150,40,40),
        sub=["Red box + 'Unknown'"], fsz=14)

    arrow(d, (170, 784), (cx-60, 845), GREEN, 2)
    arrow(d, (685, 784), (cx+60, 845), RED, 2)
    proc(845, "Annotate frame, encode JPEG")
    arrow(d, (cx, 901), (cx, 927))
    proc(927, "Yield frame  ->  MJPEG stream")
    # loop back to capture
    arrow(d, (cx-150, 955), (90, 955), NAVY, 2, label="loop")
    line(d, (90, 955), (90, 208), NAVY, 2)
    arrow(d, (90, 208), (cx-150, 208), NAVY, 2)
    save(img, "04_face_matching_flowchart.png")

architecture(); erd(); usecase(); flowchart()
print("DONE ->", OUT)
