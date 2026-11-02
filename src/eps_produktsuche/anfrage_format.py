"""EPS-Anfrage, Format 1: die eine Anfragestruktur für Homepage-Anfragefeld, Produktkonfigurator (Anfragekorb) und Shop.

Jede Anfrage kommt als Mail mit
  1. dem Textblock „--- EPS-Anfrage --- … --- Ende ---“ im Mailtext (für Menschen lesbar, übersteht Weiterleiten)
  2. dem Anhang „EPS-Anfrage.json“ mit denselben Daten (für Programme genau, z. B. mehrere Positionen)
Die Produktsuche nimmt den Anhang, wenn er da ist, sonst den Textblock. Ältere Formular-Mails (Block ohne
„Format:“-Zeile, Feld „Produkt“) werden weiter gelesen.

Beschreibung und Beispiele: tests/eps-anfrage/ (in der Produktsuche und im Produktkonfigurator identisch). Der
Konfigurator erzeugt Text und JSON mit includes/class-eps-anfrage.php – beide Seiten werden gegen dieselben
Beispieldateien getestet.
"""
from __future__ import annotations

import json
import re

FORMAT = "eps-anfrage"
VERSION = 1
ANHANG = "EPS-Anfrage.json"
BEGINN, ENDE = "--- EPS-Anfrage ---", "--- Ende ---"

QUELLEN = {"produktkonfigurator": "Produktkonfigurator", "anfrageformular": "Anfrageformular", "shop": "Shop"}
KUNDENFELDER = [("firma", "Firma"), ("rechtsform", "Rechtsform"), ("anrede", "Anrede"), ("vorname", "Vorname"),
                ("nachname", "Nachname"), ("email", "E-Mail"), ("telefon", "Telefon"), ("strasse", "Straße"),
                ("plz", "PLZ"), ("ort", "Ort"), ("land", "Land"), ("ust_id", "USt-IdNr.")]


# ------------------------------------------------------------------------ Grundform

def leer() -> dict:
    return {"format": FORMAT, "version": VERSION, "anfrage_nr": "", "erstellt": "", "quelle": "", "sprache": "de",
            "kunde": {k: "" for k, _ in KUNDENFELDER}, "positionen": [],
            "suche": {"text": "", "geraetetyp": "", "filter": {}}, "wunschtermin": "ASAP", "nachricht": "",
            "datenschutz": False}


def normalisieren(d: dict) -> dict:
    """Beliebige (auch unvollständige) Eingabe → vollständige Struktur mit Standardwerten."""
    n = leer()
    for k in ("anfrage_nr", "erstellt", "quelle", "sprache", "wunschtermin"):
        if d.get(k) not in (None, ""):
            n[k] = _einzeilig(d[k])
    nachricht = str(d.get("nachricht") or "").replace("\r\n", "\n").strip("\n")
    n["nachricht"] = "\n".join(_sicher(x.rstrip()) for x in nachricht.split("\n")) if nachricht else ""
    n["version"] = int(d.get("version") or VERSION)
    n["datenschutz"] = bool(d.get("datenschutz"))
    kunde = d.get("kunde") or {}
    for k, _ in KUNDENFELDER:
        n["kunde"][k] = _einzeilig(kunde.get(k, ""))
    for p in d.get("positionen") or []:
        try:
            menge = max(1, int(p.get("menge") or 1))
        except (TypeError, ValueError):
            menge = 1
        n["positionen"].append({"bestellnummer": _einzeilig(p.get("bestellnummer", "")),
                                "name": _einzeilig(p.get("name", "")), "menge": menge})
    s = d.get("suche") or {}
    n["suche"] = {"text": _einzeilig(s.get("text", "")), "geraetetyp": _einzeilig(s.get("geraetetyp", "")),
                  "filter": {str(k): v for k, v in (s.get("filter") or {}).items()}}
    return n


def _einzeilig(x) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


# ------------------------------------------------------------------------ Text erzeugen

