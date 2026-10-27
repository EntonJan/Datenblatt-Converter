"""EPS-Produktsuche (eigenes Programm): Shop-Texte lesen, Seiten auswerten, Anfragen bewerten."""
import pytest

from eps_produktsuche import shop as S, suche as Q
from eps_produktsuche.shop import Geraet

SERIENSEITE = """<html><body><h1>E/PSI 10000 4U Labornetzgerät 30-1920 kW</h1>
<div class="cat_desc">Die Geräte bieten standardmäßig die Möglichkeit der Parallelschaltung im Share-Bus-Betrieb sowie eine
echte Master-Slave-Verbindung. Über diese Betriebsart lassen sich bis zu 64 Geräte zu einem System verbinden.
Eine Reihenschaltung ist ebenfalls möglich bei Anhebung der DC Minus- oder Pluspole gegenüber PE.</div>
<div class="pagination_bar clearfix"><div class="pagination pagination-sm pull-left"><span class="small">Zeige <strong>1</strong> bis
<strong>2</strong> (von insgesamt <strong>2</strong> Artikeln)</span></div></div>
<div class="row"><div class="listingrow col-xs-12"><div class="panel-body row">
<div class="lr_content mb col-xs-8 col-sm-5"><div class="lr_title mb"><strong>E/PSI 10060-1000 4U Labornetzgerät</strong></div>
<div class="lr_desc mb"> <span><strong>Bestellnr.:</strong> 200360<br></span> <span><strong>Spannung:</strong>&nbsp; 0-60 VDC <br> </span>
<span><strong>Strom:</strong>&nbsp; 0-1000 A <br> </span> <span> <strong>Ausgangsleistung:</strong>&nbsp;30000 W<br> </span>
<span> <strong>Bauart:</strong>&nbsp;19 Zoll<br> </span> <span> <strong>Betriebseigenschaft:</strong>&nbsp;Unidirektional<br> </span> </div>
</div><a href="/shop/media/products/a200360_0.pdf?MODsid=abc123"><button>Datenblatt (PDF)</button></a></div></div>
<div class="listingrow col-xs-12"><div class="panel-body row">
<div class="lr_content mb col-xs-8 col-sm-5"><div class="lr_title mb"><strong>E/PSI 11000-80 4U Labornetzgerät</strong></div>
<div class="lr_desc mb"> <span><strong>Bestellnr.:</strong> 200367<br></span> <span><strong>Spannung:</strong>&nbsp; 0-1000 VDC <br> </span>
<span><strong>Strom:</strong>&nbsp; 0-80 A <br> </span> <span> <strong>Ausgangsleistung:</strong>&nbsp;30 kW/18 kW derating<br> </span>
<span> <strong>Bauart:</strong>&nbsp;19 Zoll<br> </span></div></div></div></div></div></body></html>"""

URL = "https://www.eps-germany.de/shop/AC-DC/E-PSI-10000-4U-Labornetzgeraet-30-1920-kW:::1_500.html?MODsid=abc123"


def test_serienseite_lesen():
    serie = S.serie_lesen(SERIENSEITE, URL)
    assert serie.titel == "E/PSI 10000 4U Labornetzgerät 30-1920 kW" and serie.geraetetyp == "AC/DC"
    assert serie.parallel and serie.parallel_max == 64 and serie.reihe
    assert "MODsid" not in serie.url
    g = S.geraete_lesen(SERIENSEITE, serie)
    assert [x.bestellnummer for x in g] == ["200360", "200367"]
    a = g[0]
    assert (a.umax, a.imax, a.pmax, a.ac) == (60, 1000, 30000, False)
    assert a.pdf_url == "https://www.eps-germany.de/shop/media/products/a200360_0.pdf"
    assert g[1].pmax == 30000 and g[1].spannung == "0-1000 VDC"


