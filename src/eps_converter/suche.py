"""Produktsuche für Kundenanfragen (innerbetrieblich): „0-30V 1kA 30kW“ eingeben → passende EPS-Geräte.

Grundlage sind alle Datensätze im Converter (auch Entwürfe). Bewertet wird je Gerät:
  • passt genau   – Spannung, Strom und Leistung reichen, keiner mehr als die Konfigurator-Obergrenze (+20 %)
  • passt (größer) – reicht, aber deutlich überdimensioniert
  • n× parallel / n× in Reihe – reicht erst mit mehreren Geräten (nur wenn Parallel-/Reihenschaltung möglich)
  • knapp darunter – höchstens 10 % zu klein (Hinweis für die Beratung)
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .modell import Datensatz
from .regeln import obergrenze

ELEKTRONISCHE_LAST = "Elektronische Last"
GERAETETYPEN = ["AC/AC", "AC/DC", "DC/AC", "DC/DC", ELEKTRONISCHE_LAST, "Ladegeräte"]
MAX_GERAETE = 10            # mehr Geräte parallel/in Reihe schlagen wir nicht vor
KNAPP = 0.90                # „knapp darunter“: mindestens 90 % des Bedarfs

PASST, GROESSER, PARALLEL, REIHE, KNAPP_DARUNTER = "passt genau", "passt (größer)", "parallel", "in Reihe", "knapp darunter"
REIHENFOLGE = {PASST: 0, GROESSER: 1, PARALLEL: 2, REIHE: 3, KNAPP_DARUNTER: 4}

_PRAEFIX = {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3}
_TOKEN = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(?:(?:-|–|bis|\.\.\.?|…)\s*(\d+(?:[.,]\d+)?)\s*)?([kKMm]?)(VA|V|A|W)(AC|DC|ac|dc|rms)?(?![a-zA-Z])")
AC_AUSGANG = {"AC/AC", "DC/AC"}
UEBERDIMENSIONIERT = 3.0    # ab dreifacher Reserve gibt es einen Hinweis


@dataclass
class Anfrage:
    spannung: float | None = None
    strom: float | None = None
    leistung: float | None = None
    geraetetyp: str = ""          # leer = alle
    quelle: bool = False          # „Stromquelle“, „Netzgerät“ … → reine Lasten ausblenden
    ausgang: str = ""             # "AC"/"DC", wenn die Spannung als VAC/VDC angegeben ist
    erkannt: list[str] = field(default_factory=list)

    @property
    def leistung_bedarf(self) -> float | None:
        """Benötigte Leistung: angegeben oder U × I – der größere Wert (Arbeitspunkt muss erreichbar sein)."""
        kandidaten = [x for x in (self.leistung,
                                  self.spannung * self.strom if self.spannung and self.strom else None) if x]
        return max(kandidaten) if kandidaten else None

    def leer(self) -> bool:
        return not (self.spannung or self.strom or self.leistung)


def _z(s: str) -> float:
    return float(s.replace(",", "."))


def zahl_text(x: float | None, einheit: str) -> str:
    """30000 W → „30 kW“, 1000 A → „1000 A“, 0,5 → „0,5“."""
    if x is None:
        return "–"
    if einheit == "W" and x >= 1000:
        return f"{x / 1000:g} kW".replace(".", ",")
    return f"{x:g} {einheit}".replace(".", ",")


def anfrage_lesen(text: str) -> Anfrage:
    """„Stromquelle 0-30V 1kA 30kW“ → U = 30 V, I = 1000 A, P = 30 kW, Quelle."""
    a = Anfrage()
    t = text or ""
    for m in _TOKEN.finditer(t):
        von, bis, praefix, einheit, art = m.group(1), m.group(2), m.group(3), m.group(4), (m.group(5) or "").upper()
        wert = _z(bis or von) * _PRAEFIX.get(praefix, 1.0)
        if einheit == "V":
            a.spannung = wert
            if art in ("AC", "DC"):
                a.ausgang = art
        elif einheit == "A":
            a.strom = wert
        else:
            a.leistung = wert
    tl = t.lower()
    if re.search(r"\b(e-?last|elektronische last|last|senke|sink|load)\b", tl):
        a.geraetetyp = ELEKTRONISCHE_LAST
    else:
        for typ in ("AC/AC", "AC/DC", "DC/AC", "DC/DC"):
            if typ.lower() in tl:
                a.geraetetyp = typ
                break
        if re.search(r"lade(gerät|geraet)?\b|charger", tl):
            a.geraetetyp = "Ladegeräte"
    if re.search(r"quelle|netzger|netzteil|stromversorgung|source|power supply", tl):
        a.quelle = True
    if a.spannung is not None:
        a.erkannt.append(f"U = {zahl_text(a.spannung, 'V')}")
    if a.strom is not None:
        a.erkannt.append(f"I = {zahl_text(a.strom, 'A')}")
    if a.leistung is not None:
        a.erkannt.append(f"P = {zahl_text(a.leistung, 'W')}")
    elif a.spannung and a.strom:
        a.erkannt.append(f"P = U × I = {zahl_text(a.spannung * a.strom, 'W')}")
    if a.geraetetyp:
        a.erkannt.append(a.geraetetyp)
    if a.ausgang and not a.geraetetyp:
        a.erkannt.append(f"{a.ausgang}-Ausgang")
    if a.quelle and not a.geraetetyp:
        a.erkannt.append("Quelle (ohne reine Lasten)")
    return a


# ------------------------------------------------------------------------ Gerätedaten

def _max(ds: Datensatz, fid: str) -> float | None:
    w = ds.werte.get(fid)
    if not w:
        return None
    return w.max if w.max is not None else w.min


def geraetetypen(ds: Datensatz) -> list[str]:
    w = ds.werte.get("geraetetyp")
    return list(w.auswahl) if w else []


def parallel_moeglich(ds: Datensatz) -> bool:
    w = ds.werte.get("parallelschaltung")
    if not w:
        return False
    t = " ".join([*w.auswahl, w.de]).lower()
    return bool(t.strip()) and not re.search(r"\b(nein|no|nicht)\b", t)


def reihe_moeglich(ds: Datensatz) -> bool:
    for fid in ("reihenschaltung", "master_slave_reihenschaltung"):
        w = ds.werte.get(fid)
        if w and (w.ja or (w.ja is None and w.de and not re.search(r"\b(nein|no)\b", w.de.lower()))):
            return True
    return False


def bereiche(ds: Datensatz) -> list[tuple[float | None, float | None, float | None]]:
    """(Umax, Imax, Pmax) je Ausgangsbereich – Bereich 2 (z. B. umschaltbar) als eigene Variante."""
    p = _max(ds, "ausgangsleistung")
    out = [(_max(ds, "ausgangsspannung"), _max(ds, "ausgangsstrom"), p)]
    u2, i2 = _max(ds, "ausgangsspannung_2"), _max(ds, "ausgangsstrom_2")
    if u2 or i2:
        out.append((u2 or out[0][0], i2 or out[0][1], p))
    return out


# ------------------------------------------------------------------------ Bewertung

@dataclass
class Treffer:
    ds: Datensatz
    kategorie: str
    anzahl: int = 1               # Geräte parallel bzw. in Reihe
    umax: float | None = None
    imax: float | None = None
    pmax: float | None = None
    reserve: dict = field(default_factory=dict)     # "U"/"I"/"P" → Faktor (Gesamtsystem / Bedarf)
    hinweis: str = ""

    @property
    def rang(self) -> tuple:
        ueber = sum(math.log(max(f, 1e-9)) for f in self.reserve.values() if f >= 1)
        unter = sum(-math.log(max(f, 1e-9)) for f in self.reserve.values() if f < 1)
        return (REIHENFOLGE[self.kategorie], self.anzahl, unter, ueber)

    @property
    def bewertung(self) -> str:
        if self.kategorie in (PARALLEL, REIHE):
            return f"{self.anzahl}× {self.kategorie}"
        return self.kategorie

    def reserve_text(self) -> str:
        teile = []
        for k in ("U", "I", "P"):
            f = self.reserve.get(k)
            if f is not None:
                teile.append(f"{k} {'+' if f >= 1 else '−'}{abs(f - 1) * 100:.0f} %")
        return " · ".join(teile)


def _ok_typ(ds: Datensatz, a: Anfrage) -> bool:
    typen = geraetetypen(ds)
    if a.geraetetyp:
        return a.geraetetyp in typen or not typen      # ohne Gerätetyp: lieber zeigen als verschweigen
    if a.quelle and typen == [ELEKTRONISCHE_LAST]:
        return False
    if a.ausgang and typen:
        ac = any(t in AC_AUSGANG for t in typen)
        dc = any(t not in AC_AUSGANG for t in typen)
        return ac if a.ausgang == "AC" else dc
    return True


def _bewerten_bereich(ds: Datensatz, a: Anfrage, umax, imax, pmax) -> Treffer | None:
    u, i, p = a.spannung, a.strom, a.leistung_bedarf
    # Ohne bekannten Gerätewert lässt sich die Anforderung nicht prüfen → Gerät nicht vorschlagen
    if (u and not umax) or (i and not imax) or (p and not pmax):
        return None
    fu = umax / u if u else None
    fi = imax / i if i else None
    fp = pmax / p if p else None

    def treffer(kat, n=1, hinweis=""):
        ru = fu * (n if kat == REIHE else 1) if fu is not None else None
        ri = fi * (n if kat == PARALLEL else 1) if fi is not None else None
        rp = fp * n if fp is not None else None
        res = {k: v for k, v in (("U", ru), ("I", ri), ("P", rp)) if v is not None}
        gross = [f"{name} {f:.0f}×" for name, f in (("Spannung", res.get("U")), ("Strom", res.get("I")),
                                                    ("Leistung", res.get("P"))) if f and f >= UEBERDIMENSIONIERT]
        if gross:
            hinweis = "; ".join(x for x in (hinweis, "stark überdimensioniert: " + ", ".join(gross)) if x)
        return Treffer(ds, kat, n, umax, imax, pmax, res, hinweis)

    if all(f is None or f >= 1 for f in (fu, fi, fp)):
        genau = all(x is None or g is None or g <= obergrenze(x) + 1e-9
                    for x, g in ((u, umax), (i, imax), (p, pmax)))
        return treffer(PASST if genau else GROESSER)

    # Zu wenig Strom/Leistung → parallel; zu wenig Spannung/Leistung → in Reihe
    if (fu is None or fu >= 1) and parallel_moeglich(ds):
        n = math.ceil(max(1 / f for f in (fi, fp) if f is not None) - 1e-9)
        if n <= MAX_GERAETE:
            return treffer(PARALLEL, n, "Parallelschaltung: " + _text(ds, "parallelschaltung"))
    if (fi is None or fi >= 1) and reihe_moeglich(ds):
        n = math.ceil(max(1 / f for f in (fu, fp) if f is not None) - 1e-9)
        if n <= MAX_GERAETE:
            return treffer(REIHE, n, "Reihenschaltung möglich")
    if all(f is None or f >= KNAPP for f in (fu, fi, fp)):
        knapp = [k for k, f in (("Spannung", fu), ("Strom", fi), ("Leistung", fp)) if f is not None and f < 1]
        return treffer(KNAPP_DARUNTER, hinweis=", ".join(knapp) + " etwas zu klein")
    return None


def _text(ds: Datensatz, fid: str) -> str:
    w = ds.werte.get(fid)
    if not w:
        return ""
    return ", ".join(w.auswahl) or w.de


def bewerten(ds: Datensatz, a: Anfrage) -> Treffer | None:
    if a.leer() or not _ok_typ(ds, a):
        return None
    beste = None
    for umax, imax, pmax in bereiche(ds):
        t = _bewerten_bereich(ds, a, umax, imax, pmax)
        if t and (beste is None or t.rang < beste.rang):
            beste = t
    return beste


def suchen(datensaetze: list[Datensatz], a: Anfrage, knapp_zeigen: bool = True,
           nur_freigegeben: bool = False) -> list[Treffer]:
    from .modell import FREIGEGEBEN
    out = []
    for ds in datensaetze:
        if nur_freigegeben and ds.status != FREIGEGEBEN:
            continue
        t = bewerten(ds, a)
        if t and (knapp_zeigen or t.kategorie != KNAPP_DARUNTER):
            out.append(t)
    return sorted(out, key=lambda t: t.rang)


# ------------------------------------------------------------------------ Empfehlungstext

def empfehlung(treffer: list[Treffer], a: Anfrage, sprache: str = "de") -> str:
    """Text zum Einfügen in eine Antwort-Mail."""
    en = sprache == "en"
    zeilen = []
    for t in treffer:
        ds = t.ds
        werte = [ds.text(f, sprache) or ds.text(f) for f in ("ausgangsspannung", "ausgangsstrom", "ausgangsleistung")]
        werte = " / ".join(w for w in werte if w)
        nr = f" ({'order no.' if en else 'Best.-Nr.'} {ds.bestellnummer})" if ds.bestellnummer else ""
        z = f"• {ds.titel}{nr}: {werte}"
        if t.kategorie == PARALLEL:
            z += (f" – {t.anzahl} units in parallel" if en else f" – {t.anzahl} Geräte parallel")
        elif t.kategorie == REIHE:
            z += (f" – {t.anzahl} units in series" if en else f" – {t.anzahl} Geräte in Reihe")
        if t.kategorie in (PARALLEL, REIHE):
            ges = []
            if t.kategorie == REIHE and t.umax:
                ges.append(zahl_text(t.umax * t.anzahl, "V"))
            if t.kategorie == PARALLEL and t.imax:
                ges.append(zahl_text(t.imax * t.anzahl, "A"))
            if t.pmax:
                ges.append(zahl_text(t.pmax * t.anzahl, "W"))
            if ges:
                z += f" ({'total' if en else 'gesamt'} {', '.join(ges)})"
        zeilen.append(z)
    bedarf = ", ".join(x for x in (zahl_text(a.spannung, "V") if a.spannung else "",
                                   zahl_text(a.strom, "A") if a.strom else "",
                                   zahl_text(a.leistung_bedarf, "W") if a.leistung_bedarf else "") if x)
    kopf = (f"For your requirement ({bedarf}) we recommend:" if en
            else f"Für Ihre Anforderung ({bedarf}) empfehlen wir:")
    return kopf + "\n" + "\n".join(zeilen)
