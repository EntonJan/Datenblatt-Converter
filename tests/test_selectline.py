"""SelectLine-Export: korrigiert Shopdaten (SelectLine gewinnt), ergänzt optional Artikel ohne Shopseite."""
import csv

from eps_produktsuche import selectline as SL, shop


def _zeile(nr, name, zusatz, u, i, p, status="A", richtung=""):
    r = [""] * SL.SPALTEN
    r[SL.NR], r[SL.BEZEICHNUNG], r[SL.ZUSATZ], r[SL.STATUS] = nr, name, zusatz, status
    r[SL.SPANNUNG], r[SL.STROM], r[SL.LEISTUNG], r[SL.RICHTUNG] = u, i, p, richtung
    r[SL.HERSTELLER_NR] = "HX-" + nr
    return r


def _csv(tmp_path, zeilen):
    p = tmp_path / SL.DATEI
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f, delimiter=";", quoting=csv.QUOTE_ALL).writerows(zeilen)
    return p


def _shopgeraet(nr, name, u, i, p, typ="AC/DC"):
    g = shop.Geraet(nr, name, geraetetyp=typ, spannung=u, strom=i, leistung=p)
    shop.auswerten(g)
    return g


def test_selectline_gewinnt_und_werte_werden_neu_berechnet(tmp_path):
    p = _csv(tmp_path, [_zeile("", "", "nicht mehr verwenden", "", "", ""),
                        _zeile("700029", "EPS/X 1000", "Elektronische Last", "0-1000 VDC", "0-43,75 A", "0-30000 W"),
                        _zeile("600147", "EPS/CTP 6000-48-400-EI-OF-RG", "Sinus-Wechselrichter", "3x 400V AC (L-L)", "8,7A", "6000 VA")])
    art = SL.lesen(p)
    assert set(art) == {"700029", "600147"}
    last = _shopgeraet("700029", "EPS/X 1000 Elektronische Last", "0-1000 VDC", "0-40 A", "", typ=shop.LAST)
    wr = _shopgeraet("600147", "EPS/CTP 6000-48-400-EI-OF Sinus-Wechselrichter", "3x 400V AC (L-L)", "8,7A", "6000 VA",
                     typ="DC/AC")
    fehlt = _shopgeraet("200809", "Nur im Shop", "0-60 VDC", "0-10 A", "600 W")
    geraete, b = SL.anwenden([last, wr, fehlt], art)
    assert last.imax == 43.75 and last.pmax == 30000
    assert wr.name == "EPS/CTP 6000-48-400-EI-OF-RG Sinus-Wechselrichter" and wr.phasen == 3
    assert b.nicht_in_selectline == ["200809"]
    assert {(k[0], k[1]) for k in b.korrigiert} == {("700029", "strom"), ("700029", "leistung"), ("600147", "name")}
    assert last.herkunft == "shop+selectline" and last.hersteller_nr == "HX-700029"
    assert len(geraete) == 3


def test_artikel_ohne_shopseite_nur_wenn_eingeschaltet(tmp_path):
    p = _csv(tmp_path, [_zeile("112813", "EPS/HC 1150-250", "DC Stromquelle", "0-150 VDC", "0-250 A", "37500 W"),
                        _zeile("124031", "EPS/TSDCR 06003000600", "BidirektionalesTestsystem Netzrückspeisung",
                               "0-200 VDC", "+- 600 A", "60000 W", richtung="Bidirektional"),
                        _zeile("124159", "EPS/CFPP-TP", "Touchpanel", "0-2000 VDC", "0-2,5 A", ""),
                        _zeile("113000", "ALT 1", "Labornetzgerät", "0-40 VDC", "0-20 A", "800 W", status="K")])
    art = SL.lesen(p)
    geraete, b = SL.anwenden([], art)
    assert geraete == [] and b.ohne_shop == 2
    geraete, b = SL.anwenden([], art, ohne_shop=True)
    nr = {g.bestellnummer: g for g in geraete}
    assert set(nr) == {"112813", "124031"}
    assert nr["124031"].bidirektional and nr["124031"].rueckspeisung and nr["124031"].herkunft == "selectline"
    assert nr["112813"].umax == 150 and nr["112813"].imax == 250 and nr["112813"].serie == "EPS/HC (SelectLine)"
