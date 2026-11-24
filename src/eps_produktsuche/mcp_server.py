"""MCP-Server der EPS-Produktsuche: Claude (Desktop-App) bekommt Werkzeuge für Weclapp – bisher NUR LESEN und PLANEN.

Start (lokal, stdio):   python -m eps_produktsuche.mcp_server [--einstellungen <einstellungen.json>]
Einrichtung:            siehe docs/mcp-server.md (Eintrag in claude_desktop_config.json)

Grundsätze
- Verbindung wie in der Produktsuche: Adresse aus einstellungen.json (oder EPS_WECLAPP_ADRESSE), Token aus der
  Windows-Anmeldeinformationsverwaltung (zugang.py). Der Token steht nie in der MCP-Konfiguration, nie im Repo, nie in einer
  Antwort an Claude. Adresse „demo“ = nachgebautes Weclapp (zum Ausprobieren).
- Keine Schreibwerkzeuge: alles läuft über GET. Das Planwerkzeug (eps_werte_planen) verändert nichts, es zeigt nur,
  was „Werte schreiben“ in der Produktsuche tun würde. Geschrieben wird weiterhin in der Produktsuche (Einzeltest →
  Bestätigung). Schreibwerkzeuge kommen erst, wenn der Einzeltest auf dem echten System gelaufen ist.
- Alle Rückgaben sind klein gehalten (Seitengrößen begrenzt), damit nicht versehentlich ganze Kundenstämme in den Chat
  laufen. Personenbezogene Daten kommen nur, wenn ausdrücklich danach gefragt wird (Parteien/Kunden-Abfrage).
"""
from __future__ import annotations

import argparse
import functools
import os
import sys
import time
from pathlib import Path

from . import weclapp as W, zugang
from .datenquelle import attribute_lesen, geraete_lesen
from .suche import anfrage_lesen, suchen, textsuche
from .weclapp import WeclappFehler, _liste
from .weclapp_felder import PREFIX
from .weclapp_schreiben import definitionen_lesen, planen, vorschau_zeilen, werte_aus_csv, zusammenfassung

# Nur diese Weclapp-Ressourcen dürfen abgefragt werden (GET). Namen wie in der Weclapp-API.
RESSOURCEN = ("article", "articleCategory", "articleSupplySource", "customAttributeDefinition", "party", "contact",
              "quotation", "salesOrder", "salesInvoice", "shipment", "purchaseOrder", "purchaseInvoice",
              "purchaseOrderRequest", "warehouse", "unit", "currency")
MAX_SEITE = 50
MAX_ZEILEN_PLAN = 40
GERAETE_CACHE_SEKUNDEN = 600


