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

from .modell import Datensatz, ENTWURF, jetzt
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
        return self._lesen(self.basis)

    def _lesen(self, ordner: Path) -> list[Datensatz]:
        out = []
        for d in sorted(ordner.iterdir()) if ordner.exists() else []:
            if d.name.startswith("_"):
                continue                                # z. B. _papierkorb
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

    def duplizieren(self, ds_id: str) -> Datensatz:
        """Kopie als neuer Entwurf (z. B. für ein weiteres Gerät derselben Serie).
        Bestellnummern und Prüfhaken werden zurückgesetzt, Bilder und Original-PDF mitkopiert."""
        alt = self.laden(ds_id)
        neu = Datensatz.aus_dict(alt.to_dict())
        neu.id = Datensatz().id
        neu.status = ENTWURF
        neu.erstellt = jetzt()
        neu.freigegeben_am = ""
        neu.weclapp = {"status": "ausstehend"}
        for fid in ("bestellnummer", "hersteller_bestellnummer"):
            neu.werte.pop(fid, None)
        for w in neu.werte.values():
            w.geprueft = False
        neu.protokoll = []
        quelle, ziel = self.basis / ds_id, self.ordner(neu.id)
        for f in quelle.iterdir():
            if f.is_file() and f.name != "datensatz.json":
                shutil.copy2(f, ziel / f.name)
        self.speichern(neu)
        return neu

    # ---- Papierkorb: gelöschte Entwürfe werden verschoben, nicht sofort gelöscht
    @property
    def papierkorb_dir(self) -> Path:
        return self.basis / "_papierkorb"

    def loeschen(self, ds_id: str, endgueltig: bool = False) -> None:
        p = self.basis / ds_id
        if not p.exists():
            return
        if endgueltig:
            shutil.rmtree(p)
            return
        self.papierkorb_dir.mkdir(parents=True, exist_ok=True)
        ziel = self.papierkorb_dir / ds_id
        if ziel.exists():
            shutil.rmtree(ziel)
        shutil.move(str(p), str(ziel))
        (ziel / "geloescht_am.txt").write_text(jetzt(), encoding="utf-8")

    def papierkorb(self) -> list[tuple[Datensatz, str]]:
        """Inhalt des Papierkorbs: (Datensatz, gelöscht am)."""
        out = []
        for ds in self._lesen(self.papierkorb_dir):
            f = self.papierkorb_dir / ds.id / "geloescht_am.txt"
            out.append((ds, f.read_text(encoding="utf-8").strip() if f.exists() else ""))
        return sorted(out, key=lambda x: x[1], reverse=True)

    def wiederherstellen(self, ds_id: str) -> None:
        q = self.papierkorb_dir / ds_id
        if not q.exists():
            return
        (q / "geloescht_am.txt").unlink(missing_ok=True)
        ziel = self.basis / ds_id
        if ziel.exists():
            shutil.rmtree(ziel)
        shutil.move(str(q), str(ziel))

    def endgueltig_loeschen(self, ds_id: str) -> None:
        q = self.papierkorb_dir / ds_id
        if q.exists():
            shutil.rmtree(q)

    def papierkorb_leeren(self) -> int:
        n = 0
        for ds, _ in self.papierkorb():
            self.endgueltig_loeschen(ds.id)
            n += 1
        return n

    def finde_hersteller_nr(self, hersteller_nr: str, ausser_id: str = "") -> Datensatz | None:
        key = (hersteller_nr or "").strip().lower()
        if not key:
            return None
        for ds in self.alle():
            if ds.id != ausser_id and ds.text("hersteller_bestellnummer").strip().lower() == key:
                return ds
        return None

    def finde_typbezeichnung(self, name: str, ausser_id: str = "") -> Datensatz | None:
        key = " ".join((name or "").lower().split())
        if not key:
            return None
        for ds in self.alle():
            if ds.id != ausser_id and " ".join(ds.titel.lower().split()) == key:
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
