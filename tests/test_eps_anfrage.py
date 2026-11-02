"""EPS-Anfrage Format 1: gemeinsame Beispiele mit dem Produktkonfigurator (tests/eps-anfrage, in beiden Repos gleich)."""
import json
from email.message import EmailMessage
from pathlib import Path

import pytest

from eps_produktsuche import anfrage_format as F, kunde as K, suche as Q
from eps_produktsuche.mail import Mail, eml_lesen

ORDNER = Path(__file__).parent / "eps-anfrage"
BEISPIELE = sorted(ORDNER.glob("*.json"))
BEISPIELE = [p for p in BEISPIELE if p.name != "eps-anfrage.schema.json"]


def test_beispiele_vorhanden():
    assert len(BEISPIELE) >= 3


@pytest.mark.parametrize("pfad", BEISPIELE, ids=lambda p: p.stem)
def test_text_aus_json_wie_vorgegeben(pfad):
    """Genau dieser Textblock muss entstehen – auch der Konfigurator (PHP) wird gegen die .txt-Datei getestet."""
    d = json.loads(pfad.read_text(encoding="utf-8"))
    assert F.als_text(d) + "\n" == pfad.with_suffix(".txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("pfad", BEISPIELE, ids=lambda p: p.stem)
def test_text_und_json_ergeben_dasselbe(pfad):
    aus_json = F.aus_json(pfad.read_text(encoding="utf-8"))
    aus_text = F.aus_text(pfad.with_suffix(".txt").read_text(encoding="utf-8"))
    for feld in ("anfrage_nr", "erstellt", "quelle", "sprache", "kunde", "positionen", "wunschtermin", "nachricht",
                 "datenschutz"):
        assert aus_text[feld] == aus_json[feld], feld
    assert aus_text["suche"]["text"] == aus_json["suche"]["text"]


def _mail(text: str, json_anhang: str | None = None) -> Mail:
    return Mail(betreff="Anfrage über die Homepage", absender_name="EPS Website", absender_email="website@example.com",
                text=text, daten=F.aus_json(json_anhang) if json_anhang else None)


def test_anfragekorb_mit_positionen():
    p = ORDNER / "1_konfigurator_anfragekorb.json"
    for mail in (_mail("Neue Anfrage", p.read_text(encoding="utf-8")),               # Anhang
                 _mail("Neue Anfrage\n\n" + p.with_suffix(".txt").read_text(encoding="utf-8"))):   # nur Textblock
        e = K.erkennen(mail)
        assert e.formular and e.quelle == "produktkonfigurator" and e.anfrage_nr == "EPS-20261102-114805-7F3A"
        assert [x["bestellnummer"] for x in e.positionen] == ["202307", "200961"]
        assert [x["menge"] for x in e.positionen] == [2, 1] and e.menge is None
        assert e.suchtext == "Stromquelle 0-30V 1kA 30kW" and e.termin == "KW 50"
        assert (e.kunde.firma, e.kunde.rechtsform, e.kunde.land, e.kunde.ust_id) == \
            ("Muster Prüftechnik", "GmbH", "DE", "DE123456789")
        assert e.unsicher == []


def test_textanfrage_wird_wie_kundenmail_ausgewertet():
    e = K.erkennen(_mail((ORDNER / "2_textanfrage.txt").read_text(encoding="utf-8")))
    assert e.quelle == "anfrageformular" and e.positionen == []
    assert "80" in e.suchtext and "3" in e.suchtext and e.menge == 3
    assert "– Ende –" in e.anfrage and "Danke!" in e.anfrage          # Kundentext beendet den Block nicht


def test_ein_artikel_ohne_suche_nimmt_die_menge():
    d = json.loads((ORDNER / "3_englisch_ein_artikel.json").read_text(encoding="utf-8"))
    d["suche"]["text"] = ""
    e = K.erkennen(_mail("x", json.dumps(d)))
    assert e.menge == 1 and e.suchtext == "400151" and e.sprache == "en"


def test_mehrere_bestellnummern_finden_jede():
    from eps_produktsuche.shop import Geraet
    g = [Geraet("202307", "A"), Geraet("200961", "B"), Geraet("100000", "C")]
    assert [x.bestellnummer for x in Q.textsuche(g, "202307 200961")] == ["202307", "200961"]


def test_alter_formularblock_wird_weiter_gelesen():
    text = K.FORMULAR_VORLAGE.format(firma="Alt GmbH", rechtsform="", anrede="", vorname="A", nachname="B",
                                     email="a@alt.example", telefon="", strasse="", plz="", ort="", land="DE",
                                     ust_id="", produkt="EPS/PS 10060 (200123)", menge="4", termin="", nachricht="Hallo")
    e = K.erkennen(_mail(text))
    assert e.formular and e.kunde.rechtsform == "GmbH" and e.positionen[0]["bestellnummer"] == "200123"
    assert e.menge == 4 and e.suchtext == "200123"


def test_json_anhang_in_eml(tmp_path):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = "EPS Website <website@example.com>", "vertrieb@example.com", "Anfrage"
    msg.set_content("Neue Anfrage über die Homepage (Details im Anhang).")
    msg.add_attachment((ORDNER / "1_konfigurator_anfragekorb.json").read_bytes(), maintype="application",
                       subtype="json", filename=F.ANHANG)
    pfad = tmp_path / "a.eml"
    pfad.write_bytes(bytes(msg))
    m = eml_lesen(pfad, tmp_path / "anh")
    assert m.daten and m.daten["anfrage_nr"] == "EPS-20261102-114805-7F3A" and m.anhaenge == []
    assert K.erkennen(m).positionen[0]["menge"] == 2
