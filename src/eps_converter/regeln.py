"""Fachliche Regeln aus dem Pflichtenheft (15.10.2026)."""
from __future__ import annotations

import math
import re

from . import katalog as K
from .modell import Datensatz, REGEL_HAENDLER

# ---------------------------------------------------------------- EPS-Bezeichnung

def eps_name(original: str, haendlerware: bool = False) -> str:
    """Original beginnt mit „PS“ → „E/“ + Original (PSI 10000 → E/PSI 10000),
    sonst „EPS/“ + Original (ELR 9000 HP → EPS/ELR 9000 HP). Händlerware: Original bleibt."""
    o = (original or "").strip()
    if not o or haendlerware:
        return o
    up = o.upper()
    if up.startswith(("EPS/", "E/PS")):
        return o                                  # bereits EPS-Bezeichnung
    if up.startswith("PS"):
        return "E/" + o
    return "EPS/" + o


# ---------------------------------------------------------------- Zahlen und Bereiche

_PREFIX = {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3, "µ": 1e-6, "u": 1e-6}
_EINHEIT_ALIAS = {
    "V": ["V", "VDC", "VAC", "Vdc", "Vac", "Volt"],
    "A": ["A", "ADC", "AAC", "Arms", "Amp"],
    "W": ["W", "VA"],
    "°C": ["°C", "C", "°"],
    "Ω": ["Ω", "Ohm", "ohm", "OHM"],
    "Hz": ["Hz", "HZ", "hz"],
    "kg": ["kg"],
}
_ZAHL = r"[-−]?\d+(?:[.,]\d+)?"
_TRENNER_BEREICH = re.compile(r"^\s*(?:-|–|—|\.\.\.?|…|~|bis|to)\s*$", re.I)


def _zahl(s: str) -> float:
    s = s.replace("−", "-").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    return float(s)


def _faktor_fuer(einheit_text: str, basis: str) -> float | None:
    """Gibt den Umrechnungsfaktor zur Basiseinheit zurück, wenn die Einheit passt."""
    t = einheit_text.strip()
    if not t:
        return None
    for alias in sorted(_EINHEIT_ALIAS.get(basis, [basis]), key=len, reverse=True):
        if t.startswith(alias):
            return 1.0
        if len(t) > 1 and t[0] in _PREFIX and t[1:].startswith(alias) and basis not in ("°C", "kg"):
            return _PREFIX[t[0]]
    return None


def parse_bereich(text: str, basis: str) -> tuple[float | None, float | None]:
    """Liest min/max in der Basiseinheit aus einem Datenblatt-Text.

    Beispiele: „0-750 VDC“ → (0, 750) · „1500W/1200W derating“ → (1200, 1500) ·
    „30kW / 18kW derating“ → (18000, 30000) · „-20...70°C“ → (-20, 70) · „11A“ → (None, 11)
    """
    if not text:
        return None, None
    t = text.replace("−", "-")
    # Zahlen mit Position und folgender Einheit finden
    tokens = []
    for m in re.finditer(r"(?<!\d)(?<!\d[.,])(-?\d+(?:[.,]\d+)?)\s*([a-zA-Zµ°Ω%]*)", t):
        roh, einh = m.group(1), m.group(2)
        start = m.start(1)
        neg_ok = roh.startswith("-") and (start == 0 or not t[start - 1].isdigit())
        if roh.startswith("-") and not neg_ok:
            roh = roh[1:]
        try:
            wert = _zahl(roh)
        except ValueError:
            continue
        tokens.append([wert, einh, m.start(), m.end()])
    if not tokens:
        return None, None
    # Einheiten zuordnen: fehlende Einheit von der nächsten Zahl mit Einheit übernehmen
    for i in range(len(tokens) - 1, -1, -1):
        if not tokens[i][1] and i + 1 < len(tokens):
            tokens[i][1] = tokens[i + 1][1]
    werte = []
    for w, einh, a, e in tokens:
        f = _faktor_fuer(einh, basis) if einh else (1.0 if basis in ("°C",) else None)
        if f is None and not einh and len(tokens) == 1:
            f = 1.0
        if f is not None:
            werte.append((w * f, a, e))
    if not werte:
        return None, None
    if len(werte) == 1:
        return None, werte[0][0]
    # Bereich „a - b“: zwischen den ersten beiden Zahlen steht ein Bereichs-Trenner
    zw = t[werte[0][2]:werte[1][1]]
    zw_rein = re.sub(r"[a-zA-Zµ°Ω%]", "", zw)
    if _TRENNER_BEREICH.match(zw_rein) or zw_rein.strip() == "":
        return werte[0][0], werte[1][0]
    vals = [v for v, _, _ in werte]
    return min(vals), max(vals)


def parse_zahl(text: str, basis: str) -> float | None:
    _, mx = parse_bereich(text, basis)
    return mx


# ---------------------------------------------------------------- Konfigurator-Filter (für später)

