"""Anforderungsdokumente von Kunden (Word/PDF): Text, markierte Pflichtpunkte, Ausbaustufen, offene Punkte.

Kunden schicken neben Datenblättern auch Lastenhefte/Ausschreibungen („Technical Specification / Requirement“),
oft als Word-Tabelle. Gelb (bzw. farbig) markierte Stellen bedeuten: muss genau so erfüllt sein. Die Suche prüft
davon nur, was in den Shopdaten steht (Spannung, Strom, Leistung, Bauform, bidirektional, Rückspeisung,
Wasserkühlung, Ausgangsfrequenz). Alles andere wird am Ende als „offen – vor dem Angebot klären“ gemeldet.
"""
from __future__ import annotations

import html
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import allgemein

# Markierungen, die als „Pflicht“ zählen: Textmarker jeder Farbe und farbig hinterlegter Text (Schattierung)
_MARKER = re.compile(r'<w:highlight w:val="(?!none)\w+"|<w:shd [^>]*w:fill="(?!auto|FFFFFF|ffffff)[0-9A-Fa-f]{6}"')


@dataclass
class Dokument:
    text: str                                       # Fließtext, Tabellenzeilen als „Parameter: Anforderung“
    markiert: list[str] = field(default_factory=list)


def _xml_text(teil: str) -> str:
    teil = re.sub(r"<w:tab/>", " ", teil)
    teil = re.sub(r"<w:br/>", "\n", teil)
    return html.unescape("".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", teil)))


def _markierter_text(teil: str) -> str:
    """Nur die markierten Textläufe (w:r) – eine Zelle/ein Absatz kann teilweise markiert sein."""
    stuecke = []
    for lauf in re.findall(r"<w:r\b[^>]*>.*?</w:r>", teil, re.S):
        eigenschaften = re.search(r"<w:rPr>.*?</w:rPr>", lauf, re.S)
        if eigenschaften and _MARKER.search(eigenschaften.group(0)):
            stuecke.append(_xml_text(lauf))
    # ganze Zelle hinterlegt (Zellschattierung) zählt auch
    zelle = re.search(r"<w:tcPr>.*?</w:tcPr>", teil, re.S)
    if not stuecke and zelle and _MARKER.search(zelle.group(0)):
        return _xml_text(teil).strip()
    return re.sub(r"\s+", " ", "".join(stuecke)).strip()


def docx_lesen(pfad: Path) -> Dokument:
    """Word-Datei ohne Zusatzbibliothek lesen (document.xml). Tabellen werden zeilenweise zu „Spalte: Spalte“."""
    with zipfile.ZipFile(pfad) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    koerper = re.search(r"<w:body>(.*)</w:body>", xml, re.S)
    xml = koerper.group(1) if koerper else xml
    zeilen: list[str] = []
    markiert: list[str] = []
    xml = re.sub(r"<w:(p|r|tc|tr)\b[^>]*/>", "", xml)             # leere, selbstschließende Elemente
    for block in re.findall(r"<w:tbl>.*?</w:tbl>|<w:p\b[^>]*>.*?</w:p>", xml, re.S):
        if block.startswith("<w:tbl>"):
            for zeile in re.findall(r"<w:tr\b[^>]*>.*?</w:tr>", block, re.S):
                zellen = re.findall(r"<w:tc\b[^>]*>.*?</w:tc>", zeile, re.S)
                texte = [re.sub(r"\s+", " ", _xml_text(c)).strip() for c in zellen]
                marken = [_markierter_text(c) for c in zellen]
                # laufende Nummer („1“, „S. No.“) weglassen
                if texte and re.fullmatch(r"\d{1,3}\.?|s\.? ?no\.?|nr\.?|pos\.?", texte[0], re.I):
                    texte, marken = texte[1:], marken[1:]
                texte = [t for t in texte if t]
                if texte:
                    zeilen.append(": ".join(texte))
                if any(marken):
                    bezeichnung = texte[0] if texte else ""
                    rest = [m for m, t in zip(marken, texte) if m and t != bezeichnung] or \
                           [m for m in marken if m and m != bezeichnung]
                    if not rest:                                   # nur die Bezeichnung markiert → ganze Zeile
                        markiert.append(": ".join(texte))
                    elif len(texte) > 1:
                        voll = texte[-1]
                        teil = " … ".join(rest)
                        markiert.append(f"{bezeichnung}: {teil}" + ("" if teil == voll else f"  (aus: {voll})"))
                    else:
                        markiert.append(" … ".join(rest))
        else:
            t = re.sub(r"\s+", " ", _xml_text(block)).strip()
            if t:
                zeilen.append(t)
                m = _markierter_text(block)
                if m:
                    markiert.append(m if m == t else f"{m}  (aus: {t})")
    return Dokument("\n".join(zeilen), markiert)


def pdf_markierungen(pfad: Path, max_seiten: int = 10) -> list[str]:
    """Text unter Hervorhebungs-Anmerkungen (Textmarker in Acrobat/Edge/Foxit) eines PDFs."""
    import pdfplumber
    punkte: list[str] = []
    try:
        with pdfplumber.open(str(pfad)) as pdf:
            for seite in pdf.pages[:max_seiten]:
                for a in seite.annots or []:
                    art = (a.get("data") or {}).get("Subtype", "")
                    art = str(getattr(art, "name", art)).strip("/'")       # pdfminer liefert PSLiteral(/'Highlight')
                    if art not in ("Highlight", "Squiggly", "Underline"):
                        continue
                    box = (max(a["x0"] - 1, 0), max(a["top"] - 1, 0), min(a["x1"] + 1, seite.width),
                           min(a["bottom"] + 1, seite.height))
                    t = re.sub(r"\s+", " ", seite.within_bbox(box).extract_text() or "").strip()
                    if t and t not in punkte:
                        punkte.append(t)
    except Exception:  # noqa: BLE001 – Markierungen sind eine Zugabe, das Lesen der Werte geht trotzdem
        pass
    return punkte


# ------------------------------------------------------------------------ Ausbaustufen

_STUFE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(k?A)\s*(?:for|bei|für|at|@)\s*(?:the\s+|die\s+|der\s+)?(\d+(?:[.,]\d+)?)\s*(k?W)",
                    re.I)


