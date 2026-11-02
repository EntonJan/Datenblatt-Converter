"""Anfrage oder Bestellung? Vorschlag für die Ordner Anfragen/… und Bestellungen/…"""
from pathlib import Path

from eps_produktsuche import kunde as K
from eps_produktsuche.einstellungen import Einstellungen, Anfrageordner
from eps_produktsuche.mail import Mail

SIGNATUR = "\n\nMit freundlichen Grüßen\nMax Mustermann\nMuster Prüftechnik GmbH\nMusterweg 12\n86150 Augsburg"


def art(betreff, text, anhaenge=()):
    e = K.erkennen(Mail(betreff=betreff, absender_name="Max Mustermann", absender_email="m@muster.example",
                        text=text + SIGNATUR, anhaenge=[Path(a) for a in anhaenge]))
    return e


def test_bestellung_mit_po_und_angebot():
    e = art("Bestellung 4500123456", "Sehr geehrte Damen und Herren,\n\nhiermit bestellen wir gemäß Ihrem Angebot "
            "AN-1004 vom 28.10.2026:\n2 Stück EPS/HC 40030-1000-WC (202307)\n\nBestell-Nr.: 4500123456")
    assert e.art == "bestellung" and e.art_sicher
    assert e.bestell_nr == "4500123456" and e.angebots_nr == "AN-1004"


def test_bestellung_als_pdf_anhang():
    e = art("PO 88231", "Hello,\nplease find attached our purchase order.\nBest regards", ["PO_88231.pdf"])
    assert e.art == "bestellung" and e.bestell_nr == "88231"


def test_anfrage_bleibt_anfrage():
    e = art("Anfrage Netzgerät", "Guten Tag,\nbitte um ein Angebot für ein Netzgerät 0-60 V, 50 A, Menge 2.")
    assert e.art == "anfrage" and e.art_sicher


def test_eps_artikelnummer_ist_keine_bestellnummer():
    e = art("Anfrage", "Können Sie uns ein Angebot für Bestellnummer 200961 schicken? Lieferzeit und Preis bitte.")
    assert e.art == "anfrage" and e.bestell_nr == ""


def test_angebot_erwaehnt_aber_frage_bleibt_anfrage():
    e = art("Frage zu Ihrem Angebot AN-1004", "Zu Ihrem Angebot AN-1004 hätten wir eine Frage: gibt es das Gerät "
            "auch mit 19 Zoll? Bitte um ein neues Angebot.")
    assert e.art == "anfrage"


def test_unsicher_wenn_beides():
    e = art("Bestellung", "Wir planen eine Bestellung, bitte um ein Angebot für 3 Geräte 0-30 V 100 A.")
    assert e.art == "anfrage" and not e.art_sicher and any("Bestellung" in g for g in e.art_gruende)


def test_homepage_anfrage_ist_immer_anfrage():
    text = (Path(__file__).parent / "eps-anfrage" / "1_konfigurator_anfragekorb.txt").read_text(encoding="utf-8")
    assert K.erkennen(Mail(betreff="Bestellung", text=text)).art == "anfrage"


def test_ordner_je_art_und_erledigt(tmp_path):
    import json
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"anfrageordner": [{"pfad": "Posteingang/Anfragen/Automatisch", "art": "automatisch"},
                                               {"pfad": "vertrieb@eps.example/Posteingang/Anfragen", "art": "automatisch",
                                                "gemeinsam": True}],
                             "ordner_erledigt": "Posteingang/Anfragen/Erledigt"}), encoding="utf-8")
    e = Einstellungen.laden(p)
    assert [(o.typ, o.pfad) for o in e.anfrageordner if o.typ == "bestellung"] == \
        [("bestellung", "Posteingang/Bestellungen/Automatisch")]           # gemeinsames Postfach bleibt, wie es ist
    assert e.erledigt_fuer("bestellung") == "Posteingang/Bestellungen/Erledigt"
    assert Anfrageordner("Posteingang/Bestellungen/Selbst prüfen").typ == "bestellung"
    e.speichern(p)
    assert len(Einstellungen.laden(p).anfrageordner) == 3                   # nicht doppelt ergänzen


def test_bestellung_sucht_die_bestellten_artikel():
    e = art("Bestellung 4500123456", "hiermit bestellen wir:\n2 Stück EPS/HC 40030-1000-WC (202307)\n"
            "1 Stück EPS/HC 40030-1200-M (200961)\nBestell-Nr.: 4500123456")
    assert e.art == "bestellung" and e.suchtext == "202307 200961" and e.bestell_nr == "4500123456"
