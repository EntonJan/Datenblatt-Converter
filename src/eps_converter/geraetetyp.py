"""Gerätetyp erkennen und Eingangsangaben dem richtigen Feld zuordnen (Entscheidungen Enton 26.10.2026).

AC/DC, AC/AC, Ladegeräte, Elektronische Last → Versorgung = Netzanschluss (Text) + Netzspannung (Auswahl für den Filter)
DC/DC, DC/AC                                 → Eingangsspannung (DC-Bereich, Kernfeld für den Filter)
Elektronische Last (nur Last, nicht bidirektional) → Lastseite steht in den Ausgangsfeldern, im Datenblatt beschriftet
                                               als „Eingangsspannung (Lastseite)“ usw. (Blatt „Bezeichnungen“)
Bidirektionale Geräte: bisherige Regel (AC/DC + Elektronische Last, DC-Seite = Ausgang).
"""
from __future__ import annotations

import re

from . import regeln
from .modell import Datensatz, Wert

AC_VERSORGT = {"AC/DC", "AC/AC", "Ladegeräte", "Elektronische Last"}
DC_EINGANG = {"DC/DC", "DC/AC"}
LAST = "Elektronische Last"

_AC = re.compile(r"v\s*ac\b|vac\b|\bac\b|\bhz\b|\d\s*ph\b|\d\s*-?\s*phase|phasig|\b[13]\s*~|mains|netz|l-n|l-l|single.phase|"
                 r"three.phase|\b3\s*/\s*n?\s*/?\s*pe\b|\b[13]\s*x\s*\d{3}|\d\s*v\s*/\s*3\b|drehstrom", re.I)
_DC = re.compile(r"v\s*dc\b|vdc\b|\bdc\b|batter|bordnetz", re.I)
_LAST = re.compile(r"electronic(?:al)? (?:dc )?load|elektronische(?:n)? last|\bdc[- ]load\b|\belr\s?\d|\bel\s?\d{4}|"
                   r"current sink|stromsenke|\bsenke\b|\bsink mode", re.I)
_LADE = re.compile(r"\bcharger\b|ladegerät|battery charg", re.I)
_BIDI = re.compile(r"bidirektional|bidirectional|source.{0,10}sink|quelle.{0,10}senke", re.I)


def art(text: str) -> str:
    """„AC“, „DC“ oder „“ für einen Spannungs-Text."""
    if not text:
        return ""
    ac, dc = bool(_AC.search(text)), bool(_DC.search(text))
    if ac and not dc:
        return "AC"
    if dc and not ac:
        return "DC"
    if ac and dc:                                      # z. B. „125dc nominal … 230 VAC“: was zuerst steht
        return "AC" if _AC.search(text).start() < _DC.search(text).start() else "DC"
    return ""


def _t(ds: Datensatz, fid: str) -> str:
    w = ds.werte.get(fid)
    return " ".join(x for x in (w.de, w.en) if x) if w else ""


def erkennen(ds: Datensatz, gesamttext: str, erlaubt: set[str]) -> list[str]:
    """Gerätetyp-Vorschlag aus Ein-/Ausgangsangaben und eindeutigen Begriffen."""
    t = gesamttext or ""
    if _LAST.search(t) and not _BIDI.search(t):
        return [LAST] if LAST in erlaubt else []
    if _LADE.search(t):
        return ["Ladegeräte"] if "Ladegeräte" in erlaubt else []
    ein = art(_t(ds, "netzanschluss")) or ("AC" if ds.werte.get("netzanschluss") else "") or art(_t(ds, "eingangsspannung"))
    aus = art(_t(ds, "ausgangsspannung"))
    af = ds.werte.get("ausgangsfrequenz")
    if not aus and af and af.auswahl:
        aus = "DC" if af.auswahl == ["DC"] else "AC"
    if not aus and _t(ds, "ausgangsspannung"):
        aus = "DC"                                     # „0–60 V“ ohne Angabe: Netzgeräte liefern fast immer DC
    typen = []
    if ein and aus and f"{ein}/{aus}" in erlaubt:
        typen.append(f"{ein}/{aus}")
    if _BIDI.search(t) and "AC/DC" in typen and LAST in erlaubt:
        typen.append(LAST)                             # bisherige Regel für bidirektionale Geräte
    return typen


def relevant(fid: str, geraetetypen: list[str]) -> bool:
    """Ob ein Feld beim Gerätetyp gefragt ist (sonst: keine Pflicht, kein Prüfhaken nötig)."""
    typen = set(geraetetypen or [])
    if not typen:
        return True
    if fid == "eingangsspannung":
        return bool(typen & DC_EINGANG)
    if fid in ("netzspannung", "netzanschluss"):
        return bool(typen & AC_VERSORGT)
    return True


