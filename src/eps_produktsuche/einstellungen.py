"""Einstellungen der Produktsuche (EPS-Produktsuche-Daten/einstellungen.json, pro Rechner/Benutzer).

Experimentelle Funktionen (Outlook-Anfragen, später Weclapp) sind standardmäßig aus.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Anfrageordner:
    pfad: str                      # Outlook-Pfad, z. B. „Posteingang/Anfragen/Automatisch“
    art: str = "pruefen"           # "automatisch" (Homepage-Formular, sicher) oder "pruefen" (selbst prüfen)
    gemeinsam: bool = False        # gemeinsames Postfach: beim Öffnen sofort nach „In Bearbeitung“ verschieben

    @property
    def anzeige(self) -> str:
        return f"{'Automatisch' if self.art == 'automatisch' else 'Selbst prüfen'}: {self.pfad}" + \
            ("  (gemeinsam)" if self.gemeinsam else "")


@dataclass
class Einstellungen:
    experimentell: bool = False
    anfrageordner: list[Anfrageordner] = field(default_factory=lambda: [
        Anfrageordner("Posteingang/Anfragen/Automatisch", "automatisch"),
        Anfrageordner("Posteingang/Anfragen/Selbst prüfen", "pruefen"),
    ])
    ordner_erledigt: str = "Erledigt"              # Unterordner des jeweiligen Anfrageordners
    ordner_in_bearbeitung: str = "In Bearbeitung"
    preisfrist_monate: int = 6                      # ab wann ein Einkaufspreis als zu alt gilt (Weclapp)

    @staticmethod
    def laden(pfad: Path) -> "Einstellungen":
        try:
            d = json.loads(Path(pfad).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return Einstellungen()
        e = Einstellungen()
        for k in ("experimentell", "ordner_erledigt", "ordner_in_bearbeitung", "preisfrist_monate"):
            if k in d:
                setattr(e, k, d[k])
        if isinstance(d.get("anfrageordner"), list):
            e.anfrageordner = [Anfrageordner(**{k: v for k, v in o.items() if k in ("pfad", "art", "gemeinsam")})
                               for o in d["anfrageordner"] if isinstance(o, dict) and o.get("pfad")]
        return e

    def speichern(self, pfad: Path) -> None:
        pfad = Path(pfad)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(pfad)
