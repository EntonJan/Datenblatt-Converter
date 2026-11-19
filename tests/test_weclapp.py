"""Weclapp-Anbindung gegen die Attrappe (Branch weclapp, experimentell)."""
from datetime import date, datetime

import pytest

from eps_produktsuche import weclapp as W, zugang
from eps_produktsuche.kunde import Kunde
from eps_produktsuche.weclapp_attrappe import Attrappe

HEUTE = datetime(2026, 10, 30)


def _system():
    a = Attrappe(heute=HEUTE)
    a.artikel("600149", "EPS/CTP 6000-125-400 Sinus-Wechselrichter", monate_alt=1, lieferant="TEST Absopulse")
    a.artikel("200904", "E/PS 10060-1000 4U Labornetzgerät", monate_alt=8, lieferant="TEST EA")
    a.artikel("999999", "TEST ohne Lieferant", lieferant="")
    a.kunde("TEST Bestandskunde GmbH", "einkauf@test-bestand.de", "86150")
    return a, W.Weclapp(a, web_basis="https://test.weclapp.com")


NEUKUNDE = Kunde(firma="TEST Muster Testtechnik", rechtsform="GmbH & Co. KG", anrede="Herr", vorname="Max",
                 nachname="Mustermann", email="max@muster-testtechnik.de", telefon="+49 821 1", strasse="Teststr. 1",
                 plz="86150", ort="Augsburg", land="DE", web="www.muster-testtechnik.de", ust_id="DE123456789")


def test_aktueller_preis_nur_angebot_neukunde():
    a, wc = _system()
    plan = wc.planen(NEUKUNDE, [("600149", 2)], frist_monate=3, heute=HEUTE.date())
    assert plan.kunde_neu and not plan.herstelleranfrage and plan.fehler == []
    assert plan.positionen[0].lieferant == "TEST Absopulse" and not plan.positionen[0].ek_alt
    erg = wc.ausfuehren(plan, NEUKUNDE)
    assert erg.kunde_neu and erg.angebot_nummer.startswith("AN-") and erg.anfrage_ids == []
    kunde = a.daten["party"][-1]
    assert kunde["company"] == "TEST Muster Testtechnik GmbH & Co. KG" and kunde["vatIdentificationNumber"] == "DE123456789"
    assert kunde["addresses"][0]["countryCode"] == "DE" and "[EPS-Produktsuche]" in kunde["description"]
    angebot = a.daten["quotation"][-1]
    assert angebot["customerId"] == erg.kunde_id and angebot["quotationItems"] == [{"articleId": plan.positionen[0].artikel_id,
                                                                                  "quantity": "2"}]
    assert "Wunschtermin: ASAP" in angebot["recordComment"]


def test_alter_preis_angebot_und_herstelleranfrage_bestandskunde():
    a, wc = _system()
    k = Kunde(firma="TEST Bestandskunde", rechtsform="GmbH", email="einkauf@test-bestand.de", plz="86150")
    plan = wc.planen(k, [("600149", 1), ("200904", 3)], frist_monate=6, termin="KW 50", heute=HEUTE.date())
    assert not plan.kunde_neu and "vorhanden" in plan.kunde_text
    assert [p.ek_alt for p in plan.positionen] == [False, True] and plan.herstelleranfrage
    erg = wc.ausfuehren(plan, k)
    assert len(a.daten["party"]) == 1                            # kein doppelter Kunde
    assert len(erg.anfrage_ids) == 2                            # je Lieferant eine Anfrage
    assert "Wunschtermin: KW 50" in a.daten["quotation"][-1]["recordComment"]
    assert set(erg.links) == {"Angebot", "Herstelleranfrage 1", "Herstelleranfrage 2", "Kunde"}


def test_kunde_ueber_firma_und_plz():
    _, wc = _system()
    k = Kunde(firma="TEST Bestandskunde", email="anderer@gmail.com", plz="86150")
    assert wc.kunde_finden(k)["company"] == "TEST Bestandskunde GmbH"
    assert wc.kunde_finden(Kunde(firma="TEST Bestandskunde", plz="10115")) is None


