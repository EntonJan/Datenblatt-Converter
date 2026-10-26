"""v0.11: Konfigurator-Export, Qualitätsbericht, Selbst-Update (ohne Netz)."""
import csv
import json
from pathlib import Path

from eps_converter import katalog, export, updates
from eps_converter.modell import FREIGEGEBEN, Wert
from beispiel_200034 import datensatz

KAT = Path(__file__).resolve().parents[1] / "katalog" / "feldkatalog.xlsx"


def test_konfigurator_export(tmp_path):
    k = katalog.laden(KAT)
    a = datensatz(); a.status = FREIGEGEBEN
    b = datensatz(); b.id = "entwurf"
    pc, pj, n = export.konfigurator_export([a, b], k, tmp_path, nur_freigegeben=True)
    assert n == 1
    j = json.loads(pj.read_text(encoding="utf-8"))
    g = j["geraete"][0]
    assert g["bestellnummer"] == "200034" and g["pdf_de"] == "d200034.pdf" and g["geraetetyp"] == ["AC/DC"]
    assert g["filter"]["ausgangsspannung"]["bis"] == 750 and g["filter"]["netzspannung"]["werte"] == ["1~ 230 V"]
    assert "eingangsspannung" not in g["filter"]                        # entfällt bei AC/DC
    assert "ausgangsspannung" in j["felder"]
    zeilen = list(csv.reader(pc.open(encoding="utf-8-sig"), delimiter=";"))
    kopf = zeilen[0]
    assert "Ausgangsspannung bis [V]" in kopf and zeilen[1][kopf.index("Ausgangsspannung bis [V]")] == "750"
    assert export.konfigurator_export([a, b], k, tmp_path, nur_freigegeben=False)[2] == 2


def test_sichtbarkeit():
    ds = datensatz()
    assert export.sichtbar(ds) is False
    ds.werte["herkunft"] = Wert(auswahl=["Altbestand"])
    assert export.sichtbar(ds) is True
    ds.werte["shop_sichtbar"] = Wert(ja=False)
    assert export.sichtbar(ds) is False


def test_qualitaet(tmp_path):
    k = katalog.laden(KAT)
    gut = export.qualitaet(datensatz(), k, [])
    assert gut["fehlend"] == [] and gut["ungeprueft"] == []
    schlecht = datensatz()
    schlecht.werte["bestellnummer"].de = ""
    schlecht.werte["kuehlung"].geprueft = False
    q = export.qualitaet(schlecht, k, [])
    assert "Bestellnummer" in q["fehlend"] and "Kühlung" in q["ungeprueft"] and q["punkte"] > gut["punkte"]
    p = export.qualitaet_csv([(schlecht, q)], tmp_path / "q.csv")
    assert "Bestellnummer" in p.read_text(encoding="utf-8-sig")


def test_alte_versionen_entfernen(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "__version__", "0.11.0")
    for n in ("Datenblatt-Converter-v0.9.1.exe", "Datenblatt-Converter-v0.10.0.exe", "Datenblatt-Converter-v0.11.0.exe",
              "Datenblatt-Converter-v0.12.0.exe", "Datenblatt-Converter.exe", "anderes.exe", "Datenblatt-Converter-v0.11.0.part"):
        (tmp_path / n).write_text("x")
    weg = updates.alte_versionen_entfernen(tmp_path, tmp_path / "Datenblatt-Converter-v0.11.0.exe", versuche=1)
    assert sorted(weg) == ["Datenblatt-Converter-v0.10.0.exe", "Datenblatt-Converter-v0.9.1.exe"]
    rest = sorted(p.name for p in tmp_path.iterdir())
    assert rest == ["Datenblatt-Converter-v0.11.0.exe", "Datenblatt-Converter-v0.12.0.exe", "Datenblatt-Converter.exe", "anderes.exe"]


def test_herunterladen_lokal(tmp_path):
    quelle = tmp_path / "q.bin"; quelle.write_bytes(b"A" * 700_000)
    ziel = updates.herunterladen(quelle.as_uri(), tmp_path / "neu.exe", lambda g, t: None)
    assert ziel.read_bytes() == quelle.read_bytes() and not (tmp_path / "neu.part").exists()