def _filterwert(v) -> str:
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if isinstance(v, (list, tuple)):
        if len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
            return f"{_zahl(v[0])}-{_zahl(v[1])}"
        return "|".join(_filterwert(x) for x in v)
    if isinstance(v, (int, float)):
        return _zahl(v)
    return _einzeilig(v)


def _zahl(x) -> str:
    return f"{x:g}" if isinstance(x, float) else str(x)


def _sicher(zeile: str) -> str:
    """Kundentext darf den Block nicht beenden."""
    return "– Ende –" if zeile.strip() in (BEGINN, ENDE) else zeile


def als_text(d: dict) -> str:
    """Textblock für den Mailtext. Feste Reihenfolge, „Nachricht“ zuletzt (mehrzeilig bis „--- Ende ---“)."""
    d = normalisieren(d)
    z = [BEGINN, f"Format: EPS-Anfrage {d['version']}", f"Anfrage-Nr.: {d['anfrage_nr']}", f"Erstellt: {d['erstellt']}",
         f"Quelle: {QUELLEN.get(d['quelle'], d['quelle'])}", f"Sprache: {d['sprache']}"]
    z += [f"{titel}: {d['kunde'][k]}" for k, titel in KUNDENFELDER]
    for i, p in enumerate(d["positionen"], 1):
        z.append(f"Position {i}: {p['bestellnummer']} · {p['name']} · Menge {p['menge']}")
    s = d["suche"]
    if s["text"]:
        z.append(f"Suche: {s['text']}")
    if s["geraetetyp"]:
        z.append(f"Gerätetyp: {s['geraetetyp']}")
    if s["filter"]:
        z.append("Filter: " + "; ".join(f"{k}={_filterwert(v)}" for k, v in sorted(s["filter"].items())))
    z.append(f"Wunschtermin: {d['wunschtermin']}")
    z.append(f"Datenschutz: {'zugestimmt' if d['datenschutz'] else 'nicht zugestimmt'}")
    nachricht = d["nachricht"].split("\n") if d["nachricht"] else [""]
    z.append(f"Nachricht: {nachricht[0]}")
    z += nachricht[1:]
    z.append(ENDE)
    return "\n".join(z)


def als_json(d: dict) -> str:
    return json.dumps(normalisieren(d), ensure_ascii=False, indent=2)


# ------------------------------------------------------------------------ lesen

_BLOCK = re.compile(r"-{3}\s*EPS-Anfrage\s*-{3}(.*?)-{3}\s*Ende\s*-{3}", re.S | re.I)
_LABEL = {"format": "format", "anfrage-nr.": "anfrage_nr", "anfrage-nr": "anfrage_nr", "erstellt": "erstellt",
          "quelle": "quelle",
          "sprache": "sprache", "firma": "firma", "company": "firma", "rechtsform": "rechtsform", "anrede": "anrede",
          "salutation": "anrede", "vorname": "vorname", "first name": "vorname", "nachname": "nachname",
          "last name": "nachname", "name": "name", "e-mail": "email", "email": "email", "telefon": "telefon",
          "phone": "telefon", "straße": "strasse", "strasse": "strasse", "street": "strasse", "plz": "plz",
          "zip": "plz", "ort": "ort", "city": "ort", "land": "land", "country": "land", "ust-idnr.": "ust_id",
          "ust-idnr": "ust_id", "vat id": "ust_id", "produkt": "produkt", "product": "produkt", "menge": "menge",
          "quantity": "menge", "suche": "suche", "gerätetyp": "geraetetyp", "filter": "filter",
          "wunschtermin": "wunschtermin", "datenschutz": "datenschutz", "nachricht": "nachricht",
          "message": "nachricht"}
_POSITION = re.compile(r"^\s*position\s*(\d+)\s*:\s*(.*)$", re.I)


