"""Einstellungen der Produktsuche (EPS-Produktsuche-Daten/einstellungen.json, pro Rechner/Benutzer).

Experimentelle Funktionen (Outlook-Anfragen, später Weclapp) sind standardmäßig aus.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path


TYPEN = {"anfrage": "Anfragen", "bestellung": "Bestellungen"}


@dataclass
class Anfrageordner:
    pfad: str                      # Outlook-Pfad, z. B. „Posteingang/Anfragen/Automatisch“
    art: str = "pruefen"           # "automatisch" (Homepage-Formular, sicher) oder "pruefen" (selbst prüfen)
    gemeinsam: bool = False        # gemeinsames Postfach: beim Öffnen sofort nach „In Bearbeitung“ verschieben
    typ: str = ""                  # "anfrage" oder "bestellung" (leer = aus dem Pfad: „Bestell…“ → bestellung)

    def __post_init__(self):
        if self.typ not in TYPEN:
            self.typ = "bestellung" if re.search(r"bestell|order", self.pfad, re.I) else "anfrage"

    @property
    def anzeige(self) -> str:
        name = f"{TYPEN[self.typ]} · {'Automatisch' if self.art == 'automatisch' else 'Selbst prüfen'}"
        return name + (f" · gemeinsam ({self.pfad.split('/')[0]})" if self.gemeinsam else "")


def _bestellpfad(pfad: str) -> str:
    """„Posteingang/Anfragen/Automatisch“ → „Posteingang/Bestellungen/Automatisch“."""
    teile = pfad.split("/")
    return "/".join("Bestellungen" if t.lower() in ("anfragen", "anfrage", "inquiries") else t for t in teile)


@dataclass
class Einstellungen:
    experimentell: bool = False
    anfrageordner: list[Anfrageordner] = field(default_factory=lambda: [
        Anfrageordner("Posteingang/Anfragen/Automatisch", "automatisch"),
        Anfrageordner("Posteingang/Anfragen/Selbst prüfen", "pruefen"),
        Anfrageordner("Posteingang/Bestellungen/Automatisch", "automatisch", typ="bestellung"),
        Anfrageordner("Posteingang/Bestellungen/Selbst prüfen", "pruefen", typ="bestellung"),
    ])
    ordner_erledigt: str = "Erledigt"              # Name = Unterordner des Ordners, mit „/“ = fester Ordner
    ordner_erledigt_bestellung: str = ""           # dasselbe für Bestellungen; leer = aus ordner_erledigt abgeleitet
    ordner_in_bearbeitung: str = "In Bearbeitung"
    preisfrist_monate: int = 6                      # ab wann ein Einkaufspreis als zu alt gilt (Weclapp)
    interne_domains: list[str] = field(default_factory=lambda: ["eps-germany.de"])   # Weiterleitungen erkennen
    weclapp_adresse: str = ""                       # z. B. „eps.weclapp.com“; „demo“ = nachgebautes Weclapp
    datenquelle: str = "shop"                       # "shop" oder "weclapp" (Gerätedaten für die Suche)
    dunkelmodus: bool = False
    ordner_eingang: str = "Posteingang/Arbeitssystem"   # was hier landet, sortiert das Programm selbst ein
    vorsortieren: bool = True          # beim Start alle Anfrage-/Bestellordner lesen und zählen (verschiebt nichts)

    @staticmethod
    def laden(pfad: Path) -> "Einstellungen":
        try:
            d = json.loads(Path(pfad).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return Einstellungen()
        e = Einstellungen()
        for k in ("experimentell", "ordner_erledigt", "ordner_in_bearbeitung", "preisfrist_monate", "interne_domains",
                  "weclapp_adresse", "datenquelle", "dunkelmodus", "ordner_erledigt_bestellung", "vorsortieren", "ordner_eingang"):
            if k in d:
                setattr(e, k, d[k])
        if isinstance(d.get("anfrageordner"), list):
            e.anfrageordner = [Anfrageordner(**{k: v for k, v in o.items() if k in ("pfad", "art", "gemeinsam", "typ")})
                               for o in d["anfrageordner"] if isinstance(o, dict) and o.get("pfad")]
            e.bestellordner_ergaenzen()
        return e

    def bestellordner_ergaenzen(self) -> None:
        """Ältere Einstellungen (nur Anfrage-Ordner): Bestellungen-Ordner daneben anlegen, gleiche Aufteilung."""
        if any(o.typ == "bestellung" for o in self.anfrageordner):
            return
        for o in list(self.anfrageordner):
            if not o.gemeinsam and _bestellpfad(o.pfad) != o.pfad:
                self.anfrageordner.append(Anfrageordner(_bestellpfad(o.pfad), o.art, False, "bestellung"))

    def erledigt_fuer(self, typ: str) -> str:
        """Erledigt-Ziel je Art: bei Bestellungen eigener Ordner (Posteingang/Bestellungen/Erledigt)."""
        if typ != "bestellung":
            return self.ordner_erledigt
        if self.ordner_erledigt_bestellung:
            return self.ordner_erledigt_bestellung
        return _bestellpfad(self.ordner_erledigt) if "/" in self.ordner_erledigt else self.ordner_erledigt

    def speichern(self, pfad: Path) -> None:
        pfad = Path(pfad)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(pfad)
