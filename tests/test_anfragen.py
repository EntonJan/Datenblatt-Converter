"""Kundenanfragen per Mail (Branch weclapp, experimentell): Mail lesen, Kunde erkennen, Outlook-Ordner (Attrappe)."""
from datetime import datetime
from email.message import EmailMessage

from eps_produktsuche import kunde as K, outlook, suche as Q
from eps_produktsuche.einstellungen import Einstellungen, Anfrageordner
from eps_produktsuche.mail import Mail, datei_lesen, html_zu_text

SIGNATUR_DE = """Sehr geehrte Damen und Herren,

wir suchen ein Labornetzgerät mit 0-60V, 100A und 3kW im 19" Gehäuse. Benötigt werden 2 Stück.
Liefertermin: KW 50

Mit freundlichen Grüßen

Max Mustermann
Einkauf

TEST Muster Testtechnik GmbH & Co. KG
Beispielstraße 12a
86150 Augsburg
Deutschland
Tel.: +49 (0)821 123456-0
Mobil: +49 170 1234567
Fax: +49 821 123456-99
www.muster-testtechnik.de
USt-IdNr.: DE123456789

Von: Vertrieb EPS
Gesendet: Montag
Betreff: alte Mail mit 999V 999A
"""

SIGNATUR_EN = """Hello,
please quote an inverter 125Vdc to 400Vac 6kVA, qty 3 pcs.

Best regards
Jane Doe
Purchasing Manager
TEST Example Rail Systems Ltd.
Unit 4, Test Park
Phone +44 1234 567890
"""


def test_kunde_aus_deutscher_signatur():
    e = K.erkennen(Mail(absender_name="Mustermann, Max", absender_email="Max.Mustermann@muster-testtechnik.de",
                        text=SIGNATUR_DE))
    k = e.kunde
    assert (k.firma, k.rechtsform) == ("TEST Muster Testtechnik", "GmbH & Co. KG")
    assert (k.vorname, k.nachname, k.email) == ("Max", "Mustermann", "max.mustermann@muster-testtechnik.de")
    assert (k.strasse, k.plz, k.ort, k.land) == ("Beispielstraße 12a", "86150", "Augsburg", "DE")
    assert (k.telefon, k.mobil, k.web, k.ust_id) == ("+49 (0)821 123456-0", "+49 170 1234567",
                                                     "www.muster-testtechnik.de", "DE123456789")
    assert e.unsicher == [] and e.menge == 2 and e.termin == "KW 50"
    assert e.suchtext == "Quelle 0-60V 100A 3kW"            # zitierte Mail (999V) zählt nicht, Bauform nicht in die Suche
    assert "999" not in e.anfrage


def test_kunde_aus_englischer_signatur_mit_dc_eingang():
    e = K.erkennen(Mail(absender_name="Jane Doe", absender_email="jane.doe@example-rail.co.uk", text=SIGNATUR_EN))
    k = e.kunde
    assert (k.firma, k.rechtsform, k.vorname, k.nachname, k.land) == ("TEST Example Rail Systems", "Ltd.", "Jane", "Doe", "GB")
    assert e.menge == 3 and e.termin == "ASAP"
    assert any("Adresse" in u for u in e.unsicher) and any("USt-IdNr" in u for u in e.unsicher)
    a = Q.anfrage_lesen(e.suchtext)
    assert (a.eingang, a.spannung, a.leistung, a.geraetetyp) == (125, 400, 6000, "DC/AC")


def test_homepage_formular():
    text = "Neue Anfrage über die Homepage\n\n" + K.FORMULAR_VORLAGE.format(
        firma="TEST Elektronik AG", rechtsform="", anrede="Frau", vorname="Erika", nachname="Musterfrau",
        email="e.musterfrau@test-elektronik.ch", telefon="+41 44 1234567", strasse="Teststrasse 5", plz="8000",
        ort="Zürich", land="Schweiz", ust_id="CHE-123.456.789", produkt="EPS/CTP 6000-125-400 (600149)", menge="2",
        termin="", nachricht="Bitte Angebot.\nDanke")
    e = K.erkennen(Mail(absender_email="noreply@eps-germany.de", text=text))
    assert e.formular and e.unsicher == [] and e.suchtext == "600149" and e.menge == 2 and e.termin == "ASAP"
    assert (e.kunde.firma, e.kunde.rechtsform, e.kunde.land, e.kunde.web) == ("TEST Elektronik", "AG", "CH",
                                                                              "www.test-elektronik.ch")
    assert e.anfrage.endswith("Bitte Angebot.\nDanke")


def test_freemail_ohne_firma():
    e = K.erkennen(Mail(absender_name="Hans Test", absender_email="hans.test@gmail.com",
                        text="Hallo,\nhaben Sie eine E-Last 500V 100A?\n\nViele Grüße\nHans Test"))
    assert e.kunde.firma == "" and "Firma nicht gefunden" in e.unsicher and e.kunde.web == ""
    assert e.suchtext == "Last 500V 100A"


def test_eml_mit_anhang_und_html(tmp_path):
    msg = EmailMessage()
    msg["From"] = "Max Mustermann <max@muster-testtechnik.de>"
    msg["Subject"] = "Anfrage Netzgerät"
    msg["Date"] = "Thu, 29 Oct 2026 10:15:00 +0100"
    msg.set_content("Text")
    msg.add_alternative("<p>Wir suchen <b>60V 100A</b></p><p>Mit freundlichen Grüßen<br>Max Mustermann</p>",
                        subtype="html")
    msg.add_attachment(b"%PDF-1.4 test", maintype="application", subtype="pdf", filename="kunde datenblatt.pdf")
    msg.add_attachment(b"x", maintype="image", subtype="png", filename="logo.png")
    p = tmp_path / "anfrage.eml"
    p.write_bytes(bytes(msg))
    m = datei_lesen(p, tmp_path / "anh")
    assert m.absender_email == "max@muster-testtechnik.de" and m.betreff == "Anfrage Netzgerät"
    assert m.empfangen.startswith("2026-10-29T10:15")
    assert [a.name for a in m.anhaenge] == ["kunde datenblatt.pdf"]       # Logos/Bilder nicht
    assert html_zu_text("<p>A<br>B</p><style>x{}</style>") == "A\nB"


