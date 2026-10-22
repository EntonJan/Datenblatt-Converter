"""Ordner, in denen das Programm arbeitet.

RUN_DIR      = Ordner der EXE (bzw. Projektordner beim Entwickeln). Dort liegen
               einstellungen.json, katalog\\, daten\\, ausgabe\\.
RESOURCE_DIR = mitgelieferte Dateien (Logo, Banner, Schriften) – in der EXE eingebettet.
"""
import os
import sys
from pathlib import Path


def _run_dir() -> Path:
    override = os.environ.get("EPS_CONVERTER_HOME")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _resource_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parents[2]


RUN_DIR = _run_dir()
RESOURCE_DIR = _resource_dir()
ASSETS = RESOURCE_DIR / "assets"
KATALOG_DATEI = RUN_DIR / "katalog" / "feldkatalog.xlsx"
KATALOG_MITGELIEFERT = RESOURCE_DIR / "katalog" / "feldkatalog.xlsx"
DATEN_DIR = RUN_DIR / "daten"
AUSGABE_DIR = RUN_DIR / "ausgabe"
EINSTELLUNGEN_DATEI = RUN_DIR / "einstellungen.json"
