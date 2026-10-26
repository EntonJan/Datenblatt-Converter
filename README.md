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
3. In der Prüfmaske alle Werte prüfen, die **Kernfelder** (je Gerät 18) als „geprüft“ abhaken, Bestellnummer eintragen.
4. **Freigeben** → `ausgabe\d<Bestellnummer>.pdf` und `e<Bestellnummer>.pdf`. Fehlende Felder werden rot umrandet,
   mögliche Herstellerspuren (Herstellername, „our plant“, Modellnummern in der Beschreibung) vorher gemeldet.

Weitere Funktionen: Suche und Statusfilter in der Liste, **Duplizieren** (Vorlage für ähnliche Geräte),
automatisches Speichern alle 2 Minuten, offene Punkte je Reiter („Technische Daten (2 offen)“), Schalter „Leere Felder
ausblenden“, Rechtsklick-Menü am Feld (Fundstelle, DE → EN, Originalwert wiederherstellen, leeren). Fenstergröße,
Sortierung und Filter werden gemerkt.

**Seit v0.6.0:** PDFs ins Fenster ziehen (mehrere = Stapel-Import) oder „Mehrere PDFs …“; Vorschau im Programm
(DE/EN, aktualisiert sich beim Speichern); F3 springt zum nächsten offenen Feld; ein geprüfter Wert verliert den
Prüfhaken, sobald er geändert wird; Warnung bei doppelter Typbezeichnung/Hersteller-Bestellnummer; Papierkorb für
gelöschte Entwürfe; **Verlauf** je Datenblatt (wer/wann/was – Benutzer = Anzeigename oder Windows-Anmeldename,
nicht fälschungssicher).

**Gerätetyp & Eingang (seit v0.9.0):** Der Gerätetyp wird aus Ein-/Ausgangsart (AC/DC aus VAC/VDC, Hz, Phasen) und
Begriffen (Elektronische Last, Ladegerät, bidirektional) vorgeschlagen. AC-versorgte Geräte (AC/DC, AC/AC, Ladegeräte,
Lasten): Versorgung → Netzanschluss + Kernfeld **Netzspannung** (Auswahl 1~/3~); DC-Eingang (DC/DC, DC/AC): Kernfeld
**Eingangsspannung**. Nicht zutreffende Kernfelder sind grau und ohne Prüfpflicht. Reine elektronische Lasten nutzen die
Ausgangsfelder; im Datenblatt heißen sie „Eingangsspannung (Lastseite)“ usw. (Blatt „Bezeichnungen“ im Feldkatalog).

**EPS-Altbestand (seit v0.8.0):** Alte EPS-Datenblätter („EPS - Datenblatt“ im Kopf) werden erkannt und vollständig
übernommen: Serie, Typbezeichnung, Produkttyp, Beschreibung, Lieferumfang, alle Tabellenwerte, Schnittstellen
(Standard/Option + Code), Optionen, Bestellnummer, Bild; Herkunft = Altbestand, Hersteller bleibt leer. Liegt neben
`d<Nr>.pdf` auch `e<Nr>.pdf`, kommen die englischen Texte von dort. „Netzanschluss“ füllt auch die Eingangsspannung.

**Formulierungen (seit v0.7.0):** Blatt „Formulierungen“ im Feldkatalog übersetzt Textbausteine innerhalb eines Werts
in beide Richtungen („at full load“ ↔ „bei Volllast“). Beim Import automatisch (vorübersetzte Felder gelb), außerdem
über „Werte vereinheitlichen“. Eigene Einträge einfach in Excel ergänzen.

**Werte vereinheitlichen (Strg+E), früher „Einheiten vereinheitlichen“:** schlägt die EPS-Schreibweise vor (z. B. `230Vac` → `230 VAC`, `8.7Arms` →
`8,7 Arms` / EN `8.7 Arms`, `0-50°C` → `0–50 °C`, `432 x 132 x 483mm (17" …)` → `432 × 132 × 483 mm`, `12kg (26 lbs.)` →
`12 kg`, `Ohm` → `Ω`, `3ph.` → `3-phasig`). Übernommen wird nur, was in der Vorher/Nachher-Liste angehakt ist; Normen
und Typbezeichnungen bleiben unberührt. Regeln: `src/eps_converter/formatierer.py`. Tastenkürzel: Strg+S speichern, Strg+P Vorschau DE, Strg+Umschalt+P Vorschau EN,
Strg+O PDF importieren, Strg+N leeres Datenblatt, Strg+F suchen, F1 Tastenkürzel-Leiste ein/aus.

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
