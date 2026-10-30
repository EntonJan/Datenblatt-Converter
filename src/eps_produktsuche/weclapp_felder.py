"""Vorlagen für die Weclapp-Einführung: Feldliste (eigene Artikelattribute) und Artikel-Importdatei.

Grundlage ist der Feldkatalog des Datenblatt-Converters (katalog/feldkatalog.xlsx) – dieselben Felder, die der
Converter ausliest und die der Konfigurator filtert. Ergänzt um Felder, die Produktsuche/Konfigurator brauchen
(max. Geräte parallel, Kanäle, AC-Festspannungen). Die Artikel-Importdatei entsteht aus den Shopdaten; sobald der
Converter freigegebene Datensätze liefert, kommen die ausführlichen Werte von dort.

Weclapp-Typen der eigenen Attribute: STRING, LARGE_TEXT, DECIMAL, INTEGER, BOOLEAN, LIST (Einfachauswahl),
MULTISELECT_LIST, URL. Bereiche (von–bis) werden zu Text + Minimum + Maximum, damit Homepage-Filter und
Produktsuche mit Zahlen rechnen können und das Datenblatt trotzdem den Originaltext („0-60 VDC“) zeigt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PREFIX = "eps_"

# Felder, die in Weclapp Standardfelder bzw. eigene Bereiche sind (keine eigenen Attribute)
STANDARD = {
    "bestellnummer": ("Artikelnummer", "articleNumber", "Shop-Bestellnummer = Artikelnummer (offen: bestätigen)"),
    "typbezeichnung": ("Artikelname", "name", "EPS-Name, z. B. „E/PS 10060-1000 4U“"),
    "beschreibung": ("Beschreibung", "description", "DE; EN-Text siehe eps_beschreibung_en (Übersetzungen in Weclapp prüfen)"),
    "geraetetyp": ("Artikelkategorie / Warengruppe", "articleCategoryId",
                   "Warengruppen: AC/AC, AC/DC, DC/AC, DC/DC, Elektronische Last, Ladegeräte; bidirektional zusätzlich "
                   "Elektronische Last → als Mehrfachauswahl-Attribut eps_geraetetyp zusätzlich"),
    "gewicht": ("Gewicht (kg)", "articleGrossWeight", "Standardfeld Gewicht"),
    "hersteller": ("Bezugsquelle: Lieferant", "articleSupplySource.supplierId", "Lieferantendaten am Artikel"),
    "hersteller_typ": ("Bezugsquelle: Artikelname beim Lieferanten", "articleSupplySource.articleName",
                       "Originalbezeichnung des Herstellers"),
    "hersteller_bestellnummer": ("Bezugsquelle: Artikelnummer beim Lieferanten", "articleSupplySource.supplierArticleNumber",
                                 "Hersteller-Bestellnummer"),
    "bilder": ("Artikelbilder", "articleImages", "Bilder werden in Weclapp hochgeladen"),
    "optionen": ("Zubehör / verknüpfte Artikel", "—", "Optionen sind eigene Artikel mit einheitlicher Optionsnummer"),
}

TYP = {"Text": "STRING", "Ja/Nein": "BOOLEAN", "Schnittstelle": "LIST", "Auswahl": "LIST",
       "Mehrfachauswahl": "MULTISELECT_LIST", "Liste": "LARGE_TEXT", "Zahl": "DECIMAL"}

# zusätzliche Felder für Produktsuche/Konfigurator (nicht im Datenblatt)
ZUSATZ = [
    ("parallel_max", "max. Geräte parallel", "max. units in parallel", "INTEGER", "", "Produktsuche: n× parallel"),
    ("kanaele", "Anzahl Ausgänge/Kanäle", "Number of outputs/channels", "INTEGER", "",
     "Plausibilitätsprüfung P ≤ U × I × Kanäle"),
    ("ausgangsspannung_fest", "Ausgangsspannung fest (AC)", "Fixed output voltage (AC)", "STRING", "V",
     "z. B. „115; 200“ – AC-Festspannungen müssen ±10 % passen"),
    ("beschreibung_en", "Beschreibung (EN)", "Description (EN)", "LARGE_TEXT", "", "falls Weclapp keine Übersetzung kennt"),
    ("datenblatt_url", "Datenblatt (Link)", "Datasheet (link)", "URL", "", "Übergang: Shop-PDF; später Dokument in Weclapp"),
    ("geraetetyp", "Gerätetyp (alle)", "Device type (all)", "MULTISELECT_LIST", "",
     "Warengruppe + ggf. „Elektronische Last“ bei bidirektionalen Geräten"),
]


@dataclass
class Attribut:
    schluessel: str
    de: str
    en: str
    typ: str
    einheit: str = ""
    auswahl_de: str = ""
    auswahl_en: str = ""
    pflicht: bool = False
    filter: str = ""
    abschnitt: str = ""
    bemerkung: str = ""


def feldliste(katalog) -> tuple[list[Attribut], list[tuple]]:
    """(eigene Attribute, Standardfelder[(Feld-ID, Bezeichnung, Weclapp-Feld, Bemerkung)])."""
    attribute: list[Attribut] = []
    standard: list[tuple] = []
    schnitt = katalog.schnittstellen_werte
    for f in katalog.felder:
        if f.id in STANDARD:
            standard.append((f.id, f.de, *STANDARD[f.id][1:]))
            if f.id != "geraetetyp":
                continue
        if f.id == "geraetetyp":
            continue                                      # kommt als Zusatzfeld (Mehrfachauswahl)
        werte = [w for w in (schnitt if f.typ == "Schnittstelle" else f.auswahl) if w[0] not in ("—",)]
        if f.id == "bauform":
            werte = werte + [("DIN Rail", "DIN rail")]   # kommt im Shop vor, fehlt im Katalog
        basis = dict(einheit=f.einheit, pflicht=f.pflicht, filter=f.filterart, abschnitt=f.abschnitt,
                     auswahl_de="; ".join(w[0] for w in werte), auswahl_en="; ".join(w[1] for w in werte))
        if f.typ == "Bereich (von–bis)":
            attribute.append(Attribut(PREFIX + f.id, f.de, f.en, "STRING", bemerkung="Originaltext fürs Datenblatt",
                                      **{**basis, "filter": ""}))
            attribute.append(Attribut(PREFIX + f.id + "_min", f.de + " min", f.en + " min", "DECIMAL",
                                      bemerkung="Zahl in Grundeinheit", **basis))
            attribute.append(Attribut(PREFIX + f.id + "_max", f.de + " max", f.en + " max", "DECIMAL",
                                      bemerkung="Zahl in Grundeinheit", **basis))
            continue
        bemerkung = f.bemerkung or ""
        if f.typ == "Schnittstelle":
            bemerkung = "Standard / Option (leer = nicht vorhanden)"
        attribute.append(Attribut(PREFIX + f.id, f.de, f.en, TYP.get(f.typ, "STRING"), bemerkung=bemerkung, **basis))
    for sid, de, en, typ, einheit, bem in ZUSATZ:
        werte = next((x.auswahl for x in katalog.felder if x.id == sid), []) if sid == "geraetetyp" else []
        attribute.append(Attribut(PREFIX + sid, de, en, typ, einheit, "; ".join(w[0] for w in werte),
                                  "; ".join(w[1] for w in werte), abschnitt="Produktsuche/Konfigurator", bemerkung=bem))
    return attribute, standard


# ------------------------------------------------------------------------ Artikel-Import aus den Shopdaten

BAUFORM = {"19 Zoll": "19 Zoll", "Schrank/Cabinet": "Schrank", "Einbau/Built-in": "Einbaumodul", "Desktop": "Desktop",
           "Tower": "Tower", "DIN Rail": "DIN Rail"}


def _z(x) -> str:
    return "" if x is None else (f"{x:.6g}".replace(".", ","))


def _frequenz(g) -> str:
    if not g.ac:
        return "DC"
    if g.f_bereiche:
        return "einstellbar"
    fest = sorted(set(g.f_fest))
    if fest == [50, 60]:
        return "50/60 Hz"
    if len(fest) == 1 and fest[0] in (50, 60, 400):
        return f"{fest[0]:g} Hz"
    return ""


def _kanaele(g) -> int:
    m = re.search(r"(\d)\s*x\b", g.strom) or re.search(r"(\d)x\d", g.name)
    if m:
        return int(m.group(1))
    if re.search(r"triple|3-fach", g.name + " " + g.serie, re.I):
        return 3
    return 1


IMPORT_SPALTEN = [
    ("Artikelnummer", "articleNumber"), ("Artikelname", "name"), ("Warengruppe", "articleCategory"),
    ("Einheit", "unit"), ("Beschreibung", "description"),
    ("Lieferant (ausfüllen)", "supplier"), ("Hersteller-Typ (ausfüllen)", "supplierArticleName"),
    (PREFIX + "geraetetyp", ""), (PREFIX + "serie", ""),
    (PREFIX + "ausgangsspannung", ""), (PREFIX + "ausgangsspannung_min", ""), (PREFIX + "ausgangsspannung_max", ""),
    (PREFIX + "ausgangsspannung_fest", ""),
    (PREFIX + "ausgangsstrom", ""), (PREFIX + "ausgangsstrom_min", ""), (PREFIX + "ausgangsstrom_max", ""),
    (PREFIX + "ausgangsleistung", ""), (PREFIX + "ausgangsleistung_min", ""), (PREFIX + "ausgangsleistung_max", ""),
    (PREFIX + "eingangsspannung_min", ""), (PREFIX + "eingangsspannung_max", ""),
    (PREFIX + "ausgangsfrequenz", ""), (PREFIX + "bauform", ""), (PREFIX + "bidirektional", ""),
    (PREFIX + "netzrueckspeisung", ""), (PREFIX + "kuehlung", ""), (PREFIX + "parallelschaltung", ""),
    (PREFIX + "parallel_max", ""), (PREFIX + "reihenschaltung", ""), (PREFIX + "kanaele", ""),
    (PREFIX + "datenblatt_url", ""), ("Prüfen", ""),
]


def artikel_zeilen(geraete) -> list[list]:
    from .suche import unplausibel
    zeilen = []
    for g in sorted(geraete, key=lambda x: x.bestellnummer):
        typen = [g.geraetetyp] + (["Elektronische Last"] if g.bidirektional and g.geraetetyp != "Elektronische Last" else [])
        pruefen = []
        if unplausibel(g):
            pruefen.append("Leistung > U × I im Shop (Datenfehler, siehe Fehlerliste)")
        if g.aus_name:
            pruefen.append(f"{g.aus_name} nur aus der Typbezeichnung")
        if not g.bauart:
            pruefen.append("Bauform fehlt")
        kuehlung = "Wasser" if g.wasser == "ja" else ("Lüfter (Wasser optional)" if g.wasser == "option" else "")
        zeilen.append([
            g.bestellnummer, g.name, g.geraetetyp, "Stk", g.serie,
            "", "",
            "; ".join(typen), g.serie,
            g.spannung, _z(g.umin), _z(g.umax), "; ".join(_z(u) for u in g.u_fest),
            g.strom, "0" if g.imax is not None else "", _z(g.imax),
            g.leistung, "0" if g.pmax is not None else "", _z(g.pmax),
            _z(g.u_eingang), _z(g.u_eingang),
            _frequenz(g), BAUFORM.get(g.bauart, g.bauart), "ja" if g.bidirektional else "nein",
            "ja" if g.rueckspeisung else "nein", kuehlung,
            "Ja" if g.parallel else "Nein", g.parallel_max or "", "ja" if g.reihe else "nein", _kanaele(g),
            g.pdf_url, "; ".join(pruefen),
        ])
    return zeilen
