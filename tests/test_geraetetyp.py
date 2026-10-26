"""Gerätetyp erkennen und Eingangsangaben zuordnen (Entscheidungen 26.10.2026: 1a, 2b, bidirektional wie bisher)."""
from pathlib import Path

from eps_converter import katalog, geraetetyp as G, regeln
from eps_converter.modell import Datensatz, Wert

KAT = Path(__file__).resolve().parents[1] / "katalog" / "feldkatalog.xlsx"
ALLE = {"AC/AC", "AC/DC", "DC/AC", "DC/DC", "Elektronische Last", "Ladegeräte"}


def ds_mit(**werte):
    ds = Datensatz()
    for fid, t in werte.items():
        ds.werte[fid] = Wert(de=t, en=t)
    return ds


def test_erkennen():
    assert G.erkennen(ds_mit(eingangsspannung="230Vac nominal, 47-65Hz", ausgangsspannung="115Vac, 400Hz"), "", ALLE) == ["AC/AC"]
    assert G.erkennen(ds_mit(netzanschluss="3x380...460 VAC", ausgangsspannung="0-500 VDC"), "", ALLE) == ["AC/DC"]
    assert G.erkennen(ds_mit(eingangsspannung="10 - 800 VDC", ausgangsspannung="12 VDC"), "", ALLE) == ["DC/DC"]
    assert G.erkennen(ds_mit(eingangsspannung="125dc nominal 105…140Vdc", ausgangsspannung="230Vac/21.7Arms/50Hz"), "", ALLE) == ["DC/AC"]
    assert G.erkennen(ds_mit(ausgangsspannung="0-750 V"), "Electronic DC Load ELR 9000", ALLE) == ["Elektronische Last"]
    assert G.erkennen(ds_mit(netzanschluss="400 VAC 3ph", ausgangsspannung="0-750 VDC"), "bidirectional power supply source and sink",
                      ALLE) == ["AC/DC", "Elektronische Last"]
    assert G.erkennen(ds_mit(ausgangsspannung="0-60 V"), "heat sink", ALLE) == []      # „heat sink“ ist keine Last


def test_relevanz_und_freigabe():
    assert not G.relevant("eingangsspannung", ["AC/DC"]) and G.relevant("eingangsspannung", ["DC/DC"])
    assert G.relevant("netzspannung", ["AC/DC"]) and not G.relevant("netzspannung", ["DC/AC"])
    assert G.relevant("eingangsspannung", [])                        # ohne Gerätetyp: alles gefragt
    k = katalog.laden(KAT)
    ds = Datensatz(); ds.werte["geraetetyp"] = Wert(auswahl=["DC/DC"])
    p = [t for _, _, t in regeln.pruefe_freigabe_felder(ds, k)]
    assert any("Eingangsspannung" in t for t in p) and not any("Netzspannung" in t for t in p)


def test_netzspannung_vorschlag():
    assert G.netzspannung_vorschlag("3x380...460 VAC o.N. +/- 10%") == ["3~ 400 V", "3~ 480 V"]
    assert G.netzspannung_vorschlag("90-264 VAC, 1ph.+N") == ["1~ Weitbereich 90–264 V"]
    assert G.netzspannung_vorschlag("208/220V/230V/240V AC +-10% 1ph., 110V/120V derati") == ["1~ 115 V", "1~ 230 V"]
    assert G.netzspannung_vorschlag("380V/400V/480V AC +-10% 3ph., 208V derating 18 kW") == ["3~ 208–230 V", "3~ 400 V", "3~ 480 V"]


def test_zuordnen_ac_dc_und_last():
    k = katalog.laden(KAT)
    ds = ds_mit(eingangsspannung="230Vac nominal, 47-65Hz", ausgangsspannung="0-60 VDC")
    G.zuordnen(ds, k, ["AC/DC"])
    assert "eingangsspannung" not in ds.werte and ds.werte["netzanschluss"].de.startswith("230Vac")
    assert ds.werte["netzspannung"].auswahl == ["1~ 230 V"]
    last = ds_mit(eingangsspannung="0-750 V DC", eingangsstrom="0-60 A", netzanschluss="230 VAC")
    G.zuordnen(last, k, ["Elektronische Last"])
    assert last.werte["ausgangsspannung"].de == "0-750 V DC" and last.werte["ausgangsspannung"].max == 750
    assert last.werte["ausgangsstrom"].max == 60
    from eps_converter import darstellung
    last.werte["geraetetyp"] = Wert(auswahl=["Elektronische Last"])
    assert darstellung.label(last, k.feld("ausgangsspannung"), k, "de") == "Eingangsspannung (Lastseite)"
    last.werte["geraetetyp"].auswahl.append("AC/DC")                  # bidirektional: Standard-Bezeichnung
    assert darstellung.label(last, k.feld("ausgangsspannung"), k, "de") == "Ausgangsspannung"
    dc = ds_mit(netzanschluss="24 VDC Bordnetz (18-36 VDC)")
    G.zuordnen(dc, k, ["DC/DC"])
    assert dc.werte["eingangsspannung"].min == 18 and "netzanschluss" not in dc.werte
