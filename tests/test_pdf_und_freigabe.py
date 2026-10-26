from pathlib import Path

import pdfplumber

from eps_converter import katalog, pdf_export, regeln
from eps_converter.ablage import LokaleAblage
from beispiel_200034 import datensatz, FIX

KAT = Path(__file__).resolve().parents[1] / "katalog" / "feldkatalog.xlsx"


def test_katalog_hat_19_kernfelder():
    k = katalog.laden(KAT)
    assert len(k.kernfelder) == 19   # 18 + Netzspannung (AC) – je Gerät sind 18 relevant
    assert k.feld("kuehlung").auswahl[0] == ("Lüfter", "Fan")


def test_freigabe_ok_fuer_vollstaendigen_datensatz():
    k = katalog.laden(KAT)
    assert regeln.pruefe_freigabe(datensatz(), k) == []


def test_freigabe_blockiert_ohne_bestellnummer_und_pruefung():
    k = katalog.laden(KAT)
    ds = datensatz()
    ds.werte["bestellnummer"].de = ""
    ds.werte["kuehlung"].geprueft = False
    probleme = regeln.pruefe_freigabe(ds, k)
    assert "Pflichtfeld fehlt: Bestellnummer" in probleme
    assert "Kernfeld nicht als geprüft markiert: Kühlung" in probleme


def test_pdf_de_en_ohne_herstellerspuren(tmp_path):
    k = katalog.laden(KAT)
    ds = datensatz()
    de, en = pdf_export.beide(ds, k, tmp_path, bild_dir=FIX)
    assert de.name == "d200034.pdf" and en.name == "e200034.pdf"
    for p, muss in ((de, ["KERNDATEN", "Ausgangsspannung", "0–750 V DC", "Lüfter", "Lieferumfang"]),
                    (en, ["KEY DATA", "Output voltage", "Fan", "Scope of delivery", "Altitude"])):
        with pdfplumber.open(p) as pdf:
            text = "\n".join(pg.extract_text() or "" for pg in pdf.pages)
            assert len(pdf.pages) <= 2
        for m in muss:
            assert m in text, (p.name, m)
        assert "Elektro-Automatik" not in text and "Tektronix" not in text


def test_ablage_speichern_laden(tmp_path):
    a = LokaleAblage(tmp_path)
    ds = datensatz()
    a.speichern(ds)
    neu = a.laden(ds.id)
    assert neu.werte["ausgangsspannung"].max == 750
    assert neu.optionen[0].code == "EPS/I10000 CAL"
    assert a.finde_bestellnummer("200034").id == ds.id
