"""Produktsuche V/A/W (v0.12.0)."""
from eps_converter import suche as S
from eps_converter.modell import Datensatz, Wert


def geraet(name, u, i, p, typen=("AC/DC",), parallel=None, reihe=None, nr=""):
    ds = Datensatz()
    ds.werte["typbezeichnung"] = Wert(de=name)
    if nr:
        ds.werte["bestellnummer"] = Wert(de=nr)
    ds.werte["geraetetyp"] = Wert(auswahl=list(typen))
    ds.werte["ausgangsspannung"] = Wert(de=f"0-{u:g} V", min=0, max=u)
    ds.werte["ausgangsstrom"] = Wert(de=f"0-{i:g} A", min=0, max=i)
    ds.werte["ausgangsleistung"] = Wert(de=f"0-{p:g} W", min=0, max=p)
    if parallel:
        ds.werte["parallelschaltung"] = Wert(auswahl=[parallel])
    if reihe is not None:
        ds.werte["reihenschaltung"] = Wert(ja=reihe)
    return ds


def test_anfrage_lesen_beispiel():
    a = S.anfrage_lesen("Stromquelle 0-30V 1kA 30kW")
    assert (a.spannung, a.strom, a.leistung) == (30, 1000, 30000)
    assert a.quelle and a.geraetetyp == ""
    assert "I = 1000 A" in a.erkannt and "P = 30 kW" in a.erkannt


def test_anfrage_varianten():
    a = S.anfrage_lesen("Last 500 V 100A")
    assert (a.spannung, a.strom, a.leistung, a.geraetetyp) == (500, 100, None, S.ELEKTRONISCHE_LAST)
    assert a.leistung_bedarf == 50000
    a = S.anfrage_lesen("DC/DC 48VDC 20,5A 1,5 kW")
    assert (a.spannung, a.strom, a.leistung, a.geraetetyp) == (48, 20.5, 1500, "DC/DC")
    assert S.anfrage_lesen("Netzgerät 30 kVA").leistung == 30000
    assert S.anfrage_lesen("irgendwas").leer()


def test_bewertung_und_reihenfolge():
    alle = [
        geraet("EPS/PSB 10060-1000", 60, 1000, 30000, parallel="Master-Slave"),
        geraet("EPS/PSI 9040-1000", 40, 1000, 30000),                       # genau (≤ +20 % bzw. Obergrenze)
        geraet("EPS/PSI 10080-1000", 80, 1000, 30000),
        geraet("EPS/PS 30-500", 30, 500, 15000, parallel="Ja"),              # 2× parallel
        geraet("EPS/PS 30-500 ohne", 30, 500, 15000, parallel="Nein"),        # fällt raus
        geraet("EPS/PS 30-950", 30, 950, 28500),                             # knapp darunter
        geraet("EPS/ELR 9080-1000", 80, 1000, 30000, typen=("Elektronische Last",)),   # Quelle → keine reine Last
        geraet("EPS/PSB bidir", 60, 1000, 30000, typen=("AC/DC", "Elektronische Last")),
    ]
    a = S.anfrage_lesen("Stromquelle 0-30V 1kA 30kW")
    t = S.suchen(alle, a)
    namen = [x.ds.titel for x in t]
    assert "EPS/ELR 9080-1000" not in namen and "EPS/PS 30-500 ohne" not in namen
    assert t[0].ds.titel == "EPS/PSI 9040-1000" and t[0].kategorie == S.PASST
    par = next(x for x in t if x.ds.titel == "EPS/PS 30-500")
    assert par.kategorie == S.PARALLEL and par.anzahl == 2 and par.bewertung == "2× parallel"
    knapp = next(x for x in t if x.ds.titel == "EPS/PS 30-950")
    assert knapp.kategorie == S.KNAPP_DARUNTER and "Strom" in knapp.hinweis
    assert namen.index("EPS/PS 30-950") == len(namen) - 1
    assert "EPS/PS 30-950" not in [x.ds.titel for x in S.suchen(alle, a, knapp_zeigen=False)]
    # Größere Geräte nach Überdimensionierung: 60 V vor 80 V
    assert namen.index("EPS/PSB 10060-1000") < namen.index("EPS/PSI 10080-1000")


def test_last_und_reihe():
    last = geraet("EPS/ELR 9500-100", 500, 100, 60000, typen=("Elektronische Last",))
    quelle = geraet("EPS/PSI 9500-100", 500, 100, 50000)
    t = S.suchen([last, quelle], S.anfrage_lesen("Last 500V 100A"))
    assert [x.ds.titel for x in t] == ["EPS/ELR 9500-100"]
    hv = geraet("EPS/PS 500-10", 500, 10, 5000, reihe=True)
    t = S.suchen([hv], S.anfrage_lesen("900V 5A"))
    assert t[0].kategorie == S.REIHE and t[0].anzahl == 2


def test_ohne_werte_nicht_vorschlagen():
    ds = geraet("ohne Leistung", 30, 1000, 30000)
    del ds.werte["ausgangsleistung"]
    assert S.bewerten(ds, S.anfrage_lesen("30V 1000A 30kW")) is None
    assert S.bewerten(ds, S.anfrage_lesen("30V 1000A")) is None      # P = U × I wird gebraucht
    assert S.bewerten(ds, S.anfrage_lesen("30V")) is not None


def test_empfehlungstext():
    t = S.suchen([geraet("EPS/PS 30-500", 30, 500, 15000, parallel="Ja", nr="200999")],
                 S.anfrage_lesen("30V 1kA 30kW"))
    de = S.empfehlung(t, S.anfrage_lesen("30V 1kA 30kW"))
    assert "Für Ihre Anforderung (30 V, 1000 A, 30 kW)" in de
    assert "EPS/PS 30-500 (Best.-Nr. 200999)" in de and "2 Geräte parallel (gesamt 1000 A, 30 kW)" in de
    en = S.empfehlung(t, S.anfrage_lesen("30V 1kA 30kW"), "en")
    assert "2 units in parallel" in en and "order no. 200999" in en


def test_ac_dc_und_ueberdimensioniert():
    ac = geraet("EPS/FTP 3K", 115, 8.7, 3000, typen=("AC/AC",))
    dc = geraet("EPS/PS 200-15", 200, 15, 3000)
    assert [t.ds.titel for t in S.suchen([ac, dc], S.anfrage_lesen("115VAC 3kW"))] == ["EPS/FTP 3K"]
    assert [t.ds.titel for t in S.suchen([ac, dc], S.anfrage_lesen("115 VDC 3kW"))] == ["EPS/PS 200-15"]
    assert len(S.suchen([ac, dc], S.anfrage_lesen("115V 3kW"))) == 2
    gross = S.suchen([geraet("EPS/PSB 750", 750, 120, 30000, parallel="Ja")], S.anfrage_lesen("30V 1kA 30kW"))[0]
    assert gross.anzahl == 9 and "Spannung 25×" in gross.hinweis
