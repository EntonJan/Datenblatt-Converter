# EPS Datenblatt-Converter

Windows-Programm, das Hersteller-Datenblätter (PDF) einliest, die Werte den EPS-Feldern zuordnet
und daraus EPS-Datenblätter (Deutsch und Englisch, Layout C) erzeugt. Später: Übertragung nach Weclapp.

Grundlage: Pflichtenheft Produktdaten-Pipeline (Stand 15.10.2026).

## Bedienung (Kurzfassung)

1. `Datenblatt-Converter.exe` in einen eigenen Ordner legen und starten. Beim ersten Start entstehen dort
   `katalog\feldkatalog.xlsx`, `einstellungen.json`, `daten\` und `ausgabe\`.
2. **Hersteller-PDF importieren** → bei Serien-Datenblättern das Modell zum Auftrag wählen → Werte werden vorbefüllt,
   das Original erscheint daneben (Feld anklicken = Fundstelle gelb markiert).
   Oder **Leeres Datenblatt** für Eingabe von Hand.
3. In der Prüfmaske alle Werte prüfen, die **18 Kernfelder** als „geprüft“ abhaken, Bestellnummer eintragen.
4. **Freigeben** → `ausgabe\d<Bestellnummer>.pdf` und `e<Bestellnummer>.pdf`.

## Ordner im Repo

| Ordner | Inhalt |
|---|---|
| `src/eps_converter/` | Programm (katalog, modell, regeln, auslesen, importieren, pdf_export, ablage, gui, updates) |
| `katalog/feldkatalog.xlsx` | Feldliste, Auswahlwerte, Wörterbuch, Synonyme – wird mitgeliefert und ist im Programmordner bearbeitbar |
| `assets/` | Logo, Banner, Schrift (Carlito, OFL-Lizenz) |
| `tests/` | automatische Tests (`python -m pytest`) |
| `packaging/` | PyInstaller-Bauplan für die EXE |
| `.github/workflows/build.yml` | baut bei jedem Push die EXE (Artefakt); bei neuer Versionsnummer als Release |

## Neue Version veröffentlichen

Versionsnummer in `src/eps_converter/__init__.py` erhöhen und auf `main` pushen. GitHub baut die EXE und legt
automatisch ein Release `v<Version>` mit der EXE an (nur wenn es die Version noch nicht gibt). Das Programm meldet beim Start, wenn eine neuere Version vorliegt.

## Stand

- Etappe 1–3 und 5 fertig (Feldkatalog, Prüfmaske + PDF, PDF-Import ohne KI, EXE-Build).
- Etappe 4 (KI-Auslesen und -Übersetzen) folgt nach Freigabe der API-Kosten.
- Weclapp-Übertragung folgt, sobald ein Zugang besteht.
