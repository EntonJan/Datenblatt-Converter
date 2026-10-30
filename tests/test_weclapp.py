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
    assert "eps_bestellnummer" not in schluessel and any(s[0] == "bestellnummer" for s in standard)
    g = shop.Geraet("T-125", "TEST CTP 6000-125-400 Wechselrichter", serie="TEST", geraetetyp="DC/AC",
                    spannung="3x 400V AC (L-L)", strom="8,6A", leistung="6000 VA")
    shop.auswerten(g)
    z = dict(zip([s for s, _ in WF.IMPORT_SPALTEN], WF.artikel_zeilen([g])[0]))
    assert (z["eps_eingangsspannung_min"], z["eps_ausgangsspannung_fest"], z["eps_ausgangsfrequenz"]) == ("125", "400", "")
    assert z["Warengruppe"] == "DC/AC" and "Bauform fehlt" in z["Prüfen"]
