"""Kundenanfrage lesen und Shop-Geräte bewerten.

  passt genau     – reicht, und kein Wert liegt über der Obergrenze (Wunsch +20 %, aufgerundet wie im Konfigurator)
  passt (größer)  – reicht, ist aber größer
  n× parallel     – reicht erst mit mehreren Geräten (nur Serien mit Parallelschaltung/Master-Slave laut Shop)
  n× in Reihe     – reicht erst mit mehreren Geräten in Reihe (nur wenn der Shop das erwähnt)
  knapp darunter  – höchstens 10 % zu klein (Hinweis für die Beratung)
Bei AC-Ausgängen zählt, ob die gewünschte Spannung in einem einstellbaren Bereich liegt oder einer festen Spannung
(±10 %) entspricht – eine 400-V-Festspannung passt nicht zu einer 230-V-Anfrage.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .shop import Geraet, LAST, AC_AUSGANG

GERAETETYPEN = ["AC/DC", "AC/AC", "DC/AC", "DC/DC", LAST, "Ladegeräte"]
MAX_GERAETE = 10             # ohne Angabe im Shop schlagen wir höchstens 10 Geräte parallel/in Reihe vor
KNAPP = 0.90
AC_TOLERANZ = 0.10
UEBERDIMENSIONIERT = 3.0

PASST, GROESSER, PARALLEL, REIHE, KNAPP_DARUNTER = "passt genau", "passt (größer)", "parallel", "in Reihe", "knapp darunter"
REIHENFOLGE = {PASST: 0, GROESSER: 1, PARALLEL: 2, REIHE: 3, KNAPP_DARUNTER: 4}

_PRAEFIX = {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3}
_TOKEN = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(?:(?:-|–|bis|\.\.\.?|…)\s*(\d+(?:[.,]\d+)?)\s*)?([kKMm]?)"
                    r"(VA|V|A|W)(AC|DC|ac|dc|rms|eff)?(?![a-zA-Z])")


_EINGANG = re.compile(r"(?:eingang|input|\bu_?e\b|\buin\b)\s*[:=]?\s*"
                      r"(?P<u>\d+(?:[.,]\d+)?)\s*v\s*(?:dc)?\b", re.I)
_EINGANG_VOR = re.compile(r"(?P<u>\d+(?:[.,]\d+)?)\s*v\s*dc\s*(?:to|→|->|zu|nach|auf)\s*(?P<aus>\d+(?:[.,]\d+)?\s*v\s*ac)", re.I)
EINGANG_TOLERANZ = 0.10


def obergrenze(wunsch: float) -> float:
    """Wunsch + 20 %, aufgerundet: bis 100 in der 1-2-5-Reihe, darüber in 250er-Schritten (wie Produktkonfigurator)."""
    if wunsch <= 0:
        return 0.0
    z = wunsch * 1.2
    if z > 100:
        return math.ceil(round(z, 9) / 250.0) * 250.0
    exp = math.floor(math.log10(z))
    for basis in (1, 2, 5, 10):
        if basis * 10 ** exp >= z - 1e-12:
            return float(round(basis * 10 ** exp, 12))
    return float(10 ** (exp + 1))


def zahl_text(x: float | None, einheit: str) -> str:
    if x is None:
        return "–"
    if einheit in ("W", "VA") and x >= 1000:
        return f"{x / 1000:g} k{einheit}".replace(".", ",")
    return f"{x:g} {einheit}".replace(".", ",")


@dataclass
class Anfrage:
    text: str = ""
    spannung: float | None = None
    strom: float | None = None
    leistung: float | None = None
    geraetetyp: str = ""
    quelle: bool = False
    last: bool = False
    ausgang: str = ""            # "AC"/"DC"
    erkannt: list[str] = field(default_factory=list)
    # Zusatzkriterien (v1.2)
    bauform: str = ""            # "19 Zoll", "Desktop", "Schrank/Cabinet", "Einbau/Built-in", "Tower", "DIN Rail"
    bidirektional: bool = False
    rueckspeisung: bool = False
    wasser: bool = False
    frequenzen: list[float] = field(default_factory=list)
    eingang: float | None = None # DC-Eingangsspannung (Wechselrichter, DC/DC), z. B. „Eingang 125VDC“

    @property
    def leistung_bedarf(self) -> float | None:
        """Angegebene Leistung; nur ohne Angabe U × I. Eine angegebene Leistung unter U × I bedeutet Autoranging
        (z. B. 60 V / 1000 A / 30 kW) – dann braucht es nicht U_max und I_max gleichzeitig."""
        if self.leistung:
            return self.leistung
        return self.spannung * self.strom if self.spannung and self.strom else None

    def leer(self) -> bool:
        return not (self.spannung or self.strom or self.leistung)


def anfrage_lesen(text: str) -> Anfrage:
    """„Stromquelle 0-30V 1kA 30kW“ → U 30 V, I 1000 A, P 30 kW, Quelle."""
    a = Anfrage(text=text or "")
    rest = a.text
    # Eingangsspannung zuerst herausnehmen („Eingang 125VDC“, „UE=125V“, „125Vdc to 400Vac“), sonst würde sie
    # als Ausgangsspannung gelesen
    m = _EINGANG.search(rest) or _EINGANG_VOR.search(rest)
    if m:
        a.eingang = float(m.group("u").replace(",", "."))
        rest = rest[:m.start()] + " " + rest[m.end():]
        if m.re is _EINGANG_VOR:
            rest = rest[:m.start()] + " " + m.group("aus") + " " + rest[m.start():]
    for m in _TOKEN.finditer(rest):
        wert = float((m.group(2) or m.group(1)).replace(",", ".")) * _PRAEFIX.get(m.group(3), 1.0)
        einheit, art = m.group(4), (m.group(5) or "").upper()
        if einheit == "V":
            a.spannung = wert
            if art in ("AC", "DC"):
                a.ausgang = art
        elif einheit == "A":
            a.strom = wert
        else:
            a.leistung = wert
    tl = a.text.lower()
    if re.search(r"\b(e-?last|elektronische last|last|senke|sink|load)\b", tl):
        a.geraetetyp, a.last = LAST, True
    else:
        for typ in ("AC/AC", "AC/DC", "DC/AC", "DC/DC"):
            if typ.lower() in tl:
                a.geraetetyp = typ
                break
        if re.search(r"ladeger(ä|ae)t|\blader?\b|charger", tl):
            a.geraetetyp = "Ladegeräte"
        if re.search(r"wechselrichter|inverter", tl):
            a.geraetetyp = "DC/AC"
        if re.search(r"frequenzwandler|frequency converter", tl):
            a.geraetetyp = "AC/AC"
    if re.search(r"quelle|netzger|netzteil|stromversorgung|source|power supply", tl):
        a.quelle = True
    if a.eingang and not a.geraetetyp and not a.last:   # DC-Eingang: Wechselrichter (AC-Ausgang) bzw. DC/DC
        a.geraetetyp = "DC/AC" if a.ausgang == "AC" or re.search(r"\d\s*v\s*ac|vac|wechselrichter|inverter", tl) else "DC/DC"
    merkmale_lesen(a, tl)
    if a.spannung is not None:
        a.erkannt.append(f"U = {zahl_text(a.spannung, 'V')}")
    if a.strom is not None:
        a.erkannt.append(f"I = {zahl_text(a.strom, 'A')}")
    if a.leistung is not None:
        a.erkannt.append(f"P = {zahl_text(a.leistung, 'W')}")
    elif a.spannung and a.strom:
        a.erkannt.append(f"P = U × I = {zahl_text(a.spannung * a.strom, 'W')}")
    if a.ausgang and not a.geraetetyp:
        a.erkannt.append(f"{a.ausgang}-Ausgang")
    if a.geraetetyp:
        a.erkannt.append(a.geraetetyp + (" (inkl. bidirektionaler Geräte)" if a.last else ""))
    elif a.quelle:
        a.erkannt.append("Quelle (ohne reine Lasten)")
    a.erkannt += [x for x, ja in ((a.bauform, a.bauform), ("bidirektional", a.bidirektional),
                                  ("Netzrückspeisung", a.rueckspeisung), ("wassergekühlt", a.wasser)) if ja]
    if a.frequenzen:
        a.erkannt.append(" / ".join(zahl_text(f, "Hz") for f in a.frequenzen))
    if a.eingang:
        a.erkannt.append(f"Eingang {zahl_text(a.eingang, 'V')} DC")
    return a


BAUFORMEN = [(r"19\s*(?:\"|”|“|''|zoll|inch|-zoll)|\brack\b|einschub|\b\d\s*he\b|\b\du\b", "19 Zoll"),
             (r"tischger|desktop|tischgeh", "Desktop"), (r"schrank|cabinet", "Schrank/Cabinet"),
             (r"einbau|built-?in|chassis", "Einbau/Built-in"), (r"hutschiene|din.?rail", "DIN Rail"), (r"\btower\b", "Tower")]


def merkmale_lesen(a: Anfrage, tl: str) -> None:
    """Zusatzkriterien aus dem Anfragetext: Bauform, bidirektional, Rückspeisung, Wasserkühlung, Frequenz."""
    for muster, bauform in BAUFORMEN:
        if re.search(muster, tl):
            a.bauform = bauform
            break
    a.bidirektional = bool(re.search(r"bi-?direktional|bidirectional", tl))
    a.rueckspeisung = bool(re.search(r"rückspeis|ruckspeis|regenerativ|regenerative|energy recovery", tl))
    a.wasser = bool(re.search(r"wassergek(ü|ue)hlt|wasserk(ü|ue)hlung|water.?cool|\bwc\b", tl))
    a.frequenzen = sorted({float(x.replace(",", ".")) for x in re.findall(r"(\d+(?:[.,]\d+)?)\s*hz\b", tl)})
    if a.frequenzen and not a.ausgang and not a.geraetetyp:
        a.ausgang = "AC"                           # eine Ausgangsfrequenz gibt es nur bei AC-Ausgängen


# ------------------------------------------------------------------------ Bewertung

@dataclass
class Treffer:
    g: Geraet
    kategorie: str
    anzahl: int = 1
    reserve: dict = field(default_factory=dict)
    hinweis: str = ""

    @property
    def rang(self) -> tuple:
        ueber = sum(math.log(f) for f in self.reserve.values() if f and f >= 1)
        unter = sum(-math.log(f) for f in self.reserve.values() if f and f < 1)
        return (REIHENFOLGE[self.kategorie], self.anzahl, unter, ueber)

    @property
    def bewertung(self) -> str:
        return f"{self.anzahl}× {self.kategorie}" if self.kategorie in (PARALLEL, REIHE) else self.kategorie

    def reserve_text(self) -> str:
        return " · ".join(f"{k} {'+' if f >= 1 else '−'}{abs(f - 1) * 100:.0f} %" for k, f in self.reserve.items()
                          if f is not None)


def typ_passt(g: Geraet, a: Anfrage) -> bool:
    if a.last:
        return g.kann_senken
    if a.geraetetyp:
        return g.geraetetyp == a.geraetetyp
    if a.quelle and g.geraetetyp == LAST:
        return False
    if a.ausgang == "AC":
        return g.ac
    if a.ausgang == "DC":
        return not g.ac or g.geraetetyp not in AC_AUSGANG
    return True


def unplausibel(g: Geraet) -> bool:
    """Leistung größer als Spannung × Strom × Kanäle (+10 %) – Datenfehler im Shop (vgl. Fehlerliste 27.10.2026)."""
    if not (g.umax and g.imax and g.pmax):
        return False
    m = re.search(r"(\d)\s*x\b", g.strom) or re.search(r"(\d)x\d", g.name)
    k = int(m.group(1)) if m else 3 if (re.search(r"triple|3-fach", g.name + " " + g.serie, re.I) or
                                        (g.ac and re.search(r"3\s*ph|3x|L-L|\+N", g.spannung, re.I))) else 1
    return g.pmax > g.umax * g.imax * k * 1.1


def _ac_spannung_passt(g: Geraet, u: float) -> bool:
    if any(lo - 1e-9 <= u <= hi + 1e-9 for lo, hi in g.u_bereiche):
        return True
    return any(abs(f - u) <= AC_TOLERANZ * u for f in g.u_fest)


def merkmale_pruefen(g: Geraet, a: Anfrage) -> tuple[bool, list[str]]:
    """(passt, Hinweise). Bekannte Abweichung → passt nicht; fehlende Shopangabe → passt mit Hinweis."""
    hinweise = []
    if a.bauform:
        if not g.bauart:
            hinweise.append("Bauform nicht im Shop angegeben")
        elif g.bauart != a.bauform:
            return False, []
    if a.bidirektional and not g.bidirektional:
        return False, []
    if a.rueckspeisung and not (getattr(g, "rueckspeisung", False) or re.search(r"rückspeis|regenerativ", g.name + g.serie, re.I)):
        return False, []
    if a.wasser:
        w = getattr(g, "wasser", "")
        if w == "option":
            hinweise.append("Wasserkühlung als Option")
        elif w != "ja":
            return False, []
    if a.eingang and g.geraetetyp in ("DC/AC", "DC/DC"):
        ue = getattr(g, "u_eingang", None)
        if ue is None:
            hinweise.append("Eingangsspannung nicht im Shop angegeben – prüfen")
        elif abs(ue - a.eingang) > EINGANG_TOLERANZ * a.eingang:
            return False, []
    if a.frequenzen:
        fest, bereiche, option = getattr(g, "f_fest", []), getattr(g, "f_bereiche", []), getattr(g, "f_option", [])
        for f in a.frequenzen:
            if f in fest or any(lo <= f <= hi for lo, hi in bereiche):
                continue
            if f in option:
                hinweise.append(f"{zahl_text(f, 'Hz')} als Option")
            elif not (fest or bereiche or option):
                hinweise.append("Frequenz nicht im Shop angegeben – prüfen")
            else:
                return False, []
    return True, hinweise


def bewerten(g: Geraet, a: Anfrage) -> Treffer | None:
    if a.leer() or not typ_passt(g, a):
        return None
    ok, merkmal_hinweise = merkmale_pruefen(g, a)
    if not ok:
        return None
    t = _bewerten_werte(g, a)
    if t and merkmal_hinweise:
        t.hinweis = "; ".join([*merkmal_hinweise, t.hinweis] if t.hinweis else merkmal_hinweise)
    return t


def _bewerten_werte(g: Geraet, a: Anfrage) -> Treffer | None:
    u, i, p = a.spannung, a.strom, a.leistung_bedarf
    if (u and g.umax is None) or (i and g.imax is None) or (p and g.pmax is None):
        return None
    ac_fest = bool(u and g.ac and (g.u_fest or g.u_bereiche))
    if ac_fest:
        if not _ac_spannung_passt(g, u):
            return None
        fu = 1.0                                      # AC-Spannung passt (Bereich oder Festwert)
    else:
        fu = g.umax / u if u else None
    fi = g.imax / i if i else None
    fp = g.pmax / p if p else None

    def treffer(kat, n=1, hinweis=""):
        res = {}
        if fu is not None:
            res["U"] = fu * (n if kat == REIHE else 1)
        if fi is not None:
            res["I"] = fi * (n if kat == PARALLEL else 1)
        if fp is not None:
            res["P"] = fp * n
        gross = [f"{name} {res[k]:.0f}×" for k, name in (("U", "Spannung"), ("I", "Strom"), ("P", "Leistung"))
                 if res.get(k) and res[k] >= UEBERDIMENSIONIERT]
        teile = [hinweis] if hinweis else []
        if gross:
            teile.append("stark überdimensioniert: " + ", ".join(gross))
        if g.aus_name:
            teile.append(f"{g.aus_name} aus Typbezeichnung")
        if unplausibel(g):
            teile.append("Shopdaten unplausibel (P > U × I) – vor Empfehlung prüfen")
        if "vorführ" in g.name.lower():
            teile.append("Vorführgerät")
        return Treffer(g, kat, n, res, "; ".join(teile))

    if all(f is None or f >= 1 for f in (fu, fi, fp)):
        genau = all(x is None or w is None or w <= obergrenze(x) + 1e-9
                    for x, w in ((None if ac_fest else u, g.umax), (i, g.imax), (p, g.pmax)))
        return treffer(PASST if genau else GROESSER)
    grenze = min(g.parallel_max or MAX_GERAETE, 64)
    if (fu is None or fu >= 1) and g.parallel:
        n = math.ceil(max(1 / f for f in (fi, fp) if f is not None) - 1e-9)
        if n <= grenze:
            return treffer(PARALLEL, n, "Parallelschaltung" + (f" bis {g.parallel_max} Geräte" if g.parallel_max else ""))
    if (fi is None or fi >= 1) and g.reihe and not ac_fest:
        n = math.ceil(max(1 / f for f in (fu, fp) if f is not None) - 1e-9)
        if n <= MAX_GERAETE:
            return treffer(REIHE, n, "Reihenschaltung laut Shop möglich")
    if all(f is None or f >= KNAPP for f in (fu, fi, fp)):
        knapp = [k for k, f in (("Spannung", fu), ("Strom", fi), ("Leistung", fp)) if f is not None and f < 1]
        return treffer(KNAPP_DARUNTER, hinweis=", ".join(knapp) + " etwas zu klein")
    return None


def suchen(geraete: list[Geraet], a: Anfrage, knapp_zeigen: bool = True, max_parallel: int | None = None) -> list[Treffer]:
    out = []
    for g in geraete:
        t = bewerten(g, a)
        if not t or (t.kategorie == KNAPP_DARUNTER and not knapp_zeigen):
            continue
        if max_parallel is not None and t.kategorie in (PARALLEL, REIHE) and t.anzahl > max_parallel:
            continue
        out.append(t)
    return sorted(out, key=lambda t: t.rang)


def nach_serie(treffer: list[Treffer]) -> list[tuple[str, list[Treffer]]]:
    """Treffer je Serie zusammenfassen; Reihenfolge = bester Treffer der Serie (Liste ist schon sortiert)."""
    gruppen: dict[str, list[Treffer]] = {}
    for t in treffer:
        gruppen.setdefault(t.g.serie or t.g.name, []).append(t)
    return list(gruppen.items())


def textsuche(geraete: list[Geraet], text: str) -> list[Geraet]:
    """Ohne V/A/W: Suche nach Bestellnummer oder Name („ELR 10080“, „200361“)."""
    worte = [w.lower() for w in re.split(r"\s+", text.strip()) if w]
    if not worte:
        return []
    return [g for g in geraete if all(w in f"{g.bestellnummer} {g.name} {g.serie}".lower() for w in worte)]


# ------------------------------------------------------------------------ Empfehlungstext

def empfehlung(treffer: list[Treffer], a: Anfrage, sprache: str = "de", alternative_zu: str = "") -> str:
    en = sprache == "en"
    zeilen = []
    for t in treffer:
        g = t.g
        werte = " / ".join(x for x in (g.spannung, g.strom, g.leistung) if x)
        z = f"• {g.name} ({'order no.' if en else 'Best.-Nr.'} {g.bestellnummer})" + (f": {werte}" if werte else "")
        if t.kategorie in (PARALLEL, REIHE):
            art = ("in parallel" if t.kategorie == PARALLEL else "in series") if en else \
                  ("parallel" if t.kategorie == PARALLEL else "in Reihe")
            z += f" – {t.anzahl} {'units' if en else 'Geräte'} {art}"
            ges = []
            if t.kategorie == REIHE and g.umax:
                ges.append(zahl_text(g.umax * t.anzahl, "V"))
            if t.kategorie == PARALLEL and g.imax:
                ges.append(zahl_text(g.imax * t.anzahl, "A"))
            if g.pmax:
                ges.append(zahl_text(g.pmax * t.anzahl, "W"))
            if ges:
                z += f" ({'total' if en else 'gesamt'} {', '.join(ges)})"
        if g.pdf_url:
            z += f"\n  {'Datasheet' if en else 'Datenblatt'}: {g.pdf_url}"
        zeilen.append(z)
    bedarf = ", ".join(zahl_text(x, e) for x, e in ((a.spannung, "V"), (a.strom, "A"), (a.leistung_bedarf, "W")) if x)
    if alternative_zu:
        werte = "" if re.search(r"\d\s*V\b", alternative_zu) or not bedarf else f" ({bedarf})"
        kopf = (f"As an alternative to {alternative_zu}{werte} we recommend:" if en
                else f"Als Alternative zu {alternative_zu}{werte} empfehlen wir:")
    else:
        kopf = (f"For your requirement ({bedarf}) we recommend:" if en else f"Für Ihre Anforderung ({bedarf}) empfehlen wir:") \
            if bedarf else ("We recommend:" if en else "Wir empfehlen:")
    return kopf + "\n" + "\n".join(zeilen)
