"""Fremd-Datenblatt (PDF eines Kunden/Wettbewerbers) → Suchanfrage für die Produktsuche.

Nutzt die regelbasierte Auslese des Datenblatt-Converters (eps_converter.auslesen + Feldkatalog): Ausgangsspannung,
-strom, -leistung und Gerätetyp werden erkannt, bei Seriendatenblättern wird ein Modell gewählt. Daraus entsteht
ein Anfragetext wie „AC/DC 0-60V 1000A 30kW“, den die normale Suche auswertet – der Text bleibt im Eingabefeld
sichtbar und kann vor der Suche korrigiert werden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pdfplumber

from eps_converter import auslesen, importieren, pfade, katalog as K, regeln
from eps_converter.modell import Datensatz, Wert, HERKUNFT_PDF

from . import allgemein, anforderung

LAST = "Elektronische Last"


@dataclass
class Fremdgeraet:
    datei: str
    modell: str = ""
    sprache: str = "de"
    spannung: str = ""            # Originaltexte aus dem Datenblatt
    strom: str = ""
    leistung: str = ""
    umax: float | None = None
    imax: float | None = None
    pmax: float | None = None
    ac: bool = False
    geraetetyp: list[str] = field(default_factory=list)
    hersteller_typ: str = ""
    hinweise: list[str] = field(default_factory=list)
    merkmale: list[str] = field(default_factory=list)   # z. B. ["19Zoll", "bidirektional", "400Hz"] – Teil der Anfrage
    pflicht: list[str] = field(default_factory=list)    # markierte Stellen (Textmarker) = muss genau erfüllt sein
    eingang: float | None = None                        # DC-Eingangsspannung (Wechselrichter, DC/DC)
    typ_geschaetzt: bool = False                        # Gerätetyp nur aus dem Text geraten → Suche nur „Quelle“/„Last“

    def anfrage(self) -> str:
        """Anfragetext für die Suche, z. B. „AC/DC 60V 1000A 30kW“."""
        teile = []
        typen = set(self.geraetetyp)
        if typen == {LAST}:
            teile.append("Last")
        elif LAST in typen:
            teile.append("Last")                      # bidirektional: muss auch senken können
        elif self.typ_geschaetzt and typen and not (typen & {"AC/AC", "DC/AC"}):
            teile.append("Quelle")                    # geschätzt: nicht auf einen Gerätetyp festlegen
        elif len(typen) == 1:
            teile.append(next(iter(typen)))
        if self.umax:
            teile.append(_z(self.umax) + ("VAC" if self.ac else "V"))
        if self.imax:
            teile.append(_z(self.imax) + "A")
        if self.pmax:
            teile.append(_z(self.pmax / 1000) + "kW" if self.pmax >= 1000 else _z(self.pmax) + "W")
        if self.eingang:
            teile.append(f"Eingang {_z(self.eingang)}VDC")
        # Bauform (19 Zoll, Desktop …) nur anzeigen, nicht suchen – sonst fallen gleichwertige Geräte anderer Bauart raus
        return " ".join(teile + [m for m in self.merkmale if m not in BAUFORM_MERKMALE])

    def leer(self) -> bool:
        return not (self.umax or self.imax or self.pmax)


_DC_EINGANG = [
    re.compile(r"(\d+(?:[.,]\d+)?)\s*v\s*dc\s*(?:to|→|->|zu|auf)\s*\d+(?:[.,]\d+)?\s*v\s*ac", re.I),
    re.compile(r"(\d+(?:[.,]\d+)?)\s*v\s*dc\s*(?:nominal|nenn)", re.I),
    re.compile(r"(?:input\s+voltage|eingangsspannung|nenneingangsspannung|dc\s+input)[^\n]{0,40}?(\d+(?:[.,]\d+)?)\s*v\s*dc", re.I),
]


def dc_eingang(text: str) -> float | None:
    """DC-Nenneingangsspannung eines Wechselrichters/DC-DC-Wandlers aus dem Datenblatt („125Vdc to 400Vac“)."""
    for muster in _DC_EINGANG:
        m = muster.search(text or "")
        if m:
            return float(m.group(1).replace(",", "."))
    return None


BAUFORM_MERKMALE = {"19Zoll", "Desktop", "Schrank", "Einbau", "DIN-Rail", "Tower"}


def _merkmal_hinweis(merkmale: list[str], quelle: str) -> str:
    gesucht = [m for m in merkmale if m not in BAUFORM_MERKMALE]
    bauform = [m.replace("19Zoll", "19 Zoll") for m in merkmale if m in BAUFORM_MERKMALE]
    teile = []
    if gesucht:
        teile.append(f"Merkmale aus dem {quelle}: {', '.join(gesucht)} (im Suchfeld änderbar)")
    if bauform:
        teile.append(f"Bauform laut {quelle}: {', '.join(bauform)} (nur Info – bei Bedarf ins Suchfeld schreiben)")
    return ". ".join(teile) + "."


def _tausender(text: str) -> str:
    """„10.000 A“ → „10000 A“ (Punkt vor genau drei Ziffern = Tausendertrennzeichen); „2.17 A“ bleibt."""
    return re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", text or "")


def _strangspannung(text: str) -> float | None:
    """Drehstrom mit Außenleiter- und Strangspannung („3/N/PE AC 420/242 V“, „400/230 VAC“): die kleinere (L-N),
    weil die Shopdaten AC-Geräte so führen. Sonst None."""
    werte = [float(x.replace(",", ".")) for x in re.findall(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)", text or "")
             for x in x]
    for i in range(0, len(werte) - 1, 2):
        a, b = max(werte[i], werte[i + 1]), min(werte[i], werte[i + 1])
        if b and 1.6 <= a / b <= 1.85:
            return b
    return None


def _z(x: float) -> str:
    return f"{x:g}".replace(".", ",")


@lru_cache(maxsize=1)
def katalog() -> K.Katalog:
    """Mitgelieferter Feldkatalog (in der EXE eingebettet) – die Produktsuche braucht keinen eigenen."""
    return K.laden(pfade.KATALOG_MITGELIEFERT)


@dataclass
class Analyse:
    modelle: list[auslesen.Modellspalte]          # Modellspalten der Converter-Auslese (Seriendatenblatt)
    varianten: list[allgemein.Variante]           # Zahlenreihen der allgemeinen Erkennung (nur ohne Modellspalten)
    hat_text: bool


def _text(pfad: Path, max_seiten: int = 4) -> str:
    with pdfplumber.open(str(pfad)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_seiten])


def ist_word(pfad: Path) -> bool:
    return Path(pfad).suffix.lower() in (".docx", ".docm")


def analysieren(pfad: Path) -> Analyse:
    if ist_word(pfad):
        text = anforderung.docx_lesen(Path(pfad)).text
        return Analyse([], anforderung.ausbaustufen(text) or allgemein.erkennen(text).varianten, bool(text.strip()))
    erg, _, _ = auslesen.analysieren(Path(pfad), katalog())
    varianten = [] if erg.modelle or not erg.hat_text else allgemein.erkennen(_text(Path(pfad))).varianten
    return Analyse(erg.modelle, varianten, erg.hat_text)


def modelle(pfad: Path) -> tuple[list[auslesen.Modellspalte], bool]:
    """(Modellspalten, hat_text). Leere Liste = Einzeldatenblatt."""
    a = analysieren(pfad)
    return a.modelle, a.hat_text


def lesen(pfad: Path, modell: auslesen.Modellspalte | None = None,
          variante: allgemein.Variante | None = None) -> Fremdgeraet:
    pfad = Path(pfad)
    if ist_word(pfad):
        return _word_lesen(pfad, variante)
    kat = katalog()
    erg = auslesen.auslesen(pfad, kat, modell)
    fg = Fremdgeraet(datei=pfad.name, modell=modell.label if modell else (variante.label if variante else ""),
                     sprache=erg.sprache)
    if not erg.hat_text:
        fg.hinweise.append("Das PDF enthält keinen lesbaren Text (Scan) – Werte bitte von Hand eingeben.")
        return fg
    ds = importieren.datensatz_aus_ergebnis(erg, kat, Datensatz(), fg.modell if modell else "")
    volltext = _text(pfad)
    ergaenzt = _allgemein_ergaenzen(ds, kat, allgemein.erkennen(volltext), variante, mit_modell=modell is not None)
    importieren.typ_und_zuordnung(ds, kat, volltext.replace("\n", " "))
    w = ds.werte
    fg.geraetetyp = list(w["geraetetyp"].auswahl) if "geraetetyp" in w else []
    for feld, attr, einheit in (("ausgangsspannung", "spannung", "V"), ("ausgangsstrom", "strom", "A"),
                                ("ausgangsleistung", "leistung", "W")):
        wert = w.get(feld)
        if not wert:
            continue
        text = wert.en if erg.sprache == "en" and wert.en else (wert.de or wert.en)
        setattr(fg, attr, text)
        _, mx = (None, wert.max) if wert.fundstelle == "allgemein" else regeln.parse_bereich(_tausender(text), einheit)
        if mx is None:
            mx = wert.max if wert.max is not None else wert.min
        setattr(fg, {"V": "umax", "A": "imax", "W": "pmax"}[einheit], mx)
    fg.ac = bool(re.search(r"VAC|V AC|\bAC\b|Vrms|~", fg.spannung, re.I)) or any(t in ("AC/AC", "DC/AC") for t in fg.geraetetyp)
    if not fg.geraetetyp and not fg.leer():
        fg.geraetetyp = _typ_aus_text(volltext, fg.ac)
        if fg.geraetetyp:
            fg.typ_geschaetzt = True
            fg.hinweise.append(f"Gerätetyp geschätzt: {fg.geraetetyp[0]} – gesucht wird allgemein nach "
                               f"{'Lasten' if fg.geraetetyp == [LAST] else 'Quellen'}.")
    if fg.ac:
        u = _strangspannung(fg.spannung)
        if u:
            fg.umax = u
            fg.hinweise.append(f"Drehstrom: gesucht wird mit der Strangspannung {_z(u)} V (L-N).")
    drehstrom = fg.ac and re.search(r"3\s*-?\s*phase|3\s*ph|3/N|3\s*x\b|triphas|drehstrom|L-L|\+N", fg.spannung, re.I)
    if not fg.pmax and fg.umax and fg.imax:
        if drehstrom:
            l_l = re.search(r"L-L", fg.spannung) and not _strangspannung(fg.spannung)
            fg.pmax = round((3 ** 0.5 if l_l else 3) * fg.umax * fg.imax, -1)
            fg.hinweise.append(f"Leistung berechnet ({'√3 × U(L-L)' if l_l else '3 × U(L-N)'} × I = {_z(fg.pmax)} VA).")
    _eingang_setzen(fg, volltext)
    fg.merkmale = merkmale(volltext, fg.ac)
    if fg.merkmale:
        fg.hinweise.append(_merkmal_hinweis(fg.merkmale, "Datenblatt"))
    ht = w.get("hersteller_typ") or w.get("typbezeichnung")
    fg.hersteller_typ = (ht.de or ht.en) if ht else fg.modell
    if variante or not fg.hersteller_typ:
        name = _produktname(volltext)
        fg.hersteller_typ = f"{name} ({variante.label})" if name and variante else (name or fg.hersteller_typ)
    if ergaenzt:
        fg.hinweise.append("Ohne feste Bezeichnung erkannt (bitte kurz prüfen): " + ", ".join(ergaenzt) + ".")
    fg.pflicht = anforderung.pdf_markierungen(pfad)
    return _abschliessen(fg)


def _eingang_setzen(fg: Fremdgeraet, text: str) -> None:
    """Bei Wechselrichtern/DC-DC zählt die Eingangsspannung (24/48/110/125 V …) – sonst sind alle Varianten gleich."""
    typen = set(fg.geraetetyp)
    if typen and not typen & {"DC/AC", "DC/DC"} and not fg.typ_geschaetzt:
        return
    ue = dc_eingang(text)
    if not ue:
        return
    fg.eingang = ue
    if not typen or fg.typ_geschaetzt:
        fg.geraetetyp, fg.typ_geschaetzt = (["DC/AC"] if fg.ac else ["DC/DC"]), False
    fg.hinweise.append(f"DC-Eingangsspannung: {_z(ue)} V – nur Geräte mit passendem Eingang (±10 %).")


def _abschliessen(fg: Fremdgeraet) -> Fremdgeraet:
    fehlt = [n for n, v in (("Spannung", fg.umax), ("Strom", fg.imax), ("Leistung", fg.pmax)) if not v]
    if fehlt:
        fg.hinweise.append("Nicht gefunden: " + ", ".join(fehlt) + " – ggf. von Hand ergänzen.")
    if fg.pflicht:
        offen = sum(1 for p in fg.pflicht if not anforderung.ist_geprueft(p))
        fg.hinweise.append(f"{len(fg.pflicht)} markierte Pflichtpunkte, davon {offen} nicht automatisch prüfbar "
                           "(Liste nach dem Einlesen).")
    return fg


def _word_lesen(pfad: Path, variante: allgemein.Variante | None) -> Fremdgeraet:
    """Anforderungsdokument (Word): Werte über die allgemeine Erkennung, markierte Stellen als Pflichtpunkte."""
    doc = anforderung.docx_lesen(pfad)
    sprache = "de" if re.search(r"\b(und|oder|Spannung|Strom|Leistung)\b", doc.text) else "en"
    fg = Fremdgeraet(datei=pfad.name, modell=variante.label if variante else "", sprache=sprache, pflicht=doc.markiert)
    e = allgemein.erkennen(doc.text)
    quelle = variante or e
    fg.spannung, fg.strom, fg.leistung = quelle.spannung or e.spannung, quelle.strom or e.strom, quelle.leistung or e.leistung
    fg.umax = quelle.umax or e.umax
    fg.imax = quelle.imax or e.imax
    fg.pmax = quelle.pmax or e.pmax
    fg.ac = e.ac
    if not fg.leer():
        fg.geraetetyp = _typ_aus_text(doc.text, fg.ac)
        fg.typ_geschaetzt = bool(fg.geraetetyp)
    if re.search(r"≥|>=|\bor better\b|\boder besser\b|mindestens|at least", doc.text, re.I):
        fg.hinweise.append("Anforderungen als Mindestwerte (≥) – gesucht wird ab diesen Werten.")
    _eingang_setzen(fg, doc.text)
    fg.merkmale = merkmale(doc.text, fg.ac)
    if fg.merkmale:
        fg.hinweise.append(_merkmal_hinweis(fg.merkmale, "Dokument"))
    name = _produktname(doc.text) or Path(pfad).stem.replace("_", " ")
    fg.hersteller_typ = f"{name} ({variante.label})" if variante else name
    return _abschliessen(fg)


def _allgemein_ergaenzen(ds: Datensatz, kat: K.Katalog, e: allgemein.Erkennung,
                         variante: allgemein.Variante | None, mit_modell: bool = False) -> list[str]:
    """Fehlende Ausgangswerte aus der allgemeinen Erkennung bzw. der gewählten Variante eintragen.
    Ist ein Modell einer Serie gewählt, gelten nur eindeutig bezeichnete Werte – sonst landen Serienwerte
    („bis 80 kW“, Leerlaufstrom) beim Einzelmodell."""
    ergaenzt = []
    quellen = {
        "ausgangsspannung": (variante.spannung, variante.umax) if variante and variante.umax else (e.spannung, e.umax),
        "ausgangsstrom": (variante.strom, variante.imax) if variante and variante.imax else (e.strom, e.imax),
        "ausgangsleistung": (variante.leistung, variante.pmax) if variante and variante.pmax else (e.leistung, e.pmax),
    }
    namen = {"ausgangsspannung": "Spannung", "ausgangsstrom": "Strom", "ausgangsleistung": "Leistung"}
    for fid, (text, wert) in quellen.items():
        vorhanden = ds.werte.get(fid)
        if wert is None or (vorhanden and (vorhanden.max is not None or vorhanden.min is not None) and not variante):
            continue
        einheit = {"ausgangsspannung": "V", "ausgangsstrom": "A", "ausgangsleistung": "W"}[fid]
        if mit_modell and not variante and e.prio.get(einheit, 0) < 3:
            continue
        text = text or _z(wert)
        if fid == "ausgangsspannung" and e.ac and "AC" not in text.upper():
            text += " AC"
        ds.werte[fid] = Wert(de=text, en=text, min=None, max=wert, herkunft=HERKUNFT_PDF, fundstelle="allgemein")
        ergaenzt.append(namen[fid])
    return ergaenzt


def _typ_aus_text(text: str, ausgang_ac: bool) -> list[str]:
    """Gerätetyp, wenn die Converter-Erkennung keinen findet: Netzeingang (AC) + Ausgang DC → AC/DC usw."""
    t = (text or "").lower()
    if re.search(r"elektronische last|electronic load|\bsenke\b", t):
        return [LAST]
    if re.search(r"wechselrichter|inverter", t):
        return ["DC/AC"]
    netz_ac = bool(re.search(r"netzeingang|netzanschluss|netzspannung|mains|ac[- ]input|input voltage.{0,30}v\s*ac|"
                             r"\b(230|400|115|208|480)\s*v\s*(ac|~)", t))
    dc_eingang = bool(re.search(r"dc[- ]eingang|dc[- ]input|eingangsspannung.{0,20}v\s*dc|input.{0,20}vdc", t))
    if ausgang_ac:
        return ["DC/AC"] if dc_eingang and not netz_ac else (["AC/AC"] if netz_ac else [])
    if dc_eingang and not netz_ac:
        return ["DC/DC"]
    if netz_ac or re.search(r"netzgerät|netzteil|power supply|labornetz", t):
        return ["AC/DC"]
    return []


def _produktname(text: str) -> str:
    """Erste aussagekräftige Zeile des Datenblatts (meist Serien-/Produktname, z. B. „ARGOS 1200“)."""
    for z in (text or "").splitlines()[:6]:
        z = z.strip()
        if 3 <= len(z) <= 60 and re.search(r"[A-Za-z]{2,}", z) and not re.search(r"seite|page|datenblatt|datasheet|www\.|@", z, re.I):
            return z
    return ""


_OPTION_SATZ = re.compile(r"option|optional|auf anfrage|on request|wahlweise|zubehör|accessor", re.I)


def merkmale(text: str, ausgang_ac: bool) -> list[str]:
    """Zusatzkriterien aus dem Datenblatt – nur feste Eigenschaften, nichts aus Options-/Zubehörsätzen."""
    saetze = [z for z in re.split(r"(?<=[.!;])\s+|\n", text or "") if z.strip()]
    fest = " ".join(z for z in saetze if not _OPTION_SATZ.search(z))
    out = []
    if re.search(r"19\s*(?:\"|”|“|''|zoll|inch|-zoll)|\b[1-9]\s*HE\b|\b[1-9]U\b(?!\s*[-/])", fest):
        out.append("19Zoll")
    if re.search(r"bi-?direktional|bidirectional", fest, re.I):
        out.append("bidirektional")
    if re.search(r"rückspeis|regenerativ|energy recovery", fest, re.I):
        out.append("Rückspeisung")
    if re.search(r"wassergekühlt|wasserkühlung|water.?cooled", fest, re.I):
        out.append("wassergekühlt")
    if ausgang_ac:
        hz = []
        for z in saetze:
            if re.search(r"ausgangsfrequenz|output frequency|frequenz\s*(ausgang|output)|frequency\s*out", z, re.I) \
                    and not _OPTION_SATZ.search(z):
                hz += re.findall(r"(\d{2,4})\s*Hz", z, re.I)
        if not hz:
            hz = re.findall(r"\b(400)\s*Hz", fest, re.I)        # Avionik: 400 Hz steht oft nur im Fließtext
        werte = sorted({int(x) for x in hz if 16 <= int(x) <= 2000})
        if 0 < len(werte) <= 3:
            out += [f"{w}Hz" for w in werte]
    return out
