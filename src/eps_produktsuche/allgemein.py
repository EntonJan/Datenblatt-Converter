"""Allgemeine Werte-Erkennung für fremde Datenblätter ohne feste Bezeichnungen.

Die Converter-Auslese kennt feste Bezeichnungen („Ausgangsspannung“, „Output voltage“ …). Fremde Datenblätter schreiben
oft „U-Aus (V)“, „DC Ausgang Strom“, „RMS at 150Vac“ oder stellen mehrere Modelle als Zahlenreihe nebeneinander. Hier
zählen deshalb Einheiten und Muster:

  • Zahlen mit V / A / W·kW·VA in einer Zeile, deren Bezeichnung (oder Abschnittsüberschrift) nach Ausgang aussieht
  • Eingangs-, Netz-, Toleranz-, Genauigkeits- und ähnliche Zeilen werden übersprungen
  • eine Zeile mit drei oder mehr Werten = Variantentabelle (je Spalte ein Modell); Spannungs- und Stromzeile mit
    gleicher Spaltenzahl werden zu Varianten kombiniert („0-30 V / 40 A“), eine einzelne Leistungsangabe gilt für alle
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_ZAHL = r"\d+(?:[.,]\d+)?"
_TOKEN = re.compile(r"(?:(" + _ZAHL + r")\s*(?:-|–|\.\.\.?|…|bis|to)\s*)?(" + _ZAHL + r")\s*(k|M|m)?\s*(VA|V|A|W(?:att)?)(?:AC|DC|rms|eff|ss|pp)?(?![a-zA-Z])", re.I)

# Bezeichnungen, die NICHT der Ausgang sind
_NICHT_AUSGANG = re.compile(
    r"netz|eingang|input|mains|line|primär|primary|aufnahme|consumption|sicherung|fuse|inrush|einschalt|kurzschluss|"
    r"short|leitungsquerschnitt|toleranz|tolerance|genauigkeit|accuracy|auflösung|resolution|restwelligkeit|ripple|"
    r"ausregelung|regulation|regelung|monitor|analog|innenwiderstand|isolat|isoliert|prüf|test voltage|einstellbereich|"
    r"programm|sense|abfall|drop|überspannung|ovp|uvp|offset|leistungsfaktor|power factor|luftleistung|noise|"
    r"steuer|remote|fernbedien|trigger|relais|relay|lüfter|fan|anschluss für|kabelschuh|temperatur|gewicht|weight|"
    r"schalt|switching|standards|supply voltage|versorgung|hilfs|auxiliary|isolation|kvdc|\(u\s*>",
    re.I)
_SPANNUNG = re.compile(r"ausgangsspannung|output voltage|u[-_ ]?aus|u[-_ ]?out|\bu\s*\(|spannung|voltage|\bvdc\b|"
                       r"output range|nennspannung|rated voltage", re.I)
_STROM = re.compile(r"ausgangsstrom|output current|i[-_ ]?aus|i[-_ ]?out|\bi\s*\(|strom|current|\brms\b|nennstrom|"
                    r"rated current", re.I)
_LEISTUNG = re.compile(r"ausgangsleistung|output power|dauerausgangsleistung|nennleistung|rated power|leistung|"
                       r"power|\bp\s*\(", re.I)
_UEBERSCHRIFT = re.compile(r"^(voltage|spannung|current|strom|power|leistung|output|ausgang|nenndaten dc|dc[- ]ausgang|"
                           r"nenndaten chopper|elektrische daten)\b", re.I)


@dataclass
class Variante:
    spannung: str = ""
    strom: str = ""
    leistung: str = ""
    umax: float | None = None
    imax: float | None = None
    pmax: float | None = None

    @property
    def label(self) -> str:
        teile = [t for t in (self.spannung, self.strom, self.leistung) if t]
        return " / ".join(teile)


@dataclass
class Erkennung:
    spannung: str = ""
    strom: str = ""
    leistung: str = ""
    umax: float | None = None
    imax: float | None = None
    pmax: float | None = None
    ac: bool = False
    varianten: list[Variante] = field(default_factory=list)
    prio: dict = field(default_factory=dict)      # "V"/"A"/"W" → 3 = eindeutige Ausgangsbezeichnung, 2 = Nenn/Max, 1 = sonst


def _z(s: str) -> float:
    return float(s.replace(",", "."))


def vorbereiten(text: str) -> str:
    """Tausendertrennzeichen entfernen: „1 200 V“, „1.000 A“ → „1200 V“, „1000 A“ („2.17 A“ bleibt)."""
    t = re.sub(r"(?<=\d)[ .](?=\d{3}(?!\d)(?![.,]\d))", "", text or "")
    return t.replace("±", "").replace("+/-", "")


def werte(zeile: str, einheit: str) -> list[tuple[float, str]]:
    """(Maximalwert, Originaltext) je Angabe mit passender Einheit, in Reihenfolge."""
    out = []
    for m in _TOKEN.finditer(vorbereiten(zeile)):
        e = m.group(4).upper()
        e = "W" if e.startswith("W") else e
        if e != einheit and not (einheit == "W" and e == "VA"):
            continue
        f = {"K": 1e3, "M": 1e6}.get((m.group(3) or "").upper(), 1.0)
        if m.group(3) == "m":
            f = 1e-3
        out.append((_z(m.group(2)) * f, m.group(0).strip()))
    return out


def _einheit_im_label(label: str) -> str:
    m = re.search(r"\(\s*(k?W|VA|V|A)\s*\)|\[\s*(k?W|VA|V|A)\s*\]", label, re.I)
    return (m.group(1) or m.group(2)).upper() if m else ""


def _zahlenreihe(rest: str) -> list[tuple[float, str]]:
    """Zahlen/Bereiche ohne Einheit („0-30 0-40 0-7,5“) → je Spalte (Maximum, Text)."""
    out = []
    for m in re.finditer(r"(?:(" + _ZAHL + r")\s*(?:-|–|\.\.\.?)\s*)?(" + _ZAHL + r")", vorbereiten(rest)):
        out.append((_z(m.group(2)), m.group(0).strip()))
    return out


def erkennen(text: str) -> Erkennung:
    erg = Erkennung()
    abschnitt = ""
    reihen: dict[str, list[list[tuple[float, str]]]] = {"V": [], "A": [], "W": []}
    einzel: dict[str, list[tuple[float, str, int]]] = {"V": [], "A": [], "W": []}   # (Wert, Text, Priorität)
    for roh in (text or "").splitlines():
        zeile = re.sub(r"^[\s•\-*\uf000-\uf8ff■▪●◦]+", "", roh).strip()
        if not zeile:
            continue
        if _UEBERSCHRIFT.match(zeile) and not re.search(r"\d", zeile):
            abschnitt = zeile.lower()
            continue
        mz = re.search(r"\d", zeile)
        label = zeile[:mz.start()] if mz else zeile
        if mz and not label.strip(" :"):
            label = _TOKEN.sub(" ", vorbereiten(zeile))       # „1200W Dauerausgangsleistung“: Bezeichnung steht dahinter
        if not mz or _NICHT_AUSGANG.search(label):
            continue
        kontext = label + " " + abschnitt
        for einheit, muster in (("V", _SPANNUNG), ("A", _STROM), ("W", _LEISTUNG)):
            if not muster.search(label) and not (not label.strip() and muster.search(abschnitt)) \
                    and not (muster.search(abschnitt) and not any(m.search(label) for m in (_SPANNUNG, _STROM, _LEISTUNG))):
                continue
            w = werte(zeile, einheit)
            einheit_label = _einheit_im_label(label)
            if not w and einheit_label == ("KW" if einheit == "W" and "kW" in label else einheit):
                w = [(v * (1e3 if einheit_label == "KW" else 1), t + " " + einheit) for v, t in _zahlenreihe(zeile[mz.start():])]
            elif not w and einheit_label == einheit:
                w = [(v, t + " " + einheit) for v, t in _zahlenreihe(zeile[mz.start():])]
            if not w:
                continue
            if len(w) >= 3:
                reihen[einheit].append(w)
            if re.search(r"ausgangs|output|[uip][-_ ]?(aus|out)\b|dc[- ]?ausgang|dauerausgang", label, re.I):
                prio = 3
            elif re.search(r"nenn|rated|max|dauer|ausgang|output", kontext, re.I):
                prio = 2
            else:
                prio = 1
            if re.search(r"begrenzt|limited", zeile, re.I) and einheit == "W" and len(w) > 1:
                w = [min(w)]                                  # „1440 kW (auf 650 kW begrenzt)“
            bester = max(w)
            einzel[einheit].append((bester[0], zeile if len(zeile) < 90 else bester[1], prio))
            if einheit == "V" and re.search(r"v\s*ac|vac|\bac\b|rms", zeile, re.I):
                erg.ac = True
    for einheit, attr, txt in (("V", "umax", "spannung"), ("A", "imax", "strom"), ("W", "pmax", "leistung")):
        kandidaten = einzel[einheit]
        if kandidaten:
            beste_prio = max(k[2] for k in kandidaten)
            w, t, _ = max((k for k in kandidaten if k[2] == beste_prio), key=lambda k: k[0])
            setattr(erg, attr, w)
            setattr(erg, txt, _kuerzen(t))
            erg.prio[einheit] = beste_prio
    erg.varianten = _varianten(reihen, erg)
    return erg


def _kuerzen(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()[:80]


def _varianten(reihen: dict, erg: Erkennung) -> list[Variante]:
    """Spannungs-/Strom-/Leistungsreihen mit gleicher Spaltenzahl zu Modellen kombinieren."""
    u = reihen["V"][0] if reihen["V"] else []
    i = reihen["A"][0] if reihen["A"] else []
    p = reihen["W"][0] if reihen["W"] else []
    n = max(len(u), len(i), len(p))
    if n < 2:
        return []
    def passend(r):
        if len(r) == n:
            return r
        if r and n and len(r) == 2 * n:                     # „10 A - 5 A“ je Modell (zwei Bereiche) → Maximum
            return [max(r[k], r[k + 1]) for k in range(0, len(r), 2)]
        return None
    u2, i2, p2 = passend(u), passend(i), passend(p)
    if sum(x is not None for x in (u2, i2, p2)) < (1 if (p2 and not u and not i) else 2) and not (u2 and i2):
        if not (p2 and (u2 or i2 or (not u and not i))):
            return []
    out = []
    for k in range(n):
        v = Variante()
        if u2:
            v.umax, v.spannung = u2[k][0], u2[k][1]
        elif erg.umax:
            v.umax, v.spannung = erg.umax, ""
        if i2:
            v.imax, v.strom = i2[k][0], i2[k][1]
        if p2:
            v.pmax, v.leistung = p2[k][0], p2[k][1]
        elif erg.pmax and not p:
            v.pmax, v.leistung = erg.pmax, erg.leistung if len(erg.leistung) < 20 else _wtext(erg.pmax)
        out.append(v)
    return out


def _wtext(w: float) -> str:
    return f"{w / 1000:g} kW".replace(".", ",") if w >= 1000 else f"{w:g} W".replace(".", ",")
