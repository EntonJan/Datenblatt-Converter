"""Testdatensatz mit den Werten von Artikel 200034 (E/PS 10750-06 2U) aus den SelectLine-Datenblättern d/e200034."""
from pathlib import Path

from eps_converter.modell import Datensatz, Wert, Option, Eintrag, Bild

FIX = Path(__file__).parent / "fixtures"


def datensatz() -> Datensatz:
    ds = Datensatz(id="test200034")
    W = ds.werte

    def t(fid, de, en=None, **kw):
        W[fid] = Wert(de=de, en=en if en is not None else de, geprueft=True, **kw)

    W["geraetetyp"] = Wert(auswahl=["AC/DC"], geprueft=True)
    t("serie", "E/PS 10000 2U")
    t("typbezeichnung", "E/PS 10750-06 2U")
    t("produkttyp", "Labornetzgerät", "Laboratory power supply")
    t("beschreibung", (FIX / "beschreibung_200034_de.txt").read_text(encoding="utf-8").strip(),
      (FIX / "beschreibung_200034_en.txt").read_text(encoding="utf-8").strip())
    t("technologie", "Switching")
    W["betriebsarten"] = Wert(auswahl=["CV", "CC", "CP"], geprueft=True)
    t("netzanschluss", "208/220/230/240 V AC ±10 % 1ph.")
    W["netzspannung"] = Wert(auswahl=["1~ 230 V"], geprueft=True)      # AC/DC: Versorgung über Netzspannung (seit v0.9)
    t("eingangsfrequenz", "45–65 Hz")
    t("leistungsfaktor", "> 0,99")
    W["netzrueckspeisung"] = Wert(ja=False, geprueft=True)
    W["bidirektional"] = Wert(ja=False, geprueft=True)
    t("anzeige", 'TFT Touch Panel 5"', auswahl=["TFT-Touch-Display"])
    t("spannungsaufloesung", "0,1 V")
    t("spannungsgenauigkeit", "≤ 0,05 % fs")
    t("spannungsstabilitaet_last", "< 0,05 % (0–100 %)")
    t("spannungsstabilitaet_netz", "< 0,01 % (±10 %)")
    t("spannungsausregelung_last", "< 1,5 ms (10–100 %)")
    t("anstiegszeit_spannung", "max. 20 ms (10–90 %)")
    t("stromaufloesung", "0,001 A")
    t("stromgenauigkeit", "≤ 0,1 % fs")
    t("stromstabilitaet_last", "< 0,1 % (0–100 %)")
    t("stromstabilitaet_netz", "< 0,01 % (±10 %)")
    t("anstiegszeit_strom", "max. 10 ms (10–90 %)")
    t("begrenzung_ausgangsstrom", "Standard", ja=True)
    t("leistungsgenauigkeit", "< 1 %")
    t("ueberspannungskategorie", "2", auswahl=["2"])
    t("ueberhitzungsschutz", "Standard", ja=True)
    t("spannungsfestigkeit_ein_aus", "3750 V DC")
    t("spannungsfestigkeit_aus_geh", "neg. ±1500 V DC, pos. ±2000 V DC max.")
    t("schutzklasse", "1", auswahl=["1"])
    W["parallelschaltung"] = Wert(auswahl=["Master-Slave"], geprueft=True)
    t("current_sharing", "Standard", ja=True)
    W["kuehlung"] = Wert(auswahl=["Lüfter"], geprueft=True)
    t("betriebstemperatur", "0–50 °C", min=0, max=50)
    t("lagertemperatur", "−20…70 °C", min=-20, max=70)
    t("luftfeuchtigkeit", "< 80 % n.c.")
    t("betriebshoehe", "< 2000 m")
    W["bauform"] = Wert(auswahl=["19 Zoll"], geprueft=True)
    t("normen", "EN/UL/CSA-C22.2 61010-1, EN 55011 cl. B, EN 61326-1")
    t("power_fail", "Standard", ja=True)
    W["funktionsgenerator"] = Wert(ja=False, geprueft=True)
    t("voreinstellung_ausgang", "Standard", ja=True)
    t("speicherplaetze", "5 Presets")
    t("innenkapazitaet", "40 µF")
    for fid, st, code in [("if_analog", "Standard", ""), ("if_usb", "Standard", ""), ("if_ethernet", "Standard", "IF-ETH1P/2P"),
                          ("if_rs232", "Option", "EPS/IF-AB R"), ("if_can", "Option", "EPS/IF-AB-CAN/O"),
                          ("if_profibus", "Option", "EPS/IF-AB PB"), ("if_profinet", "Option", "EPS/IF-AB PN1P/2P"),
                          ("if_modbus", "Option", "EPS/IF-AB MB1P/2P"), ("if_ethercat", "Option", "EPS/IF-AB-ECT")]:
        W[fid] = Wert(if_status=st, if_code=code if st == "Option" else "", geprueft=True)
    W["schnittstellen"] = Wert(geprueft=True)
    t("genauigkeit_schnittstelle", "0–10 V ≤ 0,2 %, 0–5 V ≤ 0,4 %")
    t("software", "Standard EPS/PC, Option EPS/MC")
    t("ausgangsspannung", "0–750 V DC", min=0, max=750)
    t("ausgangsstrom", "0–6 A", min=0, max=6)
    t("ausgangsleistung", "1500 W / 1200 W Derating", "1500 W / 1200 W derating", min=1200, max=1500)
    t("eingangsstrom", "11 A", max=11)
    t("wirkungsgrad", "95 %")
    t("restwelligkeit_u", "500 mVpp (20 MHz) / 50 mVrms (300 k)")
    t("restwelligkeit_i", "< 0,5 mArms")
    t("widerstand_einstellbereich", "4–6000 Ω", min=4, max=6000)
    t("fernfuehlung", "Standard", ja=True)
    t("ausgangsfrequenz", "", auswahl=["DC"])
    t("abmessungen", '19" × 89 × 462 mm')
    t("gewicht", "9,5 kg", max=9.5)
    t("bestellnummer", "200034")
    W["optionen"] = Wert(geprueft=True)
    t("hersteller", "EA Elektro-Automatik / Tektronix")
    ds.optionen = [
        Option("EPS/I10000 CAL", "Kalibrierung mit Protokoll", "Calibration with protocol"),
        Option("EPS/G", "Garantieverlängerung 3 / 5 Jahre", "Extended warranty 3 / 5 years"),
        Option("EPS/IF-AB MB1P/2P", "Modbus-Schnittstelle 1/2 Port", "Modbus interface 1/2 port"),
        Option("EPS/BNC", "Share-Bus-Verbindungskabel", "Share bus connection cable"),
        Option("EPS/SL", "Master-Slave-Patchkabel 4× 2× AWG", "Master-slave patch cable 4× 2× AWG"),
    ]
    ds.lieferumfang = [Eintrag(*x) for x in [
        ("Netzgerät", "Power supply unit"), ("Testprotokoll", "Test report"),
        ("2x Stecker für Fernfühlung", "2x plug for remote sense"), ("Set DC-Klemmenabdeckung", "Set DC terminal cover"),
        ("Set Klemmenabdeckung Sense", "Set terminal cover sense"), ("Kabelbinder für Zugentlastung", "Cable tie for strain relief"),
        ("USB-Kabel 1,8 m", "USB cable 1.8 m"), ("USB-Stick mit Dokumentation und Software", "USB stick with documentation and software")]]
    ds.bilder = [Bild("200034_front.jpg", "Frontansicht", "Front view"), Bild("200034_rear.jpg", "Rückseite", "Rear view")]
    return ds
