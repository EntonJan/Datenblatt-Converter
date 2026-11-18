#!/usr/bin/env python3
"""Bezugsquellen-Importdatei für weclapp erzeugen (Importassistent „Bezugsquellen“).

    python tools/weclapp-bezugsquellen.py <shopdaten.json> <Artikel-Lieferant.csv> <Lieferanten_Firmen.csv> <Zielordner>

Quellen: Shopdaten der Produktsuche (Geräte, ohne 1xxxxx-Altartikel), SelectLine-Export „Artikel-Lieferant.csv“
(Lieferant, Herstellerbestellnummer, letzter EK mit Datum und Währung) und die Lieferantenliste des Weclapp-Imports
(alte SelectLine-Nummer → Weclapp-Nummer). Erzeugt:
  Weclapp-Bezugsquellen-Probe.csv   wenige Fälle zum ersten Probeimport
  Weclapp-Bezugsquellen.csv         alle Geräte
  Weclapp-Bezugsquellen-Hinweise.csv  was auffällt (fehlende Nummer/Preis, mehrere Lieferanten, kein Lieferant)
Voraussetzung in weclapp: Lieferanten und Geräteartikel sind angelegt.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eps_produktsuche import shop, weclapp_import as WI          # noqa: E402

WAEHRUNG = {"YEN": "JPY"}          # SelectLine-Kürzel → ISO


def _datum(s: str) -> datetime:
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y")
    except ValueError:
        return datetime.min


def main(shopdaten: str, artikel_lieferant: str, lieferanten: str, ziel: str) -> None:
    ziel = Path(ziel)
    geraete, _ = shop.laden(Path(shopdaten))
    geraete = [g for g in geraete if not g.bestellnummer.startswith("1")]       # nur 200000–799999
    name = {g.bestellnummer: g.name for g in geraete}

    firmen = list(csv.DictReader(open(lieferanten, encoding="utf-8-sig"), delimiter=";"))
    lief = {}
    for f in firmen:
        lief[f["Nummer"].strip()] = f
        if f["alte Nummer (SelectLine)"].strip():
            lief[f["alte Nummer (SelectLine)"].strip()] = f

    quellen: dict[str, list[dict]] = defaultdict(list)
    for r in csv.DictReader(open(artikel_lieferant, encoding="utf-8-sig"), delimiter=";"):
        if r["Artikelnummer"] in name:
            quellen[r["Artikelnummer"]].append(r)

    zeilen, hinweise = {}, []
    for nr in sorted(name):
        rs = sorted(quellen.get(nr, []), key=lambda r: _datum(r["DatumLetzterEK"]), reverse=True)
        if not rs:
            hinweise.append([nr, name[nr], "kein Lieferant im SelectLine-Export"])
            continue
        if len(rs) > 1:
            hinweise.append([nr, name[nr], "mehrere Lieferanten: " + ", ".join(r["Lieferant"] for r in rs) +
                             " – primär = jüngster Einkauf (" + rs[0]["Lieferant"] + ")"])
        zeilen[nr] = []
        for i, r in enumerate(rs):
            f = lief.get(r["Lieferant"].strip())
            if not f:
                hinweise.append([nr, name[nr], f"Lieferant {r['Lieferant']} nicht in der Weclapp-Lieferantenliste"])
                continue
            bestell = r["Bestellnummer"].strip()
            if not bestell:
                hinweise.append([nr, name[nr], f"Herstellerbestellnummer fehlt (Pflichtfeld) – ersatzweise EPS-Nummer {nr}"])
            ek = r["LetzterEK"].strip()
            ek_ok = ek not in ("", "0,00")
            if not ek_ok:
                hinweise.append([nr, name[nr], f"kein letzter Einkaufspreis bei Lieferant {r['Lieferant']}"])
            w = WAEHRUNG.get(r["Waehrung"].strip(), r["Waehrung"].strip())
            zeilen[nr].append(WI.bq_zeile(
                A=name[nr], D=bestell or nr, E=f["Firma"], F=f["Nummer"].strip(),
                G=ek if ek_ok else "", N=w if ek_ok else "", O="Stk.", Q="ja",
                R=r["DatumLetzterEK"].strip() if ek_ok else "",
                V="ja", W=nr, BQ="ja" if i == 0 else "nein"))

    alle = [z for nr in sorted(zeilen) for z in zeilen[nr]]
    WI.bq_schreiben(ziel / "Weclapp-Bezugsquellen.csv", alle)

    probe_nr = []
    def nimm(bedingung):
        for nr in sorted(zeilen):
            if nr not in probe_nr and bedingung(nr):
                probe_nr.append(nr)
                return
    nimm(lambda nr: len(quellen[nr]) == 1 and quellen[nr][0]["Bestellnummer"].strip() and quellen[nr][0]["Waehrung"] == "EUR"
         and quellen[nr][0]["LetzterEK"].strip() not in ("", "0,00"))
    nimm(lambda nr: quellen[nr][0]["Waehrung"] == "CAD")
    nimm(lambda nr: not quellen[nr][0]["Bestellnummer"].strip())
    nimm(lambda nr: len(quellen[nr]) > 1)
    WI.bq_schreiben(ziel / "Weclapp-Bezugsquellen-Probe.csv", [z for nr in probe_nr for z in zeilen[nr]])

    with open(ziel / "Weclapp-Bezugsquellen-Hinweise.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Artikelnummer", "Typbezeichnung", "Hinweis"])
        w.writerows(hinweise)
    print(f"{len(alle)} Bezugsquellen für {len(zeilen)} von {len(name)} Geräten, {len(hinweise)} Hinweise; "
          f"Probe: {', '.join(probe_nr)} → {ziel}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