@pytest.mark.parametrize("text,basis,erwartet", [
    ("0-750 VDC", "V", 750), ("5-1000 VDC", "V", 1000), ("0-42 VDC / 0-42 VDC / 3-6 VDC", "V", 42),
    ("0-1000 A", "A", 1000), ("0-170 A / +-170 A / +-170 A", "A", 170), ("2x +-200A", "A", 200), ("+- 1000 A", "A", 1000),
    ("156A/Ph", "A", 156), ("8,7A", "A", 8.7), ("2.17A", "A", 2.17), ("1,45", "A", 1.45), ("4,3Arms/ph(500V L-L)", "A", 4.3),
    ("3Aeff/8App@0-150V / 1.5Aeff/4Ap@150-300V", "A", 3), ("200A/100A (150/300V) / 250A/125A (120/240V)", "A", 250),
    ("30kW / 18kW derating", "W", 30000), ("1500W/1200W derating", "W", 1500), ("10 kW/ 6kW derating", "W", 10000),
    ("2x160W+1x12W", "W", 160), ("10000 VA (cos f_0.8)", "W", 10000), ("265 kVA", "W", 265000),
    ("2000Wpeak/1500W@21°C", "W", 2000), ("3600W/3600VA cos.1.0", "W", 3600), ("0-30000W", "W", 30000),
])
def test_werte(text, basis, erwartet):
    assert S.maximum(text, basis) == pytest.approx(erwartet)


def test_kurzzeitleistung_ignoriert():
    g = Geraet("400000", "EPS/ACS 0400-PS", geraetetyp="AC/AC", spannung="0-300 VAC / 0-425 VDC",
               strom="3Aeff/8App@0-150V", leistung="400 VA, 500 VA 1 min")
    S.auswerten(g)
    assert g.pmax == 400


@pytest.mark.parametrize("text,fest,bereiche", [
    ("200/115 VAC 3ph.+N", [115, 200], []),
    ("3x 400V AC (L-L)", [400], []),
    ("1-150V AC (L-N),3ph.+PE / 1-300V AC (L-N),3ph.+PE", [], [[1, 150], [1, 300]]),
    ("120VAC (100-120V) +-3% se", [120], [[100, 120]]),
    ("200/220/230/240 VAC", [200, 220, 230, 240], []),
    ("1ph. 125VAC+-25A,250VAC+- / Remote: 2-150 V, 3-300 V", [125, 250], [[2, 150], [3, 300]]),
])
def test_ac_spannungen(text, fest, bereiche):
    _, _, f, b = S.spannung_lesen(text, True)
    assert f == fest and b == bereiche


@pytest.mark.parametrize("name,erwartet", [
    ("EPS/ELR 10080-510 3U Elektronische Last mit Netzrückspeisung", (80, 510, None)),
    ("EPS/ELR 12000-40 4U Elektronische Last", (2000, 40, None)),
    ("EPS/EL 9750-40 B Elektronische Last", (750, 40, None)),
    ("EPS/EL 3200-25 B Elektronische Last", (200, 25, None)),
    ("EPS/PUL 10360-480 6U Elektronische Last", (360, 480, None)),
    ("EPS/TSDCR 06003000200 Regeneratives DC Lastsystem", (300, 200, 60000)),
    ("EPS/HC 50010-5000-WC DC Stromquelle", (None, None, None)),
])
def test_aus_typbezeichnung(name, erwartet):
    assert S.aus_typbezeichnung(name) == erwartet


def last(name, nr, leistung, bidir=False, typ="Elektronische Last"):
    g = Geraet(nr, name, geraetetyp=typ, leistung=leistung, bidirektional=bidir, parallel=True, parallel_max=64)
    S.auswerten(g)
    return g


def quelle(name, nr, u, i, p, typ="AC/DC", parallel=False, pmax=None, reihe=False):
    g = Geraet(nr, name, geraetetyp=typ, spannung=u, strom=i, leistung=p, parallel=parallel, parallel_max=pmax, reihe=reihe)
    S.auswerten(g)
    return g


