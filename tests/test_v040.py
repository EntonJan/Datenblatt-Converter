"""Neuerungen v0.4.0: Herstellerspuren, Duplizieren, Layout, Bildränder, Darstellung."""
from pathlib import Path

import pdfplumber
from PIL import Image, ImageDraw

from eps_converter import katalog, pdf_export, regeln, darstellung, auslesen
from eps_converter.ablage import LokaleAblage
from eps_converter.modell import Wert, Datensatz, FREIGEGEBEN, ENTWURF
from beispiel_200034 import datensatz, FIX

KAT = Path(__file__).resolve().parents[1] / "katalog" / "feldkatalog.xlsx"


def test_200034_ohne_herstellerspuren():
    k = katalog.laden(KAT)
    assert regeln.herstellerspuren(datensatz(), k, ["EA Elektro-Automatik", "Absopulse Electronics"]) == []


def test_herstellerspuren_gefunden():
    k = katalog.laden(KAT)
    ds = datensatz()
    ds.werte["hersteller"] = Wert(de="Absopulse", en="Absopulse")
    ds.werte["hersteller_typ"] = Wert(de="FTP 3K-E/M3P", en="FTP 3K-E/M3P")
    ds.werte["beschreibung"] = Wert(de="", en="Three CAP 1200 modules. Manufactured at our plant. See www.absopulse.com")
    ds.werte["kuehlung"].de = "Absopulse Lüfter"
    ds.werte["normen"] = Wert(de="EN 60950-1, UL 458", en="EN 60950-1, UL 458")
    funde = {(f, t) for f, t, _ in regeln.herstellerspuren(ds, k, ["Absopulse Electronics"])}
    assert ("beschreibung", "CAP 1200") in funde
    assert ("beschreibung", "our plant") in funde
    assert ("beschreibung", "www.") in funde
    assert ("kuehlung", "Absopulse") in funde
    assert not any(f == "normen" for f, _ in funde)           # Normen sind keine Modellnummern


def test_bestellnummer_nicht_in_tabelle():
    k = katalog.laden(KAT)
    assert not any("Bestellnummer" in a for a, _ in darstellung.zeilen(datensatz(), k, katalog.TECH, "de"))


def test_duplizieren(tmp_path):
    ab = LokaleAblage(tmp_path)
    ds = datensatz()
    ds.status = FREIGEGEBEN
    ab.speichern(ds)
    (ab.ordner(ds.id) / "bild.png").write_bytes(b"x")
    neu = ab.duplizieren(ds.id)
    assert neu.id != ds.id and neu.status == ENTWURF
    assert neu.bestellnummer == "" and not any(w.geprueft for w in neu.werte.values())
    assert neu.text("ausgangsspannung") == ds.text("ausgangsspannung")
    assert (ab.ordner(neu.id) / "bild.png").exists()


def test_einseitig_wenn_es_passt(tmp_path):
    k = katalog.laden(KAT)
    ds = Datensatz()
    for fid, t in (("typbezeichnung", "EPS/TEST"), ("bestellnummer", "1"), ("ausgangsspannung", "230 V"),
                   ("gewicht", "12 kg")):
        ds.werte[fid] = Wert(de=t, en=t)
    ds.werte["beschreibung"] = Wert(de="Kurzer Text. " * 40, en="Short text. " * 40)
    p = pdf_export.erzeugen(ds, k, tmp_path / "x.pdf", "de")
    with pdfplumber.open(p) as pdf:
        assert len(pdf.pages) == 1


def test_bildrand_linie_wird_entfernt():
    im = Image.new("RGB", (200, 100), "white")
    d = ImageDraw.Draw(im)
    d.rectangle((40, 30, 160, 80), fill=(120, 150, 180))
    d.line((0, 0, 199, 0), fill="black", width=3)              # Tabellenlinie oben
    t = auslesen._raender_trimmen(im)
    assert t.size[1] <= 97 and t.getpixel((100, 0)) != (0, 0, 0)


def test_alle_layouts(tmp_path):
    k = katalog.laden(KAT)
    for lay in ("A", "B", "C"):
        for sp in ("de", "en"):
            p = pdf_export.erzeugen(datensatz(), k, tmp_path / f"{lay}{sp}.pdf", sp, FIX, lay)
            with pdfplumber.open(p) as pdf:
                text = " ".join(pg.extract_text() or "" for pg in pdf.pages)
                assert "E/PS 10750-06 2U" in text and "200034" in text
                assert ("Ausgangsspannung" if sp == "de" else "Output voltage") in text
                if lay == "B":
                    assert len(pdf.pages) == 1                       # Kompakt: eine Seite