def _zahl(x: str, einheit: str) -> float:
    return float(x.replace(",", ".")) * (1000 if einheit.lower().startswith("k") else 1)


def ausbaustufen(text: str) -> list[allgemein.Variante]:
    """„≥500 A for 10 kW configuration and up to ≥1000 A for 30 kW“ → zwei Varianten (Strom/Leistung je Stufe)."""
    e = allgemein.erkennen(text)
    stufen = []
    for m in _STUFE.finditer(text.replace("≥", "").replace(">=", "")):
        i, p = _zahl(m.group(1), m.group(2)), _zahl(m.group(3), m.group(4))
        if any(abs(v.pmax - p) < 1e-6 for v in stufen):
            continue
        stufen.append(allgemein.Variante(
            spannung=f"{allgemein_zahl(e.umax)} V" if e.umax else "", strom=f"{allgemein_zahl(i)} A", leistung=f"{allgemein_zahl(p / 1000)} kW",
            umax=e.umax, imax=i, pmax=p))
    return stufen if len(stufen) > 1 else []


def allgemein_zahl(x: float) -> str:
    return f"{x:g}".replace(".", ",")


# ------------------------------------------------------------------------ offene Punkte

# Was die Suche anhand der Shopdaten selbst prüft (Bezeichnung des markierten Punkts)
_GEPRUEFT = [
    (re.compile(r"output\s+voltage|ausgangsspannung|^\s*(dc\s+|ac\s+)?voltage\b|^\s*spannung", re.I), "Spannung"),
    (re.compile(r"output\s+current|ausgangsstrom|^\s*(dc\s+|ac\s+)?current\b|^\s*strom\b", re.I), "Strom"),
    (re.compile(r"output\s+power|ausgangsleistung|^\s*(dc\s+|ac\s+)?power\b|^\s*leistung\b|nennleistung", re.I), "Leistung"),
    (re.compile(r"19\s*(\"|”|zoll|inch)|rack", re.I), "Bauform"),
    (re.compile(r"bi-?direktional|bidirectional", re.I), "bidirektional"),
    (re.compile(r"rückspeis|regenerativ|energy recovery", re.I), "Netzrückspeisung"),
    (re.compile(r"output\s+frequency|ausgangsfrequenz", re.I), "Ausgangsfrequenz"),
]


def ist_geprueft(punkt: str) -> str:
    """Name des Suchkriteriums, das diesen Punkt abdeckt – oder "" (= muss von Hand geklärt werden)."""
    bezeichnung = punkt.split(":", 1)[0] if ":" in punkt else punkt
    for muster, name in _GEPRUEFT:
        if muster.search(bezeichnung):
            return name
    return ""


def offene_punkte(fremd, treffer_hinweise: list[str] | None = None) -> list[str]:
    """Liste für die Warnung am Ende: markierte Pflichtpunkte, die die Suche nicht prüfen kann, unsichere Werte
    aus dem Einlesen und Hinweise der besten Treffer („Frequenz nicht im Shop angegeben – prüfen“)."""
    offen = [f"Pflicht (markiert): {p}" for p in getattr(fremd, "pflicht", []) if not ist_geprueft(p)]
    for h in getattr(fremd, "hinweise", []):
        if re.match(r"Nicht gefunden|Gerätetyp geschätzt|Ohne feste Bezeichnung|Das PDF enthält keinen", h):
            offen.append(h)
    for h in treffer_hinweise or []:
        for teil in h.split("; "):
            if re.search(r"prüfen|nicht im Shop angegeben|als Option", teil) and f"Beste Treffer: {teil}" not in offen:
                offen.append(f"Beste Treffer: {teil}")
    return offen
