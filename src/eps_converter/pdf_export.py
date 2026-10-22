"""EPS-Datenblatt als PDF im Layout C (Seitenleiste), Deutsch und Englisch.

Leere Felder werden ausgeblendet. Herstellerangaben (Hersteller, Original-Typ, Hersteller-Nr.)
erscheinen nie auf dem Datenblatt.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.platypus import (BaseDocTemplate, Frame, Image, NextPageTemplate, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle, KeepTogether)
from xml.sax.saxutils import escape

from . import darstellung, pfade, regeln
from . import katalog as K
from .modell import Datensatz

NAVY = colors.HexColor("#35528C")
CYAN = colors.HexColor("#52B4D7")
INK = colors.HexColor("#1C2633")
GREY = colors.HexColor("#6A7380")
LINE = colors.HexColor("#D5DCE6")
SIDE_LABEL = colors.HexColor("#B9C8E4")
SIDE_SMALL = colors.HexColor("#C9D6EE")
A4W, A4H = A4

T = {
    "de": dict(datenblatt="DATENBLATT", serie="SERIE", kerndaten="KERNDATEN", bestellnr="BESTELLNUMMER",
               lieferumfang="Lieferumfang", optionen="Optionen", techdaten="Technische Daten",
               seite="Seite", geraetetyp="Gerätetyp",
               fuss="Irrtümer und Änderungen vorbehalten · Alle Wertangaben sind typische Werte",
               kontakt=["EPS Stromversorgung GmbH", "Alter Postweg 101", "86159 Augsburg",
                        "Tel. +49 (0) 821 570451-0", "info@eps-germany.de", "www.eps-germany.de"]),
    "en": dict(datenblatt="DATASHEET", serie="SERIES", kerndaten="KEY DATA", bestellnr="ORDER CODE",
               lieferumfang="Scope of delivery", optionen="Options", techdaten="Technical data",
               seite="Page", geraetetyp="Device type",
               fuss="Errors and changes excepted · All values are typical values",
               kontakt=["EPS Stromversorgung GmbH", "Alter Postweg 101", "86159 Augsburg / Germany",
                        "Tel. +49 (0) 821 570451-0", "sales@eps-germany.de", "www.eps-germany.de"]),
}

_fonts_ok = False


def _fonts():
    global _fonts_ok
    if _fonts_ok:
        return
    fd = pfade.ASSETS / "fonts"
    pdfmetrics.registerFont(TTFont("EPS", str(fd / "Carlito-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("EPS-B", str(fd / "Carlito-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("EPS-I", str(fd / "Carlito-Italic.ttf")))
    addMapping("EPS", 0, 0, "EPS"); addMapping("EPS", 1, 0, "EPS-B")
    addMapping("EPS", 0, 1, "EPS-I"); addMapping("EPS", 1, 1, "EPS-B")
    _fonts_ok = True


def _st(name, **kw):
    base = dict(fontName="EPS", fontSize=9.4, leading=12.6, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


def _p(text, style):
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _section(title, width):
    t = Table([[Paragraph(escape(title), _st("sec", fontName="EPS-B", fontSize=10.5, leading=13.5, textColor=NAVY))]],
              colWidths=[width])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("LINEBELOW", (0, 0), (-1, -1), 1.2, CYAN)]))
    return t


def _kv(rows, width, label_w):
    sl = _st("l", fontSize=8.2, leading=10, textColor=GREY)
    sv = _st("v", fontSize=8.2, leading=10)
    t = Table([[_p(a, sl), _p(b, sv)] for a, b in rows], colWidths=[label_w, width - label_w])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _bild(path: Path, max_w: float, max_h: float):
    iw, ih = PILImage.open(path).size
    s = min(max_w / iw, max_h / ih)
    return Image(str(path), width=iw * s, height=ih * s)


def _kern_sidebar(ds: Datensatz, kat: K.Katalog, sprache: str) -> list[tuple[str, str]]:
    """Belegte Kernfelder für die Seitenleiste. „Nein“-Werte werden dort weggelassen (stehen in der Tabelle)."""
    out = []
    for f in kat.kernfelder:
        if f.id in ("bestellnummer", "optionen"):
            continue
        w = ds.werte.get(f.id)
        if f.typ == K.JA_NEIN and w is not None and w.ja is False:
            continue
        if f.id == "schnittstellen":
            t = darstellung.schnittstellen_kurz(ds, kat, sprache)
        else:
            t = darstellung.text(ds, f, kat, sprache)
        if t:
            out.append((f.label(sprache), t))
    return out


def erzeugen(ds: Datensatz, kat: K.Katalog, ziel: Path, sprache: str, bild_dir: Path | None = None) -> Path:
    _fonts()
    tx = T[sprache]
    SB = 6.0 * cm
    M = 1.2 * cm
    MX = SB + 0.8 * cm
    W = A4W - MX - M
    W2 = A4W - 2 * M
    titel = ds.titel or "—"
    nr = ds.bestellnummer
    kern = _kern_sidebar(ds, kat, sprache)
    logo = pfade.ASSETS / "logo.jpg"

    def page1(c, doc):
        c.saveState()
        c.setFillColor(NAVY); c.rect(0, 0, SB, A4H, stroke=0, fill=1)
        c.setFillColor(colors.white); c.roundRect(0.6 * cm, A4H - 4.0 * cm, SB - 1.2 * cm, 3.2 * cm, 6, stroke=0, fill=1)
        lw = SB - 2.0 * cm
        c.drawImage(str(logo), 1.0 * cm, A4H - 3.8 * cm, lw, lw * 348 / 522)
        breite = SB - 1.4 * cm
        unten = 4.6 * cm                        # Platz für Bestellnummer + Kontakt
        # Schriftgröße so wählen, dass alle Kerndaten in die Seitenleiste passen
        for fs in (9.6, 9.0, 8.4, 7.8, 7.2):
            ls, lv = fs * 0.75, fs
            y = A4H - 5.25 * cm
            for lab, val in kern:
                y -= ls * 1.25 + len(simpleSplit(val, "EPS-B", lv, breite)) * lv * 1.2 + 3
            if y > unten + 2.2 * cm:
                break
        y = A4H - 5.0 * cm
        c.setFillColor(CYAN); c.setFont("EPS-B", 10); c.drawString(0.7 * cm, y, tx["kerndaten"])
        y -= 0.25 * cm
        for lab, val in kern:
            y -= ls * 1.25
            c.setFillColor(SIDE_LABEL); c.setFont("EPS", ls); c.drawString(0.7 * cm, y, lab)
            for line in simpleSplit(val, "EPS-B", lv, breite):
                y -= lv * 1.2
                c.setFillColor(colors.white); c.setFont("EPS-B", lv); c.drawString(0.7 * cm, y, line)
            y -= 3
        y = max(min(y - 0.8 * cm, A4H), unten + 1.4 * cm)
        if nr:
            c.setFillColor(CYAN); c.setFont("EPS-B", 10); c.drawString(0.7 * cm, y, tx["bestellnr"])
            c.setFillColor(colors.white); c.setFont("EPS-B", 18); c.drawString(0.7 * cm, y - 0.65 * cm, nr)
        c.setFont("EPS", 7.2); c.setFillColor(SIDE_SMALL)
        yy = 2.6 * cm
        for line in tx["kontakt"]:
            c.drawString(0.7 * cm, yy, line); yy -= 0.33 * cm
        c.setFillColor(GREY); c.setFont("EPS", 7)
        c.drawString(MX, 0.8 * cm, tx["fuss"])
        c.drawRightString(A4W - M, 0.8 * cm, f"{tx['seite']} {doc.page}")
        c.restoreState()

    def page2(c, doc):
        c.saveState()
        c.setFillColor(NAVY); c.rect(0, A4H - 1.5 * cm, A4W, 1.5 * cm, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont("EPS-B", 11)
        c.drawString(M, A4H - 0.95 * cm, f"{titel}  ·  {tx['techdaten']}")
        c.setFont("EPS", 9)
        if nr:
            c.drawRightString(A4W - M, A4H - 0.95 * cm, f"{tx['bestellnr'].capitalize()} {nr}")
        c.setFillColor(GREY); c.setFont("EPS", 7)
        c.drawString(M, 0.8 * cm, "EPS Stromversorgung GmbH · Alter Postweg 101 · 86159 Augsburg · www.eps-germany.de · " + tx["fuss"])
        c.drawRightString(A4W - M, 0.8 * cm, f"{tx['seite']} {doc.page}")
        c.restoreState()

    ziel.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(ziel), pagesize=A4, title=f"{titel} – {tx['datenblatt'].capitalize()}",
                          author="EPS Stromversorgung GmbH", subject=nr)
    f1 = Frame(MX, 1.3 * cm, W, A4H - 1.0 * cm - 1.3 * cm, leftPadding=0, rightPadding=0, topPadding=0)
    f2 = Frame(M, 1.3 * cm, W2, A4H - 2.0 * cm - 1.3 * cm, leftPadding=0, rightPadding=0, topPadding=0)
    doc.addPageTemplates([PageTemplate("p1", [f1], onPage=page1), PageTemplate("p2", [f2], onPage=page2)])

    s = [NextPageTemplate("p2")]
    serie = ds.text("serie", sprache)
    kopf = tx["datenblatt"] + (f" · {tx['serie']} {serie}" if serie else "")
    s.append(_p(kopf, _st("se", fontName="EPS-B", fontSize=9, textColor=CYAN, leading=11)))
    s.append(_p(titel, _st("ti", fontName="EPS-B", fontSize=23, leading=26, textColor=NAVY)))
    unter = [x for x in [ds.text("produkttyp", sprache),
                         darstellung.text(ds, kat.feld("geraetetyp"), kat, sprache) if kat.hat("geraetetyp") else ""] if x]
    if unter:
        s.append(_p(" · ".join(unter), _st("su", fontSize=11, textColor=GREY, leading=14)))
    s.append(Spacer(1, 6))

    bilder = [b for b in ds.bilder if bild_dir and (bild_dir / b.datei).exists()]
    if bilder:
        s.append(_bild(bild_dir / bilder[0].datei, W, 4.2 * cm))
        cap = bilder[0].en if sprache == "en" else bilder[0].de
        if cap:
            s.append(_p(cap, _st("cap", fontSize=7.5, textColor=GREY, alignment=TA_CENTER)))
        s.append(Spacer(1, 8))

    beschr = ds.text("beschreibung", sprache)
    for absatz in [a for a in beschr.split("\n\n") if a.strip()]:
        s.append(_p(absatz.strip(), _st("d", fontSize=8.8, leading=11.6, spaceAfter=4)))

    lief = [(e.en or e.de) if sprache == "en" else e.de for e in ds.lieferumfang]
    lief = [x for x in lief if x.strip()]
    if lief:
        s.append(_section(tx["lieferumfang"], W))
        half = (len(lief) + 1) // 2
        sl = _st("li", fontSize=8.4, leading=10.6)
        a, b = lief[:half], lief[half:] + [""] * (half - len(lief[half:]))
        lt = Table([[_p("– " + x, sl), _p(("– " + y) if y else "", sl)] for x, y in zip(a, b)], colWidths=[W / 2, W / 2])
        lt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        s.append(lt)
        s.append(Spacer(1, 6))

    opts = [o for o in ds.optionen if (o.code or o.de or o.en)]
    if opts:
        s.append(_section(tx["optionen"], W))
        so = _st("o", fontSize=8.4, leading=10.6)
        sob = _st("ob", fontName="EPS-B", fontSize=8.4, leading=10.6, textColor=NAVY)
        rows = []
        for o in opts:
            besch = (o.en or o.de) if sprache == "en" else o.de
            nrtxt = f"Option {o.nr}  " if o.nr else ""
            rows.append([_p(nrtxt + o.code, sob), _p(besch, so)])
        ot = Table(rows, colWidths=[4.0 * cm, W - 4.0 * cm])
        ot.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        s.append(ot)

    s.append(PageBreak())
    cw = (W2 - 0.6 * cm) / 2
    allg = darstellung.zeilen(ds, kat, K.ALLG, sprache)
    tech = darstellung.zeilen(ds, kat, K.TECH, sprache)
    schn = darstellung.zeilen(ds, kat, K.SCHN, sprache)
    col1, col2 = [], []
    if allg:
        col1 += [_section(K.ABSCHNITT_EN[K.ALLG] if sprache == "en" else K.ALLG, cw), _kv(allg, cw, 4.0 * cm)]
    if tech:
        col2 += [_section(K.ABSCHNITT_EN[K.TECH] if sprache == "en" else K.TECH, cw), _kv(tech, cw, 3.7 * cm), Spacer(1, 6)]
    if schn:
        col2 += [_section(K.ABSCHNITT_EN[K.SCHN] if sprache == "en" else K.SCHN, cw), _kv(schn, cw, 3.7 * cm)]
    for b in bilder[1:3]:
        cap = b.en if sprache == "en" else b.de
        col2 += [Spacer(1, 10), _bild(bild_dir / b.datei, cw, 4.5 * cm)]
        if cap:
            col2.append(_p(cap, _st("cap", fontSize=7.5, textColor=GREY, alignment=TA_CENTER)))
    if col1 or col2:
        t = Table([[col1 or [Spacer(1, 1)], col2 or [Spacer(1, 1)]]], colWidths=[cw + 0.6 * cm, cw])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (0, 0), 0.6 * cm), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
        s.append(t)
    doc.build(s)
    return ziel


def beide(ds: Datensatz, kat: K.Katalog, ordner: Path, bild_dir: Path | None = None) -> list[Path]:
    nr = ds.bestellnummer or ds.id
    return [erzeugen(ds, kat, ordner / regeln.dateiname(nr, sp), sp, bild_dir) for sp in ("de", "en")]
