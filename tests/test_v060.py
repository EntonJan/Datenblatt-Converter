"""v0.6.0: Papierkorb, Änderungsprotokoll, Doppelte."""
from pathlib import Path

from eps_converter import katalog, protokoll
from eps_converter.ablage import LokaleAblage
from eps_converter.modell import Wert
from beispiel_200034 import datensatz

KAT = Path(__file__).resolve().parents[1] / "katalog" / "feldkatalog.xlsx"


def test_papierkorb(tmp_path):
    ab = LokaleAblage(tmp_path)
    ds = datensatz(); ab.speichern(ds)
    ab.loeschen(ds.id)
    assert ab.alle() == [] and [d.id for d, _ in ab.papierkorb()] == [ds.id]
    ab.wiederherstellen(ds.id)
    assert [d.id for d in ab.alle()] == [ds.id] and ab.papierkorb() == []
    ab.loeschen(ds.id); assert ab.papierkorb_leeren() == 1 and ab.papierkorb() == []


def test_protokoll_unterschiede_und_zusammenfassen():
    k = katalog.laden(KAT)
    ds = datensatz()
    alt = ds.to_dict()
    ds.werte["gewicht"].de = "10 kg"
    ds.werte["kuehlung"].geprueft = not ds.werte["kuehlung"].geprueft
    u = protokoll.unterschiede(alt, ds.to_dict(), k)
    assert ["Gewicht", alt["werte"]["gewicht"]["de"], "10 kg"] in u
    assert any(z[0] == "Kühlung" for z in u)

    class E: benutzer = "Test"
    protokoll.eintragen(ds, E, "Geändert", [["Gewicht", "9,5 kg", "10 kg"]])
    protokoll.eintragen(ds, E, "Geändert", [["Gewicht", "10 kg", "11 kg"], ["Kühlung", "", "Lüfter"]])
    assert len(ds.protokoll) == 1
    assert ds.protokoll[0]["aenderungen"][0] == ["Gewicht", "9,5 kg", "11 kg"] and ds.protokoll[0]["benutzer"] == "Test"
    protokoll.eintragen(ds, E, "Geändert", [["Gewicht", "11 kg", "9,5 kg"]])      # zurück auf Anfang → entfällt
    assert ds.protokoll[0]["aenderungen"] == [["Kühlung", "", "Lüfter"]]


def test_doppelte_typbezeichnung(tmp_path):
    ab = LokaleAblage(tmp_path)
    a = datensatz(); ab.speichern(a)
    b = datensatz(); b.id = "anders"; b.werte["typbezeichnung"] = Wert(de=a.titel.lower() + "  ", en="")
    assert ab.finde_typbezeichnung(b.titel, ausser_id=b.id).id == a.id
    assert ab.finde_typbezeichnung(a.titel, ausser_id=a.id) is None
