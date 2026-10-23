"""Einheiten-Formatierer nach EPS-Hausregel (Antworten 1b 2a 3b 4b 5a 6a 7a 8a 9b 10a 11a 12b 13a 14a 15b 16a)."""
import pytest

from eps_converter.formatierer import formatieren as f


@pytest.mark.parametrize("text,sprache,feld,soll", [
    ("0-750 VDC", "de", "", "0–750 VDC"),
    ("3750V DC", "de", "", "3750 VDC"),
    ("3750VDCmax", "de", "", "3750 VDC max."),
    ("230Vac nominal, 47 – 65Hz 195-264Vac operating range", "en", "",
     "230 VAC nominal, 47–65 Hz 195–264 VAC operating range"),
    ("8.7Arms per phase", "de", "", "8,7 Arms per phase"),
    ("8.7Arms per phase", "en", "", "8.7 Arms per phase"),
    ("0,001 A", "en", "", "0.001 A"),
    ("5000VA continuous", "de", "", "5000 VA continuous"),           # 4b: keine Umrechnung
    ("-20...70°C", "de", "", "−20…70 °C"),
    ("0-50°C", "de", "", "0–50 °C"),
    ("0 º C to +50 º C", "en", "", "0 °C to +50 °C"),
    ("<=0,05% fs", "de", "", "≤0,05% fs"),
    ("<0,01% (+-10%)", "de", "", "<0,01% (±10%)"),
    ("95 %", "de", "", "95%"),
    ("3U7: 432 x 132 x 483mm (17\" x 5\" x 19”) 19” rackmount", "de", "abmessungen",
     "3U7: 432 × 132 × 483 mm 19 Zoll rackmount"),
    ("19\" x 89 x 462", "de", "abmessungen", "19 Zoll × 89 × 462"),
    ("12kg (26 lbs.)", "en", "", "12 kg"),
    ("90-264 VAC, 1ph.+N", "de", "", "90–264 VAC, 1-phasig + N"),
    ("115Vac (L-N), 3-phase, 400Hz", "en", "", "115 VAC (L-N), 3-phase, 400 Hz"),
    ("4-6000 Ohm", "de", "", "4–6000 Ω"),
    ("max.20ms (10-90%)", "de", "", "max. 20 ms (10–90%)"),
    ("500 mVpp(20Mhz)", "de", "", "500 mVpp(20 MHz)"),
    ("Attitude", "en", "", "Altitude"),
    ("Calibration with protocoll", "en", "", "Calibration with protocol"),
    ("Die Geräte sind sind kompakt", "de", "", "Die Geräte sind kompakt"),
])
def test_regeln(text, sprache, feld, soll):
    assert f(text, sprache, feld) == soll


@pytest.mark.parametrize("text", [
    "Designed to meet C22.2 No. 107.1 – 01, UL 458 and EN 60950-1",
    "EN/UL/CSA-C22.2 61010-1,EN55011 cl.B,EN61326-1",
    "E/PS 10750-06 2U",
    "EPS/SL 4x 2x AWG Master-Slave Patch Kabel",
    "TFT Touch Panel 4.0",
    "Input: 3-pole terminal block",
])
def test_normen_und_typen_bleiben(text):
    assert f(text, "de") == text and f(text, "en") == text


@pytest.mark.parametrize("text", ["8.7Arms per phase", "-20...70°C", "3U7: 432 x 132 x 483mm (17\" x 5\")", "0-10V <=0,2%"])
def test_idempotent(text):
    for sp in ("de", "en"):
        einmal = f(text, sp, "abmessungen")
        assert f(einmal, sp, "abmessungen") == einmal


def test_formulierungen_beide_richtungen():
    from pathlib import Path
    from eps_converter import katalog
    k = katalog.laden(Path(__file__).resolve().parents[1] / "katalog" / "feldkatalog.xlsx")
    assert k.teilweise("Less than 5% at full load", "de") == "Kleiner als 5% bei Volllast"
    assert k.teilweise("± 6% from no load to full load", "de") == "± 6% von Leerlauf bis Volllast"
    assert k.teilweise("5 – 95% non-condensing", "de") == "5 – 95% nicht kondensierend"
    assert k.teilweise("Designed to meet UL 458 and EN 60950-1", "de") == "Ausgelegt nach UL 458 und EN 60950-1"
    assert k.teilweise("Temperaturgeregelte Lüfter", "en") == "Temperature controlled fans"
    assert k.teilweise("5-800VDC einstellbar", "en") == "5-800VDC adjustable"
    assert k.teilweise("Standard text without phrases", "de") == "Standard text without phrases"
    # erst übersetzen, dann EPS-Schreibweise
    assert f(k.teilweise("Approx 7 kg (15 lbs)", "de"), "de") == "Ca. 7 kg"