def katalog():
    return [
        quelle("E/PSI 10060-1000 4U", "200360", "0-60 VDC", "0-1000 A", "30000 W", parallel=True, pmax=64, reihe=True),
        quelle("E/PSI 10080-1000 4U", "200361", "0-80 VDC", "0-1000 A", "30000 W", parallel=True, pmax=64),
        quelle("EPS/HC 40030-1000-WC DC Stromquelle", "202307", "0-30 VDC", "0-1000 A", "30000 W"),
        quelle("EPS/HC 40030-1200-M DC Stromquelle", "200961", "0-30 VDC", "0-1200 A", "36000 W"),
        quelle("EPS/HC 40030-600-M DC Stromquelle", "200960", "0-30 VDC", "0-600 A", "18000 W"),
        quelle("E/PSI 10060-510 3U", "200252", "0-60 VDC", "0-510 A", "15kW/ 9kW derating", parallel=True, pmax=64),
        quelle("EPS/HC 50030-2000 DC Stromquelle", "200709", "0-30 VDC", "0-2000 A", "60000 W"),
        quelle("EPS/HC 40024-1000-M DC Stromquelle", "200957", "0-24 VDC", "0-1000 A", "24000 W"),
        last("EPS/ELR 10080-1000 4U Elektronische Last mit Netzrückspeisung", "300311", "0-30000W"),
        quelle("E/PSB 10060-1000 4U Bidirektionales DC-Netzgerät", "200300", "0-60 VDC", "0-1000 A", "30kW / 18kW derating"),
        quelle("EPS/FC 1000-UE AC/AC Frequenzwandler", "400272", "230 VAC", "4,35A", "1000 VA", typ="AC/AC"),
        quelle("EPS/FTP 6000-AE-19 AC/AC Frequenzwandler", "400231", "400/230 VAC 3ph+N", "8,7A", "6000 VA", typ="AC/AC"),
        quelle("EPS/CTP 3000-48-400 Sinus-Wechselrichter", "600144", "3x 400V AC (L-L)", "4,3A", "3000 VA", typ="DC/AC"),
    ]


def test_beispiel_stromquelle_30v_1ka_30kw():
    alle = katalog()
    alle[-4].bidirektional = True
    t = Q.suchen(alle, Q.anfrage_lesen("Stromquelle 0-30V 1kA 30kW"))
    namen = [x.g.name for x in t]
    assert namen[0] == "EPS/HC 40030-1000-WC DC Stromquelle" and t[0].kategorie == Q.PASST
    assert t[1].g.name == "EPS/HC 40030-1200-M DC Stromquelle" and t[1].kategorie == Q.PASST
    assert "EPS/ELR 10080-1000 4U Elektronische Last mit Netzrückspeisung" not in namen   # Quelle → keine reine Last
    assert "EPS/HC 40030-600-M DC Stromquelle" not in namen          # 600 A, keine Parallelschaltung laut Shop
    par = next(x for x in t if x.g.name == "E/PSI 10060-510 3U")
    assert par.kategorie == Q.PARALLEL and par.anzahl == 2
    assert "EPS/HC 40024-1000-M DC Stromquelle" not in namen         # 24 V = 20 % zu wenig
    t = Q.suchen(alle, Q.anfrage_lesen("Stromquelle 0-26V 1kA"))
    assert next(x for x in t if x.g.name == "EPS/HC 40024-1000-M DC Stromquelle").kategorie == Q.KNAPP_DARUNTER
    assert namen.index("E/PSI 10060-1000 4U") < namen.index("EPS/HC 50030-2000 DC Stromquelle")


def test_last_inkl_bidirektional():
    alle = katalog()
    alle[9].bidirektional = True
    t = Q.suchen(alle, Q.anfrage_lesen("E-Last 60V 500A"))
    namen = [x.g.name for x in t]
    assert "EPS/ELR 10080-1000 4U Elektronische Last mit Netzrückspeisung" in namen
    assert "E/PSB 10060-1000 4U Bidirektionales DC-Netzgerät" in namen
    assert "E/PSI 10060-1000 4U" not in namen
    elr = next(x for x in t if x.g.bestellnummer == "300311")
    assert "U, I aus Typbezeichnung" in elr.hinweis


