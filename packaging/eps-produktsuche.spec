# PyInstaller-Bauplan für die EPS-Produktsuche (eigenständiges Programm, wird von GitHub Actions verwendet)
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "src" / "produktsuche_main.py")],
    pathex=[str(ROOT / "src")],
    # Kunden-Datenblatt auslesen: Auslese-Logik + Feldkatalog des Datenblatt-Converters, pdfplumber, openpyxl
    datas=[(str(ROOT / "assets" / "icon.ico"), "assets"), (str(ROOT / "assets" / "logo.jpg"), "assets"),
           (str(ROOT / "assets" / "fonts" / "Carlito-Regular.ttf"), "assets/fonts"),
           (str(ROOT / "assets" / "fonts" / "Carlito-Bold.ttf"), "assets/fonts"),
           (str(ROOT / "katalog" / "feldkatalog.xlsx"), "katalog")],
    hiddenimports=["eps_produktsuche.selbsttest", "eps_produktsuche.datenblatt", "eps_produktsuche.vergleich",
                   "eps_produktsuche.verlauf", "eps_produktsuche.anforderung",
                   "eps_produktsuche.anfragen", "eps_produktsuche.kunde", "eps_produktsuche.mail",
                   "eps_produktsuche.outlook", "eps_produktsuche.einstellungen", "eps_produktsuche._build", "eps_produktsuche.weclapp",
                   "eps_produktsuche.weclapp_attrappe", "eps_produktsuche.weclapp_dialog", "eps_produktsuche.zugang",
                   "keyring.backends.Windows", "win32ctypes.pywin32.win32cred", "extract_msg",
                   "win32com.client", "pythoncom", "win32timezone", "pywintypes", "eps_produktsuche.aktualisierung", "eps_converter.auslesen",
                   "eps_converter.importieren", "PIL._tkinter_finder", "tkinterdnd2"],
    excludes=["pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="EPS-Produktsuche",
    icon=str(ROOT / "assets" / "icon.ico"),
    console=False,
    upx=False,
)
