"""Verlauf der Anfragen: was wurde wann gesucht, mit welchem Kunden-Datenblatt, welche Geräte wurden empfohlen.

Gespeichert in „EPS-Produktsuche-Daten/verlauf.json“ neben der EXE (höchstens 500 Einträge, neueste zuerst).
Wiederholte Aktionen zur selben Anfrage innerhalb von 30 Minuten werden zu einem Eintrag zusammengefasst.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

MAX_EINTRAEGE = 500
ZUSAMMENFASSEN = timedelta(minutes=30)


def laden(pfad: Path) -> list[dict]:
    try:
        daten = json.loads(Path(pfad).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in daten.get("eintraege", []) if isinstance(e, dict) and e.get("anfrage") is not None]


def speichern(pfad: Path, eintraege: list[dict]) -> None:
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(".tmp")
    tmp.write_text(json.dumps({"eintraege": eintraege[:MAX_EINTRAEGE]}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(pfad)


def hinzufuegen(pfad: Path, anfrage: str, aktion: str, geraete: list[dict] | None = None, typ: str = "automatisch",
                fremd: dict | None = None, jetzt: datetime | None = None, kunde: str = "") -> dict:
    """Neuen Eintrag anlegen oder den letzten zur selben Anfrage ergänzen. Gibt den Eintrag zurück.

    geraete: [{"bestellnummer", "name"}]; fremd: Kunden-Datenblatt (datei, modell, hersteller_typ, Werte …)."""
    jetzt = jetzt or datetime.now()
    eintraege = laden(pfad)
    anfrage = (anfrage or "").strip()
    letzter = eintraege[0] if eintraege else None
    if letzter and letzter.get("anfrage") == anfrage and \
            jetzt - datetime.fromisoformat(letzter.get("zeit", "2000-01-01T00:00")) <= ZUSAMMENFASSEN:
        e = letzter
    else:
        e = {"zeit": "", "anfrage": anfrage, "typ": typ, "aktionen": [], "geraete": [], "fremd": None, "notiz": ""}
        eintraege.insert(0, e)
    e["zeit"] = jetzt.isoformat(timespec="minutes")
    e["typ"] = typ
    if aktion and aktion not in e["aktionen"]:
        e["aktionen"].append(aktion)
    if fremd:
        e["fremd"] = fremd
    if kunde:
        e["kunde"] = kunde
    bekannt = {g.get("bestellnummer") for g in e["geraete"]}
    for g in geraete or []:
        if g.get("bestellnummer") not in bekannt:
            e["geraete"].append({"bestellnummer": g.get("bestellnummer", ""), "name": g.get("name", "")})
            bekannt.add(g.get("bestellnummer"))
    speichern(pfad, eintraege)
    return e


def notiz_setzen(pfad: Path, index: int, notiz: str) -> None:
    eintraege = laden(pfad)
    if 0 <= index < len(eintraege):
        eintraege[index]["notiz"] = notiz
        speichern(pfad, eintraege)


def loeschen(pfad: Path, index: int) -> None:
    eintraege = laden(pfad)
    if 0 <= index < len(eintraege):
        del eintraege[index]
        speichern(pfad, eintraege)


def passt(e: dict, suchtext: str) -> bool:
    """Filter im Verlauf-Fenster: alle Wörter müssen in Anfrage, Datenblatt, Geräten oder Notiz vorkommen."""
    worte = [w for w in (suchtext or "").lower().split() if w]
    if not worte:
        return True
    f = e.get("fremd") or {}
    alles = " ".join([e.get("anfrage", ""), e.get("notiz", ""), e.get("kunde", ""), f.get("datei", ""), f.get("hersteller_typ", ""),
                      " ".join(g.get("bestellnummer", "") + " " + g.get("name", "") for g in e.get("geraete", []))]).lower()
    return all(w in alles for w in worte)


def kunde_von(e: dict) -> str:
    """Kunde eines Eintrags: aus der übernommenen Anfrage, sonst das Kunden-Dokument."""
    f = e.get("fremd") or {}
    return e.get("kunde") or (f"Dokument: {f.get('datei')}" if f.get("datei") else "")


def kennzahlen(eintraege: list[dict], jetzt: datetime | None = None) -> dict:
    """Zahlen für die Verlauf-Seite, jeweils für die laufende Woche (ab Montag)."""
    jetzt = jetzt or datetime.now()
    montag = (jetzt - timedelta(days=jetzt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    woche = []
    for e in eintraege:
        try:
            if datetime.fromisoformat(e.get("zeit", "")) >= montag:
                woche.append(e)
        except ValueError:
            continue
    aktionen = lambda e: " ".join(e.get("aktionen", []))  # noqa: E731
    return {"woche": len(woche),
            "mit_kunde": sum(1 for e in woche if kunde_von(e)),
            "empfohlen": sum(1 for e in woche if "Empfehlung" in aktionen(e) or "Gegenüberstellung" in aktionen(e)),
            "weclapp": sum(1 for e in woche if "Weclapp" in aktionen(e))}