class Werkzeuge:
    """Die eigentliche Arbeit, ohne MCP-Abhängigkeit (dadurch gegen die Attrappe testbar)."""

    def __init__(self, transport, web: str = ""):
        self.t = transport
        self.w = W.Weclapp(transport, web)
        self._geraete: tuple[float, list] | None = None
        self._definitionen_id: dict[str, dict] | None = None

    # ---------------------------------------------------------------- Hilfen
    @staticmethod
    def _seite(groesse: int) -> int:
        return max(1, min(int(groesse), MAX_SEITE))

    def _definitionen_nach_id(self) -> dict[str, dict]:
        if self._definitionen_id is None:
            erg, seite = {}, 1
            while True:
                teil = _liste(self.t("GET", "/customAttributeDefinition", {"page": seite, "pageSize": 200}))
                erg.update({str(d.get("id")): d for d in teil})
                if len(teil) < 200:
                    break
                seite += 1
            self._definitionen_id = erg
        return self._definitionen_id

    # ---------------------------------------------------------------- Allgemein
    def verbindung_testen(self) -> dict:
        return {"ergebnis": self.w.verbindung_testen()}

    def zaehlen(self, ressource: str, filter: dict | None = None) -> dict:
        """Anzahl Datensätze, z. B. ressource=article, filter={"active-eq": "true"} – zum Gegenprüfen von Importen."""
        self._ressource_pruefen(ressource)
        r = self.t("GET", f"/{ressource}/count", dict(filter or {}))
        anzahl = r.get("result") if isinstance(r, dict) else r
        return {"ressource": ressource, "filter": filter or {}, "anzahl": anzahl}

    def abfragen(self, ressource: str, filter: dict | None = None, felder: list[str] | None = None,
                 seite: int = 1, groesse: int = 20, sortierung: str = "") -> dict:
        """Allgemeine Leseabfrage (nur GET). filter wie in der Weclapp-API, z. B. {"articleNumber-eq": "200000"},
        {"company-ilike": "%Karlsruher%"}. felder begrenzt die Rückgabe auf diese Eigenschaften."""
        self._ressource_pruefen(ressource)
        params: dict = dict(filter or {})
        params["page"], params["pageSize"] = max(1, int(seite)), self._seite(groesse)
        if felder:
            params["properties"] = ",".join(felder)
        if sortierung:
            params["sort"] = sortierung
        r = self.t("GET", f"/{ressource}", params)
        return {"ressource": ressource, "seite": params["page"], "anzahl": len(_liste(r)), "ergebnis": _liste(r)}

    @staticmethod
    def _ressource_pruefen(ressource: str) -> None:
        if ressource not in RESSOURCEN:
            raise WeclappFehler(f"Ressource „{ressource}“ ist nicht freigegeben. Erlaubt: {', '.join(RESSOURCEN)}")

    # ---------------------------------------------------------------- Artikel
    def artikel_suchen(self, text: str, limit: int = 20) -> dict:
        """Artikelnummer (genau) oder Namensteil."""
        text = text.strip()
        gross = self._seite(limit)
        if text and " " not in text and any(c.isdigit() for c in text):
            treffer = _liste(self.t("GET", "/article", {"articleNumber-eq": text, "pageSize": gross}))
            if not treffer:
                treffer = _liste(self.t("GET", "/article", {"articleNumber-ilike": f"{text}%", "pageSize": gross}))
        else:
            treffer = _liste(self.t("GET", "/article", {"name-ilike": f"%{text}%", "pageSize": gross}))
        return {"anzahl": len(treffer), "artikel": [
            {"artikelnummer": a.get("articleNumber"), "name": a.get("name"), "id": a.get("id"),
             "aktiv": a.get("active"), "version": a.get("version")} for a in treffer]}

    def artikel_lesen(self, artikelnummer: str) -> dict:
        """Ein Artikel mit seinen eps_-Zusatzfeldern (als lesbare Werte) und den Bezugsquellen."""
        liste = _liste(self.t("GET", "/article", {"articleNumber-eq": artikelnummer.strip()}))
        if not liste:
            return {"gefunden": False, "artikelnummer": artikelnummer}
        a = liste[0]
        defs = self._definitionen_nach_id()
        werte = attribute_lesen(a, defs)
        quellen = _liste(self.t("GET", "/articleSupplySource", {"articleId-eq": str(a.get("id"))}))
        return {
            "gefunden": True,
            "artikelnummer": a.get("articleNumber"), "name": a.get("name"), "id": a.get("id"), "version": a.get("version"),
            "aktiv": a.get("active"), "warengruppe_id": a.get("articleCategoryId"),
            "zusatzfelder": werte,
            "zusatzfelder_gesamt": len(a.get("customAttributes") or []),
            "bezugsquellen": [{
                "lieferant": q.get("supplierName") or q.get("supplierNumber") or q.get("supplierId"),
                "lieferantenartikelnummer": q.get("supplierArticleNumber"),
                "preise": [{"preis": p.get("price"), "ab": W._datum(p.get("startDate")).isoformat()
                            if W._datum(p.get("startDate")) else None} for p in q.get("purchasePrices", []) or []],
            } for q in quellen],
        }

    def zusatzfelder(self) -> dict:
        """Die eps_-Zusatzfelder, die es in Weclapp gibt (Typ, Anzahl Auswahlwerte)."""
        defs = definitionen_lesen(self.t)
        return {"anzahl": len(defs), "felder": [
            {"schluessel": k, "typ": d.get("attributeType"), "bezeichnung": d.get("label"),
             "auswahlwerte": len(d.get("selectableValues") or [])} for k, d in sorted(defs.items())]}

    # ---------------------------------------------------------------- Parteien
    def partei_suchen(self, text: str, art: str = "alle", limit: int = 10) -> dict:
        """Kunden/Lieferanten/Interessenten suchen (E-Mail genau oder Firmenname/Nummernteil). Gibt Stammdaten ohne
        Ansprechpartner zurück. art: kunde | lieferant | alle."""
        text, gross = text.strip(), self._seite(limit)
        params: dict = {"pageSize": gross}
        if "@" in text:
            params["email-eq"] = text
        else:
            params["company-ilike"] = f"%{text}%"
        if art == "kunde":
            params["customer-eq"] = "true"
        elif art == "lieferant":
            params["supplier-eq"] = "true"
        treffer = _liste(self.t("GET", "/party", params))
        return {"anzahl": len(treffer), "parteien": [{
            "id": p.get("id"), "firma": p.get("company") or f"{p.get('firstName', '')} {p.get('lastName', '')}".strip(),
            "kundennummer": p.get("customerNumber"), "lieferantennummer": p.get("supplierNumber"),
            "email": p.get("email"),
            "ort": next(((a.get("zipcode") or "") + " " + (a.get("city") or "") for a in p.get("addresses", []) or []), "").strip(),
        } for p in treffer]}

    # ---------------------------------------------------------------- Geräte (Logik der Produktsuche)
    def _geraete_laden(self) -> list:
        jetzt = time.time()
        if self._geraete is None or jetzt - self._geraete[0] > GERAETE_CACHE_SEKUNDEN:
            self._geraete = (jetzt, geraete_lesen(self.t))
        return self._geraete[1]

    def geraete_suchen(self, anfrage: str, max_treffer: int = 10) -> dict:
        """Gerätesuche wie in der Produktsuche. Mit Spannung/Strom/Leistung („Stromquelle 0-30V 1kA 30kW“) wird nach
        Leistungsdaten bewertet, sonst nach Bestellnummer/Name. Liest alle Geräte aus Weclapp (10 Minuten zwischengespeichert)."""
        geraete = self._geraete_laden()
        a = anfrage_lesen(anfrage)
        gross = self._seite(max_treffer)
        if a.leer():
            treffer = textsuche(geraete, anfrage)[:gross]
            return {"modus": "text", "geraete_gesamt": len(geraete), "anzahl": len(treffer), "treffer": [
                {"bestellnummer": g.bestellnummer, "name": g.name, "serie": g.serie, "typ": g.geraetetyp} for g in treffer]}
        gefunden = suchen(geraete, a, knapp_zeigen=False)[:gross]
        return {
            "modus": "leistungsdaten",
            "erkannt": {"spannung": a.spannung, "strom": a.strom, "leistung": a.leistung, "typ": a.geraetetyp,
                        "hinweise": a.erkannt},
            "geraete_gesamt": len(geraete), "anzahl": len(gefunden),
            "treffer": [{"bestellnummer": t.g.bestellnummer, "name": t.g.name, "serie": t.g.serie,
                         "typ": t.g.geraetetyp, "bewertung": t.bewertung, "reserve": t.reserve_text()} for t in gefunden]}

    # ---------------------------------------------------------------- Plan (verändert nichts)
    def eps_werte_planen(self, csv_pfad: str, artikelnummern: list[str] | None = None) -> dict:
        """Vorschau wie „Werte schreiben → Vorschau“ in der Produktsuche, aus Weclapp-eps-Werte.csv. Schreibt NICHTS."""
        pfad = Path(csv_pfad).expanduser()
        if pfad.suffix.lower() != ".csv" or not pfad.is_file():
            raise WeclappFehler("csv_pfad muss auf eine vorhandene .csv-Datei zeigen (Weclapp-eps-Werte.csv).")
        werte = werte_aus_csv(pfad)
        if artikelnummern:
            unbekannt = [n for n in artikelnummern if n not in werte]
            werte = {n: werte[n] for n in artikelnummern if n in werte}
        else:
            unbekannt = []
        plaene = planen(self.t, werte)
        zeilen = vorschau_zeilen(plaene)
        kopf, rest = zeilen[0], zeilen[1:]
        mit_aenderung = [z for z, p in zip(rest, plaene) if p.aenderungen or p.fehler or p.fehlt_feld or p.fehlt_wert]
        return {
            "zusammenfassung": zusammenfassung(plaene),
            "nicht_in_csv": unbekannt,
            "spalten": kopf,
            "zeilen_mit_aenderung_oder_problem": mit_aenderung[:MAX_ZEILEN_PLAN],
            "weitere_zeilen": max(0, len(mit_aenderung) - MAX_ZEILEN_PLAN),
            "hinweis": "Nur Vorschau. Geschrieben wird in der Produktsuche (Einstellungen → Weclapp → Werte schreiben).",
        }


