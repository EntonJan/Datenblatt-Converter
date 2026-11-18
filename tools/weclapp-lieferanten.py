#!/usr/bin/env python3
"""Lieferanten-Importdatei für weclapp erzeugen (Importassistent „Lieferanten (CSV)“, 95 Spalten).

    python tools/weclapp-lieferanten.py <Weclapp-Import_Lieferanten_Firmen.csv> <Zielordner>

Eingabe: die vorbereitete Lieferantenliste (Nummer, Firma, Adresse, Land als ISO …). Erzeugt
  Weclapp-Lieferanten-Probe.csv     vier Fälle (Deutschland, Ausland, Sammelkonto ohne Adresse) für den Probeimport
  Weclapp-Lieferanten.csv           alle Lieferanten
  Weclapp-Lieferanten-Hinweise.csv  Auffälligkeiten (Land fehlt, Straße fehlt …)
Die Nummer steht in Spalte C „Alte Lieferantennummer“ – im Assistenten „Alte Lieferantennummer übernehmen“ anhaken.
Pflichtfeld LAND fehlt bei Sammelkonten: ersatzweise „Deutschland“ (steht in den Hinweisen).
Zahlungs- und Lieferbedingungen bleiben leer: zulässig sind nur in weclapp bereits angelegte Werte.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from babel import Locale                                         # noqa: E402

from eps_produktsuche import weclapp_import as WI                # noqa: E402

ERSATZ_LAND = "Deutschland"


def land_name(iso: str) -> str:
    iso = iso.strip().upper()
    return Locale("de").territories.get(iso, "") if iso else ""


def main(quelle: str, ziel: str) -> None:
    ziel = Path(ziel)
    firmen = list(csv.DictReader(open(quelle, encoding="utf-8-sig"), delimiter=";"))
    zeilen, hinweise, nummern = [], [], []
    for f in firmen:
        land = land_name(f["Land (ISO)"])
        if not land:
            hinweise.append([f["Nummer"], f["Firma"], f"Land fehlt oder unbekannt ({f['Land (ISO)']!r}) – ersatzweise {ERSATZ_LAND}"])
            land = ERSATZ_LAND
        if f["Prüfen"].strip():
            hinweise.append([f["Nummer"], f["Firma"], "aus der Vorbereitung: " + f["Prüfen"].strip()])
        zeilen.append(WI.li_zeile(
            A=f["Firma"], B=f["Firmenzusatz"], C=f["Nummer"].strip(), L=f["Straße"], N=f["PLZ"], O=f["Ort"], Q=land,
            R="ja", S="ja", T="ja", AJ=f["Währung"], AK=f["USt-IdNr."], AQ=f["Homepage"], AR=f["E-Mail"],
            AS=f["Telefon"], AT=f["Fax"]))
        nummern.append(f["Nummer"].strip())
    WI.li_schreiben(ziel / "Weclapp-Lieferanten.csv", zeilen)

    def nimm(bedingung) -> int | None:
        for i, f in enumerate(firmen):
            if bedingung(f):
                return i
        return None
    auswahl = []
    for bed in (lambda f: f["Nummer"] == "73628",                                   # EA, Normalfall
                lambda f: f["Land (ISO)"] == "CA",                                  # Ausland
                lambda f: f["Land (ISO)"] == "IT",
                lambda f: not f["Land (ISO)"].strip()):                             # Sammelkonto ohne Land
        i = nimm(bed)
        if i is not None and i not in auswahl:
            auswahl.append(i)
    WI.li_schreiben(ziel / "Weclapp-Lieferanten-Probe.csv", [zeilen[i] for i in auswahl])
    with open(ziel / "Weclapp-Lieferanten-Hinweise.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Nummer", "Firma", "Hinweis"])
        w.writerows(hinweise)
    print(f"{len(zeilen)} Lieferanten, {len(hinweise)} Hinweise; Probe: {', '.join(nummern[i] for i in auswahl)} → {ziel}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
