"""Gerätedaten aus Weclapp statt aus dem Shop (Einstellungen → Datenquelle).

Weclapp-Artikel tragen die technischen Werte als eigene Attribute „eps_…“ (siehe weclapp_felder / Weclapp-Feldliste).
Hier werden sie in dieselben Geraet-Objekte umgesetzt, mit denen Suche, Gruppierung, Gegenüberstellung usw.
arbeiten – die Oberfläche merkt keinen Unterschied.

Weclapp liefert eigene Attribute als Liste {attributeDefinitionId, stringValue | numberValue | booleanValue |
selectedValueId | selectedValues}; die Zuordnung Schlüssel ↔ ID kommt aus /customAttributeDefinition.
(Struktur nach API-Doku; im 30-Tage-Test prüfen.)
"""
from __future__ import annotations

import re

from .shop import Geraet, LAST, AC_AUSGANG, ist_rueckspeisend, wasserkuehlung
from .weclapp_felder import PREFIX

PFAD_DEFINITIONEN = "/customAttributeDefinition"
PFAD_ARTIKEL = "/article"
PFAD_KATEGORIEN = "/articleCategory"
SEITE = 100

BAUFORM_ZURUECK = {"19 Zoll": "19 Zoll", "Schrank": "Schrank/Cabinet", "Einbaumodul": "Einbau/Built-in",
                   "Desktop": "Desktop", "Tower": "Tower", "DIN Rail": "DIN Rail"}
GERAETETYPEN = {"AC/AC", "AC/DC", "DC/AC", "DC/DC", LAST, "Ladegeräte"}


def _alle(t, pfad: str, fortschritt=None) -> list[dict]:
    ergebnis, seite = [], 1
    while True:
        teil = t("GET", pfad, {"page": seite, "pageSize": SEITE}).get("result", [])
        ergebnis += teil
        if fortschritt:
            fortschritt(f"{pfad.strip('/')}: {len(ergebnis)}", len(ergebnis), len(ergebnis) + (SEITE if len(teil) == SEITE else 0))
        if len(teil) < SEITE:
            return ergebnis
        seite += 1


def attribute_lesen(artikel: dict, definitionen: dict[str, dict]) -> dict[str, object]:
    """customAttributes eines Artikels → {Schlüssel: Wert} (Auswahlwerte als Text, Mehrfachauswahl als Liste)."""
    werte: dict[str, object] = {}
    for ca in artikel.get("customAttributes", []) or []:
        d = definitionen.get(str(ca.get("attributeDefinitionId")))
        if not d:
            continue
        auswahl = {str(v.get("id")): v.get("value") for v in d.get("selectableValues", []) or []}
        if ca.get("selectedValues"):
            wert = [auswahl.get(str(v.get("id")), "") for v in ca["selectedValues"]]
        elif ca.get("selectedValueId") is not None:
            wert = auswahl.get(str(ca["selectedValueId"]), "")
        elif ca.get("booleanValue") is not None:
            wert = bool(ca["booleanValue"])
        elif ca.get("numberValue") not in (None, ""):
            wert = float(str(ca["numberValue"]).replace(",", "."))
        else:
            wert = ca.get("stringValue") or ""
        werte[d.get("attributeKey", "")] = wert
    return werte


def _zahl(w) -> float | None:
    if w in (None, ""):
        return None
    try:
        return float(str(w).replace(",", "."))
    except ValueError:
        return None


