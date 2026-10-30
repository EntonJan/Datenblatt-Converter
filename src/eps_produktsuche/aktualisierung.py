"""Selbst-Update der EPS-Produktsuche über GitHub-Releases (Tag „produktsuche-v<Version>“).

Ablauf wie beim Datenblatt-Converter: Beim Start wird im Hintergrund geprüft, ob es eine neuere Version gibt. Auf Wunsch
lädt das Programm „EPS-Produktsuche-v<Version>.exe“ in den Programmordner, startet sie und beendet sich. Die neue Version
entfernt beim Start ältere „EPS-Produktsuche*.exe“ im selben Ordner (eine laufende EXE kann Windows nicht löschen).
Die Shopdaten im Ordner „EPS-Produktsuche-Daten“ bleiben erhalten. Keine Admin-Rechte nötig.

Die Produktsuche-Releases sind nicht „latest“ (das ist der Converter) – deshalb wird die Release-Liste durchsucht.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import __version__

REPO = "EntonJan/Datenblatt-Converter"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=40"
SEITE = f"https://github.com/{REPO}/releases"
PREFIX = "produktsuche-v"
ASSET = "EPS-Produktsuche.exe"
_MUSTER = re.compile(r"^EPS-Produktsuche(?:-v(\d+(?:\.\d+){0,2}))?\.exe$", re.I)


def tupel(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def _anfrage(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "EPS-Produktsuche"})
    return urllib.request.urlopen(req, timeout=timeout)


def neueste(timeout: float = 6.0, releases: list | None = None) -> tuple[str, str] | None:
    """(Version, Download-URL) der neuesten Produktsuche, falls neuer als die laufende – sonst None (auch offline)."""
    if releases is None:
        try:
            with _anfrage(API, timeout) as r:
                releases = json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 – offline, Proxy, Rate-Limit → still bleiben
            return None
    beste = None
    for rel in releases or []:
        tag = rel.get("tag_name", "")
        if not tag.startswith(PREFIX) or rel.get("draft") or rel.get("prerelease"):
            continue
        url = next((a.get("browser_download_url", "") for a in rel.get("assets", []) if a.get("name") == ASSET), "")
        version = tag[len(PREFIX):]
        if url and (beste is None or tupel(version) > tupel(beste[0])):
            beste = (version, url)
    if beste and tupel(beste[0]) > tupel(__version__):
        return beste
    return None


def ist_exe() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_pfad() -> Path:
    return Path(sys.executable).resolve()


def zieldatei(ordner: Path, version: str) -> Path:
    return ordner / f"EPS-Produktsuche-v{version}.exe"


def herunterladen(url: str, ziel: Path, fortschritt=None) -> Path:
    """Lädt in eine .part-Datei und benennt erst bei vollständigem Download um."""
    teil = ziel.with_suffix(".part")
    with _anfrage(url, 30) as r:
        gesamt = int(r.headers.get("Content-Length") or 0)
        geladen = 0
        with teil.open("wb") as fh:
            while True:
                block = r.read(256 * 1024)
                if not block:
                    break
                fh.write(block)
                geladen += len(block)
                if fortschritt:
                    fortschritt(geladen, gesamt)
    if gesamt and teil.stat().st_size != gesamt:
        teil.unlink(missing_ok=True)
        raise IOError("Download unvollständig")
    if ziel.exists():
        ziel.unlink()
    teil.rename(ziel)
    return ziel


def alte_entfernen(ordner: Path | None = None, eigene: Path | None = None, versuche: int = 15) -> list[str]:
    """Löscht ältere EPS-Produktsuche*.exe (auch die unnummerierte „EPS-Produktsuche.exe“) im Programmordner.
    Läuft eine alte Version noch, wird einige Sekunden lang erneut versucht."""
    eigene = (eigene or exe_pfad()).resolve()
    ordner = ordner or eigene.parent
    meine = tupel(__version__)
    geloescht: list[str] = []
    for _ in range(versuche):
        offen = []
        for f in ordner.glob("EPS-Produktsuche*.exe"):
            m = _MUSTER.match(f.name)
            if not m or f.resolve() == eigene or tupel(m.group(1) or "0") >= meine:
                continue
            try:
                f.unlink()
                geloescht.append(f.name)
            except OSError:
                offen.append(f)
        for p in ordner.glob("EPS-Produktsuche*.part"):
            try:
                p.unlink()
            except OSError:
                pass
        if not offen:
            break
        time.sleep(1)
    return geloescht


def starten(ziel: Path) -> None:
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"      # neue EXE nutzt nicht die Temp-Dateien der alten
    subprocess.Popen([str(ziel)], cwd=str(ziel.parent), close_fds=True, env=env,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


# ------------------------------------------------------------------------ Testkanal (Branch weclapp)
# Testversionen sind Vorabversionen „produktsuche-test-<Buildnummer>“ mit EPS-Produktsuche-TEST.exe. Sie ersetzen nur
# sich selbst; die normale Version und ihr Update-Kanal bleiben unberührt.
TEST_PREFIX = "produktsuche-test-"
TEST_ASSET = "EPS-Produktsuche-TEST.exe"


def build() -> int:
    """Buildnummer der laufenden Testversion (von GitHub Actions eingetragen, sonst 0)."""
    try:
        from ._build import BUILD
        return int(BUILD)
    except Exception:  # noqa: BLE001
        return 0


def neueste_test(timeout: float = 6.0, releases: list | None = None, eigener_build: int | None = None):
    """(Buildnummer, Download-URL) der neuesten Testversion, falls neuer als die laufende – sonst None."""
    if releases is None:
        try:
            with _anfrage(API, timeout) as r:
                releases = json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
    eigener = build() if eigener_build is None else eigener_build
    beste = None
    for rel in releases or []:
        tag = rel.get("tag_name", "")
        if not tag.startswith(TEST_PREFIX) or rel.get("draft") or not tag[len(TEST_PREFIX):].isdigit():
            continue
        url = next((a.get("browser_download_url", "") for a in rel.get("assets", []) if a.get("name") == TEST_ASSET), "")
        nr = int(tag[len(TEST_PREFIX):])
        if url and nr > eigener and (beste is None or nr > beste[0]):
            beste = (nr, url)
    return beste


def test_ersetzen(url: str, fortschritt=None, exe: Path | None = None) -> Path:
    """Laufende TEST.exe beiseite benennen (geht unter Windows auch im Betrieb), neue an ihren Platz laden."""
    exe = Path(exe or exe_pfad())
    alt = exe.with_name(exe.stem + ".alt.exe")
    teil = exe.with_suffix(".part")
    herunterladen(url, teil.with_suffix(".exe.neu"), fortschritt)
    neu = teil.with_suffix(".exe.neu")
    if alt.exists():
        alt.unlink()
    exe.rename(alt)
    try:
        neu.rename(exe)
    except OSError:
        alt.rename(exe)                                   # zurück, damit das Programm startbar bleibt
        raise
    return exe


def test_aufraeumen(exe: Path | None = None, versuche: int = 15) -> None:
    exe = Path(exe or exe_pfad())
    for _ in range(versuche):
        reste = [p for p in (exe.with_name(exe.stem + ".alt.exe"), exe.with_suffix(".exe.neu")) if p.exists()]
        if not reste:
            return
        for p in reste:
            try:
                p.unlink()
            except OSError:
                pass
        time.sleep(1)