def test_fehlende_artikel_verhindern_anlegen():
    a, wc = _system()
    plan = wc.planen(NEUKUNDE, [("123456", 1), ("999999", 1)], frist_monate=3, heute=HEUTE.date())
    assert plan.fehler == ["123456: Artikel nicht in Weclapp gefunden", "999999: kein Lieferant am Artikel hinterlegt"]
    with pytest.raises(W.WeclappFehler):
        wc.ausfuehren(plan, NEUKUNDE)
    assert a.daten["quotation"] == [] and len(a.daten["party"]) == 1   # nichts angelegt


def test_http_adresse_und_datum():
    h = W.Http("eps.weclapp.com", "x")
    assert h.basis == "https://eps.weclapp.com/webapp/api/v1" and h.web == "https://eps.weclapp.com"
    assert W._datum(int(datetime(2026, 1, 15).timestamp() * 1000)) == date(2026, 1, 15)
    assert W._datum("2025-12-01") == date(2025, 12, 1) and W._datum(None) is None


def test_zugang_ohne_dauerhaften_speicher(monkeypatch):
    monkeypatch.setattr(zugang, "_keyring", lambda: None)
    assert zugang.speichern("test.weclapp.com", "geheim") is False
    assert zugang.laden("test.weclapp.com") == "geheim"
    zugang.loeschen("test.weclapp.com")
    assert zugang.laden("test.weclapp.com") == ""


def test_feldliste_und_import():
    from eps_converter import katalog as K, pfade
    from eps_produktsuche import shop, weclapp_felder as WF
    attribute, standard = WF.feldliste(K.laden(pfade.KATALOG_MITGELIEFERT))
    schluessel = [a.schluessel for a in attribute]
    assert len(schluessel) == len(set(schluessel)) and all(s.startswith("eps_") for s in schluessel)
    assert {"eps_ausgangsspannung", "eps_ausgangsspannung_min", "eps_ausgangsspannung_max"} <= set(schluessel)
    assert next(a for a in attribute if a.schluessel == "eps_bauform").auswahl_de.endswith("DIN Rail")
    opt = next(a for a in attribute if a.schluessel == "eps_optionen")
    assert opt.typ == "STRING" and opt.filter and "eps_zubehoer" not in schluessel         # ein Feld für Optionen
    assert next(a for a in attribute if a.schluessel == "eps_schnittstellen").filter == ""            # Schnittstellen: Filter über Optionen
    assert "eps_bestellnummer" not in schluessel and any(s[0] == "bestellnummer" for s in standard)
    g = shop.Geraet("T-125", "TEST CTP 6000-125-400 Wechselrichter", serie="TEST", geraetetyp="DC/AC",
                    spannung="3x 400V AC (L-L)", strom="8,6A", leistung="6000 VA")
    shop.auswerten(g)
    z = dict(zip([s for s, _ in WF.IMPORT_SPALTEN], WF.artikel_zeilen([g])[0]))
    assert (z["eps_eingangsspannung_min"], z["eps_ausgangsspannung_fest"], z["eps_ausgangsfrequenz"]) == ("125", "400", "")
    assert z["Warengruppe"] == "DC/AC" and "Bauform fehlt" in z["Prüfen"]


def test_datenquelle_weclapp_gleich_wie_shop():
    """Shopgeräte → Importdatei → (nachgebautes) Weclapp → zurückgelesen: die Suche liefert dieselben Treffer."""
    from eps_produktsuche import datenquelle as D, shop, suche as Q
    from eps_produktsuche.weclapp_attrappe import Attrappe
    import json
    from pathlib import Path
    faelle = json.loads((Path(__file__).with_name("gemeinsame-suchfaelle.json")).read_text(encoding="utf-8"))
    geraete = [shop.Geraet(**g) for g in faelle["geraete"]]
    for g in geraete:
        g.rueckspeisung = shop.ist_rueckspeisend(g.name, g.serie)
        g.u_eingang = shop.eingang_aus_name(g.name, g.geraetetyp)
    zurueck = D.geraete_lesen(Attrappe.mit_importdaten(geraete))
    assert {g.bestellnummer for g in zurueck} == {g.bestellnummer for g in geraete}
    for fall in faelle["faelle"]:
        a = Q.anfrage_lesen(fall["anfrage"])
        vorher = {(t.g.bestellnummer, t.bewertung) for t in Q.suchen(geraete, a)}
        nachher = {(t.g.bestellnummer, t.bewertung) for t in Q.suchen(zurueck, a)}
        assert vorher == nachher, fall["anfrage"]


