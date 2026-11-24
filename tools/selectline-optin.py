#!/usr/bin/env python3
"""Opt-in-Kontakte aus SelectLine (Prioritaet 0/1 an den Ansprechpartnern) als Liste für CleverReach/Weclapp.

    python tools/selectline-optin.py <Adressen.csv> <Zielordner>

Bedeutung (Enton, 24.11.2026): Prioritaet 1 = bekommt den Newsletter (Opt-in), Prioritaet 0 = will keinen Newsletter,
leer = nicht gesetzt (kein Opt-in).
Erzeugt:
  Optin-Kontakte.csv       nur Prio 1, eine Zeile je E-Mail-Adresse (Semikolon, UTF-8 mit BOM): E-Mail, Vorname, Nachname,
                           Firma, Typ (Kunde/Interessent/Lieferant/ohne Zuordnung), SelectLine-Nr, Prioritaet, Interessen
  Newsletter-Sperre.csv    Prio 0 mit gültiger E-Mail: nicht anschreiben, in CleverReach als Abmeldung/Sperrliste laden
                           (auch wenn dieselbe Adresse bei einem anderen Kontakt Prio 1 hat – dann steht sie nur hier)
  Optin-Ausgeschlossen.csv Prio 0/1, aber ohne gültige E-Mail (z. B. „kein Interesse“ im E-Mail-Feld) – nicht übernommen
Interessen = gesetzte Kennzeichen _ACDC, _ACAC, _DCDC, _DCAC, _ELAST, _LADEGERAET, _TESTER, _KUNDENSPEZIFISCH, _EPS,
_KATALOG, _KATALOGDIGITAL (für Listen/Tags im Newsletter).
"""
import csv
import io
import re
import sys
from collections import OrderedDict
from pathlib import Path

csv.field_size_limit(10**7)
MAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INTERESSEN = {"_ACDC": "AC/DC", "_ACAC": "AC/AC", "_DCDC": "DC/DC", "_DCAC": "DC/AC", "_ELAST": "E-Last",
              "_LADEGERAET": "Ladegeräte", "_TESTER": "Tester", "_KUNDENSPEZIFISCH": "Kundenspezifisch",
              "_EPS": "EPS", "_KATALOG": "Katalog", "_KATALOGDIGITAL": "Katalog digital"}


def main(adressen, ziel):
    text = Path(adressen).read_bytes().decode("utf-8-sig", errors="replace")
    r = list(csv.reader(io.StringIO(text), delimiter=";"))
    ix = {k: i for i, k in enumerate(r[0])}
    haupt = {x[ix["Id"]]: x for x in r[1:] if x[ix["Kunde"]] or x[ix["Interessent"]] or x[ix["Lieferant"]]}

    def typ(x):
        if x is None:
            return "ohne Zuordnung", ""
        for k, t in (("Kunde", "Kunde"), ("Interessent", "Interessent"), ("Lieferant", "Lieferant")):
            if x[ix[k]]:
                return t, x[ix[k]]
        return "ohne Zuordnung", ""

    ok, aus, sperre = OrderedDict(), [], OrderedDict()
    for x in r[1:]:
        if x[ix["Kunde"]] or x[ix["Interessent"]] or x[ix["Lieferant"]]:
            continue                                   # Hauptadresse, kein Ansprechpartner
        prio = x[ix["Prioritaet"]].strip()
        if prio not in ("0", "1"):
            continue
        par = haupt.get(x[ix["Hauptadresse"]])
        t, nr = typ(par)
        firma = par[ix["Name"]] if par else x[ix["Firma"]]
        mail = x[ix["Email"]].strip()
        zeile = [mail.lower(), x[ix["Vorname"]], x[ix["Name"]], firma, t, nr, prio,
                 "; ".join(n for k, n in INTERESSEN.items() if k in ix and x[ix[k]].strip())]
        if not MAIL.match(mail):
            aus.append([mail, x[ix["Vorname"]], x[ix["Name"]], firma, t, nr, prio, "keine gültige E-Mail-Adresse"])
            continue
        if prio == "0":                                # will keinen Newsletter
            sperre.setdefault(zeile[0], zeile)
            continue
        if zeile[0] in ok:                             # gleiche Adresse mehrfach: Interessen zusammenführen
            alt = ok[zeile[0]]
            alt[7] = "; ".join(sorted(set(filter(None, (alt[7] + "; " + zeile[7]).split("; ")))))
            continue
        ok[zeile[0]] = zeile
    for m in sperre:                                   # eine Sperre gewinnt immer gegen ein Opt-in derselben Adresse
        ok.pop(m, None)
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    kopf = ["E-Mail", "Vorname", "Nachname", "Firma", "Typ", "SelectLine-Nr", "Prioritaet", "Interessen"]
    for name, zeilen, k in (("Optin-Kontakte.csv", ok.values(), kopf),
                            ("Newsletter-Sperre.csv", sperre.values(), kopf),
                            ("Optin-Ausgeschlossen.csv", aus, kopf[:-1] + ["Grund"])):
        with open(ziel / name, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(k)
            w.writerows(zeilen)
    print(f"{len(ok)} Adressen mit Opt-in (Prio 1), {len(sperre)} gesperrt (Prio 0), {len(aus)} ohne gültige E-Mail")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
