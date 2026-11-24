#!/usr/bin/env python3
"""Importdateien für die E-Artikel (SelectLine „E000015“ …) im Weclapp-Format (Verkaufsartikel-Stammdaten).

    python tools/weclapp-e-artikel.py <E-Artikel_seit-2020.xlsx> <Artikel.csv> <Zielordner>

Die E-Artikel behalten ihre Nummer MIT dem führenden „E“ (sie sind mit einem anderen Anbieter synchronisiert).
Welche Artikel übernommen werden, bestimmt die Excel-Liste (Reiter „E-Artikel seit 2020“): Zeilen, die der Chef
streicht, werden nicht importiert. Erzeugt:
  Weclapp-E-Artikel-Probe.csv       wenige Fälle (verschiedene Einheiten/Typen) zum ersten Probeimport
  Weclapp-E-Artikel.csv             alle Artikel der Liste
  Weclapp-E-Artikel-Hinweise.csv    Einheiten, die es in Weclapp erst geben muss, Artikel ohne Gruppe/Name

Annahmen (bitte bestätigen): Dienstleistungen → Artikeltyp SERVICE, Lagerartikel → STORABLE, sonst BASIC;
Warengruppe = SelectLine-Artikelgruppe (in Weclapp flach; „Option“ und „Zubehör“ → vorhandene Gruppe „Optionen und Zubehör“); Zusatz → Kurztext 1.
"""
import csv
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from eps_produktsuche import weclapp_import as W  # noqa: E402

EINHEIT = {"Stück": "Stk.", "St": "Stk.", "Std": "Std.", "Stunde": "Std."}
GRUPPE = {"Option": "Optionen und Zubehör", "Zubehör/Accessories": "Optionen und Zubehör"}   # vorhandene Weclapp-Warengruppe
NORMAL = {"Stk.", "Std.", "Tag", "Set", "Satz", "Pack", "m", "km", "Woche"}


def lies(pfad):
    roh = Path(pfad).read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = roh.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    erste = text.split("\n", 1)[0]
    return list(csv.reader(io.StringIO(text), delimiter=";" if erste.count(";") > erste.count(",") else ","))


def liste_lesen(xlsx):
    from openpyxl import load_workbook
    ws = load_workbook(xlsx, data_only=True)["E-Artikel seit 2020"]
    kopf = [c.value for c in ws[1]]
    return [dict(zip(kopf, [c.value for c in row])) for row in ws.iter_rows(min_row=2) if row[0].value]


def artikeltyp(gruppe, lager):
    if gruppe == "Dienstleistungen":
        return "SERVICE"
    return "STORABLE" if lager == "ja" else "BASIC"


def zeilen_bauen(liste, selectline):
    kopf = selectline[0]
    ix = {k: i for i, k in enumerate(kopf)}
    zusatz = {r[ix["Artikelnummer"]]: r[ix["Zusatz"]] for r in selectline[1:]}
    zeilen, hinweise = {}, []
    for a in liste:
        nr = str(a["Artikelnummer"])
        if not re.fullmatch(r"E\d{6}", nr):
            hinweise.append([nr, "", "keine E-Nummer – übersprungen"])
            continue
        einheit = EINHEIT.get(a["Mengeneinheit"] or "", a["Mengeneinheit"] or "Stk.")
        name = (a["Bezeichnung"] or "").strip() or nr
        if not (a["Bezeichnung"] or "").strip():
            hinweise.append([nr, "", "Bezeichnung leer – Artikelnummer als Name eingetragen"])
        if einheit not in NORMAL:
            hinweise.append([nr, name, f"Einheit „{einheit}“ ungewöhnlich – muss in weclapp unter Einheiten existieren"])
        if not a["Artikelgruppe"]:
            hinweise.append([nr, name, "ohne Artikelgruppe in SelectLine – Warengruppe bleibt leer"])
        zeilen[nr] = W.zeile(A=name, D=nr, J=einheit, L="ja", M=GRUPPE.get(a["Artikelgruppe"], a["Artikelgruppe"]) or "",
                             P=(zusatz.get(nr) or "").strip(), BN=artikeltyp(a["Artikelgruppe"], a["Lagerartikel"]))
    return zeilen, hinweise


def main(xlsx, artikel_csv, ziel):
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    liste = liste_lesen(xlsx)
    zeilen, hinweise = zeilen_bauen(liste, lies(artikel_csv))
    alle = [zeilen[n] for n in sorted(zeilen)]
    # Probe: je eine Zeile pro Einheit/Artikeltyp, höchstens 8
    gesehen, probe = set(), []
    for n in sorted(zeilen):
        z = zeilen[n]
        schluessel = (z[W._index("J")], z[W._index("BN")])
        if schluessel not in gesehen and len(probe) < 8:
            gesehen.add(schluessel)
            probe.append(z)
    W.schreiben(ziel / "Weclapp-E-Artikel.csv", alle)
    W.schreiben(ziel / "Weclapp-E-Artikel-Probe.csv", probe)
    with open(ziel / "Weclapp-E-Artikel-Hinweise.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Artikelnummer", "Artikelname", "Hinweis"])
        w.writerows(hinweise)
    print(f"{len(alle)} E-Artikel, Probe {len(probe)}, Hinweise {len(hinweise)}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
