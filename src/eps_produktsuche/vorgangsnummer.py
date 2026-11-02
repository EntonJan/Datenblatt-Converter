"""Interne Vorgangsnummern der Produktsuche (ab 1.5.1): Anf00001 … für Anfragen, Bes00001 … für Bestellungen.

Jede Mail bekommt beim ersten Sehen (Anfragen-Seite, Vorsortieren, Eingangsordner) eine Nummer, die bleibt – auch
wenn die Mail in Outlook verschoben wird. Erkannt wird sie an Absender, Eingangszeit und Betreff (die Outlook-EntryID
ändert sich beim Verschieben). Wird die Art gewechselt (Anfrage ↔ Bestellung), gibt es eine neue Nummer der anderen
Art; die alte wird nicht wiederverwendet. Gespeichert in vorgangsnummern.json im Datenordner.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

PRAEFIX = {"anfrage": "Anf", "bestellung": "Bes"}
STELLEN = 5


def format_nr(typ: str, n: int) -> str:
    return f"{PRAEFIX[typ]}{n:0{STELLEN}d}"


def schluessel(mail) -> str:
    roh = "|".join([(getattr(mail, "absender_email", "") or "").strip().lower(),
                    (getattr(mail, "empfangen", "") or "").strip(),
                    " ".join((getattr(mail, "betreff", "") or "").split())])
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:20]


class Nummern:
    def __init__(self, pfad: Path):
        self.pfad = Path(pfad)
        self._lock = threading.Lock()
        self.zaehler = {"anfrage": 0, "bestellung": 0}
        self.mails: dict[str, str] = {}
        try:
            d = json.loads(self.pfad.read_text(encoding="utf-8"))
            self.zaehler.update({k: int(v) for k, v in d.get("zaehler", {}).items() if k in PRAEFIX})
            self.mails = dict(d.get("mails", {}))
        except (OSError, ValueError):
            pass

    def _speichern(self) -> None:
        tmp = self.pfad.with_suffix(".tmp")
        try:
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps({"zaehler": self.zaehler, "mails": self.mails}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            os.replace(tmp, self.pfad)
        except OSError:
            pass

    def vorhanden(self, mail) -> str:
        return self.mails.get(schluessel(mail), "")

    def nummer(self, mail, typ: str) -> str:
        """Nummer der Mail; neu vergeben, wenn sie noch keine hat oder ihre Nummer zur anderen Art gehört."""
        typ = typ if typ in PRAEFIX else "anfrage"
        k = schluessel(mail)
        with self._lock:
            alt = self.mails.get(k, "")
            if alt.startswith(PRAEFIX[typ]):
                return alt
            self.zaehler[typ] += 1
            nr = format_nr(typ, self.zaehler[typ])
            self.mails[k] = nr
            self._speichern()
            return nr

    def viele(self, paare) -> list[str]:
        """[(Mail, Typ)] auf einmal – speichert nur einmal."""
        neu = False
        erg = []
        with self._lock:
            for mail, typ in paare:
                typ = typ if typ in PRAEFIX else "anfrage"
                k = schluessel(mail)
                alt = self.mails.get(k, "")
                if not alt.startswith(PRAEFIX[typ]):
                    self.zaehler[typ] += 1
                    alt = format_nr(typ, self.zaehler[typ])
                    self.mails[k] = alt
                    neu = True
                erg.append(alt)
            if neu:
                self._speichern()
        return erg
