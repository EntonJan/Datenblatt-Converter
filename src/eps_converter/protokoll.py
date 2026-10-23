"""Änderungsprotokoll: wer hat wann was geändert.

Benutzer = Anzeigename aus den Einstellungen, sonst der Windows-Anmeldename (keine eigenen Accounts nötig).
Hinweis: nicht fälschungssicher – dient der Nachvollziehbarkeit, nicht der Revisionssicherheit.
"""
from __future__ import annotations

import getpass
import os
from datetime import datetime

from . import katalog as K
from .modell import Datensatz, FREIGEGEBEN, jetzt

ZUSAMMENFASSEN_MIN = 15          # aufeinanderfolgende Änderungen derselben Person zusammenfassen


def benutzer(einst=None) -> str:
    name = (getattr(einst, "benutzer", "") or "").strip()
    if name:
        return name
    for k in ("USERNAME", "USER"):
        if os.environ.get(k):
            return os.environ[k]
    try:
        return getpass.getuser()
    except Exception:
        return "unbekannt"


def _kurz(w: dict | None) -> str:
    if not w:
        return ""
    if w.get("de"):
        t = w["de"]
    elif w.get("auswahl"):
        t = ", ".join(w["auswahl"])
    elif w.get("ja") is not None:
        t = "Ja" if w["ja"] else "Nein"
    elif w.get("if_status"):
        t = w["if_status"] + (f" ({w['if_code']})" if w.get("if_code") else "")
    elif w.get("min") is not None or w.get("max") is not None:
        t = f"{w.get('min') if w.get('min') is not None else ''}–{w.get('max') if w.get('max') is not None else ''}"
    else:
        t = ""
    return t[:200]


def _liste(eintraege: list[dict], felder: tuple[str, ...]) -> str:
    return "; ".join(" ".join(str(e.get(f, "")) for f in felder if e.get(f)).strip() for e in eintraege)[:300]


def unterschiede(alt: dict, neu: dict, kat: K.Katalog) -> list[list[str]]:
    """Vergleicht zwei Datensatz-Stände (to_dict) → [[Feld, vorher, nachher], …]."""
    out = []
    aw, nw = alt.get("werte", {}), neu.get("werte", {})
    gesehen = set()
    for fid in [f.id for f in kat.felder] + sorted(set(aw) | set(nw)):
        if fid == "optionen" or fid in gesehen:
            continue
        gesehen.add(fid)
        a, n = aw.get(fid), nw.get(fid)
        if a is None and n is None:
            continue
        name = kat.feld(fid).de if kat.hat(fid) else fid
        ka, kn = _kurz(a), _kurz(n)
        if ka != kn or (a or {}).get("en", "") != (n or {}).get("en", ""):
            if ka == kn:
                ka, kn = f"EN: {(a or {}).get('en', '')}", f"EN: {(n or {}).get('en', '')}"
            out.append([name, ka, kn])
        elif bool((a or {}).get("geprueft")) != bool((n or {}).get("geprueft")):
            out.append([name, "", "✔ als geprüft markiert" if (n or {}).get("geprueft") else "Prüfhaken entfernt"])
    for key, name, felder in (("optionen", "Optionen", ("code", "de")), ("lieferumfang", "Lieferumfang", ("de",)),
                              ("bilder", "Bilder", ("datei",))):
        la, ln = _liste(alt.get(key, []), felder), _liste(neu.get(key, []), felder)
        if la != ln:
            out.append([name, la, ln])
    if alt.get("regel") != neu.get("regel"):
        out.append(["Regel", alt.get("regel", ""), neu.get("regel", "")])
    return out


def eintragen(ds: Datensatz, einst, aktion: str, aenderungen: list[list[str]] | None = None) -> None:
    aenderungen = aenderungen or []
    wer = benutzer(einst)
    nach_freigabe = ds.status == FREIGEGEBEN and aktion == "Geändert"
    letzter = ds.protokoll[-1] if ds.protokoll else None
    if (aktion == "Geändert" and letzter and letzter.get("aktion") == "Geändert" and letzter.get("benutzer") == wer
            and letzter.get("nach_freigabe") == nach_freigabe and _minuten_seit(letzter.get("zeit", "")) < ZUSAMMENFASSEN_MIN):
        alt = {z[0]: z for z in letzter.get("aenderungen", [])}
        for feld, vorher, nachher in aenderungen:
            if feld in alt:
                alt[feld][2] = nachher                    # erster „vorher“-Wert bleibt, neuester „nachher“
            else:
                letzter.setdefault("aenderungen", []).append([feld, vorher, nachher])
        letzter["aenderungen"] = [z for z in letzter["aenderungen"] if z[1] != z[2]]
        letzter["zeit"] = jetzt()
        if not letzter["aenderungen"]:
            ds.protokoll.pop()
        return
    if aktion == "Geändert" and not aenderungen:
        return
    ds.protokoll.append({"zeit": jetzt(), "benutzer": wer, "aktion": aktion, "nach_freigabe": nach_freigabe,
                         "aenderungen": aenderungen})


def _minuten_seit(zeit: str) -> float:
    try:
        return (datetime.now() - datetime.fromisoformat(zeit)).total_seconds() / 60
    except ValueError:
        return 1e9
