"""SelectLine-Artikelexport (ab 1.5.1): korrigiert die Shopdaten und kann Artikel ohne Shopseite ergänzen.

Der Export ist eine CSV ohne Kopfzeile („Text mit Trennzeichen“, ; und "), 325 Spalten. Die Spaltennummern unten
sind am Export vom 02.11.2026 bestimmt. Bei gleicher Bestellnummer gilt SelectLine (aktueller als der Shop).

Datei: selectline-artikel.csv im Datenordner (neben shopdaten.json). Fehlt sie, bleibt alles wie bisher.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import shop

DATEI = "selectline-artikel.csv"

# Spalten (0-basiert)
NR, BEZEICHNUNG, ZUSATZ, STATUS = 0, 2, 3, 33
LIEFERANT, HERSTELLER_NR = 30, 31
LEISTUNG, SPANNUNG, STROM = 282, 283, 284
RICHTUNG = 319                       # „Bidirektional“ / „Unidirektional“
SPALTEN = 325

_GESPERRT = re.compile(r"nicht (mehr )?verwenden|nicht mehr verfügbar|nicht verwenden", re.I)
# Gerätetyp für Artikel ohne Shopseite – aus dem Zusatztext (Reihenfolge zählt)
_TYPEN = [
    (re.compile(r"\bLast", re.I), shop.LAST),
    (re.compile(r"Frequenzwandler|Frequenzkonverter|Avionik|AC/AC", re.I), "AC/AC"),
    (re.compile(r"wechselrichter", re.I), "DC/AC"),
    (re.compile(r"DC/DC|DC-DC", re.I), "DC/DC"),
    (re.compile(r"Ladeger", re.I), "Ladegeräte"),
    (re.compile(r"Netzger|Netzteil|Stromquelle|Spannungsquelle|Testsystem|Grundsystem|Konverter|Batterietester|"
                r"Hochspannung|Einschub|Leistungsverstärker|USV|Stromversorgung", re.I), "AC/DC"),
]


@dataclass
class Artikel:
    nr: str
    name: str
    zusatz: str
    status: str
    spannung: str
    strom: str
    leistung: str
    lieferant: str = ""
    hersteller_nr: str = ""
    bidirektional: bool = False

    @property
    def aktiv(self) -> bool:
        return self.status == "A" and not _GESPERRT.search(self.zusatz)


@dataclass
class Bericht:
    korrigiert: list[tuple[str, str, str, str]] = field(default_factory=list)   # (Nr., Feld, Shop, SelectLine)
    nicht_in_selectline: list[str] = field(default_factory=list)
    ergaenzt: int = 0
    ohne_shop: int = 0                                                           # aufnehmbar, aber ausgeschaltet

    def text(self) -> str:
        geraete = len({k[0] for k in self.korrigiert})
        teile = [f"SelectLine: {geraete} Geräte korrigiert"]
        if self.ergaenzt:
            teile.append(f"{self.ergaenzt} ohne Shopseite ergänzt")
        return ", ".join(teile)


def _einzeilig(x: str) -> str:
    return " ".join((x or "").split())


def lesen(pfad: Path) -> dict[str, Artikel]:
    """CSV → {Bestellnummer: Artikel}. UTF-8 (mit/ohne BOM), notfalls Windows-1252."""
    pfad = Path(pfad)
    for kodierung in ("utf-8-sig", "cp1252"):
        try:
            with pfad.open(encoding=kodierung, newline="") as f:
                zeilen = list(csv.reader(f, delimiter=";"))
            break
        except UnicodeDecodeError:
            continue
    else:
        return {}
    artikel = {}
    for r in zeilen:
        if len(r) < SPALTEN - 5 or not r[NR].strip():
            continue
        nr = r[NR].strip()
        artikel[nr] = Artikel(nr=nr, name=_einzeilig(r[BEZEICHNUNG]), zusatz=_einzeilig(r[ZUSATZ]),
                              status=r[STATUS].strip(), spannung=_einzeilig(r[SPANNUNG]), strom=_einzeilig(r[STROM]),
                              leistung=_einzeilig(r[LEISTUNG]), lieferant=r[LIEFERANT].strip(),
                              hersteller_nr=_einzeilig(r[HERSTELLER_NR]),
                              bidirektional=r[RICHTUNG].strip().lower() == "bidirektional")
    return artikel


def geraetetyp(a: Artikel) -> str:
    for muster, typ in _TYPEN:
        if muster.search(a.zusatz):
            return typ
    return ""


def _serie(name: str) -> str:
    """„EPS/HC 1150-250“ → „EPS/HC“ (Typbezeichnung ohne Nummer) – zum Gruppieren in der Trefferliste."""
    m = re.match(r"([A-Za-z/.\- ]+?)\s*\d", name)
    return (m.group(1).strip() if m else name.split(" ")[0]) + " (SelectLine)"


def neues_geraet(a: Artikel) -> shop.Geraet | None:
    """Artikel ohne Shopseite → Gerät für die Suche (nur aktiv, mit Spannung und Strom und erkennbarem Typ)."""
    typ = geraetetyp(a)
    if not (a.aktiv and a.spannung and a.strom and typ):
        return None
    g = shop.Geraet(bestellnummer=a.nr, name=f"{a.name} {a.zusatz}".strip(), serie=_serie(a.name), geraetetyp=typ,
                    bidirektional=a.bidirektional or "bidirektional" in a.zusatz.lower(),
                    spannung=a.spannung, strom=a.strom, leistung=a.leistung, herkunft="selectline",
                    hersteller_nr=a.hersteller_nr)
    g.rueckspeisung = bool(re.search(r"rückspeis|regenerativ", a.zusatz, re.I))
    shop.auswerten(g)
    g.phasen = shop.phasen_aus(g)
    return g


def anwenden(geraete: list[shop.Geraet], artikel: dict[str, Artikel], ohne_shop: bool = False
             ) -> tuple[list[shop.Geraet], Bericht]:
    """Shopgeräte mit SelectLine abgleichen (SelectLine gewinnt), optional Artikel ohne Shopseite ergänzen.
    Ändert die Geräte in der Liste; gibt (Liste, Bericht) zurück."""
    b = Bericht()
    if not artikel:
        return geraete, b
    vorhanden = set()
    for g in geraete:
        vorhanden.add(g.bestellnummer)
        a = artikel.get(g.bestellnummer)
        if a is None:
            b.nicht_in_selectline.append(g.bestellnummer)
            continue
        g.herkunft = "shop+selectline"
        g.hersteller_nr = a.hersteller_nr
        geaendert = False
        name = f"{a.name} {a.zusatz}".strip()
        for feld, neu in (("name", name), ("spannung", a.spannung), ("strom", a.strom), ("leistung", a.leistung)):
            alt = getattr(g, feld)
            if neu and _einzeilig(alt) != neu:
                b.korrigiert.append((g.bestellnummer, feld, alt, neu))
                setattr(g, feld, neu)
                geaendert = True
        if geaendert:
            shop.auswerten(g)
            g.phasen = shop.phasen_aus(g)
    ergaenzt = [x for a in artikel.values() if a.nr not in vorhanden and (x := neues_geraet(a))]
    b.ohne_shop = len(ergaenzt)
    if ohne_shop:
        geraete = geraete + ergaenzt
        b.ergaenzt = len(ergaenzt)
    return geraete, b


_CACHE: dict = {}


def laden_gecacht(pfad: Path) -> dict[str, Artikel]:
    """lesen() mit Zwischenspeicher: im Speicher und als selectline-artikel.cache.json neben der CSV (der volle
    Export hat 325 Spalten und braucht beim Lesen ca. 1–2 s – der Cache nur einen Bruchteil, wichtig für den Start)."""
    import json
    from dataclasses import asdict
    pfad = Path(pfad)
    try:
        stempel = pfad.stat().st_mtime
    except OSError:
        return {}
    if _CACHE.get("pfad") == str(pfad) and _CACHE.get("stempel") == stempel:
        return _CACHE["artikel"]
    cache = pfad.with_suffix(".cache.json")
    artikel = None
    try:
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("stempel") == stempel and d.get("version") == 1:
            artikel = {a["nr"]: Artikel(**a) for a in d["artikel"]}
    except (OSError, ValueError, TypeError, KeyError):
        pass
    if artikel is None:
        artikel = lesen(pfad)
        try:
            cache.write_text(json.dumps({"version": 1, "stempel": stempel, "artikel": [asdict(a) for a in artikel.values()]},
                                        ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    _CACHE.update(pfad=str(pfad), stempel=stempel, artikel=artikel)
    return artikel
