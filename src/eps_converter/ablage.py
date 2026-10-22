"""Datenablage. Version 1: lokal als JSON-Dateien (daten/<id>/datensatz.json).

Austauschbar: Später kann eine Cloud- bzw. Weclapp-Ablage dieselbe Schnittstelle
(alle, laden, speichern, loeschen, ordner) bereitstellen.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from .modell import Datensatz, jetzt
from . import pfade


class LokaleAblage:
    def __init__(self, basis: Path | None = None):
        self.basis = Path(basis) if basis else pfade.DATEN_DIR
        self.basis.mkdir(parents=True, exist_ok=True)

    def ordner(self, ds_id: str) -> Path:
        p = self.basis / ds_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _datei(self, ds_id: str) -> Path:
        return self.basis / ds_id / "datensatz.json"

    def alle(self) -> list[Datensatz]:
        out = []
        for d in sorted(self.basis.iterdir()) if self.basis.exists() else []:
            f = d / "datensatz.json"
            if f.exists():
                try:
                    out.append(Datensatz.aus_dict(json.loads(f.read_text(encoding="utf-8"))))
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
        return sorted(out, key=lambda x: x.geaendert, reverse=True)

    def laden(self, ds_id: str) -> Datensatz:
        return Datensatz.aus_dict(json.loads(self._datei(ds_id).read_text(encoding="utf-8")))

    def speichern(self, ds: Datensatz) -> None:
        ds.geaendert = jetzt()
        ziel = self._datei(ds.id)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        # atomar schreiben, damit bei Absturz keine halbe Datei entsteht
        fd, tmp = tempfile.mkstemp(dir=ziel.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(ds.to_dict(), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, ziel)

    def loeschen(self, ds_id: str) -> None:
        p = self.basis / ds_id
        if p.exists():
            shutil.rmtree(p)

    def finde_hersteller_nr(self, hersteller_nr: str, ausser_id: str = "") -> Datensatz | None:
        key = (hersteller_nr or "").strip().lower()
        if not key:
            return None
        for ds in self.alle():
            if ds.id != ausser_id and ds.text("hersteller_bestellnummer").strip().lower() == key:
                return ds
        return None

    def finde_bestellnummer(self, nr: str, ausser_id: str = "") -> Datensatz | None:
        key = (nr or "").strip()
        if not key:
            return None
        for ds in self.alle():
            if ds.id != ausser_id and ds.bestellnummer == key:
                return ds
        return None
