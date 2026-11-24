"""MCP-Server der Produktsuche (Branch weclapp): nur lesen/planen, gegen die Attrappe."""
import asyncio
import csv
import json

import pytest

from eps_produktsuche import mcp_server as M, weclapp_schreiben as S
from eps_produktsuche.weclapp import WeclappFehler
from eps_produktsuche.weclapp_attrappe import Attrappe
from test_weclapp import _geraete_fuer_schreiben, _leeres_weclapp


def _werkzeuge():
    geraete = _geraete_fuer_schreiben()
    a = Attrappe.mit_importdaten(geraete)
    a.kunde("TEST Karlsruher Kunde GmbH", "einkauf@test-kunde.de", "76131")
    return M.Werkzeuge(a), a, geraete


def _keine_schreibzugriffe(a):
    assert not [m for m, _ in a.aufrufe if m != "GET"]


def test_artikel_suchen_und_lesen_mit_zusatzfeldern():
    w, a, geraete = _werkzeuge()
    nr = geraete[0].bestellnummer
    r = w.artikel_suchen(nr)
    assert r["anzahl"] == 1 and r["artikel"][0]["artikelnummer"] == nr
    art = w.artikel_lesen(nr)
    assert art["gefunden"] and art["zusatzfelder"]["eps_serie"] and art["zusatzfelder_gesamt"] > 5
    assert w.artikel_lesen("000000") == {"gefunden": False, "artikelnummer": "000000"}
    assert w.artikel_suchen(geraete[0].name.split()[0])["anzahl"] >= 1          # Namensteil
    _keine_schreibzugriffe(a)


def test_zaehlen_und_abfragen_nur_freigegebene_ressourcen():
    w, a, geraete = _werkzeuge()
    assert w.zaehlen("article")["anzahl"] == len(geraete)
    assert w.zaehlen("article", {"articleNumber-eq": geraete[0].bestellnummer})["anzahl"] == 1
    r = w.abfragen("article", seite=1, groesse=9999)                             # Seitengröße wird begrenzt
    assert r["anzahl"] == min(len(geraete), M.MAX_SEITE)
    for schlecht in ("user", "../party", "article/id/1"):
        with pytest.raises(WeclappFehler):
            w.abfragen(schlecht)
    with pytest.raises(WeclappFehler):
        w.zaehlen("apiToken")
    _keine_schreibzugriffe(a)


def test_partei_suchen_ohne_ansprechpartner_daten():
    w, a, _ = _werkzeuge()
    r = w.partei_suchen("karlsruher", art="kunde")
    assert r["anzahl"] == 1 and r["parteien"][0]["email"] == "einkauf@test-kunde.de"
    assert w.partei_suchen("einkauf@test-kunde.de")["anzahl"] == 1
    assert "contacts" not in json.dumps(r)


def test_zusatzfelder_und_geraetesuche():
    w, a, geraete = _werkzeuge()
    z = w.zusatzfelder()
    assert z["anzahl"] > 20 and any(f["schluessel"] == "eps_serie" for f in z["felder"])
    r = w.geraete_suchen(geraete[0].bestellnummer)                               # Text/Bestellnummer
    assert r["modus"] == "text" and r["treffer"][0]["bestellnummer"] == geraete[0].bestellnummer
    faelle = json.loads(open(__file__.replace("test_mcp_server.py", "gemeinsame-suchfaelle.json"), encoding="utf-8").read())
    r = w.geraete_suchen(faelle["faelle"][0]["anfrage"])
    assert r["modus"] == "leistungsdaten" and r["geraete_gesamt"] > 0
    _keine_schreibzugriffe(a)


def test_eps_werte_planen_liest_nur(tmp_path):
    geraete = _geraete_fuer_schreiben()
    a = _leeres_weclapp(geraete)
    werte = S.werte_aus_geraeten(geraete)
    schluessel = sorted({k for v in werte.values() for k in v})
    pfad = tmp_path / "Weclapp-eps-Werte.csv"
    with open(pfad, "w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.writer(fh, delimiter=";")
        wr.writerow(["Artikelnummer"] + schluessel)
        for nr, v in werte.items():
            wr.writerow([nr] + [v.get(k, "") for k in schluessel])
    w = M.Werkzeuge(a)
    r = w.eps_werte_planen(str(pfad))
    assert "Artikel geprüft" in r["zusammenfassung"] and r["zeilen_mit_aenderung_oder_problem"]
    assert len(r["zeilen_mit_aenderung_oder_problem"]) <= M.MAX_ZEILEN_PLAN
    r1 = w.eps_werte_planen(str(pfad), [geraete[0].bestellnummer, "000000"])
    assert r1["nicht_in_csv"] == ["000000"] and "1 Artikel geprüft" in r1["zusammenfassung"]
    _keine_schreibzugriffe(a)
    with pytest.raises(WeclappFehler):
        w.eps_werte_planen(str(tmp_path / "geheim.txt"))
    for art in a.daten["article"]:                                               # Plan hat nichts verändert
        assert art["customAttributes"] == [] and art["version"] == "1"


def test_verbindung_aus_einstellungen(tmp_path, monkeypatch):
    monkeypatch.delenv("EPS_WECLAPP_ADRESSE", raising=False)
    ein = tmp_path / "einstellungen.json"
    ein.write_text(json.dumps({"weclapp_adresse": "demo"}), encoding="utf-8")
    t, web = M.transport_aus_einstellungen(ein)
    assert isinstance(t, Attrappe) and M.Werkzeuge(t).verbindung_testen()["ergebnis"].startswith("Verbindung OK")
    ein.write_text(json.dumps({"weclapp_adresse": "test.weclapp.com"}), encoding="utf-8")
    monkeypatch.setattr(M.zugang, "laden", lambda adresse: "")
    with pytest.raises(WeclappFehler, match="Token"):
        M.transport_aus_einstellungen(ein)
    monkeypatch.setattr(M.zugang, "laden", lambda adresse: "GEHEIM-TOKEN")
    t, web = M.transport_aus_einstellungen(ein)
    assert web == "https://test.weclapp.com" and "GEHEIM-TOKEN" not in repr(web)
    ein.write_text("{}", encoding="utf-8")
    with pytest.raises(WeclappFehler, match="Adresse"):
        M.transport_aus_einstellungen(ein)


def test_mcp_registrierung_nur_lesend_und_fehler_als_text():
    pytest.importorskip("mcp")
    w, a, geraete = _werkzeuge()
    server = M.server_bauen(w)
    tools = asyncio.run(server.list_tools())
    namen = {t.name for t in tools}
    assert "weclapp_artikel_lesen" in namen and "weclapp_eps_werte_planen" in namen and len(namen) == 9
    assert not [n for n in namen if any(s in n for s in ("schreiben", "anlegen", "loeschen", "put", "post"))]
    tool = next(t for t in tools if t.name == "weclapp_abfragen")
    schema = getattr(tool, "inputSchema", None) or tool.input_schema            # mcp 1.x / 2.x
    assert "ressource" in schema["properties"] and "filter" in schema["properties"]
    ergebnis = asyncio.run(server.call_tool("weclapp_artikel_lesen", {"artikelnummer": geraete[0].bestellnummer}))
    assert geraete[0].bestellnummer in json.dumps(ergebnis, default=str)
    fehler = asyncio.run(server.call_tool("weclapp_zaehlen", {"ressource": "nichtda"}))
    assert "nicht freigegeben" in json.dumps(fehler, default=str)
    _keine_schreibzugriffe(a)