def test_ac_festspannung():
    alle = katalog()
    assert [x.g.bestellnummer for x in Q.suchen(alle, Q.anfrage_lesen("230VAC 1kVA"))] == ["400272", "400231"]
    assert [x.g.bestellnummer for x in Q.suchen(alle, Q.anfrage_lesen("400 VAC 3kVA"))] == ["600144", "400231"]
    assert Q.suchen(alle, Q.anfrage_lesen("115VAC 1kVA")) == []
    assert [x.g.bestellnummer for x in Q.suchen(alle, Q.anfrage_lesen("Wechselrichter 400V 3kW"))] == ["600144"]


def test_anfrage_varianten():
    a = Q.anfrage_lesen("DC/DC 48VDC 20,5A 1,5 kW")
    assert (a.spannung, a.strom, a.leistung, a.geraetetyp, a.ausgang) == (48, 20.5, 1500, "DC/DC", "DC")
    assert Q.anfrage_lesen("Netzgerät 30 kVA").leistung == 30000
    a = Q.anfrage_lesen("Last 500V 100A")
    assert a.last and a.leistung_bedarf == 50000


def test_textsuche_und_max_parallel():
    alle = katalog()
    assert [g.bestellnummer for g in Q.textsuche(alle, "hc 40030")] == ["202307", "200961", "200960"]
    assert [g.bestellnummer for g in Q.textsuche(alle, "200361")] == ["200361"]
    t = Q.suchen(alle, Q.anfrage_lesen("Stromquelle 60V 2000A"))          # P = 120 kW
    assert {x.g.bestellnummer: x.anzahl for x in t if x.kategorie == Q.PARALLEL} == {"200360": 4, "200361": 4, "200252": 8}
    t = Q.suchen(alle, Q.anfrage_lesen("Stromquelle 60V 2000A"), max_parallel=4)
    assert {x.g.bestellnummer for x in t if x.kategorie == Q.PARALLEL} == {"200360", "200361"}


def test_empfehlung():
    alle = katalog()
    a = Q.anfrage_lesen("Stromquelle 0-30V 1kA 30kW")
    t = [x for x in Q.suchen(alle, a) if x.g.name == "E/PSI 10060-510 3U"]
    t[0].g.pdf_url = "https://www.eps-germany.de/shop/media/products/a200252_0.pdf"
    de = Q.empfehlung(t, a)
    assert de.startswith("Für Ihre Anforderung (30 V, 1000 A, 30 kW) empfehlen wir:")
    assert "E/PSI 10060-510 3U (Best.-Nr. 200252): 0-60 VDC / 0-510 A / 15kW/ 9kW derating – 2 Geräte parallel (gesamt 1020 A, 30 kW)" in de
    assert "Datenblatt: https://www.eps-germany.de/shop/media/products/a200252_0.pdf" in de
    assert "2 units in parallel" in Q.empfehlung(t, a, "en")


def test_cache(tmp_path):
    alle = katalog()
    S.speichern(alle, tmp_path / "d.json")
    zurueck, stand = S.laden(tmp_path / "d.json")
    assert len(zurueck) == len(alle) and zurueck[0].umax == 60 and stand and not S.veraltet(stand)
    assert S.laden(tmp_path / "fehlt.json") == ([], "")
    assert S.veraltet("2020-01-01T10:00")


def test_einlesen_mit_attrappe():
    start = ('<a href="https://www.eps-germany.de/shop/AC-DC:::1.html?MODsid=x">AC/DC</a>'
             '<a href="https://www.eps-germany.de/shop/AC-DC/E-PSI-10000-4U-Labornetzgeraet-30-1920-kW:::1_500.html?MODsid=x">S</a>')
    seiten = {S.BASIS: start, "https://www.eps-germany.de/shop/AC-DC:::1.html": start,
              "https://www.eps-germany.de/shop/AC-DC/E-PSI-10000-4U-Labornetzgeraet-30-1920-kW:::1_500.html": SERIENSEITE}

    class Attrappe(S.Leser):
        def holen(self, url):
            return seiten[url]
    meldungen = []
    g = S.einlesen(Attrappe(pause=0), lambda *a: meldungen.append(a))
    assert len(g) == 2 and meldungen[-1][0] == "fertig"


