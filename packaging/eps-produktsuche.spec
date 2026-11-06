# PyInstaller-Bauplan für die EPS-Produktsuche (eigenständiges Programm, wird von GitHub Actions verwendet)
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files
ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "src" / "produktsuche_main.py")],
    pathex=[str(ROOT / "src")],
    # Kunden-Datenblatt auslesen: Auslese-Logik + Feldkatalog des Datenblatt-Converters, pdfplumber, openpyxl
    datas=[(str(ROOT / "assets" / "icon.ico"), "assets"), (str(ROOT / "assets" / "logo.jpg"), "assets"),
           (str(ROOT / "assets" / "fonts" / "Carlito-Regular.ttf"), "assets/fonts"),
           (str(ROOT / "assets" / "fonts" / "Carlito-Bold.ttf"), "assets/fonts"),
           (str(ROOT / "katalog" / "feldkatalog.xlsx"), "katalog")] + collect_data_files("customtkinter"),
    hiddenimports=["eps_produktsuche.selbsttest", "eps_produktsuche.datenblatt", "eps_produktsuche.vergleich",
                   "eps_produktsuche.verlauf", "eps_produktsuche.anforderung",
                   "eps_produktsuche.anfragen", "eps_produktsuche.kunde", "eps_produktsuche.mail",
                   "eps_produktsuche.outlook", "eps_produktsuche.einstellungen", "eps_produktsuche._build", "eps_produktsuche.weclapp",
                   "eps_produktsuche.weclapp_attrappe", "eps_produktsuche.weclapp_dialog", "eps_produktsuche.zugang",
                   "eps_produktsuche.datenquelle", "eps_produktsuche.weclapp_felder",
                   "eps_produktsuche.thema", "eps_produktsuche.seiten", "eps_produktsuche.verbraucher", "eps_produktsuche.anfrage_format", "eps_produktsuche.eingang", "eps_produktsuche.vorgangsnummer", "eps_produktsuche.selectline", "eps_produktsuche.sortiment", "customtkinter", "darkdetect",
                   "keyring.backends.Windows", "win32ctypes.pywin32.win32cred", "extract_msg",
                   "win32com.client", "pythoncom", "win32timezone", "pywintypes", "eps_produktsuche.aktualisierung", "eps_converter.auslesen",
                   "eps_converter.importieren", "PIL._tkinter_finder", "tkinterdnd2"],
    excludes=["pytest"],
)
pyz = PYZ(a.pure)
# Startbild: erscheint sofort beim Doppelklick, während die EXE sich entpackt (schließt das Programm selbst)
splash = Splash(str(ROOT / "assets" / "splash.png"), binaries=a.binaries, datas=a.datas, text_pos=None,
                minify_script=True, always_on_top=False)
import os

if os.environ.get("EPS_ORDNER") == "1":
    # Ordner-Variante (schneller Start: kein Entpacken bei jedem Start), als ZIP im Release.
    exe = EXE(
        pyz, a.scripts, splash, [],
        exclude_binaries=True,
        name="EPS-Produktsuche",
        icon=str(ROOT / "assets" / "icon.ico"),
        console=False,
        upx=False,
    )
    coll = COLLECT(exe, splash.binaries, a.binaries, a.datas, upx=False,
                   name=os.environ.get("EPS_ORDNER_NAME", "EPS-Produktsuche-TEST-Ordner"))
else:
    exe = EXE(
        pyz, a.scripts, splash, splash.binaries, a.binaries, a.datas, [],
        name="EPS-Produktsuche",
        icon=str(ROOT / "assets" / "icon.ico"),
        console=False,
        upx=False,
    )