def obergrenze(wunsch: float) -> float:
    """Wunsch + 20 %, aufgerundet: bis 100 in der 1-2-5-Reihe, darüber in 250er-Schritten."""
    if wunsch <= 0:
        return 0.0
    z = wunsch * 1.2
    if z > 100:
        return math.ceil(round(z, 9) / 250.0) * 250.0
    exp = math.floor(math.log10(z))
    for basis in (1, 2, 5, 10):
        kandidat = basis * 10 ** exp
        if kandidat >= z - 1e-12:
            return float(round(kandidat, 12))
    return float(10 ** (exp + 1))


# ---------------------------------------------------------------- Gerätetyp / Schnittstellen

ELEKTRONISCHE_LAST = "Elektronische Last"


def geraetetyp_vorschlag(ds: Datensatz) -> None:
    """Bidirektional = Ja → zusätzlich „Elektronische Last“. Wird nur beim Umschalten auf „Ja“
    aufgerufen; danach kann der Eintrag in der Prüfmaske wieder abgewählt werden."""
    bidi = ds.werte.get("bidirektional")
    gt = ds.wert("geraetetyp")
    if bidi and bidi.ja and ELEKTRONISCHE_LAST not in gt.auswahl:
        gt.auswahl.append(ELEKTRONISCHE_LAST)


def schnittstellen_ableiten(ds: Datensatz, kat: K.Katalog) -> list[str]:
    """Filterwert „Schnittstellen“ aus den einzelnen Schnittstellen-Zeilen (Standard oder Option)."""
    namen = []
    for f in kat.abschnitt(K.SCHN):
        if f.typ != K.SCHNITTSTELLE:
            continue
        w = ds.werte.get(f.id)
        if w and w.if_status in ("Standard", "Option"):
            namen.append(f.de)
    return namen


def schnittstelle_text(w, sprache: str) -> str:
    if not w or not w.if_status or w.if_status == "—":
        return ""
    s = w.if_status if sprache == "de" else {"Standard": "Standard", "Option": "Option"}.get(w.if_status, w.if_status)
    return f"{s} {w.if_code}".strip()


# ---------------------------------------------------------------- Freigabe-Prüfung

def hat_wert(w, f: K.Feld) -> bool:
    """Ob ein Feld belegt ist. Maßgeblich ist der deutsche Text bzw. die Auswahl."""
    if w is None:
        return False
    if f.typ in (K.TEXT,):
        return bool(w.de.strip())
    if f.typ in (K.ZAHL, K.BEREICH):
        return bool(w.de.strip()) or w.min is not None or w.max is not None
    if f.typ == K.JA_NEIN:
        return w.ja is not None or bool(w.de.strip())
    if f.typ in (K.AUSWAHL, K.MEHRFACH):
        return bool(w.auswahl) or bool(w.de.strip())
    if f.typ == K.SCHNITTSTELLE:
        return bool(w.if_status)
    return not w.leer()


def pruefe_freigabe(ds: Datensatz, kat: K.Katalog) -> list[str]:
    """Liefert eine Liste von Problemen. Leer = Freigabe möglich."""
    return [t for _, _, t in pruefe_freigabe_felder(ds, kat)]


def pruefe_freigabe_felder(ds: Datensatz, kat: K.Katalog) -> list[tuple[str, str, str]]:
    """Wie pruefe_freigabe, aber mit Feld-ID und Art: (feld_id, "wert" | "geprueft", Meldung)."""
    p = []
    for f in kat.felder:
        w = ds.werte.get(f.id)
        if f.pflicht and f.typ != K.LISTE and not hat_wert(w, f):
            p.append((f.id, "wert", f"Pflichtfeld fehlt: {f.de}"))
        if f.kern and f.typ != K.LISTE and not (w and w.geprueft):
            p.append((f.id, "geprueft", f"Kernfeld nicht als geprüft markiert: {f.de}"))
        if w and f.typ == K.BEREICH and w.min is not None and w.max is not None and w.min > w.max:
            p.append((f.id, "wert", f"{f.de}: „von“ ist größer als „bis“"))
    opt = ds.werte.get("optionen")
    if kat.hat("optionen") and kat.feld("optionen").kern and not (opt and opt.geprueft):
        p.append(("optionen", "geprueft", "Kernfeld nicht als geprüft markiert: Optionen"))
    nr = ds.bestellnummer
    if nr and not re.fullmatch(r"[A-Za-z0-9._-]+", nr):
        p.append(("bestellnummer", "wert", "Bestellnummer enthält unzulässige Zeichen (erlaubt: Buchstaben, Ziffern, . _ -)"))
    if ds.regel != REGEL_HAENDLER:
        name = ds.titel
        if name and not name.upper().startswith(("EPS/", "E/")):
            p.append(("typbezeichnung", "wert", "Typbezeichnung ist keine EPS-Bezeichnung (beginnt nicht mit „EPS/“ bzw. „E/“)"))
    return p


