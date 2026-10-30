"""Nachgebautes Weclapp für Tests und den Demo-Modus (Einstellungen → Weclapp-Adresse „demo“).

Speichert alles nur im Arbeitsspeicher; nach dem Schließen ist alles weg. Artikel entstehen aus den Shopdaten,
Einkaufspreise bekommen ein fest ausgedachtes Datum (je nach Bestellnummer 0–14 Monate alt) – DEMO-Daten.
"""
from __future__ import annotations

import zlib
from datetime import datetime, timedelta


def _ms(d: datetime) -> int:
    return int(d.timestamp() * 1000)


DEMO_LIEFERANTEN = [("CTP", "DEMO Absopulse"), ("CSI", "DEMO Absopulse"), ("E/PS", "DEMO EA Elektro-Automatik"),
                    ("ELR", "DEMO EA Elektro-Automatik"), ("", "DEMO Lieferant")]


class Attrappe:
    web = ""                              # Demo hat keine Weboberfläche → keine Links

    def __init__(self, geraete=(), heute: datetime | None = None):
        self.heute = heute or datetime.now()
        self.naechste = 1000
        self.daten: dict[str, list[dict]] = {"party": [], "article": [], "articleSupplySource": [], "quotation": [],
                                             "purchaseOrderRequest": [], "customAttributeDefinition": [],
                                             "articleCategory": []}
        self.aufrufe: list[tuple[str, str]] = []
        for g in geraete:
            self.artikel(g.bestellnummer, g.name)

    def _id(self) -> str:
        self.naechste += 1
        return str(self.naechste)

    def artikel(self, nr: str, name: str, monate_alt: int | None = None, lieferant: str | None = None) -> dict:
        a = {"id": self._id(), "articleNumber": nr, "name": name}
        self.daten["article"].append(a)
        if monate_alt is None:
            monate_alt = zlib.crc32(nr.encode()) % 15
        if lieferant is None:
            lieferant = next(l for kennung, l in DEMO_LIEFERANTEN if kennung in name)
        if lieferant:
            self.daten["articleSupplySource"].append({
                "id": self._id(), "articleId": a["id"], "supplierName": lieferant,
                "purchasePrices": [{"price": "100.00", "startDate": _ms(self.heute - timedelta(days=30 * monate_alt))}]})
        return a

    @classmethod
    def mit_importdaten(cls, geraete, heute: datetime | None = None) -> "Attrappe":
        """Weclapp, wie es nach Feldliste + Import aussähe: eigene Attribute angelegt, Artikel aus der Importdatei."""
        from eps_converter import katalog as K, pfade
        from .weclapp_felder import feldliste, artikel_zeilen, IMPORT_SPALTEN
        a = cls(heute=heute)
        attribute, _ = feldliste(K.laden(pfade.KATALOG_MITGELIEFERT))
        defs = {}
        for at in attribute:
            d = {"id": a._id(), "attributeKey": at.schluessel, "attributeType": at.typ, "label": at.de,
                 "selectableValues": [{"id": a._id(), "value": w} for w in at.auswahl_de.split("; ") if w]}
            a.daten["customAttributeDefinition"].append(d)
            defs[at.schluessel] = d
        kategorien = {}
        spalten = [s for s, _ in IMPORT_SPALTEN]
        for zeile in artikel_zeilen(geraete):
            z = dict(zip(spalten, zeile))
            kat = z["Warengruppe"]
            if kat not in kategorien:
                kategorien[kat] = {"id": a._id(), "name": kat}
                a.daten["articleCategory"].append(kategorien[kat])
            werte = []
            for schluessel, wert in z.items():
                d = defs.get(schluessel)
                if not d or wert in (None, ""):
                    continue
                ca = {"attributeDefinitionId": d["id"]}
                typ = d["attributeType"]
                if typ in ("LIST", "MULTISELECT_LIST"):
                    ids = []
                    for w in (str(wert).split("; ") if typ == "MULTISELECT_LIST" else [str(wert)]):
                        sv = next((v for v in d["selectableValues"] if v["value"] == w), None)
                        if sv is None:                       # Wert fehlt in der Auswahlliste → wie in Weclapp ergänzen
                            sv = {"id": a._id(), "value": w}
                            d["selectableValues"].append(sv)
                        ids.append(sv["id"])
                    if typ == "LIST":
                        ca["selectedValueId"] = ids[0]
                    else:
                        ca["selectedValues"] = [{"id": i} for i in ids]
                elif typ in ("DECIMAL", "INTEGER"):
                    ca["numberValue"] = str(wert).replace(",", ".")
                elif typ == "BOOLEAN":
                    ca["booleanValue"] = str(wert).lower() in ("ja", "true", "1")
                else:
                    ca["stringValue"] = str(wert)
                werte.append(ca)
            art = a.artikel(z["Artikelnummer"], z["Artikelname"])
            art.update(articleCategoryId=kategorien[kat]["id"], customAttributes=werte)
        return a

    def kunde(self, firma: str, email: str, plz: str = "") -> dict:
        k = {"id": self._id(), "partyType": "ORGANIZATION", "customer": True, "company": firma, "email": email,
             "customerNumber": f"D{self.naechste}", "addresses": [{"zipcode": plz}]}
        self.daten["party"].append(k)
        return k

    # ---------------------------------------------------------------- Transport
    def __call__(self, methode: str, pfad: str, params: dict | None = None, daten: dict | None = None) -> dict:
        self.aufrufe.append((methode, pfad))
        teile = pfad.strip("/").split("/")
        art = teile[0]
        if methode == "GET":
            liste = self.daten.get(art, [])
            for schluessel, wert in (params or {}).items():
                if schluessel.endswith("-eq"):
                    feld = schluessel[:-3]
                    liste = [x for x in liste if str(x.get(feld, "")).lower() == str(wert).lower()]
                elif schluessel.endswith("-ilike"):
                    feld, w = schluessel[:-6], str(wert).strip("%").lower()
                    liste = [x for x in liste if w in str(x.get(feld, "")).lower()]
            groesse, seite = int((params or {}).get("pageSize", 100)), int((params or {}).get("page", 1))
            return {"result": liste[(seite - 1) * groesse: seite * groesse]}
        if methode == "POST" and len(teile) == 1:
            neu = dict(daten or {}, id=self._id())
            if art == "party":
                neu["customerNumber"] = f"D{neu['id']}"
            if art == "quotation":
                neu["quotationNumber"] = f"AN-{neu['id']}"
                neu["status"] = "QUOTATION_CREATED"
            self.daten.setdefault(art, []).append(neu)
            return neu
        if methode == "POST" and teile[:2] == ["quotation", "id"] and teile[3] == "createPurchaseOrderRequest":
            angebot = next(q for q in self.daten["quotation"] if q["id"] == teile[2])
            je_lieferant: dict[str, list] = {}
            for pos in angebot["quotationItems"]:
                quelle = next((q for q in self.daten["articleSupplySource"] if q["articleId"] == pos["articleId"]), {})
                je_lieferant.setdefault(quelle.get("supplierName", "?"), []).append(pos)
            neu = []
            for lieferant, pos in je_lieferant.items():
                r = {"id": self._id(), "supplierName": lieferant, "quotationId": angebot["id"], "items": pos}
                self.daten["purchaseOrderRequest"].append(r)
                neu.append(r)
            return {"result": neu}
        raise ValueError(f"Attrappe kennt {methode} {pfad} nicht")