def aus_text(text: str) -> dict | None:
    """Textblock → Struktur (auch der ältere Formularblock ohne „Format“). None, wenn kein Block da ist."""
    m = _BLOCK.search(text or "")
    if not m:
        return None
    werte: dict[str, str] = {}
    positionen = []
    nachricht: list[str] | None = None
    for zeile in m.group(1).strip("\n").split("\n"):
        if nachricht is not None:                      # alles nach „Nachricht:“ gehört zur Nachricht
            nachricht.append(zeile.rstrip())
            continue
        pm = _POSITION.match(zeile)
        if pm:
            teile = [t.strip() for t in pm.group(2).split("·")]
            menge = re.search(r"(\d+)", teile[-1]) if len(teile) >= 3 else None
            positionen.append({"bestellnummer": teile[0], "name": teile[1] if len(teile) > 1 else "",
                               "menge": int(menge.group(1)) if menge else 1})
            continue
        km = re.match(r"\s*([\w .\-ä-üÄ-Üß]+?)\s*:\s*(.*)$", zeile)
        if not km or km.group(1).lower() not in _LABEL:
            continue
        feld = _LABEL[km.group(1).lower()]
        if feld == "nachricht":
            nachricht = [km.group(2).rstrip()]
        else:
            werte[feld] = km.group(2).strip()
    d = leer()
    d["version"] = int(re.search(r"\d+", werte.get("format", "")).group(0)) if re.search(r"\d+", werte.get("format", "")) else 0
    d["anfrage_nr"] = werte.get("anfrage_nr", "")
    d["erstellt"] = werte.get("erstellt", "")
    quelle = werte.get("quelle", "").lower()
    d["quelle"] = next((k for k, v in QUELLEN.items() if v.lower() == quelle or k == quelle), quelle or "anfrageformular")
    d["sprache"] = werte.get("sprache", "de") or "de"
    for k, _ in KUNDENFELDER:
        d["kunde"][k] = werte.get(k, "")
    if werte.get("name") and not d["kunde"]["nachname"]:
        teile = werte["name"].split()
        d["kunde"]["vorname"], d["kunde"]["nachname"] = " ".join(teile[:-1]), teile[-1]
    if not positionen and werte.get("produkt"):        # älterer Block: „Produkt: Name (123456)“ + „Menge“
        bm = re.search(r"\((\d{6})\)|\b(\d{6})\b", werte["produkt"])
        try:
            menge = max(1, int(werte.get("menge") or 1))
        except ValueError:
            menge = 1
        positionen.append({"bestellnummer": (bm.group(1) or bm.group(2)) if bm else "",
                           "name": re.sub(r"\s*\(\d{6}\)\s*", " ", werte["produkt"]).strip(), "menge": menge})
    d["positionen"] = positionen
    d["suche"] = {"text": werte.get("suche", ""), "geraetetyp": werte.get("geraetetyp", ""),
                  "filter": _filter_lesen(werte.get("filter", ""))}
    d["wunschtermin"] = werte.get("wunschtermin") or "ASAP"
    d["datenschutz"] = werte.get("datenschutz", "").lower().startswith(("zugestimmt", "ja", "yes"))
    d["nachricht"] = "\n".join(nachricht or []).strip("\n")
    return d


def _filter_lesen(text: str) -> dict:
    out = {}
    for teil in (text or "").split(";"):
        if "=" in teil:
            k, v = teil.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def aus_json(text_oder_dict) -> dict | None:
    """JSON-Anhang → Struktur. None, wenn es kein EPS-Anfrage-JSON ist."""
    try:
        d = json.loads(text_oder_dict) if isinstance(text_oder_dict, (str, bytes)) else dict(text_oder_dict)
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict) or d.get("format") != FORMAT:
        return None
    return normalisieren(d)


def ist_anfrage_json(dateiname: str, daten: bytes) -> dict | None:
    """Für die Mail-Leser: Anhang prüfen (Name egal, Inhalt zählt; höchstens 200 kB)."""
    if not dateiname.lower().endswith(".json") or len(daten) > 200_000:
        return None
    try:
        return aus_json(daten.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return None
