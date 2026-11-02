"""Eingangsordner „Arbeitssystem“ (ab 1.5.1): Was du dort hineinziehst, sortiert das Programm selbst ein.

Ablauf je Mail (älteste zuerst):
  1. Art erkennen (Anfrage oder Bestellung, kunde.art_erkennen).
  2. Prüfen, ob die Suche ein Gerät findet (gewählte Artikel, Bestellnummern, V/A/W aus Text oder Datenblatt).
  3. Gefunden → „Automatisch“ dieser Art, sonst → „Selbst prüfen“ dieser Art.
Nur dieser eine Ordner wird automatisch geleert – alle anderen bleiben bei „verschoben wird nur per Klick“.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import kunde as K, suche as Q
from .einstellungen import _bestellpfad

_ARTIKELNR = re.compile(r"\b\d{6}\b")
_DATENBLATT = {".pdf", ".docx", ".doc"}
STANDARD_PFAD = "Posteingang/Arbeitssystem"


@dataclass
class Sortiert:
    mail: object
    erkennung: K.Erkennung
    gefunden: int
    ziel: str
    fehler: str = ""


@dataclass
class Lauf:
    sortiert: list[Sortiert] = field(default_factory=list)

    def text(self) -> str:
        ok = [s for s in self.sortiert if not s.fehler]
        auto = sum(1 for s in ok if s.gefunden)
        teile = [f"{len(ok)} aus „Arbeitssystem“ einsortiert"]
        if len(ok) - auto:
            teile.append(f"{len(ok) - auto} → Selbst prüfen")
        if len(ok) != len(self.sortiert):
            teile.append(f"{len(self.sortiert) - len(ok)} Fehler")
        return " · ".join(teile)


def zielordner(einstellungen, typ: str, art: str) -> str:
    """Eingestellter Ordner für Art (anfrage/bestellung) und Status (automatisch/pruefen), sonst Standardpfad."""
    ordner = [o for o in einstellungen.anfrageordner if o.typ == typ and not o.gemeinsam]
    passend = [o for o in ordner if o.art == art]
    if passend:
        return passend[0].pfad
    basis = "Posteingang/Anfragen/" + ("Automatisch" if art == "automatisch" else "Selbst prüfen")
    return _bestellpfad(basis) if typ == "bestellung" else basis


def geraete_finden(mail, e: K.Erkennung, geraete: list, datenblatt_lesen=None) -> int:
    """Wie viele Geräte würde die Suche liefern? 0 = „Selbst prüfen“. Ohne Oberfläche, ohne Rückfragen."""
    if not geraete:
        return 0
    nummern = {str(g.bestellnummer) for g in geraete}
    if e.positionen:
        return sum(1 for p in e.positionen if str(p.get("bestellnummer", "")) in nummern)
    text = (e.suchtext or "").strip()
    if text:
        a = Q.anfrage_lesen(text)
        if not a.leer():
            n = sum(1 for t in Q.suchen(geraete, a, knapp_zeigen=False) if t.kategorie != Q.KNAPP_DARUNTER)
            if n:
                return n
        elif _ARTIKELNR.search(text):
            n = len(Q.textsuche(geraete, text))
            if n:
                return n
    if datenblatt_lesen is None:
        from .datenblatt import lesen as datenblatt_lesen
    for pfad in getattr(mail, "anhaenge", []) or []:
        if Path(str(pfad)).suffix.lower() not in _DATENBLATT:
            continue
        try:
            fg = datenblatt_lesen(Path(pfad))
            a = Q.anfrage_lesen(fg.anfrage())
        except Exception:  # noqa: BLE001 – unlesbares Datenblatt → selbst prüfen
            continue
        if not a.leer():
            n = sum(1 for t in Q.suchen(geraete, a, knapp_zeigen=False) if t.kategorie != Q.KNAPP_DARUNTER)
            if n:
                return n
    return 0


def einsortieren(ol, einstellungen, geraete: list, anhang_ordner: Path, maximal: int = 25) -> Lauf:
    """Eingangsordner leeren (läuft im Hintergrund-Thread). Fehlt der Ordner, passiert nichts."""
    lauf = Lauf()
    pfad = (einstellungen.ordner_eingang or "").strip()
    if not pfad:
        return lauf
    try:
        mails = ol.mails(pfad, anhang_ordner, maximal=maximal)
    except Exception:  # noqa: BLE001 – Ordner gibt es (noch) nicht
        return lauf
    for m in reversed(mails):                                  # älteste zuerst
        e = K.erkennen(m, tuple(einstellungen.interne_domains))
        typ = "bestellung" if e.art == "bestellung" else "anfrage"
        try:
            n = geraete_finden(m, e, geraete)
        except Exception:  # noqa: BLE001
            n = 0
        ziel = zielordner(einstellungen, typ, "automatisch" if n else "pruefen")
        s = Sortiert(m, e, n, ziel)
        try:
            m.quelle = ol.verschieben(m.quelle, ziel)
            m.ordner = ziel
        except Exception as ex:  # noqa: BLE001
            s.fehler = str(ex)
        lauf.sortiert.append(s)
    return lauf
