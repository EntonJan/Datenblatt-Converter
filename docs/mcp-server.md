# MCP-Server „EPS-Weclapp“ (Branch `weclapp`, nur lesen)

Gibt Claude (Claude-Desktop-App auf deinem Rechner) Werkzeuge für dein Weclapp. **Er schreibt nichts**: alle Zugriffe
sind GET-Abfragen. Das Schreiben der `eps_…`-Werte bleibt in der Produktsuche (Einstellungen → Weclapp → Werte schreiben).

## Werkzeuge

| Werkzeug | Zweck |
|---|---|
| `weclapp_verbindung_testen` | Token und Adresse prüfen |
| `weclapp_zaehlen` | Anzahl Datensätze (z. B. Artikel, Parteien) – zum Gegenprüfen von Importen |
| `weclapp_abfragen` | Allgemeine Leseabfrage auf freigegebene Ressourcen (Artikel, Parteien, Angebote, Aufträge, Rechnungen, Lieferungen, Lager …), max. 50 pro Seite |
| `weclapp_artikel_suchen` / `weclapp_artikel_lesen` | Artikel mit `eps_`-Zusatzfeldern (lesbar) und Bezugsquellen |
| `weclapp_zusatzfelder` | Die `eps_`-Zusatzfelder, die es in Weclapp gibt |
| `weclapp_partei_suchen` | Kunden/Lieferanten nach Firma oder E-Mail (ohne Ansprechpartner) |
| `weclapp_geraete_suchen` | Gerätesuche wie in der Produktsuche („Stromquelle 0-30V 1kA 30kW“ oder Bestellnummer) |
| `weclapp_eps_werte_planen` | Vorschau aus `Weclapp-eps-Werte.csv`: was „Werte schreiben“ ändern würde. Verändert nichts. |

## Einrichten (Windows)

1. Branch `weclapp` im Ordner `Datenblatt-Converter` aktuell holen (`git pull`).
2. Python 3.12 oder neuer. Einmalig: `pip install mcp keyring` (oder `pip install -r requirements-mcp.txt`).
3. In der Produktsuche (Testversion) ist Adresse und Token schon eingetragen. Der Server liest den Token aus der
   Windows-Anmeldeinformationsverwaltung. Er muss **unter demselben Windows-Benutzer** laufen.
4. Claude-Desktop-App → Einstellungen → Entwickler → Konfiguration bearbeiten. In `claude_desktop_config.json` ergänzen
   (Pfade anpassen, Backslashes doppelt):

```json
{
  "mcpServers": {
    "eps-weclapp": {
      "command": "C:\\Users\\Enkelmann\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
      "args": ["-m", "eps_produktsuche.mcp_server", "--adresse", "nokbtjnwznizheh.weclapp.com"],
      "env": { "PYTHONPATH": "C:\\Users\\Enkelmann\\Desktop\\Berichtsheft\\Arbeiten-ausserhalb-der-Berichtshefte\\Datenblatt-Converter\\src" }
    }
  }
}
```

   * `--adresse` muss **genau so** geschrieben sein wie in der Produktsuche (Einstellungen → Weclapp-Adresse), sonst findet
     der Server den Token nicht. Ohne `--adresse` liest er die Adresse aus der `einstellungen.json` der Produktsuche
     (`--einstellungen <Pfad>` falls sie nicht neben dem Programm liegt).
   * Den Token **niemals** in diese Datei schreiben.
5. Claude-Desktop-App neu starten. Unter den Werkzeugen erscheinen die `weclapp_…`-Einträge.
6. Test: „Zähle die Artikel in weclapp“ → `weclapp_zaehlen` (erwartet: die importierten Geräte und Optionsartikel).

Zum Ausprobieren ohne echtes System: `"--adresse", "demo"` (nachgebautes Weclapp, nur im Speicher).

## Sicherheit

* Nur GET. Freigegebene Ressourcen stehen in `mcp_server.RESSOURCEN`; alles andere wird abgelehnt.
* Seitengröße ≤ 50, damit nicht ganze Kundenstämme in einen Chat laufen. Antworten von `weclapp_abfragen` auf
  Parteien/Kontakte enthalten personenbezogene Daten: nur gezielt abfragen.
* Der Token liegt nur in der Windows-Anmeldeinformationsverwaltung, nicht in der Konfiguration, nicht im Repo und nicht in
  Fehlermeldungen.
* Schreibwerkzeuge (Einzelwert, Plan ausführen) kommen erst nach erfolgreichem Einzeltest in der Produktsuche, dann über
  dieselben geprüften Funktionen (`weclapp_schreiben`): erst Plan, dann Ausführung mit Bestätigung.

## Tests

`python -m pytest tests/test_mcp_server.py` (gegen die Attrappe; läuft mit mcp 1.x und 2.x, ohne mcp wird der
Registrierungstest übersprungen).