def netzspannung_vorschlag(text: str) -> list[str]:
    """„3x380...460 VAC“ → [3~ 400 V, 3~ 480 V]; „90-264 VAC, 1ph.+N“ → [1~ Weitbereich 90–264 V]."""
    if not text:
        return []
    tl = text.lower()
    drei = bool(re.search(r"\b3\s*(?:x|~|ph|-?\s*phas)|three.phase|drehstrom|\bl-l\b|3p\b|\b3\s*/\s*n?\s*/?\s*pe\b|"
                          r"\d\s*v\s*/\s*3\b", tl))
    zahlen = [float(z.replace(",", ".")) for z in re.findall(r"(?<!\d)(?<!\d[.,])(\d{2,3}(?:[.,]\d)?)(?=\s*(?:v|…|\.\.\.|-|–|/|\s*$))", tl)]
    zahlen = [z for z in zahlen if 80 <= z <= 530]
    if not zahlen:
        return []
    lo, hi = min(zahlen), max(zahlen)
    out = []
    if drei:
        if lo <= 240 and hi >= 200 and lo < 300:
            out.append("3~ 208–230 V")
        if any(370 <= z <= 420 for z in zahlen) or (lo <= 400 <= hi):
            out.append("3~ 400 V")
        if any(430 <= z <= 500 for z in zahlen) or (lo <= 480 <= hi):
            out.append("3~ 480 V")
    else:
        if lo <= 100 and hi >= 240:
            out.append("1~ Weitbereich 90–264 V")
        else:
            if any(100 <= z <= 127 for z in zahlen):
                out.append("1~ 115 V")
            if any(200 <= z <= 250 for z in zahlen):
                out.append("1~ 230 V")
    return out or ["Sonderspannung"]


def zuordnen(ds: Datensatz, kat, typen: list[str]) -> list[str]:
    """Verschiebt Eingangsangaben ins richtige Feld. Rückgabe: kurze Hinweise, was verschoben wurde."""
    hinweise = []
    w = ds.werte
    ts = set(typen)
    # Reine elektronische Last: Lastseite → Ausgangsfelder (Entscheidung 1a)
    if ts == {LAST}:
        for von, nach in (("eingangsspannung", "ausgangsspannung"), ("eingangsstrom", "ausgangsstrom"),
                          ("eingangsleistung", "ausgangsleistung")):
            if von in w and (nach not in w or not regeln.hat_wert(w[nach], kat.feld(nach))) and kat.hat(nach):
                if von == "eingangsspannung" and art(_t(ds, von)) == "AC":
                    continue                               # das ist die Netzversorgung, nicht die Lastseite
                alt = w.pop(von)
                neu = Wert(**{**alt.__dict__})
                neu.min, neu.max = regeln.parse_bereich(alt.de or alt.en, kat.feld(nach).einheit)
                w[nach] = neu
                hinweise.append(f"{kat.feld(von).de} → {kat.feld(nach).de} (Lastseite)")
    # AC-versorgt: Eingangsspannung → Netzanschluss; Netzspannung als Auswahl vorschlagen
    if ts & AC_VERSORGT and "eingangsspannung" in w and art(_t(ds, "eingangsspannung")) != "DC":
        alt = w.pop("eingangsspannung")
        if "netzanschluss" not in w or not (w["netzanschluss"].de or w["netzanschluss"].en):
            w["netzanschluss"] = Wert(de=alt.de, en=alt.en, herkunft=alt.herkunft, fundstelle=alt.fundstelle,
                                      teiluebersetzt=alt.teiluebersetzt, en_manuell=alt.en_manuell)
            hinweise.append("Eingangsspannung → Netzanschluss (AC-Versorgung)")
    ohne_typ_ac = not ts and "netzanschluss" in w and art(_t(ds, "netzanschluss")) != "DC"
    if (ts & AC_VERSORGT or ohne_typ_ac) and kat.hat("netzspannung") and "netzspannung" not in w:
        n = w.get("netzanschluss")
        vorschlag = netzspannung_vorschlag((n.de or n.en) if n else "")
        erlaubt = {a for a, _ in kat.feld("netzspannung").auswahl}
        vorschlag = [v for v in vorschlag if v in erlaubt]
        if vorschlag:
            w["netzspannung"] = Wert(auswahl=vorschlag, herkunft=n.herkunft, fundstelle=n.fundstelle)
    # DC-Eingang: Netzanschluss mit DC-Angabe → Eingangsspannung
    if ts & DC_EINGANG and "eingangsspannung" not in w and "netzanschluss" in w and art(_t(ds, "netzanschluss")) == "DC":
        n = w.pop("netzanschluss")
        e = Wert(de=n.de, en=n.en, herkunft=n.herkunft, fundstelle=n.fundstelle, teiluebersetzt=n.teiluebersetzt)
        e.min, e.max = regeln.parse_bereich(n.de or n.en, "V")
        w["eingangsspannung"] = e
        hinweise.append("Netzanschluss → Eingangsspannung (DC-Eingang)")
    return hinweise
