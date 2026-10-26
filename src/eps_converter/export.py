"""Konfigurator-Export (CSV für Excel + JSON) und Qualitätsbericht.

Der Export enthält je Gerät die Filterwerte des Produktkonfigurators: Bereiche als von/bis in der Grundeinheit,
Auswahlwerte, Ja/Nein, Schnittstellen (Standard/Option). So kann CharismaCom den Konfigurator schon mit echten
Daten aufbauen, bevor die Weclapp-Anbindung steht.
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from . import katalog as K, regeln, geraetetyp
from .modell import Datensatz, FREIGEGEBEN

ALLGEMEIN = ["bestellnummer", "typbezeichnung", "serie", "produkttyp", "geraetetyp"]


def sichtbar(ds: Datensatz) -> bool:
    """Shop-Sichtbarkeit: Feld „Im Shop sichtbar“, sonst Voreinstellung (Altbestand ja, neue Auftragsgeräte nein)."""
    w = ds.werte.get("shop_sichtbar")
    if w is not None and w.ja is not None:
        return bool(w.ja)
    h = ds.werte.get("herkunft")
    return bool(h and "Altbestand" in h.auswahl)


def filterfelder(kat: K.Katalog) -> list[K.Feld]:
    """Alle Felder mit einer Filterart für den Konfigurator (Reihenfolge wie im Katalog)."""
    return [f for f in kat.felder if f.filterart and f.abschnitt != K.INTERN and f.typ != K.LISTE]


def _wert(ds: Datensatz, f: K.Feld, kat: K.Katalog | None = None) -> dict:
    if f.id == "schnittstellen" and kat is not None:                 # abgeleitet aus den einzelnen Schnittstellen
        namen = regeln.schnittstellen_ableiten(ds, kat)
        return {"werte": list(namen)} if namen else {}
    w = ds.werte.get(f.id)
    if w is None or not regeln.hat_wert(w, f):
        return {}
    if f.typ in (K.BEREICH, K.ZAHL):
        return {"von": w.min, "bis": w.max, "einheit": f.einheit, "text_de": w.de, "text_en": w.en or w.de}
    if f.typ in (K.AUSWAHL, K.MEHRFACH):
        werte = list(w.auswahl) or ([w.de] if w.de else [])
        return {"werte": werte}
    if f.typ == K.JA_NEIN:
        return {"ja": w.ja} if w.ja is not None else {"text": w.de}
    if f.typ == K.SCHNITTSTELLE:
        return {"status": w.if_status, "code": w.if_code}
    return {"text_de": w.de, "text_en": w.en or w.de}


def datensatz_export(ds: Datensatz, kat: K.Katalog) -> dict:
    typen = ds.werte["geraetetyp"].auswahl if "geraetetyp" in ds.werte else []
    nr = ds.bestellnummer
    eintrag = {
        "id": ds.id, "status": ds.status, "sichtbar": sichtbar(ds),
        "bestellnummer": nr, "typbezeichnung": ds.titel,
        "serie": ds.text("serie"), "produkttyp_de": ds.text("produkttyp"), "produkttyp_en": ds.text("produkttyp", "en"),
        "geraetetyp": typen,
        "pdf_de": regeln.dateiname(nr, "de") if nr and ds.status == FREIGEGEBEN else "",
        "pdf_en": regeln.dateiname(nr, "en") if nr and ds.status == FREIGEGEBEN else "",
        "filter": {},
    }
    for f in filterfelder(kat):
        if f.id in ALLGEMEIN or not geraetetyp.relevant(f.id, typen):
            continue
        v = _wert(ds, f, kat)
        if v:
            eintrag["filter"][f.id] = v
    return eintrag


def konfigurator_export(datensaetze: list[Datensatz], kat: K.Katalog, ordner: Path,
                        nur_freigegeben: bool = True) -> tuple[Path, Path, int]:
    """Schreibt Konfigurator-Export_<Datum>.csv (Excel, ;-getrennt) und .json. Rückgabe (csv, json, Anzahl)."""
    auswahl = [ds for ds in datensaetze if ds.status == FREIGEGEBEN or not nur_freigegeben]
    eintraege = [datensatz_export(ds, kat) for ds in auswahl]
    ordner.mkdir(parents=True, exist_ok=True)
    stamm = ordner / f"Konfigurator-Export_{date.today().isoformat()}"
    pj, pc = stamm.with_suffix(".json"), stamm.with_suffix(".csv")

    felder = [f for f in filterfelder(kat) if f.id not in ALLGEMEIN]
    pj.write_text(json.dumps({
        "erstellt": date.today().isoformat(), "anzahl": len(eintraege),
        "felder": {f.id: {"de": f.de, "en": f.en, "typ": f.typ, "einheit": f.einheit, "filterart": f.filterart,
                          "auswahl": [{"de": de, "en": en} for de, en in f.auswahl]} for f in felder},
        "geraete": eintraege}, ensure_ascii=False, indent=2), encoding="utf-8")

    kopf = ["Bestellnummer", "Typbezeichnung", "Status", "Im Shop sichtbar", "Serie", "Produkttyp", "Gerätetyp", "PDF DE", "PDF EN"]
    spalten = []
    for f in felder:
        if f.typ in (K.BEREICH, K.ZAHL):
            einheit = f" [{f.einheit}]" if f.einheit else ""
            spalten += [(f, "von", f"{f.de} von{einheit}"), (f, "bis", f"{f.de} bis{einheit}")]
        else:
            spalten.append((f, "", f.de))
    with pc.open("w", encoding="utf-8-sig", newline="") as fh:              # BOM: Excel erkennt UTF-8
        w = csv.writer(fh, delimiter=";")
        w.writerow(kopf + [s[2] for s in spalten])
        for e in eintraege:
            zeile = [e["bestellnummer"], e["typbezeichnung"], e["status"], "ja" if e["sichtbar"] else "nein", e["serie"],
                     e["produkttyp_de"], " | ".join(e["geraetetyp"]), e["pdf_de"], e["pdf_en"]]
            for f, teil, _ in spalten:
                v = e["filter"].get(f.id, {})
                if teil:
                    x = v.get(teil)
                    zeile.append("" if x is None else (f"{x:g}".replace(".", ",")))
                elif "werte" in v:
                    zeile.append(" | ".join(v["werte"]))
                elif "ja" in v:
                    zeile.append("ja" if v["ja"] else "nein")
                elif "status" in v:
                    zeile.append(v["status"] + (f" ({v['code']})" if v.get("code") else ""))
                else:
                    zeile.append(v.get("text_de", v.get("text", "")))
            w.writerow(zeile)
    return pc, pj, len(eintraege)


# ------------------------------------------------------------------------ Qualitätsbericht

def qualitaet(ds: Datensatz, kat: K.Katalog, hersteller: list[str]) -> dict:
    """Kennzahlen je Datenblatt für den Qualitätsbericht."""
    probleme = regeln.pruefe_freigabe_felder(ds, kat)
    fehlend = sorted({kat.feld(fid).de if kat.hat(fid) else fid for fid, art, _ in probleme if art == "wert"})
    ungeprueft = sorted({kat.feld(fid).de if kat.hat(fid) else "Optionen" for fid, art, _ in probleme if art == "geprueft"})
    spuren = regeln.herstellerspuren(ds, kat, hersteller) if ds.regel != "Händlerware" else []
    gelb = sorted({kat.feld(fid).de for fid, w in ds.werte.items() if w.teiluebersetzt and kat.hat(fid)})
    hinweise = []
    if not ds.bilder:
        hinweise.append("kein Bild")
    if not ds.text("beschreibung"):
        hinweise.append("keine Beschreibung DE")
    b = ds.werte.get("beschreibung")
    if not (b and b.en):
        hinweise.append("keine Beschreibung EN")
    if not (ds.werte.get("geraetetyp") and ds.werte["geraetetyp"].auswahl):
        hinweise.append("kein Gerätetyp")
    punkte = 3 * len(fehlend) + len(ungeprueft) + 2 * len(spuren) + len(gelb) + len(hinweise)
    return {"fehlend": fehlend, "ungeprueft": ungeprueft, "spuren": [m for _, _, m in spuren], "gelb": gelb,
            "hinweise": hinweise, "punkte": punkte}


def qualitaet_csv(zeilen: list[tuple[Datensatz, dict]], ziel: Path) -> Path:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with ziel.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Bestellnummer", "Typbezeichnung", "Status", "Punkte", "Fehlende Pflichtwerte", "Ungeprüfte Kernfelder",
                    "Herstellerspuren", "Vorübersetzt (gelb)", "Sonstiges"])
        for ds, q in zeilen:
            w.writerow([ds.bestellnummer, ds.titel, ds.status, q["punkte"], ", ".join(q["fehlend"]), ", ".join(q["ungeprueft"]),
                        " | ".join(q["spuren"]), ", ".join(q["gelb"]), ", ".join(q["hinweise"])])
    return ziel
