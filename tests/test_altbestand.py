"""Import alter EPS-Datenblätter. PDFs liegen nicht im Repo: EPS_ALTBESTAND=…\\EPS-Datenblaetter"""
import os
from pathlib import Path

import pytest

from eps_converter import katalog, eps_altbestand as A
from eps_converter.importieren import _schnittstelle, _wert_altbestand

D = os.environ.get("EPS_ALTBESTAND")
KAT = Path(__file__).resolve().parents[1] / "katalog" / "feldkatalog.xlsx"


def test_option_teilen():
    assert A._option_teilen("Kalibrierung mit Protokoll EPS/I10000 CAL") == ("EPS/I10000 CAL", "Kalibrierung mit Protokoll")
    assert A._option_teilen("EPS/BNC Kabel Share-Bus Verbindungskabel") == ("EPS/BNC", "Kabel Share-Bus Verbindungskabel")
    assert A._option_teilen("E115035 Netz- und Systemüberwachungseinheit") == ("E115035", "Netz- und Systemüberwachungseinheit")
    assert A._option_teilen("Modbus Schnittstelle 1/2Port 2 EPS/IF-AB MB1P/2P")[0] == "EPS/IF-AB MB1P/2P"


def test_schnittstelle_und_auswahl():
    assert _schnittstelle("Option EPS/IF-AB R") == ("Option", "EPS/IF-AB R")
    assert _schnittstelle("Opt. EPS/HC IF-DASI") == ("Option", "EPS/HC IF-DASI")
    assert _schnittstelle("Standard") == ("Standard", "")
    k = katalog.laden(KAT)
    w = _wert_altbestand(k.feld("betriebsarten"), k, "CV. CC. CP", "", "")
    assert w.auswahl == ["CV", "CC", "CP"]
    assert _wert_altbestand(k.feld("kuehlung"), k, "Lüfter", "Fan", "").auswahl == ["Lüfter"]
    assert _wert_altbestand(k.feld("power_fail"), k, "Standard", "Standard", "").ja is True
    assert _wert_altbestand(k.feld("alarmmanagement"), k, "Optional", "", "").ja is None


@pytest.mark.skipif(not D, reason="EPS_ALTBESTAND nicht gesetzt")
def test_103389_und_200034():
    k = katalog.laden(KAT)
    e = A.lesen(Path(D) / "d103389.pdf", k)
    assert (e.serie, e.typbezeichnung, e.produkttyp) == ("EPS/HC 4000-M", "EPS/HC 40500-05-M-DASI", "DC Stromquelle")
    assert e.werte["bestellnummer"][0] == "103389" and e.werte["netzanschluss"][0].startswith("3x380")
    assert e.optionen == [("2", "EPS/HC MP", "Montageplatte")] and e.lieferumfang[0] == "Netzgerät"
    assert e.werte["abmessungen"][0] == "106 x 245 x 402" and not e.unbekannt
    en = A.lesen(Path(D) / "e200034.pdf", k)
    assert en.sprache == "en" and en.serie == "E/PS 10000 2U" and en.produkttyp == "Laboratory Power Supply"
    assert A.partner_datei(Path(D) / "d200034.pdf").name == "e200034.pdf"
