"""Einheiten-Formatierer: vereinheitlicht Schreibweisen nach der EPS-Hausregel (Stand 23.10.2026).

Festgelegt von Enton (Fragen 1–17):
  1b  Spannung mit Art direkt an der Einheit:      230Vac      → 230 VAC,   3750V DC → 3750 VDC
  2a  Leerzeichen zwischen Zahl und Einheit:       11A         → 11 A,      40µF     → 40 µF
  3b  Effektiv-/Spitzenwerte zusammen:             8.7Arms     → 8,7 Arms,  500mVpp  → 500 mVpp
  4b  keine Umrechnung (5000VA bleibt 5000 VA)
  5a  Dezimalzeichen: Deutsch Komma, Englisch Punkt (nur bei Zahlen mit Einheit)
  6a  Bereiche mit Halbgeviertstrich:              0-750 VDC   → 0–750 VDC; mit negativem Start: −20…70 °C
  7a  Temperatur:                                  0-50°C / 0 º C → 0–50 °C
  8a  Zeichen:                                     <= ≥ +-     → ≤ ≥ ±
  9b  Prozent ohne Leerzeichen:                    95 %        → 95%
  10a Abmessungen:                                 432 x 132 x 483mm (17" x 5" x 19") → 432 × 132 × 483 mm
  11a Imperiale Angaben in Klammern entfernen:     12kg (26 lbs.) → 12 kg
  12b 19 Zoll / 19 inch statt 19"
  13a Phasen:                                      3ph. / 3-phase → 3-phasig (DE) / 3-phase (EN)
  14a Ω statt Ohm
  15b Abkürzungen bleiben, nur Leerzeichen:        max.20ms    → max. 20 ms
  16a bekannte Tippfehler:                         Mhz → MHz, Attitude → Altitude, protocoll → protocol, doppelte Wörter
  17b nur per Knopf mit Vorher/Nachher-Liste (siehe gui.FormatierDialog)
"""
from __future__ import annotations

import re

# Einheiten, hinter die ein Leerzeichen kommt (längere zuerst, damit „mVpp“ nicht als „mV“ erkannt wird)
_EINHEITEN = ["mVpp", "Vpp", "mVrms", "Vrms", "mArms", "Arms", "App", "VAC", "VDC", "kVA", "MVA", "VA",
              "kV", "mV", "µV", "V", "kA", "mA", "µA", "A", "MW", "kW", "mW", "W",
              "GHz", "MHz", "kHz", "Hz", "ms", "µs", "ns", "kg", "mm", "cm", "km", "m",
              "µF", "mF", "nF", "pF", "kΩ", "MΩ", "mΩ", "Ω", "°C", "dB", "dBA", "Ah", "kWh", "Wh"]
_EINHEITEN.sort(key=len, reverse=True)
E = "(?:" + "|".join(re.escape(e) for e in _EINHEITEN) + ")"
ZAHL = r"\d+(?:[.,]\d+)?"
_ZOLL = r"(?:\"|”|″|''|’’|“)"


def _dezimal(z: str, sprache: str) -> str:
    """Dezimalzeichen anpassen. „1.200“/„1,200“ (Ganzzahl ≠ 0, genau 3 Nachkommastellen) ist mehrdeutig → unverändert."""
    m = re.fullmatch(r"(\d+)[.,](\d+)", z)
    if not m:
        return z
    ganz, nach = m.groups()
    if ganz.strip("0") and len(nach) == 3:
        return z
    return f"{ganz}{',' if sprache == 'de' else '.'}{nach}"


