# PyInstaller-Bauplan für die EPS-Produktsuche (eigenständiges Programm, wird von GitHub Actions verwendet)
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "src" / "produktsuche_main.py")],
    pathex=[str(ROOT / "src")],
    # Kunden-Datenblatt auslesen: Auslese-Logik + Feldkatalog des Datenblatt-Converters, pdfplumber, openpyxl
    datas=[(str(ROOT / "assets" / "icon.ico"), "assets"), (str(ROOT / "katalog" / "feldkatalog.xlsx"), "katalog")],
    hiddenimports=["eps_produktsuche.selbsttest", "eps_produktsuche.datenblatt", "eps_converter.auslesen",
                   "eps_converter.importieren", "PIL._tkinter_finder", "tkinterdnd2"],
    excludes=["pytest", "reportlab"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="EPS-Produktsuche",
    icon=str(ROOT / "assets" / "icon.ico"),
    console=False,
    upx=False,
)
