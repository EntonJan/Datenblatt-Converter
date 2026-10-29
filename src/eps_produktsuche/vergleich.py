"""Gegenüberstellung als PDF: Kundengerät (bzw. Anforderung) neben bis zu vier EPS-Vorschlägen – für Angebote.

Kundentauglich: keine internen Bewertungen wie „knapp darunter“, sondern „Lösung“ (1 Gerät / n Geräte parallel) und
die Reserve gegenüber der Anforderung. Angaben laut Shop bzw. Kunden-Datenblatt, ohne Gewähr.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import suche as Q

NAVY = colors.HexColor("#35528C")
CYAN = colors.HexColor("#52B4D7")
INK = colors.HexColor("#1C2633")
GREY = colors.HexColor("#6A7380")
LINE = colors.HexColor("#D5DCE6")
TINT = colors.HexColor("#EEF4FA")
MAX_VORSCHLAEGE = 4

T = {
    "de": {"titel": "Gegenüberstellung", "alternative": "EPS-Alternativen zu", "anforderung": "Anforderung",
           "kunde": "Ihr Gerät", "vorschlag": "EPS-Vorschlag", "bezeichnung": "Bezeichnung", "bestellnr": "Bestellnummer",
           "typ": "Gerätetyp", "spannung": "Spannung", "strom": "Strom", "leistung": "Leistung", "bauform": "Bauform",
           "merkmale": "Merkmale", "loesung": "Lösung", "reserve": "Reserve", "datenblatt": "Datenblatt",
           "ein_geraet": "1 Gerät", "parallel": "{n} Geräte parallel", "reihe": "{n} Geräte in Reihe",
           "auf_anfrage": "Systemlösung auf Anfrage", "hinweis": "Angaben laut Datenblatt bzw. EPS-Onlineshop, ohne Gewähr. "
           "Maßgeblich ist das jeweilige Datenblatt. Gerne beraten wir Sie zur passenden Konfiguration.",
           "stand": "Stand", "bidirektional": "bidirektional", "rueckspeisung": "Netzrückspeisung",
           "wasser": "wassergekühlt", "wasser_option": "Wasserkühlung optional", "link": "PDF öffnen"},
    "en": {"titel": "Comparison", "alternative": "EPS alternatives to", "anforderung": "Requirement",
           "kunde": "Your device", "vorschlag": "EPS proposal", "bezeichnung": "Model", "bestellnr": "Order no.",
           "typ": "Device type", "spannung": "Voltage", "strom": "Current", "leistung": "Power", "bauform": "Design",
           "merkmale": "Features", "loesung": "Solution", "reserve": "Headroom", "datenblatt": "Datasheet",
           "ein_geraet": "1 unit", "parallel": "{n} units in parallel", "reihe": "{n} units in series",
           "auf_anfrage": "System solution on request", "hinweis": "Data according to datasheet or EPS online shop, "
           "without guarantee. The respective datasheet is binding. We will gladly advise you on the right configuration.",
           "stand": "Date", "bidirektional": "bidirectional", "rueckspeisung": "mains regeneration",
           "wasser": "water-cooled", "wasser_option": "water cooling optional", "link": "open PDF"},
}
TYP_EN = {"Elektronische Last": "Electronic load", "Ladegeräte": "Charger"}
BAUFORM_EN = {"19 Zoll": "19 inch", "Schrank/Cabinet": "Cabinet", "Einbau/Built-in": "Built-in", "Desktop": "Desktop",
              "Tower": "Tower", "DIN Rail": "DIN rail"}


def _ressource(*teile: str) -> Path:
    basis = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return basis.joinpath("assets", *teile)


_SCHRIFT = None


def _schrift() -> tuple[str, str]:
    global _SCHRIFT
    if _SCHRIFT is None:
        try:
            pdfmetrics.registerFont(TTFont("EPS", str(_ressource("fonts", "Carlito-Regular.ttf"))))
            pdfmetrics.registerFont(TTFont("EPS-B", str(_ressource("fonts", "Carlito-Bold.ttf"))))
            _SCHRIFT = ("EPS", "EPS-B")
        except Exception:  # noqa: BLE001 – Schrift fehlt → Standardschrift
            _SCHRIFT = ("Helvetica", "Helvetica-Bold")
    return _SCHRIFT


def _x(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _merkmale_geraet(g, sp: str) -> str:
    t = T[sp]
    teile = []
    if g.bidirektional:
        teile.append(t["bidirektional"])
    if getattr(g, "rueckspeisung", False) or re.search(r"rückspeis|regenerativ", g.name, re.I):
        teile.append(t["rueckspeisung"])
    w = getattr(g, "wasser", "")
    if w == "ja":
        teile.append(t["wasser"])
    elif w == "option":
        teile.append(t["wasser_option"])
    f = [Q.zahl_text(x, "Hz") for x in getattr(g, "f_fest", [])] + \
        [f"{Q.zahl_text(a, 'Hz').split()[0]}–{Q.zahl_text(b, 'Hz')}" for a, b in getattr(g, "f_bereiche", [])]
    if f:
        teile.append(" / ".join(f))
    return ", ".join(teile) or "–"


def _loesung(tr, sp: str, kunde: bool) -> str:
    t = T[sp]
    if tr.kategorie == Q.PARALLEL:
        return t["parallel"].format(n=tr.anzahl) if not kunde else t["auf_anfrage"] + f" ({t['parallel'].format(n=tr.anzahl)})"
    if tr.kategorie == Q.REIHE:
        return t["reihe"].format(n=tr.anzahl)
    return t["ein_geraet"]


def erzeugen(ziel: Path, treffer: list, anfrage: Q.Anfrage, fremd=None, sprache: str = "de") -> Path:
    """Schreibt die Gegenüberstellung nach ziel (PDF) und gibt den Pfad zurück."""
    sp = "en" if sprache == "en" else "de"
    t = T[sp]
    normal, fett = _schrift()
    st = lambda n, **k: ParagraphStyle(n, fontName=k.pop("f", normal), fontSize=k.pop("s", 9), leading=k.pop("l", 11.5),  # noqa: E731
                                       textColor=k.pop("c", INK), **k)
    z, zb, kopf = st("z"), st("zb", f=fett), st("k", f=fett, c=colors.white)
    treffer = list(treffer)[:MAX_VORSCHLAEGE]
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(str(ziel), pagesize=landscape(A4), leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                            topMargin=1.3 * cm, bottomMargin=1.4 * cm, title=t["titel"], author="EPS Stromversorgung GmbH")
    breite = landscape(A4)[0] - 3.2 * cm
    elemente = []
    logo = _ressource("logo.jpg")
    titel_zeile = [Paragraph(t["titel"], st("h", f=fett, s=20, l=24, c=NAVY)),
                   Image(str(logo), width=2.4 * cm, height=1.6 * cm) if logo.exists() else ""]
    kopf_tab = Table([titel_zeile], colWidths=[breite - 2.6 * cm, 2.6 * cm])
    kopf_tab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    elemente.append(kopf_tab)
    name_kunde = (fremd.hersteller_typ or fremd.modell or fremd.datei) if fremd else ""
    unter = f"{t['alternative']} {name_kunde}" if name_kunde else f"{t['anforderung']}: {anfrage.text.strip()}"
    elemente += [Paragraph(_x(unter), st("u", s=11, l=14, c=GREY)),
                 Paragraph(f"{t['stand']}: {date.today().strftime('%d.%m.%Y')}", st("d", s=8.5, c=GREY)), Spacer(1, 8)]

    # Spalte 1: Kundengerät oder Anforderung
    if fremd:
        mk = list(fremd.merkmale)
        bauform_k = "19 Zoll" if "19Zoll" in mk else ""
        anzeige = {"bidirektional": t["bidirektional"], "Rückspeisung": t["rueckspeisung"], "wassergekühlt": t["wasser"]}
        mk_text = ", ".join(anzeige.get(m, re.sub(r"(\d)Hz$", r"\1 Hz", m)) for m in mk if m != "19Zoll")
        sp1 = {"kopf": t["kunde"], "bezeichnung": name_kunde, "bestellnr": "–",
               "typ": ", ".join(TYP_EN.get(x, x) if sp == "en" else x for x in fremd.geraetetyp) or "–",
               "spannung": fremd.spannung or Q.zahl_text(fremd.umax, "V"), "strom": fremd.strom or Q.zahl_text(fremd.imax, "A"),
               "leistung": fremd.leistung or Q.zahl_text(fremd.pmax, "W"),
               "bauform": (BAUFORM_EN.get(bauform_k, bauform_k) if sp == "en" else bauform_k) or "–",
               "merkmale": mk_text or "–", "loesung": "", "reserve": "", "datenblatt": fremd.datei}
    else:
        sp1 = {"kopf": t["anforderung"], "bezeichnung": "–", "bestellnr": "–",
               "typ": (TYP_EN.get(anfrage.geraetetyp, anfrage.geraetetyp) if sp == "en" else anfrage.geraetetyp) or "–",
               "spannung": Q.zahl_text(anfrage.spannung, "V") if anfrage.spannung else "–",
               "strom": Q.zahl_text(anfrage.strom, "A") if anfrage.strom else "–",
               "leistung": Q.zahl_text(anfrage.leistung_bedarf, "W") if anfrage.leistung_bedarf else "–",
               "bauform": (BAUFORM_EN.get(anfrage.bauform, anfrage.bauform) if sp == "en" else anfrage.bauform) or "–",
               "merkmale": ", ".join(x for x in (t["bidirektional"] if anfrage.bidirektional else "",
                                                 t["rueckspeisung"] if anfrage.rueckspeisung else "",
                                                 t["wasser"] if anfrage.wasser else "",
                                                 " / ".join(Q.zahl_text(f, "Hz") for f in anfrage.frequenzen)) if x) or "–",
               "loesung": "", "reserve": "", "datenblatt": ""}
    spalten = [sp1]
    for tr in treffer:
        g = tr.g
        spalten.append({
            "kopf": f"{t['vorschlag']} {len(spalten)}" if len(treffer) > 1 else t["vorschlag"],
            "bezeichnung": g.name, "bestellnr": g.bestellnummer,
            "typ": (TYP_EN.get(g.geraetetyp, g.geraetetyp) if sp == "en" else g.geraetetyp)
                   + (f" ({t['bidirektional']})" if g.bidirektional and g.geraetetyp != "Elektronische Last" else ""),
            "spannung": g.spannung or "–", "strom": g.strom or "–", "leistung": g.leistung or "–",
            "bauform": (BAUFORM_EN.get(g.bauart, g.bauart) if sp == "en" else g.bauart) or "–",
            "merkmale": _merkmale_geraet(g, sp), "loesung": _loesung(tr, sp, kunde=True), "reserve": tr.reserve_text(),
            "datenblatt": f'<link href="{_x(g.pdf_url)}" color="#35528C"><u>{t["link"]}</u></link>' if g.pdf_url else "–",
        })
    zeilen = ["bezeichnung", "bestellnr", "typ", "spannung", "strom", "leistung", "bauform", "merkmale", "loesung",
              "reserve", "datenblatt"]
    erste = 3.4 * cm
    rest = (breite - erste) / len(spalten)
    daten = [[Paragraph("", kopf)] + [Paragraph(_x(s["kopf"]), kopf) for s in spalten]]
    for k in zeilen:
        reihe = [Paragraph(t[k], zb)]
        for i, s in enumerate(spalten):
            inhalt = s.get(k, "") or ("" if i == 0 and k in ("loesung", "reserve") else "–")
            reihe.append(Paragraph(inhalt if k == "datenblatt" and i else _x(inhalt), zb if k == "bezeichnung" else z))
        daten.append(reihe)
    tab = Table(daten, colWidths=[erste] + [rest] * len(spalten), repeatRows=1)
    stil = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("BACKGROUND", (1, 0), (1, 0), GREY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (1, 1), (1, -1), TINT), ("LINEAFTER", (1, 0), (1, -1), 1.2, CYAN)]
    tab.setStyle(TableStyle(stil))
    elemente += [tab, Spacer(1, 10), Paragraph(t["hinweis"], st("f", s=8, l=10, c=GREY)),
                 Paragraph("EPS Stromversorgung GmbH · www.eps-germany.de", st("f2", s=8, l=10, c=GREY))]
    doc.build(elemente)
    return ziel


def dateiname(fremd, anfrage: Q.Anfrage, sprache: str) -> str:
    basis = (fremd.hersteller_typ or fremd.modell or Path(fremd.datei).stem) if fremd else anfrage.text
    basis = re.sub(r"[^\w\-]+", "_", basis or "Anfrage").strip("_")[:50] or "Anfrage"
    return f"Gegenueberstellung_{basis}_{date.today().isoformat()}{'_EN' if sprache == 'en' else ''}.pdf"
