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

from eps_converter import auslesen, importieren, pfade, katalog as K, regeln
from eps_converter.modell import Datensatz

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

    def anfrage(self) -> str:
        """Anfragetext für die Suche, z. B. „AC/DC 60V 1000A 30kW“."""
        teile = []
        typen = set(self.geraetetyp)
        if typen == {LAST}:
            teile.append("Last")
        elif LAST in typen:
            teile.append("Last")                      # bidirektional: muss auch senken können
        elif len(typen) == 1:
            teile.append(next(iter(typen)))
        if self.umax:
            teile.append(_z(self.umax) + ("VAC" if self.ac else "V"))
        if self.imax:
            teile.append(_z(self.imax) + "A")
        if self.pmax:
            teile.append(_z(self.pmax / 1000) + "kW" if self.pmax >= 1000 else _z(self.pmax) + "W")
        return " ".join(teile)

    def leer(self) -> bool:
        return not (self.umax or self.imax or self.pmax)


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


def modelle(pfad: Path) -> tuple[list[auslesen.Modellspalte], bool]:
    """(Modellspalten, hat_text). Leere Liste = Einzeldatenblatt."""
    erg, _, _ = auslesen.analysieren(Path(pfad), katalog())
    return erg.modelle, erg.hat_text


def lesen(pfad: Path, modell: auslesen.Modellspalte | None = None) -> Fremdgeraet:
    pfad = Path(pfad)
    kat = katalog()
    erg = auslesen.auslesen(pfad, kat, modell)
    fg = Fremdgeraet(datei=pfad.name, modell=modell.label if modell else "", sprache=erg.sprache)
    if not erg.hat_text:
        fg.hinweise.append("Das PDF enthält keinen lesbaren Text (Scan) – Werte bitte von Hand eingeben.")
        return fg
    ds = importieren.datensatz_aus_ergebnis(erg, kat, Datensatz(), fg.modell)
    _, zeilen, _ = auslesen.analysieren(pfad, kat)
    gesamt = " ".join(s.text for z in zeilen for s in z.stuecke)
    importieren.typ_und_zuordnung(ds, kat, gesamt)
    w = ds.werte
    fg.geraetetyp = list(w["geraetetyp"].auswahl) if "geraetetyp" in w else []
    for feld, attr, einheit in (("ausgangsspannung", "spannung", "V"), ("ausgangsstrom", "strom", "A"),
                                ("ausgangsleistung", "leistung", "W")):
        wert = w.get(feld)
        if not wert:
            continue
        text = wert.en if erg.sprache == "en" and wert.en else (wert.de or wert.en)
        setattr(fg, attr, text)
        _, mx = regeln.parse_bereich(_tausender(text), einheit)
        if mx is None:
            mx = wert.max if wert.max is not None else wert.min
        setattr(fg, {"V": "umax", "A": "imax", "W": "pmax"}[einheit], mx)
    fg.ac = bool(re.search(r"VAC|V AC|\bAC\b|Vrms|~", fg.spannung)) or any(t in ("AC/AC", "DC/AC") for t in fg.geraetetyp)
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
    ht = w.get("hersteller_typ") or w.get("typbezeichnung")
    fg.hersteller_typ = (ht.de or ht.en) if ht else fg.modell
    fehlt = [n for n, v in (("Spannung", fg.umax), ("Strom", fg.imax), ("Leistung", fg.pmax)) if not v]
    if fehlt:
        fg.hinweise.append("Nicht gefunden: " + ", ".join(fehlt) + " – ggf. von Hand ergänzen.")
    return fg
