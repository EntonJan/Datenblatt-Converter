"""EPS-Datenblatt als PDF, Deutsch und Englisch, in drei Layouts:
A = Klassisch (Banner, Kerndaten-Kasten, 2 Seiten) · B = Kompakt (eine Seite, Kennzahl-Kacheln) · C = Seitenleiste (Standard).

Leere Felder werden ausgeblendet. Herstellerangaben (Hersteller, Original-Typ, Hersteller-Nr.)
erscheinen nie auf dem Datenblatt.
"""
from __future__ import annotations

import io
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
                                Paragraph, Spacer, Table, TableStyle, KeepTogether, CondPageBreak)
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
            out.append((darstellung.label(ds, f, kat, sprache), t))
    return out


LAYOUTS = {"A": "A – Klassisch", "B": "B – Kompakt (1 Seite)", "C": "C – Seitenleiste"}
STANDARD_LAYOUT = "C"


def erzeugen(ds: Datensatz, kat: K.Katalog, ziel: Path, sprache: str, bild_dir: Path | None = None,
             layout: str = STANDARD_LAYOUT) -> Path:
    if layout == "A":
        return _layout_a(ds, kat, ziel, sprache, bild_dir)
    if layout == "B":
        return _layout_b(ds, kat, ziel, sprache, bild_dir)
    return _layout_c(ds, kat, ziel, sprache, bild_dir)


def _layout_c(ds: Datensatz, kat: K.Katalog, ziel: Path, sprache: str, bild_dir: Path | None = None) -> Path:
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

    def bauen(ausgabe, kompakt: bool) -> int:
        """Baut das Datenblatt; liefert die Seitenzahl."""
        doc = BaseDocTemplate(ausgabe, pagesize=A4, title=f"{titel} – {tx['datenblatt'].capitalize()}",
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

        allg = darstellung.zeilen(ds, kat, K.ALLG, sprache)
        tech = darstellung.zeilen(ds, kat, K.TECH, sprache)
        schn = darstellung.zeilen(ds, kat, K.SCHN, sprache)

        # Wenig Inhalt auf Seite 1 (kein Bild, kurze/keine Beschreibung) → Technische Daten direkt
        # anschließen statt einer fast leeren ersten Seite. Überlauf geht auf die Folgeseite.
        if kompakt:
            s.append(Spacer(1, 4))
            for titel_abschnitt, zeilen in ((K.ALLG, allg), (K.TECH, tech), (K.SCHN, schn)):
                if zeilen:
                    kopf_t = K.ABSCHNITT_EN[titel_abschnitt] if sprache == "en" else titel_abschnitt
                    s += [_section(kopf_t, W), _kv(zeilen, W, 5.0 * cm), Spacer(1, 8)]
            for b in bilder[1:3]:
                cap = b.en if sprache == "en" else b.de
                s += [Spacer(1, 6), _bild(bild_dir / b.datei, W, 4.5 * cm)]
                if cap:
                    s.append(_p(cap, _st("cap", fontSize=7.5, textColor=GREY, alignment=TA_CENTER)))
            doc.build(s)
            return doc.page

        s.append(PageBreak())
        cw = (W2 - 0.6 * cm) / 2
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
        return doc.page

    # Erst einseitig versuchen (technische Daten direkt unter Bild/Beschreibung). Nur wenn das nicht
    # auf eine Seite passt, das zweispaltige Layout mit eigener Seite für die technischen Daten.
    puffer = io.BytesIO()
    if bauen(puffer, kompakt=True) == 1:
        ziel.write_bytes(puffer.getvalue())
    else:
        bauen(str(ziel), kompakt=False)
    return ziel


def beide(ds: Datensatz, kat: K.Katalog, ordner: Path, bild_dir: Path | None = None,
          layout: str = STANDARD_LAYOUT) -> list[Path]:
    nr = ds.bestellnummer or ds.id
    return [erzeugen(ds, kat, ordner / regeln.dateiname(nr, sp), sp, bild_dir, layout) for sp in ("de", "en")]


# ======================================================================== gemeinsame Bausteine für A und B

TX2 = {
    "de": dict(kerndaten="Kerndaten auf einen Blick", forts="(Forts.)", optnr="Opt.-Nr.", code="Code",
               beschreibung="Beschreibung", bestellnummer="Bestellnummer", datenblatt="Datenblatt", serie="Serie",
               stand="Stand"),
    "en": dict(kerndaten="Key data at a glance", forts="(cont.)", optnr="Opt. no.", code="Code",
               beschreibung="Description", bestellnummer="Order code", datenblatt="Datasheet", serie="Series",
               stand="Issued"),
}
TINT = colors.HexColor("#EEF4FA")
TINT2 = colors.HexColor("#E3F1F8")
DARK = colors.HexColor("#0B1A2E")


def _inhalt(ds: Datensatz, kat: K.Katalog, sprache: str, bild_dir: Path | None) -> dict:
    """Alles, was die Layouts brauchen – einmal zusammengestellt."""
    abschnitt = lambda a: K.ABSCHNITT_EN[a] if sprache == "en" else a      # noqa: E731
    beschr = ds.text("beschreibung", sprache)
    return dict(
        titel=ds.titel or "—", nr=ds.bestellnummer, serie=ds.text("serie", sprache),
        unter=[x for x in [ds.text("produkttyp", sprache),
                           darstellung.text(ds, kat.feld("geraetetyp"), kat, sprache) if kat.hat("geraetetyp") else ""] if x],
        kern=_kern_sidebar(ds, kat, sprache),
        allg=(abschnitt(K.ALLG), darstellung.zeilen(ds, kat, K.ALLG, sprache)),
        tech=(abschnitt(K.TECH), darstellung.zeilen(ds, kat, K.TECH, sprache)),
        schn=(abschnitt(K.SCHN), darstellung.zeilen(ds, kat, K.SCHN, sprache)),
        absaetze=[a.strip() for a in beschr.split("\n\n") if a.strip()],
        lief=[x for x in [((e.en or e.de) if sprache == "en" else e.de) for e in ds.lieferumfang] if x.strip()],
        opts=[(o.nr, o.code, (o.en or o.de) if sprache == "en" else o.de) for o in ds.optionen if (o.code or o.de or o.en)],
        bilder=[(bild_dir / b.datei, (b.en or b.de) if sprache == "en" else b.de)
                for b in ds.bilder if bild_dir and (bild_dir / b.datei).exists()],
    )


def _kv_zebra(rows, width, label_w, fs=8.2, lead=10.2, pad=2.4, zebra=TINT, label_color=GREY):
    sl = _st("lz", fontSize=fs, leading=lead, textColor=label_color)
    sv = _st("vz", fontSize=fs, leading=lead)
    t = Table([[_p(a, sl), _p(b, sv)] for a, b in rows], colWidths=[label_w, width - label_w])
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), pad),
          ("BOTTOMPADDING", (0, 0), (-1, -1), pad), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if zebra is not None:
        st += [("BACKGROUND", (0, i), (-1, i), zebra) for i in range(0, len(rows), 2)]
    else:
        st.append(("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE))
    t.setStyle(TableStyle(st))
    return t


def _sec(title, width, fs=10.5):
    t = Table([[Paragraph(escape(title), _st("secx", fontName="EPS-B", fontSize=fs, leading=fs + 3, textColor=NAVY))]],
              colWidths=[width])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 1.2, CYAN)]))
    return t


