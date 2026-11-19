"""Technische Werte (eps_…) in Weclapp-Artikel schreiben – Vorschau, Einzeltest, Gesamtlauf.

Der Standard-Importassistent von Weclapp kennt keine eigenen Zusatzfelder; die Werte kommen deshalb per API an die
Artikel. Reihenfolge im Programm (Einstellungen → Weclapp):
  1. Vorschau: liest Zusatzfeld-Definitionen und Artikel, vergleicht mit den Sollwerten, zeigt was neu/geändert wäre.
     Verändert nichts.
  2. Einzeltest: schreibt die Werte EINES Artikels (Eingabe der Artikelnummer) und liest ihn danach zur Kontrolle neu.
  3. Alle schreiben: erst nach Einzeltest und ausdrücklicher Bestätigung.

Sollwerte = dieselben Zeilen wie Weclapp-eps-Werte.csv (weclapp_felder.artikel_zeilen). Leere Sollwerte überschreiben
nichts. Zusatzfelder, die es in Weclapp (noch) nicht gibt, und Auswahlwerte, die in der Auswahlliste fehlen, werden
übersprungen und gemeldet – sie werden NICHT angelegt (Definitionen pflegt man in Weclapp selbst).
Die API-Struktur der customAttributes ist mit echten Diagnosedaten geprüft; das Schreiben (PUT /article/id/{id}) wird
im Einzeltest zum ersten Mal gegen das echte System probiert.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .weclapp import WeclappFehler, _liste
from .weclapp_felder import IMPORT_SPALTEN, PREFIX, artikel_zeilen

PFAD_DEFINITIONEN = "/customAttributeDefinition"
PFAD_ARTIKEL = "/article"
SEITE = 100


@dataclass
class ArtikelPlan:
    nummer: str
    artikel_id: str = ""
    version: str = ""
    name: str = ""
    neu: list[str] = field(default_factory=list)
    geaendert: list[str] = field(default_factory=list)
    gleich: list[str] = field(default_factory=list)
    eintraege: list[dict] = field(default_factory=list)          # kompletter customAttributes-Satz zum Schreiben
    fehlt_feld: list[str] = field(default_factory=list)          # kein Zusatzfeld mit diesem Schlüssel in Weclapp
    fehlt_wert: list[tuple[str, str]] = field(default_factory=list)   # Wert fehlt in der Auswahlliste
    fehler: str = ""                                             # z. B. „Artikel nicht in Weclapp“

    @property
    def aenderungen(self) -> int:
        return len(self.neu) + len(self.geaendert)

    @property
    def status(self) -> str:
        if self.fehler:
            return self.fehler
        if not self.aenderungen:
            return "unverändert"
        return f"{len(self.neu)} neu, {len(self.geaendert)} geändert"


# ------------------------------------------------------------------------ Sollwerte

def werte_aus_geraeten(geraete) -> dict[str, dict[str, str]]:
    """{Artikelnummer: {eps_Schlüssel: Text}} aus den Geräten (Shopdaten) – nur nicht leere eps_-Werte."""
    spalten = [s for s, _ in IMPORT_SPALTEN]
    erg: dict[str, dict[str, str]] = {}
    for zeile in artikel_zeilen(geraete):
        z = dict(zip(spalten, zeile))
        erg[str(z["Artikelnummer"])] = {k: str(v) for k, v in z.items() if k.startswith(PREFIX) and str(v).strip()}
    return erg


def werte_aus_csv(pfad) -> dict[str, dict[str, str]]:
    """Dasselbe aus Weclapp-eps-Werte.csv (Semikolon, UTF-8)."""
    erg: dict[str, dict[str, str]] = {}
    with open(Path(pfad), encoding="utf-8-sig", newline="") as fh:
        for z in csv.DictReader(fh, delimiter=";"):
            erg[str(z["Artikelnummer"])] = {k: v for k, v in z.items() if k.startswith(PREFIX) and (v or "").strip()}
    return erg


# ------------------------------------------------------------------------ Umsetzung in customAttributes

def _zahl(text: str) -> str:
    return str(text).strip().replace(",", ".")


def eintrag(d: dict, wert: str) -> tuple[dict | None, str]:
    """Sollwert → customAttributes-Eintrag für die Definition d. (None, Auswahlwert) wenn ein Auswahlwert in der Liste fehlt."""
    ca = {"attributeDefinitionId": str(d["id"])}
    typ = d.get("attributeType", "STRING")
    wert = str(wert).strip()
    if typ in ("LIST", "MULTISELECT_LIST"):
        ids = {str(v.get("value")): str(v.get("id")) for v in d.get("selectableValues", []) or []}
        teile = [w.strip() for w in wert.split(";") if w.strip()] if typ == "MULTISELECT_LIST" else [wert]
        for w in teile:
            if w not in ids:
                return None, w
        if typ == "LIST":
            ca["selectedValueId"] = ids[teile[0]]
        else:
            ca["selectedValues"] = [{"id": ids[w]} for w in teile]
    elif typ in ("DECIMAL", "INTEGER"):
        ca["numberValue"] = _zahl(wert)
    elif typ == "BOOLEAN":
        ca["booleanValue"] = wert.lower() in ("ja", "true", "1")
    else:
        ca["stringValue"] = wert
    return ca, ""


def _gleich(alt: dict, neu: dict) -> bool:
    if "numberValue" in neu:
        try:
            return float(str(alt.get("numberValue"))) == float(neu["numberValue"])
        except (TypeError, ValueError):
            return False
    if "selectedValues" in neu:
        return {str(v.get("id")) for v in alt.get("selectedValues") or []} == {str(v["id"]) for v in neu["selectedValues"]}
    for k in ("selectedValueId", "booleanValue", "stringValue"):
        if k in neu:
            return str(alt.get(k)) == str(neu[k])
    return False


# ------------------------------------------------------------------------ Lesen

def definitionen_lesen(t) -> dict[str, dict]:
    """{attributeKey: Definition} aller eps_-Zusatzfelder."""
    erg, seite = {}, 1
    while True:
        teil = _liste(t("GET", PFAD_DEFINITIONEN, {"page": seite, "pageSize": 200}))
        for d in teil:
            if str(d.get("attributeKey", "")).startswith(PREFIX):
                erg[d["attributeKey"]] = d
        if len(teil) < 200:
            return erg
        seite += 1


def artikel_lesen(t, nummern: list[str] | None = None, fortschritt=None) -> dict[str, dict]:
    """{Artikelnummer: Artikel}. Mit Nummern: gezielt (articleNumber-eq), sonst alle Artikel seitenweise."""
    erg: dict[str, dict] = {}
    if nummern is not None and len(nummern) <= 5:
        for nr in nummern:
            for a in _liste(t("GET", PFAD_ARTIKEL, {"articleNumber-eq": nr})):
                erg[str(a.get("articleNumber"))] = a
        return erg
    seite = 1
    while True:
        teil = _liste(t("GET", PFAD_ARTIKEL, {"page": seite, "pageSize": SEITE}))
        for a in teil:
            erg[str(a.get("articleNumber"))] = a
        if fortschritt:
            fortschritt(f"Artikel gelesen: {len(erg)}", len(erg), 0)
        if len(teil) < SEITE:
            return erg
        seite += 1


# ------------------------------------------------------------------------ Plan

def plan_fuer(nummer: str, soll: dict[str, str], artikel: dict | None, definitionen: dict[str, dict]) -> ArtikelPlan:
    p = ArtikelPlan(nummer)
    if artikel is None:
        p.fehler = "Artikel nicht in Weclapp gefunden"
        return p
    p.artikel_id, p.version, p.name = str(artikel.get("id", "")), str(artikel.get("version", "")), artikel.get("name", "")
    vorhanden = {str(c.get("attributeDefinitionId")): c for c in artikel.get("customAttributes", []) or []}
    neue: dict[str, dict] = {}
    for schluessel, wert in soll.items():
        d = definitionen.get(schluessel)
        if d is None:
            p.fehlt_feld.append(schluessel)
            continue
        ca, fehlend = eintrag(d, wert)
        if ca is None:
            p.fehlt_wert.append((schluessel, fehlend))
            continue
        alt = vorhanden.get(ca["attributeDefinitionId"])
        if alt is not None and _gleich(alt, ca):
            p.gleich.append(schluessel)
            continue
        (p.geaendert if alt is not None and len(alt) > 1 else p.neu).append(schluessel)
        neue[ca["attributeDefinitionId"]] = ca
    # kompletter Satz: Vorhandenes bleibt, unsere Werte ersetzen/ergänzen
    satz = [neue.pop(i, c) for i, c in vorhanden.items()] + list(neue.values())
    p.eintraege = satz
    return p


def planen(t, werte: dict[str, dict[str, str]], nummern: list[str] | None = None, fortschritt=None) -> list[ArtikelPlan]:
    """Vorschau-Plan (nur lesen). nummern=None → alle Artikelnummern aus den Sollwerten."""
    nummern = sorted(werte) if nummern is None else list(nummern)
    definitionen = definitionen_lesen(t)
    if not definitionen:
        raise WeclappFehler("In Weclapp gibt es keine Zusatzfelder „eps_…“ (Zusatzfelder anlegen, siehe Feldliste).")
    artikel = artikel_lesen(t, nummern, fortschritt)
    return [plan_fuer(nr, werte.get(nr, {}), artikel.get(nr), definitionen) for nr in nummern]


# ------------------------------------------------------------------------ Schreiben

def schreiben(t, plan: ArtikelPlan) -> None:
    """Schreibt den customAttributes-Satz des Artikels (PUT /article/id/{id}). Nur aufrufen nach ausdrücklichem Klick."""
    if plan.fehler or not plan.artikel_id:
        raise WeclappFehler(f"{plan.nummer}: {plan.fehler or 'kein Artikel'}")
    if not plan.aenderungen:
        return
    body = {"customAttributes": plan.eintraege}
    if plan.version:
        body["version"] = plan.version                     # Weclapp prüft damit, dass niemand dazwischen geändert hat
    t("PUT", f"{PFAD_ARTIKEL}/id/{plan.artikel_id}", daten=body)


def kontrolle(t, plan: ArtikelPlan, soll: dict[str, str], definitionen: dict[str, dict]) -> list[str]:
    """Liest den Artikel neu und nennt Werte, die nicht wie gewünscht angekommen sind (leer = alles da)."""
    neu = plan_fuer(plan.nummer, soll, artikel_lesen(t, [plan.nummer]).get(plan.nummer), definitionen)
    if neu.fehler:
        return [neu.fehler]
    return [f"{k}: nicht wie gewünscht gespeichert" for k in neu.neu + neu.geaendert]


@dataclass
class Lauf:
    geschrieben: int = 0
    unveraendert: int = 0
    fehler: list[str] = field(default_factory=list)


def alle_schreiben(t, plaene: list[ArtikelPlan], fortschritt=None, abbruch=lambda: False) -> Lauf:
    """Schreibt alle Pläne nacheinander; ein Fehler bricht NICHT ab, sondern wird gesammelt. Läuft erneut gefahrlos
    (bereits geschriebene Artikel zeigen dann „unverändert“)."""
    lauf = Lauf()
    for i, p in enumerate(plaene, 1):
        if abbruch():
            lauf.fehler.append("abgebrochen")
            break
        try:
            if p.aenderungen and not p.fehler:
                schreiben(t, p)
                lauf.geschrieben += 1
            elif p.fehler:
                lauf.fehler.append(f"{p.nummer}: {p.fehler}")
            else:
                lauf.unveraendert += 1
        except WeclappFehler as e:
            lauf.fehler.append(f"{p.nummer}: {e}")
        if fortschritt:
            fortschritt(f"{i}/{len(plaene)}", i, len(plaene))
    return lauf


# ------------------------------------------------------------------------ Anzeige

def zusammenfassung(plaene: list[ArtikelPlan]) -> str:
    gefunden = [p for p in plaene if not p.fehler]
    fehlt_feld = sorted({k for p in gefunden for k in p.fehlt_feld})
    fehlt_wert: dict[str, set] = {}
    for p in gefunden:
        for k, w in p.fehlt_wert:
            fehlt_wert.setdefault(k, set()).add(w)
    zeilen = [
        f"{len(plaene)} Artikel geprüft: {len(gefunden)} in Weclapp gefunden, {len(plaene) - len(gefunden)} nicht.",
        f"Zu schreiben: {sum(1 for p in gefunden if p.aenderungen)} Artikel "
        f"({sum(len(p.neu) for p in gefunden)} neue, {sum(len(p.geaendert) for p in gefunden)} geänderte Werte); "
        f"{sum(1 for p in gefunden if not p.aenderungen)} Artikel unverändert.",
    ]
    if fehlt_feld:
        zeilen.append("Zusatzfelder, die es in Weclapp nicht gibt (werden übersprungen): " + ", ".join(fehlt_feld))
    for k in sorted(fehlt_wert):
        zeilen.append(f"{k}: Wert nicht in der Auswahlliste (wird übersprungen): " + "; ".join(sorted(fehlt_wert[k])))
    return "\n".join(zeilen)


def vorschau_zeilen(plaene: list[ArtikelPlan]) -> list[list[str]]:
    kopf = ["Artikelnummer", "Artikelname", "Status", "neu", "geändert", "unverändert", "Zusatzfeld fehlt",
            "Auswahlwert fehlt"]
    zeilen = [kopf]
    for p in plaene:
        zeilen.append([p.nummer, p.name, p.status, "; ".join(p.neu), "; ".join(p.geaendert), str(len(p.gleich)),
                       "; ".join(p.fehlt_feld), "; ".join(f"{k} = {w}" for k, w in p.fehlt_wert)])
    return zeilen