def formatieren(text: str, sprache: str = "de", feld_id: str = "") -> str:
    if not text:
        return text
    t = text

    # 16a Tippfehler
    t = re.sub(r"(?<=\d)\s*Mhz\b|\bMhz\b", lambda m: m.group(0).replace("Mhz", "MHz"), t)
    t = re.sub(r"\b([0-9]*\s*)(khz|Khz|KHz)\b", r"\1kHz", t)
    t = re.sub(r"\bGhz\b", "GHz", t)
    t = re.sub(r"\b(\d+\s*)hz\b", r"\1Hz", t)
    if sprache == "en":
        t = re.sub(r"\bAttitude\b", "Altitude", t)
        t = re.sub(r"\bprotocoll\b", "protocol", t)
    else:
        t = re.sub(r"\bProtokol\b", "Protokoll", t)
    t = re.sub(r"\b([A-Za-zÄÖÜäöüß]{3,})\s+\1\b", r"\1", t)                 # „sind sind“

    # 7a Gradzeichen
    t = re.sub(r"[º˚]\s*C\b", "°C", t)
    t = re.sub(r"°\s+C\b", "°C", t)

    # 8a Zeichen
    t = t.replace("<=", "≤").replace(">=", "≥").replace("+/-", "±").replace("+-", "±")
    t = re.sub(r"([≤≥±<>])\s+(?=\d)", r"\1", t)

    # 11a / 10a imperiale Angaben in Klammern
    t = re.sub(r"\s*\(\s*" + ZAHL + r"\s*(?:lbs?|pounds?)\.?\s*\)", "", t, flags=re.I)
    t = re.sub(r"\s*\((?:\s*" + ZAHL + r"\s*(?:" + _ZOLL + r"|in\.?|inch(?:es)?)\s*[xX×]?\s*)+\)", "", t)

    # 10a Abmessungen: Zahl x Zahl x Zahl (bei „Abmessungen“ auch zwei Werte)
    dim = r"\d[\d.,]*(?:\s*(?:mm|cm|m)\b|\s*" + _ZOLL + r")?"
    if feld_id == "abmessungen":
        muster = re.compile(dim + r"(?:\s*[xX×]\s*" + dim + r")+")
    else:
        muster = re.compile(dim + r"\s*[xX×]\s*" + dim + r"\s*[xX×]\s*" + dim)

    def _dim(m):
        teile = re.split(r"\s*[xX×]\s*", m.group(0))
        einheit = ""
        for i, p in enumerate(teile):
            em = re.search(r"\s*(mm|cm|m)$", p)
            if em:
                einheit = einheit or em.group(1)
                teile[i] = p[:em.start()]
        return " × ".join(teile) + (f" {einheit}" if einheit else "")
    t = muster.sub(_dim, t)

    # 12b 19 Zoll
    zoll = "19 Zoll" if sprache == "de" else "19 inch"
    t = re.sub(r"\b19\s*" + _ZOLL + r"(?=[\s\-,.;)]|$)", zoll, t)
    t = re.sub(r"\b19\s*(?:Zoll|inch)\b", zoll, t)

    # 13a Phasen
    phase = "phasig" if sprache == "de" else "phase"
    t = re.sub(r"\b([123])\s*(?:-\s*)?(?:ph\.?|phase|phasig|phasen)(?![a-zA-Z])", lambda m: f"{m.group(1)}-{phase}", t)
    t = re.sub(r"(\d-" + phase + r")\s*\+\s*N\b", r"\1 + N", t)

    # 14a Ohm
    t = re.sub(r"(?<=\d)\s*([kKmM]?)Ohm\b", lambda m: " " + {"k": "k", "K": "k", "m": "m", "M": "M"}.get(m.group(1), "") + "Ω", t)

    # 1b Spannungsart an der Einheit: 230Vac / 230 V AC / 3750V DC → 230 VAC
    t = re.sub(r"(\d)\s*(k?V)\s*(ac|dc|AC|DC|Ac|Dc)(?=max\b|\b)", lambda m: f"{m.group(1)} {m.group(2)}{m.group(3).upper()}", t)
    t = re.sub(r"\b(VAC|VDC)max\b", r"\1 max.", t)

    # 15b Abkürzungen: nur Leerzeichen
    t = re.sub(r"\b(max|min|ca|approx|typ)\.(?=\d)", r"\1. ", t)

    # 6a Bereiche (nur wenn eine Einheit oder % folgt, damit Normen/Typen wie „61010-1“ unberührt bleiben)
    nach = r"(\s*(?:" + E + r"|%)(?![\w]))"
    t = re.sub(r"(?<![\w.,\d])[-−](" + ZAHL + r")\s*(?:" + E + r")?\s*(?:\.\.\.|…|–|-|to)\s*\+?(" + ZAHL + r")" + nach,
               lambda m: f"−{_dezimal(m.group(1), sprache)}…{_dezimal(m.group(2), sprache)}{m.group(3)}", t)

    def _bereich(m):
        a, ein1, b, rest = m.group(1), (m.group(2) or "").strip(), m.group(3), m.group(4)
        a, b = _dezimal(a, sprache), _dezimal(b, sprache)
        if ein1 and not rest.strip().startswith(ein1):
            return f"{a} {ein1}–{b}{rest}"
        return f"{a}–{b}{rest}"
    t = re.sub(r"(?<![\w.,\d−-])(" + ZAHL + r")(\s*" + E + r")?\s*(?:-|–|—|\.\.\.|…)\s*\+?(" + ZAHL + r")" + nach, _bereich, t)

    # 2a / 3b / 5a Zahl + Einheit: Leerzeichen und Dezimalzeichen
    t = re.sub(r"(?<![\w.,])(" + ZAHL + r")\s*(" + E + r")(?![\w])",
               lambda m: f"{_dezimal(m.group(1), sprache)} {m.group(2)}", t)
    # 9b Prozent ohne Leerzeichen, Dezimalzeichen anpassen
    t = re.sub(r"(?<![\w.,])(" + ZAHL + r")\s+%", r"\1%", t)
    t = re.sub(r"(?<![\w.,])(" + ZAHL + r")%", lambda m: f"{_dezimal(m.group(1), sprache)}%", t)

    # Aufräumen
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\s+([,;])", r"\1", t)
    return t.strip()