def _optionen_tabelle(opts, width, sprache, fs=8.0):
    tx = TX2[sprache]
    so = _st("ot", fontSize=fs, leading=fs + 1.8)
    sob = _st("otb", fontName="EPS-B", fontSize=fs, leading=fs + 1.8, textColor=NAVY)
    zeilen = [[_p(tx["optnr"], sob), _p(tx["code"], sob), _p(tx["beschreibung"], sob)]]
    zeilen += [[_p(nr or "–", so), _p(code, sob), _p(text, so)] for nr, code, text in opts]
    t = Table(zeilen, colWidths=[1.4 * cm, 3.2 * cm, width - 4.6 * cm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _zweispaltig(links, rechts, breite, abstand):
    t = Table([[links or [Spacer(1, 1)], rechts or [Spacer(1, 1)]]], colWidths=[breite + abstand, breite])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (0, 0), abstand), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    return t


# ======================================================================== Layout A – Klassisch

def _layout_a(ds: Datensatz, kat: K.Katalog, ziel: Path, sprache: str, bild_dir: Path | None = None) -> Path:
    _fonts()
    tx, tx2 = T[sprache], TX2[sprache]
    d = _inhalt(ds, kat, sprache, bild_dir)
    M = 1.6 * cm
    W = A4W - 2 * M
    banner = pfade.ASSETS / "banner.jpg"
    bh = W * 525 / 3132
    fuss1 = " · ".join(tx["kontakt"])

    def seite(c, doc):
        c.saveState()
        if doc.page == 1:
            c.drawImage(str(banner), M, A4H - 1.0 * cm - bh, W, bh)
        else:
            c.setFillColor(NAVY); c.setFont("EPS-B", 9)
            c.drawString(M, A4H - 1.3 * cm, f"{tx2['datenblatt']} · {d['titel']}")
            c.setFont("EPS", 9); c.setFillColor(GREY)
            if d["nr"]:
                c.drawRightString(A4W - M, A4H - 1.3 * cm, f"{tx2['bestellnummer']} {d['nr']}")
            c.setStrokeColor(CYAN); c.setLineWidth(1.2)
            c.line(M, A4H - 1.45 * cm, A4W - M, A4H - 1.45 * cm)
        c.setStrokeColor(LINE); c.setLineWidth(0.5)
        c.line(M, 1.45 * cm, A4W - M, 1.45 * cm)
        c.setFont("EPS", 7); c.setFillColor(GREY)
        c.drawString(M, 1.1 * cm, fuss1)
        c.drawString(M, 0.78 * cm, tx["fuss"])
        c.drawRightString(A4W - M, 0.78 * cm, f"{tx['seite']} {doc.page}")
        c.restoreState()

    ziel.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(ziel), pagesize=A4, title=f"{d['titel']} – {tx['datenblatt'].capitalize()}",
                          author="EPS Stromversorgung GmbH", subject=d["nr"])
    f1 = Frame(M, 1.8 * cm, W, A4H - 1.0 * cm - bh - 0.3 * cm - 1.8 * cm, leftPadding=0, rightPadding=0, topPadding=0)
    f2 = Frame(M, 1.8 * cm, W, A4H - 1.8 * cm - 1.8 * cm, leftPadding=0, rightPadding=0, topPadding=0)
    doc.addPageTemplates([PageTemplate("p1", [f1], onPage=seite), PageTemplate("p2", [f2], onPage=seite)])

    s = [NextPageTemplate("p2")]
    if d["serie"]:
        s.append(_p(f"{tx2['serie']} {d['serie']}", _st("aS", fontName="EPS-B", fontSize=10, textColor=CYAN, leading=12)))
    s.append(_p(d["titel"], _st("aT", fontName="EPS-B", fontSize=23, leading=26, textColor=NAVY)))
    unter = d["unter"] + ([f"{tx2['bestellnummer']} {d['nr']}"] if d["nr"] else [])
    if unter:
        s.append(_p(" · ".join(unter), _st("aU", fontSize=10.5, textColor=GREY, leading=14)))
    s.append(Spacer(1, 8))

    lw = W * 0.48
    rw = W - lw - 0.5 * cm
    links = [_bild(d["bilder"][0][0], lw, 6.5 * cm)] if d["bilder"] else []
    rechts = []
    if d["kern"]:
        rechts += [_sec(tx2["kerndaten"], rw), _kv_zebra(d["kern"], rw, 3.3 * cm, fs=8.4, lead=10.4, pad=2.6,
                                                          zebra=TINT2, label_color=NAVY)]
    if links or rechts:
        s.append(_zweispaltig(links, rechts, lw, 0.5 * cm) if links else rechts[0])
        if not links:
            s += rechts[1:]
    s.append(Spacer(1, 8))
    s += [_p(a, _st("aD", fontSize=9, leading=12.2, spaceAfter=5)) for a in d["absaetze"]]
    if d["lief"]:
        half = (len(d["lief"]) + 1) // 2
        sl = _st("aL", fontSize=8.4, leading=10.6)
        a_, b_ = d["lief"][:half], d["lief"][half:] + [""] * (half - len(d["lief"][half:]))
        lt = Table([[_p("– " + x, sl), _p(("– " + y) if y else "", sl)] for x, y in zip(a_, b_)], colWidths=[W / 2, W / 2])
        lt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        s.append(KeepTogether([_sec(tx["lieferumfang"], W), lt]))
    s.append(CondPageBreak(A4H * 0.55))             # Tabellen auf eine neue Seite – außer es ist dort ohnehin noch Platz

    cw = (W - 0.6 * cm) / 2
    sp1, sp2 = [], []
    if d["allg"][1]:
        sp1 += [_sec(d["allg"][0], cw), _kv_zebra(d["allg"][1], cw, 3.9 * cm, fs=7.9, lead=9.6, pad=2)]
    for titel, zeilen in (d["tech"], d["schn"]):
        if zeilen:
            sp2 += [_sec(titel, cw), _kv_zebra(zeilen, cw, 3.6 * cm, fs=7.9, lead=9.6, pad=2), Spacer(1, 4)]
    if d["opts"]:
        sp2 += [_sec(tx["optionen"], cw), _optionen_tabelle(d["opts"], cw, sprache, fs=7.9)]
    s.append(_zweispaltig(sp1, sp2, cw, 0.6 * cm))
    weitere = d["bilder"][1:4]
    if weitere:
        s.append(Spacer(1, 10))
        iw = (W - 0.6 * cm) / 3
        zellen = []
        for pfad, cap in weitere:
            z = [_bild(pfad, iw, 2.4 * cm)]
            if cap:
                z.append(_p(cap, _st("aC", fontSize=7.5, textColor=GREY, alignment=TA_CENTER)))
            zellen.append(z)
        zellen += [[Spacer(1, 1)]] * (3 - len(zellen))
        pt = Table([zellen], colWidths=[iw + 0.3 * cm, iw + 0.3 * cm, iw])
        pt.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        s.append(KeepTogether(pt))
    doc.build(s)
    return ziel


