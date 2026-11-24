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


def _tool(name):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).parent.parent / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_e_artikel_behalten_e_nummer_und_typ():
    m = _tool("weclapp-e-artikel")
    liste = [{"Artikelnummer": "E000039", "Bezeichnung": "Dienstleistung", "Mengeneinheit": "Tag", "Artikelgruppe": "Dienstleistungen", "Lagerartikel": "nein"},
             {"Artikelnummer": "E110835", "Bezeichnung": "Sechskantschraube", "Mengeneinheit": "Stück", "Artikelgruppe": "Schraube, Mutter", "Lagerartikel": "ja"},
             {"Artikelnummer": "E100027", "Bezeichnung": "", "Mengeneinheit": "Stück", "Artikelgruppe": "Option", "Lagerartikel": "nein"},
             {"Artikelnummer": "123456", "Bezeichnung": "x", "Mengeneinheit": "Stück", "Artikelgruppe": "", "Lagerartikel": "ja"}]
    sl = [["Artikelnummer", "Zusatz"], ["E000039", "Reisetag"]]
    zeilen, hinweise = m.zeilen_bauen(liste, sl)
    assert set(zeilen) == {"E000039", "E110835", "E100027"}
    w = m.W
    z = zeilen["E000039"]
    assert z[w._index("D")] == "E000039" and z[w._index("BN")] == "SERVICE" and z[w._index("P")] == "Reisetag"
    assert zeilen["E110835"][w._index("BN")] == "STORABLE" and zeilen["E110835"][w._index("J")] == "Stk."
    assert zeilen["E100027"][w._index("M")] == "Optionen und Zubehör" and zeilen["E100027"][w._index("A")] == "E100027"
    assert any("keine E-Nummer" in h[2] for h in hinweise)


def test_optin_liste_nur_prio_1_prio_0_ist_sperre(tmp_path):
    m = _tool("selectline-optin")
    kopf = ["Kunde", "Lieferant", "Interessent", "Id", "Hauptadresse", "Vorname", "Name", "Firma", "Email", "Prioritaet", "_EPS"]
    zeilen = [kopf,
              ["10004", "", "", "4", "", "", "Pichler", "", "", "", ""],
              ["", "", "", "10", "4", "Eva", "Muster", "", "Eva@Pichler.de", "1", "*"],
              ["", "", "", "11", "4", "Max", "Muster", "", "max@pichler.de", "0", ""],
              ["", "", "", "12", "4", "Kai", "Keiner", "", "kein Interesse", "0", ""],
              ["", "", "", "13", "4", "Ohne", "Prio", "", "ohne@prio.de", "", ""],
              ["", "", "", "14", "4", "Zwie", "Spalt", "", "zwie@pichler.de", "1", ""],
              ["", "", "", "15", "4", "Zwie", "Spalt2", "", "ZWIE@pichler.de", "0", ""]]
    p = tmp_path / "Adressen.csv"
    p.write_text("\n".join(";".join(z) for z in zeilen), encoding="utf-8")
    m.main(p, tmp_path / "aus")
    import csv

    def lies(name):
        return list(csv.reader(open(tmp_path / "aus" / name, encoding="utf-8-sig"), delimiter=";"))
    ok = lies("Optin-Kontakte.csv")
    assert [x[0] for x in ok[1:]] == ["eva@pichler.de"] and ok[1][4:6] == ["Kunde", "10004"] and "EPS" in ok[1][7]
    assert sorted(x[0] for x in lies("Newsletter-Sperre.csv")[1:]) == ["max@pichler.de", "zwie@pichler.de"]
    assert [x[0] for x in lies("Optin-Ausgeschlossen.csv")[1:]] == ["kein Interesse"]