# ---------------------------------------------------------------------- Verbindung herstellen

def transport_aus_einstellungen(einstellungen_pfad: Path | None = None, adresse: str = ""):
    """(Transport, Web-Basis). Adresse: Argument > EPS_WECLAPP_ADRESSE > einstellungen.json."""
    adresse = (adresse or os.environ.get("EPS_WECLAPP_ADRESSE", "")).strip()
    if not adresse:
        from .einstellungen import Einstellungen
        if einstellungen_pfad is None:
            from eps_converter import pfade
            einstellungen_pfad = pfade.EINSTELLUNGEN_DATEI
        adresse = Einstellungen.laden(Path(einstellungen_pfad)).weclapp_adresse.strip()
    if not adresse:
        raise WeclappFehler("Keine Weclapp-Adresse: in der Produktsuche einstellen oder EPS_WECLAPP_ADRESSE setzen.")
    if adresse.lower() == "demo":
        from .weclapp_attrappe import Attrappe
        a = Attrappe()
        a.kunde("DEMO Bestandskunde GmbH", "einkauf@demo-bestandskunde.de", "86150")
        return a, ""
    token = zugang.laden(adresse)
    if not token:
        raise WeclappFehler("Kein Weclapp-Token hinterlegt: in der Produktsuche unter Einstellungen → „Token eintragen …“ "
                            "(als derselbe Windows-Benutzer, unter dem dieser Server läuft).")
    http = W.Http(adresse, token)
    return http, http.web


