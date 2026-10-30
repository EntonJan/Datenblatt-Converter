"""Selbsttest der fertigen EXE (GitHub Actions): Beispielseite auswerten, Suche ausführen, Oberfläche kurz öffnen."""
from __future__ import annotations

import traceback
from pathlib import Path

from . import __version__, shop, suche as Q

BEISPIEL = """<h1>E/PSI 10000 4U Labornetzgerät 30-1920 kW</h1><p>Parallelschaltung … bis zu 64 Geräte</p>
<div class="listingrow col-xs-12"><div class="lr_title mb"> <strong>E/PSI 10060-1000 4U Labornetzgerät</strong></div>
<div class="lr_desc mb"><span><strong>Bestellnr.:</strong> 200360<br></span><span><strong>Spannung:</strong>&nbsp; 0-60 VDC <br></span>
<span><strong>Strom:</strong>&nbsp; 0-1000 A <br></span><span><strong>Ausgangsleistung:</strong>&nbsp;30000 W<br></span></div>
<a href="/shop/media/products/a200360_0.pdf">PDF</a></div>"""


def selbsttest(ziel: Path) -> int:
    ziel.mkdir(parents=True, exist_ok=True)
    zeilen = [f"EPS-Produktsuche {__version__}"]
    ok = True
    try:
        serie = shop.serie_lesen(BEISPIEL, shop.BASIS + "AC-DC/E-PSI-10000-4U:::1_500.html")
        g = shop.geraete_lesen(BEISPIEL, serie)
        t = Q.suchen(g, Q.anfrage_lesen("Stromquelle 0-30V 1kA 30kW"))
        zeilen.append(f"Geräte: {len(g)} · Treffer: {[x.bewertung for x in t]}")
        ok &= len(g) == 1 and bool(t)
        shop.speichern(g, ziel / "shopdaten.json")
        from . import datenblatt
        kat = datenblatt.katalog()
        zeilen.append(f"Feldkatalog: {len(kat.felder)} Felder · Datenblatt-Import bereit")
        ok &= len(kat.felder) > 50
        fg = datenblatt.Fremdgeraet("test.pdf", umax=60, imax=1000, pmax=30000, geraetetyp=["AC/DC"])
        ok &= fg.anfrage() == "AC/DC 60V 1000A 30kW"
        try:
            import tkinterdnd2  # noqa: F401
            zeilen.append("DnD OK")
        except ImportError:
            zeilen.append("DnD fehlt")
            ok = False
        from . import vergleich, verlauf, aktualisierung
        tr = Q.suchen(g, Q.anfrage_lesen("Stromquelle 0-30V 1kA 30kW"))
        pdf = vergleich.erzeugen(ziel / "vergleich.pdf", tr, Q.anfrage_lesen("Stromquelle 0-30V 1kA 30kW"))
        zeilen.append(f"Gegenüberstellung: {pdf.stat().st_size} Bytes")
        ok &= pdf.stat().st_size > 5000
        verlauf.hinzufuegen(ziel / "verlauf.json", "30V 1kA", "Test")
        ok &= len(verlauf.laden(ziel / "verlauf.json")) == 1
        ok &= aktualisierung.neueste(releases=[{"tag_name": "produktsuche-v99.0.0", "assets": [
            {"name": aktualisierung.ASSET, "browser_download_url": "x"}]}]) == ("99.0.0", "x")
        from . import kunde as KD
        from .mail import Mail
        ek = KD.erkennen(Mail(absender_email="t@test-firma.de", text="Bitte 60V 100A\n\nMit freundlichen Grüßen\n"
                                                                        "Max Test\nTEST Firma GmbH\nTeststr. 1\n86150 Augsburg"))
        zeilen.append(f"Mail-Erkennung: {ek.kunde.firmenname} · {ek.suchtext}")
        ok &= ek.kunde.firmenname == "TEST Firma GmbH" and ek.suchtext == "60V 100A"
        try:
            import extract_msg  # noqa: F401
            from . import outlook as OL
            zeilen.append(f"Outlook-Anbindung: {'verfügbar' if OL.verfuegbar() else 'nicht verfügbar'}")
        except ImportError as ie:
            zeilen.append(f"Mail-Bibliotheken fehlen: {ie}")
            ok = False
        from .gui import App
        app = App(pfad=ziel / "shopdaten.json", automatisch_laden=False, update_pruefen=False)
        app.eingabe.set("Stromquelle 0-30V 1kA 30kW")
        app.update()
        zeilen.append(f"GUI-Zeilen: {len(app.tv.get_children())}")
        ok &= len(app.tv.get_children()) == 1
        app.destroy()
    except Exception:  # noqa: BLE001
        zeilen.append(traceback.format_exc())
        ok = False
    zeilen.append("SELBSTTEST OK" if ok else "SELBSTTEST FEHLER")
    (ziel / "selbsttest.txt").write_text("\n".join(zeilen), encoding="utf-8")
    return 0 if ok else 1