ECHTE_LAST = """<h1 class="well well-sm b #C39FAC">EPS/ELR 10000 3U Elektronische Last Netzrückspeisung 5-15kW</h1>
<div class="listingrow col-xs-12">
<div class="lr_content mb col-xs-8 col-sm-5">
<div class="lr_title mb"> <strong>EPS/ELR 10080-510 3U Elektronische Last mit Netzrückspeisung</strong></div>
<div class="lr_desc mb">
<span><strong>Bestellnr.:</strong> 300297<br></span>
<span>
<strong>Eingangsleistung:</strong>&nbsp;0-15000W<br>
</span>
<span>
<strong>Bauart:</strong>&nbsp;19 Zoll<br>
</span>
<span>
<strong>Betriebseigenschaft:</strong>&nbsp;Unidirektional<br>
</span>

</div>
</div>
<div id="prod_desc3764" class="panel-collapse collapse in" role="tabpanel" aria-labelledby="acc1">
<div class="panel-body">
<div itemprop="description">Konstant I-, U-, P- und R-Betrieb<br/>Lastgleichspannung: 0 V bis 80V<br/>Lastgleichstrom: 0,01 A bis 510A<br/>Lastleistung: 0-15000W<br/>Widerstand:0,02-25 Ohm<br/>Netzspannung: 380V/400V/480V AC +-10% 3ph., <br/>Share Bus für Parallelschaltung<br/></div>
<br/>
<a href="/shop/media/products/a300297_0.pdf" target="_blank">
<button>Datenblatt (PDF)</button>
</a>
</div></div>
<div class="listingbox col-xs-6 col-sm-4"><div class="lb_title mb"><a href="x"><strong>EPS/ELR CAL Kalibrierung mit Protokoll</strong></a></div></div>
"""


def test_echte_lastseite():
    serie = S.serie_lesen(ECHTE_LAST, "https://www.eps-germany.de/shop/E-Last/EPS-ELR-10000-3U-Elektronische-Last-Netzrueckspeisung-5-15kW:::76_504.html")
    assert serie.geraetetyp == "Elektronische Last" and not serie.parallel
    g = S.geraete_lesen(ECHTE_LAST, serie)
    assert len(g) == 1
    e = g[0]
    assert (e.bestellnummer, e.umax, e.imax, e.pmax, e.aus_name) == ("300297", 80, 510, 15000, "")
    assert e.spannung == "0 V bis 80V" and e.strom == "0,01 A bis 510A" and e.parallel
    assert e.pdf_url == "https://www.eps-germany.de/shop/media/products/a300297_0.pdf"


def test_kleiner_groesser_zeichen_bleiben_erhalten():
    seite = ('<h1>EPS/B AC/AC</h1><div class="listingrow"><div class="lr_title mb"><strong>EPS/BB1.5-SSR-AU</strong></div>'
             '<div class="lr_desc mb"><span><strong>Bestellnr.:</strong> 400040<br></span>'
             '<span><strong>Strom:</strong>&nbsp;10Aeff/15App@<150V / 5Aeff/7.5App@>150V<br></span></div></div>')
    g = S.geraete_lesen(seite, S.serie_lesen(seite, "https://www.eps-germany.de/shop/AC-AC/x:::22_577.html"))
    assert g[0].strom == "10Aeff/15App@<150V / 5Aeff/7.5App@>150V"


# ------------------------------------------------------------------ Kunden-/Fremddatenblatt (v1.1.0)
import os
from pathlib import Path

BEISPIELE = Path(os.environ.get("EPS_BEISPIELE", "/nicht/vorhanden"))


def test_angegebene_leistung_gilt_autoranging():
    a = Q.anfrage_lesen("60V 1000A 30kW")
    assert a.leistung_bedarf == 30000                      # nicht 60 kW
    t = Q.suchen(katalog(), a)
    assert t[0].g.bestellnummer == "200360" and t[0].kategorie == Q.PASST
    assert Q.anfrage_lesen("Ladegeräte 230VAC 1kW").geraetetyp == "Ladegeräte"


