"""Eingangsordner „Arbeitssystem“: Art erkennen, Gerät gefunden → Automatisch, sonst → Selbst prüfen."""
from pathlib import Path

from eps_produktsuche import eingang
from eps_produktsuche.einstellungen import Anfrageordner, Einstellungen
from eps_produktsuche.mail import Mail


class FakeOL:
    def __init__(self, mails):
        self._mails, self.bewegt = mails, []

    def mails(self, pfad, ziel, maximal=200):
        assert pfad == "Posteingang/Arbeitssystem"
        return list(self._mails)

    def verschieben(self, q, z):
        self.bewegt.append((q, z))
        return q + "-neu"


def _einst():
    e = Einstellungen()
    e.anfrageordner = [Anfrageordner("Posteingang/Anfragen/Automatisch", "automatisch"),
                       Anfrageordner("Posteingang/Anfragen/Selbst prüfen", "pruefen")]
    return e


def test_zielordner_mit_und_ohne_eingestellte_bestellordner():
    e = _einst()
    assert eingang.zielordner(e, "anfrage", "automatisch") == "Posteingang/Anfragen/Automatisch"
    assert eingang.zielordner(e, "bestellung", "pruefen") == "Posteingang/Bestellungen/Selbst prüfen"
    assert eingang.zielordner(e, "bestellung", "automatisch") == "Posteingang/Bestellungen/Automatisch"


def test_einsortieren_gefunden_automatisch_sonst_selbst_pruefen(monkeypatch):
    bestellung = Mail(betreff="Bestellung 4711", absender_name="E", absender_email="e@kunde.de",
                      empfangen="2026-11-02T08:00", quelle="B",
                      text="Hiermit bestellen wir gemäß Ihrem Angebot AN-1234:\n2 Stück 202307\nUnsere Bestellnummer: PO-88231")
    unklar = Mail(betreff="Frage", absender_name="M", absender_email="m@kunde.de", empfangen="2026-11-02T09:00",
                  quelle="A", text="Haben Sie etwas für unsere Anlage? Bitte melden.")
    ol = FakeOL([unklar, bestellung])                    # Outlook liefert neueste zuerst
    gefunden = {"B": 1, "A": 0}
    monkeypatch.setattr(eingang, "geraete_finden", lambda m, e, g: gefunden[m.quelle])
    lauf = eingang.einsortieren(ol, _einst(), ["x"], Path("."))
    assert ol.bewegt == [("B", "Posteingang/Bestellungen/Automatisch"), ("A", "Posteingang/Anfragen/Selbst prüfen")]
    assert lauf.sortiert[0].mail.quelle == "B-neu"
    assert "1 → Selbst prüfen" in lauf.text()


def test_eingang_leer_eingestellt_macht_nichts():
    e = _einst()
    e.ordner_eingang = ""
    assert eingang.einsortieren(FakeOL([]), e, [], Path(".")).sortiert == []


def test_geraete_finden_ueber_werte_und_bestellnummer():
    from eps_produktsuche import kunde as K
    from test_produktsuche import katalog
    geraete = katalog()
    anfrage = Mail(betreff="Anfrage", absender_name="M", absender_email="m@kunde.de", empfangen="2026-11-02T09:00",
                   quelle="A", text="Wir suchen eine Stromquelle 0-30V 1kA 30kW. Bitte um Angebot.")
    e = K.erkennen(anfrage)
    assert eingang.geraete_finden(anfrage, e, geraete) >= 1
    leer = Mail(betreff="Frage", absender_name="M", absender_email="m@kunde.de", empfangen="2026-11-02T09:00",
                quelle="C", text="Haben Sie etwas für unsere Anlage? Bitte melden.")
    assert eingang.geraete_finden(leer, K.erkennen(leer), geraete) == 0
    nr = str(geraete[0].bestellnummer)
    best = Mail(betreff="Bestellung", absender_name="E", absender_email="e@kunde.de", empfangen="2026-11-02T08:00",
                quelle="B", text=f"Hiermit bestellen wir:\n2 Stück {nr}\nUnsere Bestellnummer: PO-88231")
    eb = K.erkennen(best)
    assert eingang.geraete_finden(best, eb, geraete) >= 1, eb.suchtext
