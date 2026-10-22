"""Prüft beim Start, ob auf GitHub eine neuere Version veröffentlicht ist (läuft im Hintergrund).

Die EXE wird nicht selbst ersetzt (eine laufende EXE kann unter Windows nicht überschrieben werden):
Bei einer neuen Version erscheint ein Hinweis mit Link zur Download-Seite.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.request

from . import __version__

REPO = "EntonJan/Datenblatt-Converter"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
SEITE = f"https://github.com/{REPO}/releases/latest"


def _tupel(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def neuere_version(timeout: float = 4.0) -> str | None:
    try:
        req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "EPS-Datenblatt-Converter"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            tag = json.loads(r.read().decode("utf-8")).get("tag_name", "")
    except Exception:  # offline, kein Release, privates Repo … → still bleiben
        return None
    return tag if tag and _tupel(tag) > _tupel(__version__) else None


def im_hintergrund(app) -> None:
    def lauf():
        tag = neuere_version()
        if tag:
            app.after(0, lambda: _melden(app, tag))
    threading.Thread(target=lauf, daemon=True).start()


def _melden(app, tag):
    from tkinter import messagebox
    import webbrowser
    if messagebox.askyesno("Update verfügbar", f"Version {tag} ist verfügbar (installiert: {__version__}).\n\n"
                                               "Download-Seite öffnen?\n\nDie neue EXE einfach über die alte kopieren "
                                               "(Programm vorher schließen). Daten und Einstellungen bleiben erhalten."):
        webbrowser.open(SEITE)