def test_antwort_gzip_wird_gelesen():
    import gzip
    from eps_produktsuche.weclapp import _text
    roh = '{"result": [{"name": "Größe ß"}]}'.encode("utf-8")
    assert _text(gzip.compress(roh)) == roh.decode("utf-8")                 # an den Bytes 1f 8b erkannt
    assert _text(gzip.compress(roh), "gzip") == roh.decode("utf-8")
    assert _text(roh) == roh.decode("utf-8") and _text(b"") == ""          # unkomprimiert / leer wie bisher


def test_diagnose_liest_nur_und_faengt_fehler_pro_abschnitt():
    aufrufe = []

    def transport(methode, pfad, params=None, daten=None):
        aufrufe.append((methode, pfad))
        if pfad == "/articleCategory":
            raise W.WeclappFehler("Weclapp meldet 404")
        return {"result": [{"id": "1"}]}

    d = W.Weclapp(transport, web_basis="x").diagnose()
    assert all(m == "GET" for m, _ in aufrufe) and len(aufrufe) == 3
    assert d["definitionen"]["result"] and d["artikel_zuletzt"]["result"]
    assert "404" in d["kategorien"]["fehler"] and "token" not in str(d).lower()

def test_stammdatenimport_format_und_standardwerte():
    from eps_produktsuche import shop, weclapp_felder as WF, weclapp_import as WI
    assert len(WI.KOPF) == 93 and WI.KOPF[0] == "ARTIKELNAME" and WI.KOPF[3] == "ARTIKELNUMMER" and WI.KOPF[9] == "EINHEIT"
    g = shop.Geraet("123456", "E/PS 10060-1000 4U", geraetetyp="AC/DC")
    z = WF.stammdaten_zeilen([g])[0]
    assert len(z) == 93 and z[0] == "E/PS 10060-1000 4U" and z[3] == "123456" and z[9] == "Stk." and z[12] == "AC/DC"
    assert z[WI._index("BN")] == "STORABLE" and z[WI._index("BR")] == "nein"      # kein Ladehilfsmittel
    assert z[WI._index("E")] == z[WI._index("F")] == z[WI._index("I")] == ""       # kein Preis


def test_bezugsquellen_format():
    from eps_produktsuche import weclapp_import as WI
    assert len(WI.BQ_KOPF) == 69 and WI.BQ_KOPF[0] == "ARTIKELNAME" and WI.BQ_KOPF[3] == "Lieferantenartikelnummer"
    z = WI.bq_zeile(A="x", D="y", F="73628", O="Stk.", W="200000", BQ="ja")
    assert (z[0], z[3], z[5], z[14], z[22], z[68]) == ("x", "y", "73628", "Stk.", "200000", "ja")


def test_lieferanten_format():
    from eps_produktsuche import weclapp_import as WI
    assert len(WI.LI_KOPF) == 95 and WI.LI_KOPF[0] == "LIEFERANT-FIRMA" and WI.LI_KOPF[2] == "Alte Lieferantennummer"
    z = WI.li_zeile(A="EA", C="73628", Q="Deutschland")
    assert (z[0], z[2], z[16]) == ("EA", "73628", "Deutschland") and WI.LI_KOPF[16] == "LAND"


def _geraete_fuer_schreiben():
    import json
    from pathlib import Path
    from eps_produktsuche import shop
    faelle = json.loads((Path(__file__).with_name("gemeinsame-suchfaelle.json")).read_text(encoding="utf-8"))
    geraete = [shop.Geraet(**g) for g in faelle["geraete"]]
    for g in geraete:
        g.rueckspeisung = shop.ist_rueckspeisend(g.name, g.serie)
        g.u_eingang = shop.eingang_aus_name(g.name, g.geraetetyp)
    return geraete


def _leeres_weclapp(geraete):
    """Weclapp mit Zusatzfeld-Definitionen und Artikeln OHNE eps_-Werte (wie nach dem Stammdatenimport)."""
    a = Attrappe.mit_importdaten(geraete)
    for art in a.daten["article"]:
        art["customAttributes"] = []
        art["version"] = "1"
    return a


