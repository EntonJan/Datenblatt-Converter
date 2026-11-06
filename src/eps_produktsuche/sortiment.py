"""Passt die Anfrage überhaupt zu unserem Sortiment? (ab 1.5.3)

Händler und Einkaufsplattformen schicken Anfragen oft nur wegen eines Namens oder einer Markenähnlichkeit
(„EPS“ = Electric Power Steering, z. B. Curtis 1220 Lenkungsregler). Solche Anfragen haben Spannung und Strom,
die Suche findet also scheinbar passende Netzgeräte. Diese Prüfung erkennt fachfremde Produktbegriffe und gibt
einen Hinweis – nur wenn im Text nichts aus unserem Sortiment vorkommt. Sie schließt nichts aus.
"""
from __future__ import annotations

import re

# Produkte, die wir nicht führen (Stämme, Groß/klein egal). Bezeichnung für den Hinweis = Fundstelle im Text.
_FREMD = re.compile(
    r"\b(?:"
    r"(?:servo)?lenk(?:ung|ungsregler|getriebe|rad)\w*|steering\w*|"
    r"hydraulik\w*|hydraulic\w*|ventil\w*|valve\w*|magnetventil\w*|pumpe\w*|pumps?\b|"
    r"getriebe\w*|gearbox\w*|kugellager\w*|wälzlager\w*|bearings?\b|dichtung\w*|dichtring\w*|o-ring\w*|"
    r"kupplung\w*|clutch\w*|bremse\w*|bremsen\w*|brake\w*|zylinder\w*|cylinders?\b|"
    r"fahrtregler\w*|fahrsteuerung\w*|motorsteuerung\w*|motor ?controller\w*|traction controller\w*|"
    r"gabelstapler\w*|stapler\w*|flurförderzeug\w*|forklift\w*|hubwagen\w*|"
    r"drucksensor\w*|näherungsschalter\w*|proximity switch\w*|endschalter\w*|drehgeber\w*|encoder\w*|"
    r"schütz\w*|contactor\w*|frequenzumrichter\w*|servoverstärker\w*|servo drive\w*|"
    r"reifen\w*|felge\w*|tyres?\b|tires?\b|filterelement\w*|schlauch\w*|hose\b|"
    r"leiterplatte\w*|platine\w*|ersatzteil\w*|spare parts?\b|teilenummer\w*"
    r")",
    re.I,
)

# Unser Sortiment: kommt eines davon vor, ist die Anfrage nicht fachfremd (auch wenn z. B. „Ersatzteil“ fällt).
_EIGEN = re.compile(
    r"netzger|netzteil|stromversorgung|stromquelle|spannungsquelle|labornetz|elektronische last|e-last|\blasten\b|electronic load|"
    r"wechselrichter|inverter|frequenzwandler|frequency converter|ladeger|charger|power supply|power supplies|"
    r"dc[- ]?quelle|ac[- ]?quelle|dc source|ac source|netzrückspeis|regenerativ|batterietest|battery test|"
    r"\busv\b|\bups\b|dc/dc|ac/dc|dc/ac|ac/ac|konverter|converter|prüfsystem|testsystem",
    re.I,
)

# Unser Firmenname steht in jeder Anfrage (Empfänger, zitierte Mails) und sagt nichts über das Produkt
_WIR = re.compile(r"EPS[\s-]*Stromversorgung(?:\s*GmbH)?|[\w.+-]*@eps-germany\.de|eps-germany\.de", re.I)

# „Ersatzteil“, „Teilenummer“ allein sind kein Ausschlussgrund, nur zusammen mit einem Produktbegriff
_SCHWACH = re.compile(r"^(?:ersatzteil\w*|spare parts?|teilenummer\w*|platine\w*|leiterplatte\w*)$", re.I)


def fachfremd(text: str) -> list[str]:
    """Fachfremde Produktbegriffe im Text (höchstens 3, in Reihenfolge des Auftretens) – leer, wenn etwas aus
    unserem Sortiment vorkommt oder nur schwache Begriffe wie „Ersatzteil“ fallen."""
    text = _WIR.sub(" ", text or "")
    if not text.strip() or _EIGEN.search(text):
        return []
    funde: list[str] = []
    for m in _FREMD.finditer(text):
        wort = m.group(0)
        if wort.lower() not in (f.lower() for f in funde):
            funde.append(wort)
    if all(_SCHWACH.match(f) for f in funde):
        return []
    return [f for f in funde if not _SCHWACH.match(f)][:3]


def hinweis(funde: list[str]) -> str:
    return ("Möglicherweise kein Produkt aus unserem Sortiment (" + ", ".join(f"„{f}“" for f in funde) +
            ") – Anfrage prüfen, bevor ein Angebot rausgeht.")