def geraet(artikel: dict, a: dict[str, object], kategorien: dict[str, str]) -> Geraet:
    p = PREFIX
    typen = a.get(p + "geraetetyp") or []
    typen = typen if isinstance(typen, list) else [typen]
    typ = kategorien.get(str(artikel.get("articleCategoryId")), "")
    if typ not in GERAETETYPEN:
        typ = next((t for t in typen if t in GERAETETYPEN and t != LAST), typen[0] if typen else "")
    name = artikel.get("name", "")
    serie = str(a.get(p + "serie") or "")
    frequenz = str(a.get(p + "ausgangsfrequenz") or "")
    g = Geraet(bestellnummer=str(artikel.get("articleNumber", "")), name=name, serie=serie, geraetetyp=typ,
               spannung=str(a.get(p + "ausgangsspannung") or ""), strom=str(a.get(p + "ausgangsstrom") or ""),
               leistung=str(a.get(p + "ausgangsleistung") or ""),
               bauart=BAUFORM_ZURUECK.get(str(a.get(p + "bauform") or ""), str(a.get(p + "bauform") or "")),
               pdf_url=str(a.get(p + "datenblatt_url") or ""))
    g.umin, g.umax = _zahl(a.get(p + "ausgangsspannung_min")), _zahl(a.get(p + "ausgangsspannung_max"))
    g.imax, g.pmax = _zahl(a.get(p + "ausgangsstrom_max")), _zahl(a.get(p + "ausgangsleistung_max"))
    g.bidirektional = a.get(p + "bidirektional") is True or LAST in typen and typ != LAST
    g.rueckspeisung = a.get(p + "netzrueckspeisung") is True or ist_rueckspeisend(name, serie)
    kuehlung = str(a.get(p + "kuehlung") or "")
    g.wasser = "ja" if kuehlung == "Wasser" else ("option" if "Wasser" in kuehlung else wasserkuehlung(name, serie, ""))
    g.ac = typ in AC_AUSGANG or (frequenz not in ("", "DC"))
    fest = str(a.get(p + "ausgangsspannung_fest") or "")
    g.u_fest = [z for z in (_zahl(x) for x in re.split(r"[;/,]\s*", fest) if x.strip()) if z]
    if g.ac and not g.u_fest and g.umax and g.umin is not None and g.umin < g.umax:
        g.u_bereiche = [[g.umin, g.umax]]
    if frequenz == "einstellbar":
        lo, hi = _zahl(a.get(p + "ausgangsfrequenz_min")), _zahl(a.get(p + "ausgangsfrequenz_max"))
        g.f_bereiche = [[lo or 0.0, hi or 1e6]]
    elif frequenz.endswith("Hz"):
        g.f_fest = [float(x) for x in re.findall(r"\d+", frequenz)]
    fest_hz = [z for z in (_zahl(x) for x in re.split(r"[;/,]\s*", str(a.get(p + "ausgangsfrequenz_fest") or ""))
               if x.strip()) if z]
    if fest_hz:
        g.f_fest = fest_hz
    g.f_option = [z for z in (_zahl(x) for x in re.split(r"[;/,]\s*", str(a.get(p + "ausgangsfrequenz_option") or ""))
                              if x.strip()) if z]
    parallel = str(a.get(p + "parallelschaltung") or "")
    g.parallel = parallel in ("Ja", "Master-Slave")
    pm = _zahl(a.get(p + "parallel_max"))
    g.parallel_max = int(pm) if pm else None
    g.reihe = a.get(p + "reihenschaltung") is True
    if typ in ("DC/AC", "DC/DC"):
        g.u_eingang = _zahl(a.get(p + "eingangsspannung_min")) or _zahl(a.get(p + "eingangsspannung_max"))
    return g


def geraete_lesen(t, fortschritt=None) -> list[Geraet]:
    """Alle Artikel mit eps_-Werten aus Weclapp. Artikel ohne Gerätetyp und ohne Werte (Zubehör, Optionen)
    werden übersprungen."""
    definitionen = {str(d.get("id")): d for d in _alle(t, PFAD_DEFINITIONEN)}
    try:
        kategorien = {str(k.get("id")): k.get("name", "") for k in _alle(t, PFAD_KATEGORIEN)}
    except Exception:  # noqa: BLE001 – Kategorien sind nur ein Zusatz (Gerätetyp steht auch in eps_geraetetyp)
        kategorien = {}
    geraete = []
    for art in _alle(t, PFAD_ARTIKEL, fortschritt):
        if art.get("active") is False:
            continue
        g = geraet(art, attribute_lesen(art, definitionen), kategorien)
        if g.geraetetyp and (g.umax or g.imax or g.pmax):
            geraete.append(g)
    return geraete