def dateiname(bestellnummer: str, sprache: str) -> str:
    return f"{'e' if sprache == 'en' else 'd'}{bestellnummer}.pdf"


# ------------------------------------------------------------------------ Herstellerspuren

_ALLGEMEIN = {"power", "elektronik", "electronics", "electronic", "gmbh", "group", "systems", "system", "technik",
              "technology", "industries", "germany", "deutschland", "international", "company", "sas", "ltd", "inc"}
SPUR_FLOSKELN = (r"\bour\s+(?:plant|company|factory|products?|engineers?|facility|own)\b|\bwe\s+(?:offer|manufacture|produce|recommend)\b"
                 r"|\bunser(?:e|em|en|er|es)?\b|\bwir\b|www\.|https?://|\b[\w.-]+@[\w-]+\.\w+|®|™")
# Kürzel, die wie Modellnummern aussehen, aber Normen/Schnittstellen sind
_KEIN_MODELL = {"EN", "UL", "IEC", "DIN", "ISO", "VDE", "IP", "RS", "CAN", "USB", "AC", "DC", "MTBF", "EMV", "EMC", "TFT",
                "LCD", "LED", "PWM", "CSA", "GPIB", "LAN", "SCPI", "CE", "UKCA", "IEEE", "ANSI", "NEMA", "MIL", "STD", "TÜV"}
_MODELL = re.compile(r"\b([A-ZÄÖÜ]{2,5})[ -]?(\d{3,5})[A-Z]?\b")


def _namen_muster(namen: list[str]) -> list[re.Pattern]:
    muster = []
    for n in namen:
        n = (n or "").strip()
        if len(n) < 3:
            continue
        muster.append(re.compile(r"(?<!\w)" + re.escape(n) + r"(?!\w)", re.I))
        erstes = re.split(r"[\s/,&-]+", n)[0]
        if len(erstes) >= 4 and erstes.lower() not in _ALLGEMEIN and erstes.lower() != n.lower():
            muster.append(re.compile(r"(?<!\w)" + re.escape(erstes) + r"(?!\w)", re.I))
    return muster


def herstellerspuren(ds: Datensatz, kat: K.Katalog, hersteller_namen: list[str]) -> list[tuple[str, str, str]]:
    """Sucht in allen Texten, die ins EPS-Datenblatt gehen, nach Herstellerspuren.
    Liefert (feld_id, gefundener Text, Meldung). Feld-IDs: Katalogfelder, "beschreibung", "optionen", "lieferumfang", "bilder"."""
    namen = list(hersteller_namen or []) + [ds.text("hersteller")]
    muster = _namen_muster(namen)
    typ = ds.text("hersteller_typ").strip()
    if len(typ) >= 4:
        muster.append(re.compile(re.escape(typ).replace(r"\ ", r"\s*"), re.I))
    floskel = re.compile(SPUR_FLOSKELN, re.I)
    texte: list[tuple[str, str]] = []
    for fid, w in ds.werte.items():
        if not kat.hat(fid) or kat.feld(fid).abschnitt == K.INTERN or fid in ("typbezeichnung", "hersteller"):
            continue
        for t in (w.de, w.en):
            if t:
                texte.append((fid, t))
    for o in ds.optionen:
        texte += [("optionen", t) for t in (o.code, o.de, o.en) if t]
    texte += [("lieferumfang", t) for e in ds.lieferumfang for t in (e.de, e.en) if t]
    texte += [("bilder", t) for b in ds.bilder for t in (b.de, b.en) if t]

    erg, gesehen = [], set()

    def neu(fid, fund, meldung):
        if (fid, fund.lower()) not in gesehen:
            gesehen.add((fid, fund.lower()))
            erg.append((fid, fund, meldung))

    for fid, t in texte:
        name = kat.feld(fid).de if kat.hat(fid) else {"beschreibung": "Beschreibung", "optionen": "Optionen",
                                                        "lieferumfang": "Lieferumfang", "bilder": "Bildunterschrift"}[fid]
        for m in muster:
            for f in m.finditer(t):
                neu(fid, f.group(0), f"{name}: Herstellername/-typ „{f.group(0)}“")
        for f in floskel.finditer(t):
            neu(fid, f.group(0), f"{name}: Herstellerformulierung „{f.group(0)}“")
        if fid == "beschreibung":
            eigene = " ".join([ds.titel, ds.text("serie"), ds.text("serie", "en")]).lower()
            for f in _MODELL.finditer(t):
                vorne = t[max(0, f.start() - 4):f.start()].upper()
                if f.group(0).lower() in eigene or vorne.endswith(("E/", "EPS/")):
                    continue                            # EPS-eigene Serien-/Typbezeichnung
                if f.group(1) not in _KEIN_MODELL:
                    neu(fid, f.group(0), f"{name}: mögliche Hersteller-Modellbezeichnung „{f.group(0)}“")
    return erg
