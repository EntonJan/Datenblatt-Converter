"""Zu versorgendes Gerät (Waschmaschine & Co.): Anschlusswerte → Suche nach AC/AC bzw. DC/AC."""
from eps_produktsuche import verbraucher as V, suche as Q

WASCHMASCHINE_DE = """Muster WM 8000 Waschmaschine
Technische Daten
Fassungsvermögen 8 kg · Schleuderdrehzahl 1400 U/min
Elektrischer Anschluss
Anschlussspannung 220-240 V
Frequenz 50 Hz
Anschlusswert 2,3 kW
Heizleistung 2,0 kW
Absicherung 10 A
Netzkabel mit Schutzkontaktstecker
Wasseranschluss 3/4 Zoll
"""

WASHER_US = """Demo Laundry Pro 120 Washing machine
Electrical connection: 120 V / 60 Hz, 15 A fuse
Rated current 9.5 A
Power consumption 1100 W
Motor power 500 W · Spin speed 1200 rpm
"""

INDUSTRIE = """Industriewaschmaschine IW 25
Anschluss 3N~ 400/230 V 50 Hz
Gesamtanschlusswert 18 kW (Heizung 15 kW, Motor 2,2 kW)
Absicherung 3 x 32 A
Anlaufstrom Motor 28 A
"""

NETZGERAET = """PSX 1000 Labornetzgerät
Ausgangsspannung 0-60 V, Ausgangsstrom 0-50 A, Ausgangsleistung 1000 W
Netzanschluss 230 V 50 Hz, Absicherung 10 A
Restwelligkeit < 10 mV
"""


def test_erkennung_verbraucher_oder_netzgeraet():
    assert V.wahrscheinlich(WASCHMASCHINE_DE)
    assert V.wahrscheinlich(WASHER_US)
    assert V.wahrscheinlich(INDUSTRIE)
    assert not V.wahrscheinlich(NETZGERAET)


def test_waschmaschine_de():
    v = V.lesen(WASCHMASCHINE_DE)
    assert (v.spannung, v.phasen, v.frequenzen, v.leistung, v.absicherung) == (230, 1, [50], 2300, 10)
    assert v.lastart == "gemischt" and v.reserve == 1.5
    v.versorgung = "netz"
    assert v.anfrage() == "AC/AC 230VAC 3,45kVA"            # 50 Hz wird nicht gesucht (Standard)
    a = Q.anfrage_lesen(v.anfrage())
    assert a.spannung == 230 and a.leistung == 3450 and a.geraetetyp == "AC/AC"


def test_waschmaschine_us_auf_batterie():
    v = V.lesen(WASHER_US)
    assert (v.spannung, v.frequenzen, v.leistung, v.strom) == (120, [60], 1100, 9.5)
    v.versorgung, v.dc_spannung = "dc", 48
    assert v.anfrage() == "DC/AC 120VAC 2,2kVA 60Hz Eingang 48VDC"
    a = Q.anfrage_lesen(v.anfrage())
    assert a.geraetetyp == "DC/AC" and a.frequenzen == [60] and a.eingang == 48


def test_industrie_drehstrom_mit_anlaufstrom():
    v = V.lesen(INDUSTRIE)
    assert (v.spannung, v.phasen, v.leistung, v.anlaufstrom) == (230, 3, 18000, 28)
    assert v.reserve == 1.2                                   # Anlaufstrom bekannt → nur kleine Reserve
    h = " ".join(v.hinweise())
    assert "Dreiphasig" in h and "Anlaufstrom 28 A" in h and "Was hat der Kunde zur Verfügung" in h


def test_offene_punkte_im_fremdgeraet(tmp_path):
    from eps_produktsuche import datenblatt, anforderung
    v = V.lesen(WASCHMASCHINE_DE)
    p = tmp_path / "wm.docx"
    _docx(p, WASCHMASCHINE_DE)
    fg = datenblatt.als_verbraucher(p, v)
    assert fg.rolle == "verbraucher" and fg.anfrage() == "230VAC 3,45kVA"
    offen = anforderung.offene_punkte(fg)
    assert any("zur Verfügung" in o for o in offen) and any("Anlaufstrom" in o for o in offen)


def _docx(pfad, text):
    import zipfile
    absaetze = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{z}</w:t></w:r></w:p>" for z in text.splitlines())
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   f'<w:body>{absaetze}</w:body></w:document>')


TABELLE = """WT 360 Waschtrockner 8/5kg
Durchgängig Waschen und Trocknen •
Max. Schleuderdrehzahl 1600
Gewichteter Energieverbrauch pro 100 Betriebszyklen für 262
den vollständigen Betriebszyklus in kWh
Leistungsaufnahme im Aus-Zustand in W 0,30
DuraLife Motor •
Technische Daten
Spannung in V 220-240
Absicherung in A 10
Frequenz in HZ 50
Gesamtanschlusswert in kW 2,10-2,40
Länge der elektrischen Zuleitung in m 2
"""


def test_tabellen_datenblatt_einheit_im_namen():
    """Herstellertabellen „Spannung in V 220-240“ (Einheit vor dem Wert), Standby-Leistung zählt nicht."""
    assert V.wahrscheinlich(TABELLE)
    v = V.lesen(TABELLE)
    assert (v.spannung, v.frequenzen, v.leistung, v.absicherung, v.lastart) == (230, [50], 2400, 10, "gemischt")
    v.versorgung = "netz"
    assert v.anfrage() == "AC/AC 230VAC 3,6kVA"
