"""Interne Vorgangsnummern Anf00001 / Bes00001."""
from eps_produktsuche.mail import Mail
from eps_produktsuche.vorgangsnummer import Nummern


def _m(betreff, wann="2026-11-02T09:00", von="a@kunde.de", quelle="X"):
    return Mail(betreff=betreff, absender_name="A", absender_email=von, empfangen=wann, text="", quelle=quelle)


def test_nummern_zaehlen_je_art_und_bleiben(tmp_path):
    n = Nummern(tmp_path / "vorgangsnummern.json")
    a1, a2, b1 = _m("Anfrage 1"), _m("Anfrage 2", "2026-11-02T10:00"), _m("Bestellung", "2026-11-02T11:00")
    assert n.nummer(a1, "anfrage") == "Anf00001"
    assert n.nummer(b1, "bestellung") == "Bes00001"
    assert n.nummer(a2, "anfrage") == "Anf00002"
    verschoben = _m("Anfrage 1", quelle="NEUE-ENTRYID")         # Outlook-EntryID ändert sich beim Verschieben
    assert n.nummer(verschoben, "anfrage") == "Anf00001"
    n2 = Nummern(tmp_path / "vorgangsnummern.json")              # nach Neustart
    assert n2.vorhanden(a2) == "Anf00002"
    assert n2.nummer(_m("Neu", "2026-11-03T08:00"), "anfrage") == "Anf00003"


def test_artwechsel_gibt_neue_nummer_der_anderen_art(tmp_path):
    n = Nummern(tmp_path / "v.json")
    m = _m("Bestellung PO-1")
    assert n.nummer(m, "anfrage") == "Anf00001"
    assert n.nummer(m, "bestellung") == "Bes00001"
    assert n.nummer(_m("Andere"), "anfrage") == "Anf00002"     # Anf00001 wird nicht wiederverwendet


def test_viele_auf_einmal(tmp_path):
    n = Nummern(tmp_path / "v.json")
    assert n.viele([(_m("x"), "anfrage"), (_m("y", "2026-11-02T12:00"), "bestellung"), (_m("x"), "anfrage")]) == \
        ["Anf00001", "Bes00001", "Anf00001"]
