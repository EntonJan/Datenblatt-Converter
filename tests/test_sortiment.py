"""Hinweis bei Anfragen außerhalb unseres Sortiments (z. B. „EPS“ = Electric Power Steering)."""
from pathlib import Path

from eps_produktsuche import eingang, kunde as K, sortiment as S
from eps_produktsuche.mail import Mail


def test_fachfremde_begriffe_nur_ohne_sortimentsbegriff():
    assert S.fachfremd("Elektronischer Lenkungsregler; Modell 1220-2201; Spannung 24V; Strom 40A\n"
                       "An: EPS Stromversorgung GmbH, sales@eps-germany.de") == ["Lenkungsregler"]
    assert S.fachfremd("Hydraulikpumpe 24V 40A, Magnetventil 24 V") == ["Hydraulikpumpe", "Magnetventil"]
    assert S.fachfremd("Wir suchen eine Stromquelle 0-30V 1kA 30kW") == []
    assert S.fachfremd("Ersatzteil für unser Netzgerät PSI 9000") == []
    assert S.fachfremd("Ersatzteil Nr. 4711, Teilenummer 17728700") == []        # schwache Begriffe allein
    assert S.fachfremd("Bitte Angebot für 2 Stück 202307") == []
    assert S.fachfremd("Forklift steering controller 24V 40A, last order was in May") == ["Forklift", "steering"]


def test_mail_hinweis_ohne_signatur_und_eingang_selbst_pruefen():
    fremd = Mail(betreff="Anfrage 2097645", absender_name="I. D.", absender_email="iryna@impexron.de",
                 empfangen="2026-11-06T09:00", quelle="X",
                 text="Sehr geehrte Damen und Herren,\nbitte um Angebot: Elektronischer Lenkungsregler 1220-2201, "
                      "Spannung 24V; Strom 40A, 1 St.\n\nMit freundlichen Grüßen\nIryna Demenko\nIMPEXRON GmbH")
    e = K.erkennen(fremd)
    assert e.fachfremd == ["Lenkungsregler"] and "Sortiment" in e.unsicher[0]
    assert eingang.geraete_finden(fremd, e, ["irgendein Gerät"]) == 0
    normal = Mail(betreff="Anfrage", absender_name="M", absender_email="m@kunde.de", empfangen="2026-11-06T09:00",
                  quelle="Y", text="Wir benötigen ein Netzteil 24V 10A.\n\nMit freundlichen Grüßen\nMax Müller\n"
                                   "Müller Hydraulik GmbH")
    assert K.erkennen(normal).fachfremd == []


def test_datenblatt_hinweis(tmp_path):
    from eps_produktsuche import datenblatt as D
    fg = D.Fremdgeraet(datei="x.pdf")
    D._sortiment_pruefen(fg, "Elektronischer Lenkungsregler; Spannung 24V; Strom 40A")
    assert fg.fachfremd == ["Lenkungsregler"] and fg.hinweise[0].startswith("⛔ Nicht aus unserem Sortiment")