# ---------------------------------------------------------------- Outlook-Attrappe
class _Liste:
    def __init__(self, eintraege):
        self.e = eintraege

    @property
    def Count(self):
        return len(self.e)

    def Item(self, i):
        return self.e[i - 1]

    def Sort(self, *a):
        self.e.sort(key=lambda x: x.ReceivedTime, reverse=True)


class _Ordner:
    def __init__(self, name, parent=None):
        self.Name, self.Parent, self._kinder, self._items = name, parent, [], []
        self.Folders = self
        self.Items = _Liste(self._items)

    @property
    def Count(self):
        return len(self._kinder)

    def Item(self, i):
        return self._kinder[i - 1]

    def Add(self, name):
        k = _Ordner(name, self)
        self._kinder.append(k)
        return k


class _Anhang:
    def __init__(self, name, daten):
        self.FileName, self._d = name, daten

    def SaveAsFile(self, pfad):
        open(pfad, "wb").write(self._d)


class _Item:
    zaehler = 0

    def __init__(self, ordner, betreff, text, anhaenge=()):
        _Item.zaehler += 1
        self.EntryID, self.Class, self.Subject, self.Body, self.HTMLBody = f"ID{_Item.zaehler}", 43, betreff, text, ""
        self.SenderName, self.SenderEmailAddress = "Max Mustermann", "/O=EXCHANGELABS/OU=TEST"
        self.ReceivedTime = datetime(2026, 10, 29, 9, _Item.zaehler % 60)
        self.Attachments = _Liste([_Anhang(n, d) for n, d in anhaenge])
        self.Sender = type("S", (), {"GetExchangeUser": lambda s: type("U", (), {"PrimarySmtpAddress": "Max@Test.de"})()})()
        self.ordner = ordner
        ordner._items.append(self)

    def Move(self, ziel):
        self.ordner._items.remove(self)
        neu = _Item(ziel, self.Subject, self.Body)
        return neu


class _Namespace:
    def __init__(self):
        self.wurzel = _Ordner("jandean.enkelmann@eps-germany.de")
        self.eingang = self.wurzel.Add("Posteingang")
        self.gemeinsam = _Ordner("vertrieb@eps-germany.de")
        self.Folders = _Liste([self.wurzel, self.gemeinsam])

    def GetDefaultFolder(self, n):
        return self.eingang

    def GetItemFromID(self, i):
        for o in self._alle(self.wurzel) + self._alle(self.gemeinsam):
            for it in o._items:
                if it.EntryID == i:
                    return it
        raise LookupError(i)

    def _alle(self, o):
        return [o] + [x for k in o._kinder for x in self._alle(k)]


def test_outlook_ordner_lesen_und_verschieben(tmp_path):
    ns = _Namespace()
    auto = ns.eingang.Add("Anfragen").Add("Automatisch")
    _Item(auto, "Anfrage 1", SIGNATUR_DE, [("datenblatt.pdf", b"%PDF"), ("bild.jpg", b"x")])
    _Item(auto, "Anfrage 2", SIGNATUR_EN)
    geteilt = ns.gemeinsam.Add("Posteingang").Add("Anfragen")
    _Item(geteilt, "Homepage", "x")
    ol = outlook.Outlook(namespace=ns)
    mails = ol.mails("Posteingang/Anfragen/Automatisch", tmp_path)
    assert [m.betreff for m in mails] == ["Anfrage 2", "Anfrage 1"]           # neueste zuerst
    assert mails[1].absender_email == "max@test.de"                            # Exchange-Adresse aufgelöst
    assert [a.name for a in mails[1].anhaenge] == ["datenblatt.pdf"]
    assert len(ol.mails("vertrieb@eps-germany.de/Posteingang/Anfragen", tmp_path)) == 1
    neu = ol.verschieben(mails[0].quelle, outlook.unterordner("Posteingang/Anfragen/Automatisch", "Erledigt"))
    assert [m.betreff for m in ol.mails("Posteingang/Anfragen/Automatisch/Erledigt", tmp_path)] == ["Anfrage 2"]
    assert len(auto._items) == 1 and neu.startswith("ID")
    try:
        ol.mails("Posteingang/gibtsnicht", tmp_path)
        raise AssertionError("Fehler erwartet")
    except outlook.OutlookFehler as e:
        assert "gibtsnicht" in str(e)


def test_einstellungen(tmp_path):
    p = tmp_path / "einstellungen.json"
    e = Einstellungen.laden(p)
    assert not e.experimentell and len(e.anfrageordner) == 2
    e.experimentell = True
    e.anfrageordner.append(Anfrageordner("vertrieb@eps-germany.de/Posteingang/Anfragen", "automatisch", True))
    e.speichern(p)
    e2 = Einstellungen.laden(p)
    assert e2.experimentell and e2.anfrageordner[-1].gemeinsam and e2.anfrageordner[-1].art == "automatisch"


def test_zielordner_name_oder_pfad():
    assert outlook.unterordner("Posteingang/Anfragen/Automatisch", "Erledigt") == "Posteingang/Anfragen/Automatisch/Erledigt"
    assert outlook.unterordner("Posteingang/Anfragen/Automatisch", "Posteingang/Anfragen/Erledigt") == \
        "Posteingang/Anfragen/Erledigt"