# ---------------------------------------------------------------------- MCP

def server_bauen(werkzeuge: Werkzeuge):
    """FastMCP-Server mit allen Werkzeugen (nur lesend)."""
    try:                                           # mcp 1.x
        from mcp.server.fastmcp import FastMCP
    except ImportError:                            # mcp 2.x hat die Klasse umbenannt
        from mcp.server.mcpserver import MCPServer as FastMCP
    mcp = FastMCP("EPS-Weclapp")
    w = werkzeuge

    def sicher(f):
        """Fehler als Text zurückgeben statt den Server abstürzen zu lassen; Token taucht nie in Meldungen auf."""
        @functools.wraps(f)
        def umhuellt(*a, **k):
            try:
                return f(*a, **k)
            except WeclappFehler as e:
                return {"fehler": str(e)}
        return umhuellt

    for name in ("verbindung_testen", "zaehlen", "abfragen", "artikel_suchen", "artikel_lesen", "zusatzfelder",
                 "partei_suchen", "geraete_suchen", "eps_werte_planen"):
        mcp.tool(name=f"weclapp_{name}")(sicher(getattr(w, name)))
    return mcp


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="EPS-Weclapp MCP-Server (nur lesen)")
    ap.add_argument("--einstellungen", help="Pfad zu einstellungen.json der Produktsuche")
    ap.add_argument("--adresse", help="Weclapp-Adresse, z. B. nokbtjnwznizheh.weclapp.com (sonst aus den Einstellungen)")
    args = ap.parse_args(argv)
    try:
        t, web = transport_aus_einstellungen(Path(args.einstellungen) if args.einstellungen else None, args.adresse or "")
    except WeclappFehler as e:
        sys.exit(f"EPS-Weclapp MCP: {e}")
    server_bauen(Werkzeuge(t, web)).run()          # stdio


if __name__ == "__main__":
    main()