# ======================================================================== Layout B – Kompakt (1 Seite)

KACHEL_FELDER = ["ausgangsspannung", "ausgangsstrom", "ausgangsleistung", "eingangsspannung", "netzspannung",
                 "ausgangsfrequenz", "bauform"]


def _layout_b(ds: Datensatz, kat: K.Katalog, ziel: Path, sprache: str, bild_dir: Path | None = None) -> Path:
    _fonts()
    tx, tx2 = T[sprache], TX2[sprache]
    d = _inhalt(ds, kat, sprache, bild_dir)
    M = 1.2 * cm
    W = A4W - 2 * M
    HB = 2.0 * cm
    fuss1 = " · ".join(tx["kontakt"])
    band = None
    try:                                            # Kopfband: rechter Ausschnitt aus dem EPS-Banner
        ban = PILImage.open(pfade.ASSETS / "banner.jpg")
        bw, bhh = ban.size
        x0 = int(bw * 0.367)
        ausschnitt = ban.crop((x0, int(bhh * 0.076), bw, int(bhh * 0.076) + int((bw - x0) * HB / A4W)))
        puffer = io.BytesIO(); ausschnitt.convert("RGB").save(puffer, "JPEG", quality=92); puffer.seek(0)
        from reportlab.lib.utils import ImageReader
        band = ImageReader(puffer)
    except Exception:
        band = None

    def seite(c, doc):
        c.saveState()
        if band is not None:
            c.drawImage(band, 0, A4H - HB, A4W, HB)
        else:
            c.setFillColor(NAVY); c.rect(0, A4H - HB, A4W, HB, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont("EPS-B", 15)
        c.drawString(M, A4H - 1.05 * cm, tx2["datenblatt"])
        if d["serie"]:
            c.setFont("EPS", 9.5); c.setFillColor(colors.HexColor("#BFD9EA"))
            c.drawString(M, A4H - 1.55 * cm, f"{tx2['serie']} {d['serie']}")
        c.setFillColor(DARK); c.rect(0, 0, A4W, 1.05 * cm, stroke=0, fill=1)
        c.setFont("EPS", 6.8); c.setFillColor(colors.HexColor("#C9D6E3"))
        c.drawString(M, 0.62 * cm, fuss1)
        c.drawString(M, 0.32 * cm, tx["fuss"])
        c.drawRightString(A4W - M, 0.32 * cm, f"{tx['seite']} {doc.page}")
        c.restoreState()

    ziel.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(ziel), pagesize=A4, title=f"{d['titel']} – {tx['datenblatt'].capitalize()}",
                          author="EPS Stromversorgung GmbH", subject=d["nr"])
    fr = Frame(M, 1.35 * cm, W, A4H - HB - 0.35 * cm - 1.35 * cm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate("p", [fr], onPage=seite)])
    s = []
    tl = Paragraph(f'<font name="EPS-B" size="19" color="#35528C">{escape(d["titel"])}</font>'
                   + (f'<br/><font size="9.5" color="#6A7380">{escape(" · ".join(d["unter"]))}</font>' if d["unter"] else ""),
                   _st("bT", leading=21))
    tr = Paragraph((f'<font size="8" color="#6A7380">{tx2["bestellnummer"]}</font><br/>'
                    f'<font name="EPS-B" size="17" color="#35528C">{escape(d["nr"])}</font>') if d["nr"] else "",
                   _st("bR", alignment=2, leading=19))
    tt = Table([[tl, tr]], colWidths=[W * 0.7, W * 0.3])
    tt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("LINEBELOW", (0, 0), (-1, -1), 1.2, CYAN),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    s += [tt, Spacer(1, 6)]

    # Kennzahl-Kacheln aus den Kernfeldern
    kacheln = []
    for fid in KACHEL_FELDER:
        if kat.hat(fid) and len(kacheln) < 4:
            t = darstellung.text(ds, kat.feld(fid), kat, sprache)
            if t:
                kacheln.append((darstellung.label(ds, kat.feld(fid), kat, sprache), t))
    iw = W * 0.40 if d["bilder"] else 0
    tw = W - iw - (0.4 * cm if iw else 0)
    kurz, laenge = [], 0
    for a in d["absaetze"]:                          # kompakt: nur so viel Beschreibung, wie neben das Bild passt
        if kurz and laenge + len(a) > 700:
            break
        kurz.append(a); laenge += len(a)
    rechts = [_p(a, _st("bD", fontSize=8.1, leading=10.4, spaceAfter=4)) for a in kurz]
    if kacheln:
        n = len(kacheln)
        zellen = [Paragraph(f'<font size="6.8" color="#6A7380">{escape(l)}</font><br/>'
                            f'<font name="EPS-B" size="11.5" color="#35528C">{escape(v)}</font>', _st("bK", leading=13.5))
                  for l, v in kacheln]
        kt = Table([zellen], colWidths=[tw / n] * n)
        kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TINT2), ("LINEAFTER", (0, 0), (-2, -1), 2, colors.white),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
        rechts += [Spacer(1, 3), kt]
    if iw:
        oben = Table([[_bild(d["bilder"][0][0], iw, 5.2 * cm), rechts]], colWidths=[iw + 0.4 * cm, tw])
        oben.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        s.append(oben)
    else:
        s += rechts
    s.append(Spacer(1, 4))

    # Dreispaltiges Datenraster: alle Abschnitte nacheinander, gleichmäßig auf drei Spalten verteilt
    gap = 0.35 * cm
    cw = (W - 2 * gap) / 3
    kw = dict(fs=7.2, lead=8.7, pad=1.4)
    bloecke = [(t, z) for t, z in (d["allg"], d["tech"], d["schn"]) if z]

    def hoehe(zeile):                                # grobe Zeilenzahl (lange Werte brechen um)
        return 1 + len(zeile[1]) // 26 + len(zeile[0]) // 24
    gesamt = sum(sum(hoehe(z) for z in rows) + 2 for _, rows in bloecke)
    ziel_h = gesamt / 3
    spalten, akt, akt_h = [[]], [], 0.0
    for titel, rows in bloecke:
        teil, erster = [], True
        for z in rows:
            if akt_h >= ziel_h and len(spalten) < 3 and (teil or akt):
                if teil:
                    spalten[-1] += [_sec(titel if erster else f"{titel} {tx2['forts']}", cw, fs=9), _kv_zebra(teil, cw, 3.0 * cm, **kw)]
                    erster = False
                spalten.append([]); teil, akt_h = [], 0.0
            teil.append(z); akt_h += hoehe(z)
        if teil:
            spalten[-1] += [_sec(titel if erster else f"{titel} {tx2['forts']}", cw, fs=9), _kv_zebra(teil, cw, 3.0 * cm, **kw),
                            Spacer(1, 2)]
            akt_h += 2
    while len(spalten) < 3:
        spalten.append([])
    g = Table([[sp or [Spacer(1, 1)] for sp in spalten]], colWidths=[cw + gap, cw + gap, cw])
    g.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (1, 0), gap), ("RIGHTPADDING", (2, 0), (2, 0), 0)]))
    s += [g, Spacer(1, 3)]

    # Optionen + Lieferumfang nebeneinander
    if d["opts"] or d["lief"]:
        ow = W * 0.6 if d["lief"] else W
        teile, breiten = [], []
        if d["opts"]:
            so = _st("bO", fontSize=7.3, leading=9)
            ozeilen = [[Paragraph(f'<font name="EPS-B" color="#35528C">{escape(code)}</font>  {escape(text)}', so)]
                       for _, code, text in d["opts"]]
            ot = Table(ozeilen, colWidths=[ow - 0.3 * cm])
            ot.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            teile.append([_sec(tx["optionen"], ow - 0.3 * cm, fs=9), ot]); breiten.append(ow)
        if d["lief"]:
            lw2 = W - (ow if d["opts"] else 0)
            teile.append([_sec(tx["lieferumfang"], lw2, fs=9), _p(" · ".join(d["lief"]), _st("bL", fontSize=7.3, leading=9))])
            breiten.append(lw2)
        bt = Table([teile], colWidths=breiten)
        bt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        s.append(bt)
    doc.build(s)
    return ziel
