"""Einstellungen (einstellungen.json im Programmordner, nicht im Repo)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import pfade

FREIGABE_JEDER = "Jeder darf freigeben"
FREIGABE_BERECHTIGTE = "Nur berechtigte Personen"
FREIGABE_VIER_AUGEN = "Vier-Augen-Prinzip"


@dataclass
class Einstellungen:
    anthropic_api_key: str = ""
    ki_modell: str = "claude-sonnet-5-5"
    ausgabe_ordner: str = ""          # leer = <Programmordner>\ausgabe
    archiv_ordner: str = ""           # leer = kein zusätzliches Archiv
    benutzer: str = ""
    freigabe_modus: str = FREIGABE_JEDER          # Chef entscheidet (Punkt 8)
    haendlerware_hersteller: list[str] = field(default_factory=list)   # z. B. ["EA Elektro-Automatik"] – aus, bis freigeschaltet
    hersteller: list[str] = field(default_factory=lambda: [
        "Absopulse", "EA Elektro-Automatik / Tektronix", "M.C.B", "Trustec", "Plating Electronics",
        "Gustav Klein", "Schäfer Elektronik", "SHT-Power SAS"])
    update_pruefen: bool = True
    legende_anzeigen: bool = True     # Tastenkürzel-Leiste rechts (F1)
    leere_ausblenden: bool = False    # in den Reitern leere Nicht-Kernfelder ausblenden
    fenster: str = ""                 # letzte Fenstergröße/-position, z. B. "1280x820+100+50"
    fenster_maximiert: bool = False
    start_sortierung: list = field(default_factory=lambda: ["geaendert", True])
    start_status: str = "Alle"

    def ausgabe(self) -> Path:
        return Path(self.ausgabe_ordner) if self.ausgabe_ordner else pfade.AUSGABE_DIR

    def ist_haendlerware(self, hersteller: str) -> bool:
        h = (hersteller or "").strip().lower()
        return bool(h) and any(h == x.strip().lower() for x in self.haendlerware_hersteller)


def laden(pfad: Path | None = None) -> Einstellungen:
    p = Path(pfad) if pfad else pfade.EINSTELLUNGEN_DATEI
    if not p.exists():
        e = Einstellungen()
        speichern(e, p)
        return e
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return Einstellungen()
    return Einstellungen(**{k: v for k, v in d.items() if k in Einstellungen.__dataclass_fields__})


def speichern(e: Einstellungen, pfad: Path | None = None) -> None:
    p = Path(pfad) if pfad else pfade.EINSTELLUNGEN_DATEI
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(e), ensure_ascii=False, indent=2), encoding="utf-8")
