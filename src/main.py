"""Startpunkt der EXE.

Datenblatt-Converter.exe                → Programm starten
Datenblatt-Converter.exe --selbsttest D → Katalog laden, Test-Datenblatt (DE/EN) nach D schreiben, Ergebnis in D\\selbsttest.txt
"""
import sys
from pathlib import Path


def selbsttest(ordner: Path) -> int:
    ordner.mkdir(parents=True, exist_ok=True)
    bericht = ordner / "selbsttest.txt"
    try:
        from eps_converter import katalog, pdf_export, __version__
        from eps_converter.modell import Datensatz, Wert
        k = katalog.laden()
        ds = Datensatz(id="selbsttest")
        for fid, de, en in [("typbezeichnung", "E/PS 10750-06 2U", "E/PS 10750-06 2U"), ("serie", "E/PS 10000 2U", "E/PS 10000 2U"),
                            ("ausgangsspannung", "0–750 V DC", "0–750 V DC"), ("bestellnummer", "999999", "999999"),
                            ("produkttyp", "Labornetzgerät", "Laboratory power supply")]:
            ds.werte[fid] = Wert(de=de, en=en)
        ds.werte["kuehlung"] = Wert(auswahl=["Lüfter"])
        pdfs = pdf_export.beide(ds, k, ordner)
        for lay in ("A", "B"):                                       # alle Layouts müssen sich erzeugen lassen
            pdf_export.erzeugen(ds, k, ordner / f"layout_{lay}.pdf", "de", None, lay)
        from eps_converter import formatierer, protokoll, importieren, gui  # noqa: F401  (alles mitgebaut?)
        assert formatierer.formatieren("230Vac", "de") == "230 VAC"
        dnd = "DnD fehlt"
        try:
            import tkinter
            from tkinterdnd2 import TkinterDnD
            root = tkinter.Tk(); root.withdraw()
            dnd = f"DnD OK {TkinterDnD._require(root)}"
            root.destroy()
        except Exception as e:  # noqa: BLE001
            dnd = f"DnD fehlt: {e}"
        bericht.write_text(f"OK {__version__}: {len(k.felder)} Felder, {len(k.kernfelder)} Kernfelder; "
                           + ", ".join(p.name for p in pdfs) + f"; {dnd}", encoding="utf-8")
        return 0
    except Exception as e:  # noqa: BLE001
        import traceback
        bericht.write_text("FEHLER\n" + traceback.format_exc(), encoding="utf-8")
        return 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selbsttest":
        sys.exit(selbsttest(Path(sys.argv[2])))
    from eps_converter.gui import main
    main()
