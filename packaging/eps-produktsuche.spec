# PyInstaller-Bauplan für die EPS-Produktsuche (eigenständiges Programm, wird von GitHub Actions verwendet)
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "src" / "produktsuche_main.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "assets" / "icon.ico"), "assets")],
    hiddenimports=["eps_produktsuche.selbsttest"],
    excludes=["pytest", "reportlab", "openpyxl", "pdfplumber", "pypdfium2", "PIL", "tkinterdnd2", "eps_converter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="EPS-Produktsuche",
    icon=str(ROOT / "assets" / "icon.ico"),
    console=False,
    upx=False,
)
