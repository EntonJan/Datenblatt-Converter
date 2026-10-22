"""Wie ein Wert als Text erscheint (Prüfmaske, PDF) – einheitlich für DE und EN."""
from __future__ import annotations

from . import katalog as K
from . import regeln
from .modell import Datensatz

JA = {"de": "Ja", "en": "Yes"}
NEIN = {"de": "Nein", "en": "No"}


def auswahl_en(feld: K.Feld, wert_de: str, kat: K.Katalog) -> str:
    for de, en in feld.auswahl:
        if de == wert_de:
            return en
    return kat.uebersetze(wert_de) or wert_de


def text(ds: Datensatz, feld: K.Feld, kat: K.Katalog, sprache: str = "de") -> str:
    w = ds.werte.get(feld.id)
    if feld.id == "schnittstellen":
        namen = regeln.schnittstellen_ableiten(ds, kat)
        if sprache == "en":
            namen = [kat.feld(f.id).en for f in kat.abschnitt(K.SCHN) if f.de in namen]
        return ", ".join(namen)
    if w is None:
        return ""
    if feld.typ == K.SCHNITTSTELLE:
        return regeln.schnittstelle_text(w, sprache)
    eigener = (w.en or w.de) if sprache == "en" else w.de
    if feld.typ == K.JA_NEIN:
        if eigener:
            return eigener
        if w.ja is True:
            return JA[sprache]
        if w.ja is False:
            return NEIN[sprache]
        return ""
    if feld.typ in (K.AUSWAHL, K.MEHRFACH):
        if eigener:
            return eigener
        vals = w.auswahl if sprache == "de" else [auswahl_en(feld, v, kat) for v in w.auswahl]
        return ", ".join(vals)
    return eigener


def zeilen(ds: Datensatz, kat: K.Katalog, abschnitt: str, sprache: str) -> list[tuple[str, str]]:
    """Belegte Zeilen eines Abschnitts in Katalog-Reihenfolge (leere Felder werden ausgeblendet)."""
    out = []
    for f in kat.abschnitt(abschnitt):
        if f.typ == K.LISTE or f.id == "schnittstellen":
            continue
        t = text(ds, f, kat, sprache)
        if t:
            out.append((f.label(sprache), t))
    return out


def _kurz(name: str) -> str:
    for suf in ("-Schnittstelle", " interface", " Schnittstelle"):
        if name.endswith(suf):
            return name[: -len(suf)]
    return name


def schnittstellen_kurz(ds: Datensatz, kat: K.Katalog, sprache: str) -> str:
    """Kurzform für die Seitenleiste: „USB, Ethernet, Analog (isoliert) · Option: RS232, CAN …“"""
    std, opt = [], []
    for f in kat.abschnitt(K.SCHN):
        if f.typ != K.SCHNITTSTELLE:
            continue
        w = ds.werte.get(f.id)
        if not w or w.if_status not in ("Standard", "Option"):
            continue
        name = _kurz(f.label(sprache))
        (std if w.if_status == "Standard" else opt).append(name)
    teile = []
    if std:
        teile.append(", ".join(std))
    if opt:
        teile.append(("Option: " if sprache == "de" else "Optional: ") + ", ".join(opt))
    return " · ".join(teile)
