"""Weclapp-Anbindung (REST API v1) – Vorbereitung, experimentell.

Ablauf „In Weclapp vorbereiten“ (nur nach Klick, verschickt nichts):
  1. Kunde suchen (E-Mail, sonst Firma + PLZ); fehlt er, wird er mit den Stammdaten aus der Anfrage angelegt.
  2. Artikel zu den Bestellnummern lesen, letzten Einkaufspreis mit Datum prüfen (Frist aus den Einstellungen).
  3. Angebotsentwurf mit allen Positionen anlegen (Verkaufspreise rechnet Weclapp selbst).
  4. Ist mindestens ein Einkaufspreis älter als die Frist: aus dem Angebot die Lieferantenanfrage(n) erzeugen
     (Weclapp: /quotation/id/{id}/createPurchaseOrderRequest), Wunschtermin „ASAP“ bzw. aus der Kundenanfrage.
  5. Links zum Öffnen im Browser zurückgeben.

Alle Feld- und Endpunktnamen stehen in diesem Modul an EINER Stelle (FELDER, PFADE). Sie folgen der weclapp-API-Doku,
sind aber noch nicht gegen ein echtes System geprüft → im 30-Tage-Test zuerst „Verbindung testen“ und einen
Testvorgang anlegen, Abweichungen hier anpassen. Die Testsuite prüft den Ablauf gegen eine Attrappe (weclapp_attrappe).
Token: pro Benutzer in der Windows-Anmeldeinformationsverwaltung (zugang.py), nie in der EXE oder im Repo.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

PFADE = {
    "kunde": "/party",
    "artikel": "/article",
    "bezugsquelle": "/articleSupplySource",
    "angebot": "/quotation",
    "lieferantenanfrage_aus_angebot": "/quotation/id/{id}/createPurchaseOrderRequest",
}
# Links in die Weboberfläche (im Test prüfen und ggf. anpassen)
ANSICHT = {
    "kunde": "/webapp/view/party/party.page?entityId={id}",
    "angebot": "/webapp/view/quotation/quotation.page?entityId={id}",
    "lieferantenanfrage": "/webapp/view/purchaseOrderRequest/purchaseOrderRequest.page?entityId={id}",
}
MARKIERUNG = "[EPS-Produktsuche]"          # steht im Kommentar jedes angelegten Datensatzes (Testdaten wiederfinden)


class WeclappFehler(RuntimeError):
    pass


# ------------------------------------------------------------------------ Transport

class Http:
    """Echte Verbindung: https://<firma>.weclapp.com/webapp/api/v1 + Header „AuthenticationToken“."""

    def __init__(self, basis: str, token: str, timeout: float = 20):
        basis = basis.strip().rstrip("/")
        if not basis.startswith("http"):
            basis = "https://" + basis
        if "/webapp/api/" not in basis:
            basis += "/webapp/api/v1"
        self.basis, self.token, self.timeout = basis, token, timeout
        self.web = basis.split("/webapp/api/")[0]

    def __call__(self, methode: str, pfad: str, params: dict | None = None, daten: dict | None = None) -> dict:
        url = self.basis + pfad + ("?" + urllib.parse.urlencode(params) if params else "")
        body = json.dumps(daten).encode("utf-8") if daten is not None else None
        req = urllib.request.Request(url, data=body, method=methode, headers={
            "AuthenticationToken": self.token, "Accept": "application/json", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                inhalt = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")[:500]
            if e.code in (401, 403):
                raise WeclappFehler("Zugang abgelehnt – Token oder Rechte prüfen.") from e
            raise WeclappFehler(f"Weclapp meldet {e.code} bei {methode} {pfad}: {text}") from e
        except OSError as e:
            raise WeclappFehler(f"Weclapp nicht erreichbar: {e}") from e
        return json.loads(inhalt) if inhalt.strip() else {}


# ------------------------------------------------------------------------ Ergebnis

@dataclass
class Position:
    bestellnummer: str
    name: str = ""
    menge: int = 1
    artikel_id: str = ""
    ek_datum: date | None = None          # Datum des letzten Einkaufspreises
    ek_alt: bool = True                   # älter als die Frist oder unbekannt → Herstelleranfrage
    lieferant: str = ""
    fehler: str = ""


@dataclass
class Plan:
    """Was angelegt würde – wird vor dem Klick angezeigt."""
    kunde_id: str = ""
    kunde_neu: bool = False
    kunde_text: str = ""
    positionen: list[Position] = field(default_factory=list)
    termin: str = "ASAP"

    @property
    def herstelleranfrage(self) -> bool:
        return any(p.ek_alt for p in self.positionen if not p.fehler)

    @property
    def fehler(self) -> list[str]:
        return [f"{p.bestellnummer}: {p.fehler}" for p in self.positionen if p.fehler]


@dataclass
class Ergebnis:
    kunde_id: str = ""
    kunde_neu: bool = False
    angebot_id: str = ""
    angebot_nummer: str = ""
    anfrage_ids: list[str] = field(default_factory=list)
    links: dict[str, str] = field(default_factory=dict)


# ------------------------------------------------------------------------ Client

def _liste(antwort: dict) -> list[dict]:
    return antwort.get("result", []) if isinstance(antwort, dict) else []


def _datum(wert) -> date | None:
    """weclapp liefert Zeitpunkte als Millisekunden seit 1970."""
    if wert in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(wert) / 1000).date()
    except (TypeError, ValueError, OSError):
        try:
            return date.fromisoformat(str(wert)[:10])
        except ValueError:
            return None


class Weclapp:
    def __init__(self, transport, web_basis: str = ""):
        self.t = transport
        self.web = web_basis or getattr(transport, "web", "")

    # ---------------------------------------------------------------- Prüfen
    def verbindung_testen(self) -> str:
        r = self.t("GET", PFADE["artikel"], {"pageSize": 1})
        return f"Verbindung OK ({len(_liste(r))} Testartikel gelesen)."

    # ---------------------------------------------------------------- Kunde
    def kunde_finden(self, k) -> dict | None:
        if k.email:
            treffer = _liste(self.t("GET", PFADE["kunde"], {"email-eq": k.email}))
            if treffer:
                return treffer[0]
        if k.firma:
            for p in _liste(self.t("GET", PFADE["kunde"], {"company-ilike": f"%{k.firma}%"})):
                plz = {a.get("zipcode") for a in p.get("addresses", [])}
                if not k.plz or k.plz in plz:
                    return p
        return None

    @staticmethod
    def kunde_daten(k) -> dict:
        """Stammdaten aus der Anfrage → weclapp-Partei (Organisation, Kunde). Feldnamen hier anpassen."""
        firma = f"{k.firma} {k.rechtsform}".strip()
        daten = {
            "partyType": "ORGANIZATION" if firma else "PERSON",
            "customer": True,
            "company": firma,
            "salutation": {"Herr": "MR", "Frau": "MRS"}.get(k.anrede, None),
            "firstName": k.vorname,
            "lastName": k.nachname,
            "email": k.email,
            "phone": k.telefon,
            "mobilePhone1": k.mobil,
            "website": k.web,
            "vatIdentificationNumber": k.ust_id,
            "addresses": [{"street1": k.strasse, "zipcode": k.plz, "city": k.ort, "countryCode": k.land or "DE",
                           "primeAddress": True, "invoiceAddress": True, "deliveryAddress": True}],
            "description": f"{MARKIERUNG} aus Kundenanfrage angelegt",
        }
        if k.vorname or k.nachname:
            daten["contacts"] = [{"partyType": "PERSON", "salutation": daten["salutation"], "firstName": k.vorname,
                                  "lastName": k.nachname, "email": k.email, "phone": k.telefon}]
        return {s: w for s, w in daten.items() if w not in (None, "", [])}

    # ---------------------------------------------------------------- Artikel
    def position_pruefen(self, nr: str, menge: int, frist_monate: int, heute: date | None = None) -> Position:
        heute = heute or date.today()
        pos = Position(nr, menge=menge)
        treffer = _liste(self.t("GET", PFADE["artikel"], {"articleNumber-eq": nr}))
        if not treffer:
            pos.fehler = "Artikel nicht in Weclapp gefunden"
            return pos
        a = treffer[0]
        pos.artikel_id, pos.name = str(a.get("id", "")), a.get("name", "")
        quellen = _liste(self.t("GET", PFADE["bezugsquelle"], {"articleId-eq": pos.artikel_id}))
        daten = []
        for q in quellen:
            for preis in q.get("purchasePrices", []) or []:
                daten.append((_datum(preis.get("startDate")) or _datum(q.get("lastModifiedDate")), q))
            if not q.get("purchasePrices"):
                daten.append((_datum(q.get("lastModifiedDate")), q))
        daten = [(d, q) for d, q in daten if d]
        if daten:
            d, q = max(daten, key=lambda x: x[0])
            pos.ek_datum = d
            pos.lieferant = q.get("supplierName") or q.get("supplierNumber") or str(q.get("supplierId", ""))
            pos.ek_alt = d < heute - timedelta(days=round(frist_monate * 30.44))
        elif not quellen:
            pos.fehler = "kein Lieferant am Artikel hinterlegt"
        return pos

    # ---------------------------------------------------------------- Ablauf
    def planen(self, kunde, positionen: list[tuple[str, int]], frist_monate: int, termin: str = "ASAP",
               heute: date | None = None) -> Plan:
        plan = Plan(termin=termin or "ASAP")
        vorhanden = self.kunde_finden(kunde)
        if vorhanden:
            plan.kunde_id = str(vorhanden.get("id", ""))
            plan.kunde_text = vorhanden.get("company") or f"{vorhanden.get('firstName', '')} {vorhanden.get('lastName', '')}"
            plan.kunde_text += f" (vorhanden, Nr. {vorhanden.get('customerNumber', '–')})"
        else:
            plan.kunde_neu = True
            plan.kunde_text = f"{kunde.firmenname or (kunde.vorname + ' ' + kunde.nachname).strip()} (wird neu angelegt)"
        plan.positionen = [self.position_pruefen(nr, menge, frist_monate, heute) for nr, menge in positionen]
        return plan

    def ausfuehren(self, plan: Plan, kunde, notiz: str = "") -> Ergebnis:
        if plan.fehler:
            raise WeclappFehler("Nicht alle Artikel sind anlegbar:\n" + "\n".join(plan.fehler))
        erg = Ergebnis(kunde_id=plan.kunde_id, kunde_neu=plan.kunde_neu)
        if plan.kunde_neu:
            neu = self.t("POST", PFADE["kunde"], daten=self.kunde_daten(kunde))
            erg.kunde_id = str(neu.get("id", ""))
        kommentar = f"{MARKIERUNG} Wunschtermin: {plan.termin}" + (f"\n{notiz}" if notiz else "")
        angebot = self.t("POST", PFADE["angebot"], daten={
            "customerId": erg.kunde_id,
            "quotationItems": [{"articleId": p.artikel_id, "quantity": str(p.menge)} for p in plan.positionen],
            "recordComment": kommentar,
        })
        erg.angebot_id, erg.angebot_nummer = str(angebot.get("id", "")), str(angebot.get("quotationNumber", ""))
        if plan.herstelleranfrage:
            r = self.t("POST", PFADE["lieferantenanfrage_aus_angebot"].format(id=erg.angebot_id), daten={})
            anfragen = r.get("result", r)
            anfragen = anfragen if isinstance(anfragen, list) else [anfragen]
            erg.anfrage_ids = [str(a.get("id", "")) for a in anfragen if isinstance(a, dict) and a.get("id")]
        if self.web:
            erg.links["Angebot"] = self.web + ANSICHT["angebot"].format(id=erg.angebot_id)
            for i, a in enumerate(erg.anfrage_ids, 1):
                erg.links[f"Herstelleranfrage {i}"] = self.web + ANSICHT["lieferantenanfrage"].format(id=a)
            erg.links["Kunde"] = self.web + ANSICHT["kunde"].format(id=erg.kunde_id)
        return erg
