# EPS-Anfrage, Format 1

Eine Anfragestruktur für alles, was Kunden an EPS schicken: das Anfragefeld der Homepage, den Anfragekorb des
Produktkonfigurators und später den Shop. Die EPS-Produktsuche liest jede so erzeugte Anfrage sicher
(Ordner „Automatisch“).

**Dieser Ordner ist in beiden Repos identisch** (Datenblatt-Converter/EPS-Produktsuche und Produktkonfigurator).
Beide Seiten werden gegen dieselben Beispiele getestet:

- `*.json` – Beispielanfragen (Eingabe)
- `*.txt` – genau dieser Textblock muss daraus entstehen
- `eps-anfrage.schema.json` – Beschreibung der Felder (JSON Schema)

## So wird verschickt

Eine Mail an das Anfrage-Postfach mit

1. dem **Textblock** im Mailtext (Beispiel unten) – für Menschen lesbar, übersteht Weiterleiten und Kopieren
2. dem **Anhang `EPS-Anfrage.json`** mit denselben Daten – für Programme genau

Die Produktsuche nimmt den Anhang, wenn er da ist, sonst den Textblock.

## Regeln für den Textblock

- Erste Zeile `--- EPS-Anfrage ---`, letzte Zeile `--- Ende ---`
- Feste Reihenfolge, Bezeichnungen immer deutsch (auch bei `Sprache: en`)
- Kundenfelder stehen immer da, auch leer
- `Position n: <Bestellnummer> · <Name> · Menge <n>` – nur bei Artikelanfragen, beliebig viele
- `Suche`, `Gerätetyp`, `Filter` nur, wenn vorhanden
- `Nachricht` steht zuletzt und darf mehrzeilig sein; alles bis `--- Ende ---` gehört dazu
- Eine Zeile `--- Ende ---` oder `--- EPS-Anfrage ---` im Kundentext wird zu `– Ende –`
- Zeilenumbrüche in anderen Feldern werden zu Leerzeichen

## Beispiel (Anfragekorb)

```
--- EPS-Anfrage ---
Format: EPS-Anfrage 1
Anfrage-Nr.: EPS-20261102-114805-7F3A
Erstellt: 2026-11-02T11:48:05+01:00
Quelle: Produktkonfigurator
Sprache: de
Firma: Muster Prüftechnik
Rechtsform: GmbH
…
Position 1: 202307 · EPS/HC 40030-1000-WC DC Stromquelle · Menge 2
Position 2: 200961 · EPS/HC 40030-1200-M DC Stromquelle · Menge 1
Suche: Stromquelle 0-30V 1kA 30kW
Gerätetyp: AC/DC
Filter: cooling=Wasser; output_current=1000-1200; output_voltage=0-30
Wunschtermin: KW 50
Datenschutz: zugestimmt
Nachricht: Bitte ein Angebot für beide Varianten.
Lieferung nach Augsburg.
--- Ende ---
```

Eine reine Textanfrage hat keine `Position`-Zeilen; die Produktsuche wertet dann die Nachricht aus wie eine
normale Kundenmail (Werte, Menge, Termin).
