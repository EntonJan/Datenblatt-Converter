"""Selbst-Update der EPS-Produktsuche über GitHub-Releases (Tag „produktsuche-v<Version>“).

Ablauf wie beim Datenblatt-Converter: Beim Start wird im Hintergrund geprüft, ob es eine neuere Version gibt. Auf Wunsch
lädt das Programm „EPS-Produktsuche-v<Version>.exe“ in den Programmordner, startet sie und beendet sich. Die neue Version
entfernt beim Start ältere „EPS-Produktsuche*.exe“ im selben Ordner (eine laufende EXE kann Windows nicht löschen).
Die Shopdaten im Ordner „EPS-Produktsuche-Daten“ bleiben erhalten. Keine Admin-Rechte nötig.

Ordner-Variante (ab 1.5.1): Jedes Release hat zusätzlich „EPS-Produktsuche-Ordner.zip“ (startet schneller, weil
nichts bei jedem Start entpackt wird). Läuft das Programm schon als Ordner (neben der EXE liegt „_internal“) oder ist
ORDNER_KANAL eingeschaltet, installiert das Update „EPS-Produktsuche-v<Version>\“ neben die alte Version, startet sie,
und die neue Version löscht beim Start ältere Ordner und EXE-Dateien.

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
ORDNER_ASSET = "EPS-Produktsuche-Ordner.zip"
# Schalter: True = auch die Einzel-EXE wechselt beim nächsten Update auf die Ordner-Variante (schnellerer Start).
ORDNER_KANAL = False
_ORDNER_MUSTER = re.compile(r"^EPS-Produktsuche-v(\d+(?:\.\d+){0,2})$", re.I)
_MUSTER = re.compile(r"^EPS-Produktsuche(?:-v(\d+(?:\.\d+){0,2}))?\.exe$", re.I)


def tupel(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def _anfrage(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "EPS-Produktsuche"})
    return urllib.request.urlopen(req, timeout=timeout)


def ist_ordner_variante(exe: Path | None = None) -> bool:
    """Läuft die Ordner-Variante (PyInstaller onedir: „_internal“ neben der EXE)?"""
    exe = Path(exe or exe_pfad())
    return (exe.parent / "_internal").is_dir()


def _ordner_gewuenscht() -> bool:
    return ist_exe() and (ist_ordner_variante() or ORDNER_KANAL)


def _asset(rel: dict, name: str) -> str:
    return next((a.get("browser_download_url", "") for a in rel.get("assets", []) if a.get("name") == name), "")


def neueste(timeout: float = 6.0, releases: list | None = None, ordner: bool | None = None) -> tuple[str, str] | None:
    """(Version, Download-URL) der neuesten Produktsuche, falls neuer als die laufende – sonst None (auch offline).
    URL der ZIP (Ordner-Variante), wenn gewünscht und vorhanden, sonst der EXE."""
    ordner = _ordner_gewuenscht() if ordner is None else ordner
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
        url = (ordner and _asset(rel, ORDNER_ASSET)) or _asset(rel, ASSET)
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
    ordner = ordner or _programmordner(eigene)
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
TEST_ORDNER_ASSET = "EPS-Produktsuche-TEST-Ordner.zip"
_TEST_ORDNER_MUSTER = re.compile(r"^EPS-Produktsuche-TEST-(?:Ordner|b(\d+))$", re.I)


def build() -> int:
    """Buildnummer der laufenden Testversion (von GitHub Actions eingetragen, sonst 0)."""
    try:
        from ._build import BUILD
        return int(BUILD)
    except Exception:  # noqa: BLE001
        return 0


def neueste_test(timeout: float = 6.0, releases: list | None = None, eigener_build: int | None = None,
                 ordner: bool | None = None):
    """(Buildnummer, Download-URL) der neuesten Testversion, falls neuer als die laufende – sonst None.
    Läuft die Ordner-Variante, die URL der Ordner-ZIP."""
    ordner = (ist_exe() and ist_ordner_variante()) if ordner is None else ordner
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
        url = (ordner and _asset(rel, TEST_ORDNER_ASSET)) or _asset(rel, TEST_ASSET)
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


def _programmordner(exe: Path) -> Path:
    """Ordner mit den EXE-Dateien bzw. Programmordnern – bei der Ordner-Variante der Ordner darüber."""
    return exe.parent.parent if ist_ordner_variante(exe) else exe.parent


def ordner_installieren(url: str, zielname: str, fortschritt=None, exe: Path | None = None) -> Path:
    """Ordner-ZIP laden und als „<Programmordner>/<zielname>/“ auspacken. Gibt die neue EXE zurück.
    Die laufende Version bleibt unangetastet (Windows sperrt ihren Ordner) – die neue räumt sie beim Start weg."""
    import shutil
    import zipfile
    basis = _programmordner(Path(exe or exe_pfad()).resolve())
    ziel = basis / zielname
    zip_datei = herunterladen(url, basis / f"{zielname}.zip", fortschritt)
    tmp = basis / f"{zielname}.entpacken"
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(zip_datei) as z:
            z.extractall(tmp)
        kandidaten = [p.parent for p in tmp.rglob("EPS-Produktsuche.exe") if (p.parent / "_internal").is_dir()]
        if not kandidaten:
            raise IOError("Die ZIP enthält keine EPS-Produktsuche.exe mit _internal-Ordner")
        if ziel.exists():
            shutil.rmtree(ziel)
        kandidaten[0].rename(ziel)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        zip_datei.unlink(missing_ok=True)
    return ziel / "EPS-Produktsuche.exe"


def alte_ordner_entfernen(exe: Path | None = None, test: bool = False, versuche: int = 15) -> list[str]:
    """Ältere Programmordner löschen: normal „EPS-Produktsuche-v<ältere Version>“, Testkanal „…-TEST-b<kleinerer
    Build>“ und „…-TEST-Ordner“. Nie den eigenen Ordner, nie Daten."""
    import shutil
    exe = Path(exe or exe_pfad()).resolve()
    eigener = exe.parent.resolve()
    basis = _programmordner(exe)
    meine, mein_build = tupel(__version__), build()
    weg: list[str] = []
    for _ in range(versuche):
        offen = False
        for p in basis.iterdir() if basis.is_dir() else []:
            if not p.is_dir() or p.resolve() == eigener:
                continue
            if test:
                m = _TEST_ORDNER_MUSTER.match(p.name)
                alt = bool(m) and (m.group(1) is None or int(m.group(1)) < mein_build)
            else:
                m = _ORDNER_MUSTER.match(p.name)
                alt = bool(m) and tupel(m.group(1)) < meine
            if not alt:
                continue
            try:
                shutil.rmtree(p)
                weg.append(p.name)
            except OSError:
                offen = True
        if not offen:
            break
        time.sleep(1)
    return weg


_ALT_EXE = re.compile(r"^EPS-Produktsuche[\w.-]*\.alt\d*\.exe$", re.I)
_ALT_ORDNER = re.compile(r"^EPS-Produktsuche[\w-]*-Ordner\.alt\d*$", re.I)


def reste_entfernen(exe: Path | None = None, versuche: int = 15) -> list[str]:
    """Liegengebliebene Reste früherer Updates löschen: „…TEST.alt123456.exe“, „…-Ordner.alt123456“ (die Datei
    war beim Austausch gesperrt, weil das Programm lief). Die eigene EXE und der eigene Ordner bleiben."""
    import shutil
    exe = Path(exe or exe_pfad()).resolve()
    ordner = _programmordner(exe)
    eigener_ordner = exe.parent.resolve()
    weg: list[str] = []
    for _ in range(versuche):
        offen = False
        try:
            eintraege = list(ordner.iterdir())
        except OSError:
            return weg
        for p in eintraege:
            try:
                if p.is_file() and _ALT_EXE.match(p.name) and p.resolve() != exe:
                    p.unlink()
                    weg.append(p.name)
                elif p.is_dir() and _ALT_ORDNER.match(p.name) and p.resolve() != eigener_ordner:
                    shutil.rmtree(p)
                    weg.append(p.name)
            except OSError:
                offen = True
        if not offen:
            break
        time.sleep(1)
    return weg


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