def test_hilfsfunktionen_datenblatt():
    from eps_produktsuche import datenblatt as D
    assert D._tausender("max. 10.000 A bzw. 2 x 5000 A") == "max. 10000 A bzw. 2 x 5000 A"
    assert D._tausender("2.17 A") == "2.17 A"
    assert D._strangspannung("3/N/PE AC 420/242 V") == 242
    assert D._strangspannung("400/230 VAC 3ph+N") == 230
    assert D._strangspannung("200/220/230/240 VAC") is None
    fg = D.Fremdgeraet("x.pdf", umax=80, imax=360, pmax=15000, geraetetyp=["AC/DC", "Elektronische Last"])
    assert fg.anfrage() == "Last 80V 360A 15kW"
    fg = D.Fremdgeraet("x.pdf", umax=115, imax=8.7, pmax=3000, ac=True, geraetetyp=["AC/AC"])
    assert fg.anfrage() == "AC/AC 115VAC 8,7A 3kW"


def test_empfehlung_als_alternative():
    t = Q.suchen(katalog(), Q.anfrage_lesen("Stromquelle 0-30V 1kA 30kW"))[:1]
    txt = Q.empfehlung(t, Q.anfrage_lesen("Stromquelle 0-30V 1kA 30kW"), alternative_zu="Delta SM 30-1000")
    assert txt.startswith("Als Alternative zu Delta SM 30-1000 (30 V, 1000 A, 30 kW) empfehlen wir:")


@pytest.mark.skipif(not BEISPIELE.exists(), reason="Beispiel-PDFs fehlen")
def test_fremddatenblatt_ftp3k(tmp_path, monkeypatch):
    monkeypatch.setenv("EPS_CONVERTER_HOME", str(tmp_path))
    from eps_produktsuche import datenblatt as D
    p = next(BEISPIELE.glob("Absopulse/*FTP3K*.pdf"))
    mods, hat_text = D.modelle(p)
    assert hat_text and not mods
    fg = D.lesen(p)
    assert (fg.umax, fg.imax, fg.pmax, fg.ac, fg.geraetetyp) == (115, 8.7, 3000, True, ["AC/AC"])
    assert fg.anfrage() == "AC/AC 115VAC 8,7A 3kW"


@pytest.mark.skipif(not BEISPIELE.exists(), reason="Beispiel-PDFs fehlen")
def test_fremddatenblatt_serie_mit_modell():
    from eps_produktsuche import datenblatt as D
    p = next(BEISPIELE.glob("EA-Tektronix/*.pdf"))
    mods, _ = D.modelle(p)
    m = next(x for x in mods if "9080-360" in x.label)
    fg = D.lesen(p, m)
    assert (fg.umax, fg.imax, fg.pmax) == (80, 360, 15000) and "Elektronische Last" in fg.geraetetyp


@pytest.mark.skipif(not BEISPIELE.exists(), reason="Beispiel-PDFs fehlen")
def test_fremddatenblatt_drehstrom_und_tausender():
    from eps_produktsuche import datenblatt as D
    fg = D.lesen(next(BEISPIELE.glob("Gustav Klein/Datenblatt TS-AC-5446-120.pdf")))
    assert fg.umax == 242 and fg.imax == 165.1 and 119000 < fg.pmax < 121000
    fg = D.lesen(next(BEISPIELE.glob("Plating Electronics/*pe5910*.pdf")),
                 next(m for m in D.modelle(next(BEISPIELE.glob("Plating Electronics/*pe5910*.pdf")))[0] if m.label == "unipolar"))
    assert fg.imax == 10000 and fg.pmax == 200000


def test_unplausible_shopdaten_markiert():
    g = quelle("EPS/FTP 3000-UM-19-CT-OF", "400232", "115 VAC", "8,7A", "3000 VA", typ="AC/AC")
    t = Q.bewerten(g, Q.anfrage_lesen("115VAC 3kVA"))
    assert "Shopdaten unplausibel" in t.hinweis
    assert not Q.unplausibel(quelle("EPS/FTP 3000-UM-19", "400227", "200/115 VAC 3ph+N", "8,7A", "3000 VA", typ="AC/AC"))
