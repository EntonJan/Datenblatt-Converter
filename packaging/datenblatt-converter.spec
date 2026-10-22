# PyInstaller-Bauplan für die Windows-EXE (wird von GitHub Actions verwendet)
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "src" / "main.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "assets"), "assets"), (str(ROOT / "katalog" / "feldkatalog.xlsx"), "katalog")],
    hiddenimports=["eps_converter.importieren", "PIL._tkinter_finder"],
    excludes=["pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="Datenblatt-Converter",
    icon=str(ROOT / "assets" / "icon.ico"),
    console=False,
    upx=False,
)