def test_schreiben_vorschau_aendert_nichts_und_schreiben_stimmt_mit_lesen():
    from eps_produktsuche import datenquelle as D, weclapp_schreiben as S
    geraete = _geraete_fuer_schreiben()
    erwartet = {g.bestellnummer: g for g in D.geraete_lesen(Attrappe.mit_importdaten(geraete))}
    a = _leeres_weclapp(geraete)
    werte = S.werte_aus_geraeten(geraete)
    plaene = S.planen(a, werte)
    assert not [m for m, _ in a.aufrufe if m != "GET"]                  # Vorschau liest nur
    assert all(p.aenderungen and not p.fehler for p in plaene) and "Artikel geprüft" in S.zusammenfassung(plaene)
    lauf = S.alle_schreiben(a, plaene)
    assert lauf.geschrieben == len(geraete) and lauf.fehler == []
    assert all(art["version"] == "2" for art in a.daten["article"])      # Version wurde mitgeschickt und erhöht
    gelesen = {g.bestellnummer: g for g in D.geraete_lesen(a)}
    assert gelesen.keys() == erwartet.keys()
    for nr, g in gelesen.items():
        e = erwartet[nr]
        assert (g.umin, g.umax, g.imax, g.pmax, g.geraetetyp, g.bauart) == (e.umin, e.umax, e.imax, e.pmax, e.geraetetyp, e.bauart)
    # zweiter Lauf: alles schon da
    assert all(not p.aenderungen for p in S.planen(a, werte))


def test_schreiben_einzelner_artikel_mit_kontrolle_und_fehlende_felder():
    from eps_produktsuche import weclapp_schreiben as S
    geraete = _geraete_fuer_schreiben()
    a = _leeres_weclapp(geraete)
    nr = geraete[0].bestellnummer
    werte = S.werte_aus_geraeten(geraete)
    # ein Zusatzfeld fehlt in Weclapp, bei einem Auswahlfeld fehlt der Wert in der Liste
    a.daten["customAttributeDefinition"] = [d for d in a.daten["customAttributeDefinition"]
                                            if d["attributeKey"] != "eps_serie"]
    bauform = next(d for d in a.daten["customAttributeDefinition"] if d["attributeKey"] == "eps_bauform")
    bauform["selectableValues"] = []
    soll = dict(werte[nr], eps_bauform="Gartenhaus")
    plan = S.planen(a, {nr: soll}, [nr])[0]
    assert "eps_serie" in plan.fehlt_feld and ("eps_bauform", "Gartenhaus") in plan.fehlt_wert
    S.schreiben(a, plan)
    gesetzt = {c["attributeDefinitionId"] for art in a.daten["article"] if art["articleNumber"] == nr
               for c in art["customAttributes"]}
    assert len(gesetzt) == plan.aenderungen and bauform["id"] not in gesetzt
    assert S.kontrolle(a, plan, soll, S.definitionen_lesen(a)) == []      # alles Schreibbare ist angekommen
    assert all(art["customAttributes"] == [] for art in a.daten["article"] if art["articleNumber"] != nr)


def test_schreiben_unbekannter_artikel_und_veraltete_version():
    from eps_produktsuche import weclapp_schreiben as S
    from eps_produktsuche.weclapp import WeclappFehler
    geraete = _geraete_fuer_schreiben()
    a = _leeres_weclapp(geraete)
    werte = S.werte_aus_geraeten(geraete)
    p = S.planen(a, {"XXX": {"eps_bauform": "19 Zoll"}}, ["XXX"])[0]
    assert p.fehler and p.status == "Artikel nicht in Weclapp gefunden"
    nr = geraete[0].bestellnummer
    plan = S.planen(a, {nr: werte[nr]}, [nr])[0]
    for art in a.daten["article"]:                                     # jemand ändert dazwischen
        art["version"] = "9"
    with pytest.raises(ValueError):
        S.schreiben(a, plan)
    lauf = S.alle_schreiben(lambda *x, **k: (_ for _ in ()).throw(WeclappFehler("409")), [plan])
    assert lauf.geschrieben == 0 and "409" in lauf.fehler[0]
