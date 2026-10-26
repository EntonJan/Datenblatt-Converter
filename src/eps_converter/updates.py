"""Updates über GitHub-Releases – mit Selbst-Update.

Ablauf: Beim Start wird im Hintergrund geprüft, ob es eine neuere Version gibt. Auf Wunsch lädt das Programm die neue
EXE als „Datenblatt-Converter-v<Version>.exe“ in denselben Ordner, startet sie und beendet sich. Die neue Version
entfernt beim Start ältere „Datenblatt-Converter-v*.exe“ im selben Ordner (eine laufende EXE kann Windows nicht
löschen – deshalb erst nach dem Wechsel). Keine Admin-Rechte nötig: nur der Programmordner wird beschrieben.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from . import __version__

REPO = "EntonJan/Datenblatt-Converter"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
SEITE = f"https://github.com/{REPO}/releases/latest"
ASSET = "Datenblatt-Converter.exe"
_MUSTER = re.compile(r"^Datenblatt-Converter-v(\d+(?:\.\d+){0,2})\.exe$", re.I)


def _tupel(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def _anfrage(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "EPS-Datenblatt-Converter"})
    return urllib.request.urlopen(req, timeout=timeout)


def neueste(timeout: float = 4.0) -> tuple[str, str] | None:
    """(Tag, Download-URL der EXE) des neuesten Releases, falls neuer als die laufende Version."""
    try:
        with _anfrage(API, timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:  # offline, kein Release … → still bleiben
        return None
    tag = d.get("tag_name", "")
    url = next((a.get("browser_download_url", "") for a in d.get("assets", []) if a.get("name") == ASSET), "")
    if tag and _tupel(tag) > _tupel(__version__):
        return tag, url
    return None


def neuere_version(timeout: float = 4.0) -> str | None:
    n = neueste(timeout)
    return n[0] if n else None


def ist_exe() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_pfad() -> Path:
    return Path(sys.executable).resolve()


def herunterladen(url: str, ziel: Path, fortschritt=None) -> Path:
    """Lädt in eine .part-Datei und benennt erst bei Erfolg um (kein halbes Programm bei Abbruch)."""
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


def alte_versionen_entfernen(ordner: Path | None = None, eigene: Path | None = None, versuche: int = 15) -> list[str]:
    """Löscht ältere Datenblatt-Converter-v*.exe im Programmordner (nur kleinere Versionsnummern als die eigene).
    Läuft die alte noch, wird einige Sekunden lang erneut versucht."""
    eigene = eigene or exe_pfad()
    ordner = ordner or eigene.parent
    meine = _tupel(__version__)
    geloescht = []
    for _ in range(versuche):
        offen = []
        for f in ordner.glob("Datenblatt-Converter-v*.exe"):
            m = _MUSTER.match(f.name)
            if not m or f.resolve() == eigene or _tupel(m.group(1)) >= meine:
                continue
            try:
                f.unlink()
                geloescht.append(f.name)
            except OSError:
                offen.append(f)
        for p in ordner.glob("Datenblatt-Converter-v*.part"):
            try:
                p.unlink()
            except OSError:
                pass
        if not offen:
            break
        time.sleep(1)
    return geloescht


def start(app, pruefen: bool = True) -> None:
    """Beim Programmstart: alte Versionen aufräumen (immer) und – falls eingestellt – nach Updates suchen."""
    if ist_exe():
        threading.Thread(target=alte_versionen_entfernen, daemon=True).start()
    if pruefen:
        im_hintergrund(app)


def im_hintergrund(app, auch_ohne_update_melden: bool = False) -> None:
    def lauf():
        n = neueste(timeout=8.0)
        if n:
            app.after(0, lambda: _melden(app, *n))
        elif auch_ohne_update_melden:
            from tkinter import messagebox
            app.after(0, lambda: messagebox.showinfo("Updates", f"Version {__version__} ist aktuell "
                                                                "(oder GitHub ist gerade nicht erreichbar)."))
    threading.Thread(target=lauf, daemon=True).start()


def _melden(app, tag: str, url: str):
    from tkinter import messagebox
    import webbrowser
    if not ist_exe() or not url:
        if messagebox.askyesno("Update verfügbar", f"Version {tag} ist verfügbar (installiert: {__version__}).\n\n"
                                                   "Download-Seite öffnen?"):
            webbrowser.open(SEITE)
        return
    if messagebox.askyesno("Update verfügbar",
                           f"Version {tag} ist verfügbar (installiert: {__version__}).\n\n"
                           "Jetzt automatisch aktualisieren?\n\nDie neue Version wird in den Programmordner geladen und "
                           "gestartet, die alte danach entfernt. Daten, Einstellungen und Feldkatalog bleiben erhalten."):
        aktualisieren(app, tag, url)


def aktualisieren(app, tag: str, url: str):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from .gui import Maske
    if isinstance(app.aktuell, Maske) and app.aktuell.ungespeichert():
        app.aktuell.zwischenspeichern(still=True)
    ziel = exe_pfad().parent / f"Datenblatt-Converter-{tag if tag.startswith('v') else 'v' + tag}.exe"
    fenster = tk.Toplevel(app)
    fenster.title("Update")
    fenster.transient(app)
    ttk.Label(fenster, text=f"Lade Version {tag} …", padding=12).pack(anchor="w")
    bar = ttk.Progressbar(fenster, length=380, maximum=100)
    bar.pack(padx=12, pady=(0, 12))
    fehler: list[str] = []

    def fortschritt(geladen, gesamt):
        if gesamt:
            app.after(0, lambda: bar.configure(value=geladen * 100 / gesamt))

    def laden():
        try:
            herunterladen(url, ziel, fortschritt)
        except Exception as e:  # noqa: BLE001
            fehler.append(str(e))
        app.after(0, fertig)

    def fertig():
        fenster.destroy()
        if fehler:
            messagebox.showerror("Update", f"Das Update konnte nicht geladen werden:\n{fehler[0]}\n\n"
                                           "Das Programm läuft normal weiter.")
            return
        env = os.environ.copy()
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"     # neue EXE ist eigenständig (nicht die Temp-Dateien der alten nutzen)
        try:
            subprocess.Popen([str(ziel)], cwd=str(ziel.parent), close_fds=True, env=env,
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        except OSError as e:
            messagebox.showerror("Update", f"Neue Version geladen, konnte aber nicht gestartet werden:\n{e}\n\n{ziel}")
            return
        try:
            app._fenster_merken()
        except Exception:
            pass
        app.destroy()
        os._exit(0)

    threading.Thread(target=laden, daemon=True).start()
