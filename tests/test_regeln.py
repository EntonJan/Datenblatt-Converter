import pytest

from eps_converter import regeln as R


@pytest.mark.parametrize("orig,erwartet", [
    ("PSI 10000", "E/PSI 10000"),
    ("PSB 10000", "E/PSB 10000"),
    ("PS 9000 T", "E/PS 9000 T"),
    ("ELR 9000 HP", "EPS/ELR 9000 HP"),
    ("MP", "EPS/MP"),
    ("EPS/ELR 9000 HP", "EPS/ELR 9000 HP"),
    ("E/PSI 10000", "E/PSI 10000"),
    ("", ""),
])
def test_eps_name(orig, erwartet):
    assert R.eps_name(orig) == erwartet


def test_eps_name_haendlerware():
    assert R.eps_name("ELR 9000 HP", haendlerware=True) == "ELR 9000 HP"


@pytest.mark.parametrize("text,basis,erwartet", [
    ("0-750 VDC", "V", (0, 750)),
    ("0–6 A", "A", (0, 6)),
    ("0-750 V DC", "V", (0, 750)),
    ("1500W/1200W derating", "W", (1200, 1500)),
    ("30kW / 18kW derating", "W", (18000, 30000)),
    ("0-1000 W", "W", (0, 1000)),
    ("208/220V/230V/240V AC +-10% 1ph.", "V", (208, 240)),
    ("90-264 VAC, 1ph.+N", "V", (90, 264)),
    ("-20...70°C", "°C", (-20, 70)),
    ("0-50°C", "°C", (0, 50)),
    ("4-6000 Ohm", "Ω", (4, 6000)),
    ("0,2-370 Ohm", "Ω", (0.2, 370)),
    ("11A", "A", (None, 11)),
    ("9,5 kg", "kg", (None, 9.5)),
    ("", "V", (None, None)),
])
def test_parse_bereich(text, basis, erwartet):
    mn, mx = R.parse_bereich(text, basis)
    assert (mn, mx) == pytest.approx(erwartet) if None not in erwartet else (mn, mx) == erwartet


@pytest.mark.parametrize("wunsch,grenze", [
    (48, 100), (20, 50), (90, 250), (600, 750), (3000, 3750), (0.4, 0.5), (1, 2), (8, 10), (100, 250),
])
def test_obergrenze(wunsch, grenze):
    assert R.obergrenze(wunsch) == pytest.approx(grenze)


def test_dateiname():
    assert R.dateiname("200034", "de") == "d200034.pdf"
    assert R.dateiname("200034", "en") == "e200034.pdf"


def test_versionsvergleich():
    from eps_converter.updates import _tupel
    assert _tupel("v0.3.1") > _tupel("0.3.0")
    assert not _tupel("v0.3.0") > _tupel("0.3.0")
