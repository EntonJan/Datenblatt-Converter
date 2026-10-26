"""Import alter EPS-Datenblätter (Altbestand, d<Nr>.pdf / e<Nr>.pdf).

EPS-Blätter haben ein festes Layout: Seite 1 = Serie, Beschreibung, Lieferumfang; ab Seite 2 = EPS-Typbezeichnung,
Produkttyp und Tabellen „Bezeichnung  Wert“ (Allgemeine Daten, Schnittstellen, Technische Daten, Optionen).
Die Bezeichnungen entsprechen dem Feldkatalog. Liegt neben d<Nr>.pdf auch e<Nr>.pdf, werden die englischen Texte
von dort übernommen (keine Übersetzung nötig).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from . import katalog as K
from .katalog import normalisieren

KOPF_DE, KOPF_EN = "eps - datenblatt", "eps - datasheet"
ABSCHNITTE = {"allgemeine daten", "schnittstellen", "technische daten", "optionen", "general data", "interfaces",
              "technical data", "options"}
LIEFER_START = ("lieferumfang", "scope of delivery", "delivery scope", "included in delivery")
# EPS-eigene Bezeichnungen, die nicht 1:1 im Feldkatalog stehen
EXTRA = {
    "bestellnummer": "bestellnummer", "order code": "bestellnummer", "order no": "bestellnummer",
    "abmessung in mm (b x h x t)": "abmessungen", "dimensions in mm (wxhxd)": "abmessungen",
    "dimensions in mm (w x h x d)": "abmessungen",
    "analoge programmierung iso": "if_analog", "analoge programmierung": "if_analog", "analog isolation": "if_analog",
    "analog interface": "if_analog",
    "usb schnittstelle": "if_usb", "usb interface": "if_usb",
    "ethernet schnittstelle": "if_ethernet", "ethernet interface": "if_ethernet", "lan schnittstelle": "if_ethernet",
    "rs232 schnittstelle": "if_rs232", "rs232 interface": "if_rs232",
    "rs485 schnittstelle": "if_rs485", "rs485 interface": "if_rs485",
    "gpib schnittstelle": "if_gpib", "gpib interface": "if_gpib",
    "can schnittstelle": "if_can", "can interface": "if_can",
    "canopen schnittstelle": "if_canopen", "canopen interface": "if_canopen",
    "ethercat schnittstelle": "if_ethercat", "ethercat interface": "if_ethercat",
    "gbip schnittstelle": "if_gpib", "gbip interface": "if_gpib",          # Tippfehler in alten EPS-Blättern
    "profibus": "if_profibus", "profinet": "if_profinet", "modbus": "if_modbus",
    "modbus schnittstelle": "if_modbus", "modbus interface": "if_modbus",
    "attitude": "betriebshoehe", "altitude": "betriebshoehe",
    "operation temperature": "betriebstemperatur", "operating temperature": "betriebstemperatur",
    "mains": "netzanschluss", "display": "anzeige", "design": "bauform", "memory": "speicherplaetze",
    "capacity": "innenkapazitaet", "kapazität": "innenkapazitaet",
    "ripple u": "restwelligkeit_u", "ripple i": "restwelligkeit_i",
    "remote sensing": "fernfuehlung", "fernfühlungsausregelung": "fernfuehlung",
    "output current limitation": "begrenzung_ausgangsstrom", "overheat protection": "ueberhitzungsschutz",
    "isolation in-/output": "spannungsfestigkeit_ein_aus", "isolation output/enclosure": "spannungsfestigkeit_aus_geh",
    "accuracy interface": "genauigkeit_schnittstelle", "output preset": "voreinstellung_ausgang",
    "resistance adjustment range": "widerstand_einstellbereich", "widerstand einstellbereich": "widerstand_einstellbereich",
    "resistance resolution range": "widerstand_aufloesung", "resistance resolution": "widerstand_aufloesung",
}
_CODE = re.compile(r"^(?:EPS/|E/|E\d{5,})")


def ist_eps_datenblatt(pfad: Path) -> bool:
    try:
        with pdfplumber.open(str(pfad)) as pdf:
            t = (pdf.pages[0].extract_text() or "").lower()
    except Exception:
        return False
    return (KOPF_DE in t or KOPF_EN in t) and "eps-germany.de" in t


@dataclass
class Zeile:
    seite: int
    text: str
    fett: bool
    x0: float
    top: float
    x1: float
    bottom: float
    label: str = ""
    wert: str = ""
    wert_box: tuple = ()


@dataclass
class Altbestand:
    sprache: str = "de"
    serie: str = ""
    typbezeichnung: str = ""
    produkttyp: str = ""
    beschreibung: str = ""
    lieferumfang: list[str] = field(default_factory=list)
    werte: dict[str, tuple[str, int, tuple]] = field(default_factory=dict)    # fid -> (text, seite, box)
    optionen: list[tuple[str, str, str]] = field(default_factory=list)        # (nr, code, text)
    unbekannt: list[str] = field(default_factory=list)


def _zeilen(pfad: Path) -> list[Zeile]:
    out = []
    with pdfplumber.open(str(pfad)) as pdf:
        for i, p in enumerate(pdf.pages):
            for l in p.extract_text_lines(return_chars=True):
                txt = l["text"].strip()
                if not txt:
                    continue
                fett = any("bold" in c.get("fontname", "").lower() for c in l["chars"] if c["text"].strip())
                z = Zeile(i + 1, txt, fett, l["x0"], l["top"], l["x1"], l["bottom"])
                # Bezeichnung | Wert an der größten Lücke zwischen zwei Wörtern trennen
                chars = [c for c in l["chars"]]
                woerter, akt = [], []
                for c in chars:
                    if c["text"] == " ":
                        if akt:
                            woerter.append(akt); akt = []
                        continue
                    if akt and c["x0"] - akt[-1]["x1"] > 2.2:
                        woerter.append(akt); akt = []
                    akt.append(c)
                if akt:
                    woerter.append(akt)
                if len(woerter) >= 2:
                    luecken = [(woerter[k + 1][0]["x0"] - woerter[k][-1]["x1"], k) for k in range(len(woerter) - 1)]
                    g, k = max(luecken)
                    if g > 12:
                        z.label = " ".join("".join(c["text"] for c in w) for w in woerter[:k + 1])
                        rest = woerter[k + 1:]
                        z.wert = " ".join("".join(c["text"] for c in w) for w in rest)
                        z.wert_box = (rest[0][0]["x0"], min(c["top"] for w in rest for c in w),
                                      rest[-1][-1]["x1"], max(c["bottom"] for w in rest for c in w))
                out.append(z)
    return out


def _fuss(z: Zeile) -> bool:
    t = z.text.lower()
    return "eps-germany.de" in t or t.startswith(KOPF_DE) or t.startswith(KOPF_EN) or "seite:" in t or t.startswith("page ")


def _feld_fuer(label: str, kat: K.Katalog) -> str | None:
    n = normalisieren(label)
    n2 = re.sub(r"\s+\d+$", "", n)                    # „Widerstand Einstellbereich 1“
    for key in (n, n2):
        if key in EXTRA:
            return EXTRA[key]
    for f in kat.felder:
        if normalisieren(f.de) in (n, n2) or normalisieren(f.en) in (n, n2):
            return f.id
    for key in (n, n2):
        fid = kat.synonyme.get(key)
        if fid and fid != "hersteller_bestellnummer":
            return fid
    return None


def lesen(pfad: Path, kat: K.Katalog) -> Altbestand:
    zeilen = _zeilen(pfad)
    erg = Altbestand()
    kopf = next((z for z in zeilen if z.text.lower().startswith(("eps - datenblatt", "eps - datasheet"))), None)
    erg.sprache = "en" if kopf and "datasheet" in kopf.text.lower() else "de"

    # Seite 1: Serie, Beschreibung, Lieferumfang
    s1 = [z for z in zeilen if z.seite == 1 and not _fuss(z)]
    serie_z = next((z for z in s1 if re.match(r"^(series|serie)\s*", z.text, re.I)), None)
    if serie_z:
        erg.serie = re.sub(r"^(series|serie)\s*", "", serie_z.text, flags=re.I).strip()
    absatz, absaetze, liefer, im_liefer, letzte = [], [], [], False, None
    for z in s1:
        if z is serie_z or (serie_z and z.top <= serie_z.top):
            continue
        t = z.text
        if t.lower().rstrip(":").strip() in LIEFER_START or t.lower().startswith(tuple(s + ":" for s in LIEFER_START)):
            im_liefer = True
            rest = t.split(":", 1)[1].strip() if ":" in t else ""
            if rest:
                liefer.append(rest)
            continue
        if im_liefer:
            liefer.append(t)
            continue
        if letzte is not None and z.top - letzte.bottom > 6 and absatz:   # Leerzeile → neuer Absatz
            absaetze.append(" ".join(absatz)); absatz = []
        absatz.append(t)
        letzte = z
    if absatz:
        absaetze.append(" ".join(absatz))
    erg.beschreibung = "\n\n".join(re.sub(r"\s+", " ", a).strip() for a in absaetze if a.strip())
    erg.lieferumfang = [l.strip(" -•–") for l in liefer if l.strip(" -•–")]

    # Ab Seite 2: Typbezeichnung + Produkttyp (fett, linke Spalte, vor „Allgemeine Daten“), dann Tabellen
    rest = [z for z in zeilen if z.seite >= 2 and not _fuss(z)]
    tabelle_begonnen = False
    for z in rest:
        t = z.text
        tl = normalisieren(t)
        if re.match(r"^(serie|series)\s*", t, re.I) and z.fett:
            continue
        if tl in ABSCHNITTE:
            tabelle_begonnen = True
            continue
        if not tabelle_begonnen:
            if z.fett and not erg.typbezeichnung and _CODE.match(t):
                erg.typbezeichnung = t
            elif z.fett and erg.typbezeichnung and not erg.produkttyp:
                erg.produkttyp = t
            continue
        if not z.label:
            continue                                      # Bildunterschriften o. Ä.
        m = re.match(r"^Option\s*(\d+)$", z.label, re.I)
        if m:
            erg.optionen.append((m.group(1), *_option_teilen(z.wert)))
            continue
        fid = _feld_fuer(z.label, kat)
        if fid and kat.hat(fid):
            if fid not in erg.werte:
                erg.werte[fid] = (z.wert, z.seite, z.wert_box)
        else:
            erg.unbekannt.append(f"{z.label}: {z.wert}")
    return erg


def _option_teilen(text: str) -> tuple[str, str]:
    """„Kalibrierung mit Protokoll EPS/I10000 CAL“ → („EPS/I10000 CAL“, „Kalibrierung mit Protokoll“);
    „EPS/BNC Kabel Share-Bus …“ → („EPS/BNC“, „Kabel Share-Bus …“)."""
    teile = text.split()
    for i, w in enumerate(teile):
        if _CODE.match(w):
            j = i + 1
            while j < len(teile) and re.fullmatch(r"[A-Z0-9][A-Z0-9/\-.+]*", teile[j]):
                j += 1
            code = " ".join(teile[i:j])
            beschr = " ".join(teile[:i] + teile[j:]).strip(" ,;")
            return code, beschr
    return "", text


def partner_datei(pfad: Path) -> Path | None:
    """d103389.pdf ↔ e103389.pdf im selben Ordner."""
    m = re.fullmatch(r"([deDE])(.+)\.pdf", pfad.name)
    if not m:
        return None
    andere = ("e" if m.group(1).lower() == "d" else "d") + m.group(2) + ".pdf"
    for kandidat in (pfad.with_name(andere), pfad.with_name(andere.upper()[0] + andere[1:])):
        if kandidat.exists():
            return kandidat
    return None
