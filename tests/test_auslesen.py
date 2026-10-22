"""Prüft das Auslesen an echten Hersteller-PDFs.

Die Beispiel-PDFs liegen NICHT im Repo (Herstellerunterlagen). Pfad per Umgebungsvariable:
    EPS_BEISPIELE=…\\Datenblatt-Converter\\Beispiele
Ohne die Variable werden die Tests übersprungen.
"""
import os
from pathlib import Path

import pytest

from eps_converter import katalog, auslesen

B = os.environ.get("EPS_BEISPIELE")
pytestmark = pytest.mark.skipif(not B, reason="EPS_BEISPIELE nicht gesetzt")
KAT = Path(__file__).resolve().parents[1] / "katalog" / "feldkatalog.xlsx"


def _lesen(datei, modell_label=None):
    k = katalog.laden(KAT)
    p = Path(B) / datei
    erg, _, _ = auslesen.analysieren(p, k)
    m = next(x for x in erg.modelle if x.label == modell_label) if modell_label else None
    return {f: x.text for f, x in auslesen.auslesen(p, k, m).funde.items()}


@pytest.mark.parametrize("modell,u,i,nr", [
    ("PSBE 9750-60", "0...750 V", "0...60 A", "30000328"),
    ("PSBE 91500-30", "0...1500 V", "0...30 A", "30000327"),
])
def test_ea_modelltabelle(modell, u, i, nr):
    f = _lesen("EA-Tektronix/datasheet_elr9000hp_preliminary.pdf", modell)
    assert (f["ausgangsspannung"], f["ausgangsstrom"], f["hersteller_bestellnummer"]) == (u, i, nr)
    assert f["kuehlung"] == "Temperaturgeregelte Lüfter"


def test_trustec_zweistufiger_kopf():
    f = _lesen("TRUSTEC/SP Serie.pdf", "SP-2000 / 248")
    assert f["ausgangsleistung"] == "2000 VA (±3%)"
    assert f["wirkungsgrad"] == "95%"
    assert f["abmessungen"] == "248x83x404.5mm"


def test_absopulse_ueberschrift_ueber_wert():
    f = _lesen("Absopulse/CTP_5K_3P480_E_3U7_3U3_U9118_SCD_U9118A_EPS.pdf")
    assert f["kuehlung"] == "By built-in high quality fans"
    assert f["klirrfaktor"] == "Less than 5% at full load"
    assert f["gewicht"] == "18kg (40 lbs)"


def test_gustav_klein_fussnoten():
    f = _lesen("Gustav Klein/20890-1-1801478 Technische Daten 160kW.pdf")
    assert f["ausgangsspannung"] == "5-800VDC einstellbar"
    assert f["ausgangsleistung"] == "160kW"


def test_schaefer_aufzaehlung_mit_doppelpunkt():
    f = _lesen("Schäfer Elektronik/EPS_DC-DC Serie DE.pdf")
    assert f["eingangsspannung"] == "10 - 800 VDC"
    assert f["ausgangsleistung"] == "50 W - 22 kW"


def test_absopulse_model_mit_doppelpunkt_und_anzeige():
    f = _lesen("Absopulse/SCD - FTC 1K-3PAE-3U3-S8736 EPS.pdf")
    assert f["hersteller_typ"] == "FTC1K-3PA/E-3U3-S8736"
    assert f["anzeige"] == "None"
    assert f["abmessungen"].startswith("3U3: 187 x 132 x 432mm")


def test_absopulse_ausgangsblock_aufteilen():
    f = _lesen("Absopulse/SCD - FTP3K-E-M3P-3U7-19-T5192.pdf")
    assert f["ausgangsspannung"] == "115Vac (L-N), 3-phase, 400Hz"
    assert f["ausgangsstrom"] == "8.7Arms per phase"
    assert f["ausgangsleistung"] == "3000W continuous"
    assert f["ausgangsfrequenz"] == "400Hz"
    assert f["abmessungen"].startswith("3U7: 432 x 132 x 483mm")


def test_absopulse_schraegstrich_in_einer_zeile():
    f = _lesen("Absopulse/CTP_5K_3P480_E_3U7_3U3_U9118_SCD_U9118A_EPS.pdf")
    assert (f["ausgangsspannung"], f["ausgangsstrom"], f["ausgangsleistung"], f["ausgangsfrequenz"]) == \
        ("230Vac", "21.7Arms", "5000VA continuous", "50Hz")


def test_absopulse_ableitungen_und_merkmale():
    f = _lesen("Absopulse/SCD - FTP3K-E-M3P-3U7-19-T5192.pdf")
    assert f["eingangsfrequenz"] == "47 – 65Hz"
    assert f["spannungsfestigkeit_aus_geh"] == "3000Vdc"
    assert f["einschaltstrombegrenzung"] == "Inrush current limiting"
    assert f["alarmmanagement"] == "Not installed"
    assert f["produkttyp"] == "3000VA Industrial Quality Frequency Converter"
    assert f["beschreibung"].startswith("This rugged, AC/AC frequency converter")
    assert "bauform" in f and "ueberhitzungsschutz" in f


def test_produktbild_ohne_logos():
    b = auslesen.bilder_finden(Path(B) / "Absopulse/SCD - FTP3K-E-M3P-3U7-19-T5192.pdf")
    assert len(b) == 1 and b[0][0] == 0
    assert auslesen.bilder_finden(Path(B) / "Gustav Klein/Datenblatt TS-AC-5446-120.pdf") == []   # nur Logo
