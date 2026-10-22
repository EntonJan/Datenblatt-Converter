"""Datensatz eines Geräts – das, was gespeichert, geprüft und in PDF/Weclapp ausgegeben wird."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime

ENTWURF = "Entwurf"
FREIGEGEBEN = "Freigegeben"

REGEL_EPS = "EPS"
REGEL_HAENDLER = "Händlerware"

HERKUNFT_HAND = "hand"
HERKUNFT_PDF = "pdf"
HERKUNFT_KI = "ki"


def jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Wert:
    de: str = ""                 # Text fürs deutsche Datenblatt
    en: str = ""                 # Text fürs englische Datenblatt
    min: float | None = None     # Bereich/Zahl: in Grundeinheit (V, A, W, °C, Ω, kg …)
    max: float | None = None
    ja: bool | None = None       # Ja/Nein
    auswahl: list[str] = field(default_factory=list)   # Auswahl/Mehrfachauswahl (deutsche Werte)
    if_status: str = ""          # Schnittstelle: Standard / Option / ""
    if_code: str = ""            # Schnittstelle: Optionscode, z. B. EPS/IF-AB R
    herkunft: str = HERKUNFT_HAND
    geprueft: bool = False
    en_manuell: bool = False     # True, wenn der englische Text von Hand geändert wurde
    fundstelle: str = ""         # z. B. „Seite 2: Output Voltage 0-750 V“

    def leer(self) -> bool:
        return not (self.de or self.en or self.min is not None or self.max is not None or self.ja is not None
                    or self.auswahl or self.if_status)

    @classmethod
    def aus_dict(cls, d: dict) -> "Wert":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Option:
    code: str = ""
    de: str = ""
    en: str = ""
    nr: str = ""                 # einheitliche Optionsnummer (Stammliste folgt in Weclapp)


@dataclass
class Eintrag:
    de: str = ""
    en: str = ""


@dataclass
class Bild:
    datei: str = ""              # Dateiname im Datensatz-Ordner
    de: str = ""
    en: str = ""


@dataclass
class Datensatz:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = ENTWURF
    regel: str = REGEL_EPS
    erstellt: str = field(default_factory=jetzt)
    geaendert: str = field(default_factory=jetzt)
    freigegeben_am: str = ""
    quelle_pdf: str = ""
    modell_auswahl: str = ""
    werte: dict[str, Wert] = field(default_factory=dict)
    optionen: list[Option] = field(default_factory=list)
    lieferumfang: list[Eintrag] = field(default_factory=list)
    bilder: list[Bild] = field(default_factory=list)
    weclapp: dict = field(default_factory=lambda: {"status": "ausstehend"})
    format_version: int = 1

    def wert(self, fid: str) -> Wert:
        if fid not in self.werte:
            self.werte[fid] = Wert()
        return self.werte[fid]

    def text(self, fid: str, sprache: str = "de") -> str:
        w = self.werte.get(fid)
        if not w:
            return ""
        return (w.en or w.de) if sprache == "en" else w.de

    @property
    def bestellnummer(self) -> str:
        return self.text("bestellnummer").strip()

    @property
    def titel(self) -> str:
        return self.text("typbezeichnung").strip()

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def aus_dict(cls, d: dict) -> "Datensatz":
        ds = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__
                    and k not in ("werte", "optionen", "lieferumfang", "bilder")})
        ds.werte = {k: Wert.aus_dict(v) for k, v in d.get("werte", {}).items()}
        ds.optionen = [Option(**o) for o in d.get("optionen", [])]
        ds.lieferumfang = [Eintrag(**e) for e in d.get("lieferumfang", [])]
        ds.bilder = [Bild(**b) for b in d.get("bilder", [])]
        return ds
