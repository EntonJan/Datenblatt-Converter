"""Kunde, Stammdaten und Anfrage aus einer E-Mail erkennen (regelbasiert, ohne KI, nichts verlässt den Rechner).

Zwei Arten von Mails:
  • Homepage-Formular: feste Zeilen „Feld: Wert“ zwischen „--- EPS-Anfrage ---“ und „--- Ende ---“ (FORMULAR_VORLAGE)
    → sicher erkennbar, gehört in den Outlook-Ordner „Automatisch“.
  • freie Kundenmail: Gruß + Signatur werden ausgewertet (Firma + Rechtsform, Ansprechpartner, Adresse, Land,
    Telefon, Web, USt-IdNr.) → Ordner „Selbst prüfen“; alles Unsichere wird markiert und vor dem Anlegen bestätigt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from .mail import Mail

FORMULAR_VORLAGE = """--- EPS-Anfrage ---
Firma: {firma}
Rechtsform: {rechtsform}
Anrede: {anrede}
Vorname: {vorname}
Nachname: {nachname}
E-Mail: {email}
Telefon: {telefon}
Straße: {strasse}
PLZ: {plz}
Ort: {ort}
Land: {land}
USt-IdNr.: {ust_id}
Produkt: {produkt}
Menge: {menge}
Wunschtermin: {termin}
Nachricht: {nachricht}
--- Ende ---"""


@dataclass
class Kunde:
    firma: str = ""
    rechtsform: str = ""
    anrede: str = ""
    vorname: str = ""
    nachname: str = ""
    email: str = ""
    telefon: str = ""
    mobil: str = ""
    strasse: str = ""
    plz: str = ""
    ort: str = ""
    land: str = ""               # ISO-Code, z. B. „DE“
    web: str = ""
    ust_id: str = ""

    def als_dict(self) -> dict:
        return asdict(self)

    @property
    def firmenname(self) -> str:
        return f"{self.firma} {self.rechtsform}".strip()


@dataclass
class Erkennung:
    kunde: Kunde
    anfrage: str = ""            # Kern der Nachricht (ohne Gruß, Signatur, zitierte Mails)
    suchtext: str = ""           # Vorschlag fürs Suchfeld (V/A/W, Gerätetyp, Bestellnummer)
    menge: int | None = None
    termin: str = "ASAP"
    formular: bool = False       # Homepage-Formular erkannt (sicher)
    unsicher: list[str] = field(default_factory=list)   # Felder, die geprüft werden sollten
    weitergeleitet_von: str = "" # interne Weiterleitung (z. B. vom Chef) – Kunde stammt aus der Original-Mail
    notiz: str = ""              # Text des Weiterleitenden über der Original-Mail


INTERN = ("eps-germany.de",)     # eigene Domains: Mails von hier sind Weiterleitungen, nie der Kunde


# ------------------------------------------------------------------------ Bausteine

RECHTSFORMEN = [
    "GmbH & Co. KGaA", "GmbH & Co. KG", "GmbH & Co KG", "AG & Co. KG", "UG (haftungsbeschränkt) & Co. KG",
    "UG (haftungsbeschränkt)", "gGmbH", "GmbH", "KGaA", "AG", "UG", "OHG", "KG", "GbR", "PartG mbB", "PartG",
    "e. K.", "e.K.", "e. V.", "e.V.", "eG", "SE", "Pty Ltd", "Pty. Ltd.", "Ltd.", "Ltd", "Limited", "LLC", "PLC",
    "Inc.", "Inc", "Corp.", "Corporation", "S.A.S.", "SAS", "S.A.R.L.", "SARL", "S.à r.l.", "S.A.", "SA", "B.V.", "BV",
    "N.V.", "NV", "S.r.l.", "Srl", "S.p.A.", "SpA", "Sp. z o.o.", "s.r.o.", "a.s.", "A/S", "ApS", "AB", "Oy", "AS",
]
_RF = re.compile(r"(?<![\w.])(" + "|".join(re.escape(r) for r in sorted(RECHTSFORMEN, key=len, reverse=True))
                 + r")(?![\w])")

GRUSS = re.compile(r"^\s*(mit freundlichen gr(ü|ue)(ß|ss)en|freundliche gr(ü|ue)(ß|ss)e|viele gr(ü|ue)(ß|ss)e|"
                   r"beste gr(ü|ue)(ß|ss)e|liebe gr(ü|ue)(ß|ss)e|sch(ö|oe)ne gr(ü|ue)(ß|ss)e|gru(ß|ss)|mfg|vg|lg|"
                   r"best regards|kind regards|regards|best wishes|sincerely|yours sincerely|thanks and regards|"
                   r"cordialement|distinti saluti|cordiali saluti|met vriendelijke groet|med vänliga hälsningar)\b[ ,.!]*",
                   re.I | re.M)
ZITAT = re.compile(r"^(-{2,}\s*(original|ursprüngliche)|von:\s.+|from:\s.+|am .{5,60} schrieb|on .{5,80} wrote:|>)",
                   re.I | re.M)

LAENDER = {
    "deutschland": "DE", "germany": "DE", "österreich": "AT", "oesterreich": "AT", "austria": "AT", "schweiz": "CH",
    "switzerland": "CH", "suisse": "CH", "frankreich": "FR", "france": "FR", "italien": "IT", "italy": "IT",
    "italia": "IT", "niederlande": "NL", "netherlands": "NL", "nederland": "NL", "belgien": "BE", "belgium": "BE",
    "spanien": "ES", "spain": "ES", "españa": "ES", "polen": "PL", "poland": "PL", "polska": "PL",
    "tschechien": "CZ", "czech republic": "CZ", "czechia": "CZ", "dänemark": "DK", "denmark": "DK",
    "schweden": "SE", "sweden": "SE", "norwegen": "NO", "norway": "NO", "finnland": "FI", "finland": "FI",
    "großbritannien": "GB", "united kingdom": "GB", "england": "GB", "uk": "GB", "irland": "IE", "ireland": "IE",
    "usa": "US", "united states": "US", "kanada": "CA", "canada": "CA", "luxemburg": "LU", "luxembourg": "LU",
    "ungarn": "HU", "hungary": "HU", "slowakei": "SK", "slovakia": "SK", "slowenien": "SI", "slovenia": "SI",
    "portugal": "PT", "türkei": "TR", "turkey": "TR", "indien": "IN", "india": "IN", "china": "CN", "israel": "IL",
}
VORWAHL = {"49": "DE", "43": "AT", "41": "CH", "33": "FR", "39": "IT", "31": "NL", "32": "BE", "34": "ES", "48": "PL",
           "420": "CZ", "45": "DK", "46": "SE", "47": "NO", "358": "FI", "44": "GB", "353": "IE", "1": "US",
           "352": "LU", "36": "HU", "421": "SK", "386": "SI", "351": "PT", "90": "TR", "91": "IN", "86": "CN",
           "972": "IL"}
TLD = {"de": "DE", "at": "AT", "ch": "CH", "fr": "FR", "it": "IT", "nl": "NL", "be": "BE", "es": "ES", "pl": "PL",
       "cz": "CZ", "dk": "DK", "se": "SE", "no": "NO", "fi": "FI", "uk": "GB", "ie": "IE", "lu": "LU", "hu": "HU",
       "sk": "SK", "si": "SI", "pt": "PT", "tr": "TR", "in": "IN", "cn": "CN", "il": "IL"}
FREEMAIL = {"gmail.com", "googlemail.com", "gmx.de", "gmx.net", "gmx.at", "web.de", "t-online.de", "outlook.com",
            "outlook.de", "hotmail.com", "hotmail.de", "live.com", "live.de", "yahoo.com", "yahoo.de", "icloud.com",
            "me.com", "aol.com", "freenet.de", "posteo.de", "mailbox.org", "proton.me", "protonmail.com"}

_TELEFON = re.compile(r"(?i)\b(tel(?:efon)?|phone|fon|t|direkt|direct|zentrale|office)\b\.?\s*[:.]?\s*"
                      r"(\+?\(?\d[\d\s/().-]{5,}\d)")
_MOBIL = re.compile(r"(?i)\b(mobil(?:e)?|handy|cell|m)\b\.?\s*[:.]?\s*(\+?\(?\d[\d\s/().-]{5,}\d)")
_FAX = re.compile(r"(?i)\bfax\b")
_WEB = re.compile(r"(?i)\b((?:https?://)?www\.[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})(?:/\S*)?")
_UST = re.compile(r"(?i)(?:ust\.?-?\s?id(?:ent)?\.?(?:-?nr\.?)?|umsatzsteuer-?id(?:entifikationsnummer)?|vat(?:\s*(?:id|no\.?|"
                  r"number|reg(?:istration)?\.?\s*no\.?))?|uid(?:-nr\.?)?|tva|p\.?\s?iva|nip)\s*[:.]?\s*"
                  r"([A-Z]{2}[\s-]?[0-9A-Z][0-9A-Z .-]{6,14}[0-9A-Z])")
_UST_FREI = re.compile(r"\b(DE\s?\d{3}\s?\d{3}\s?\d{3}|ATU\s?\d{8}|CHE-?\d{3}\.\d{3}\.\d{3})\b")
_PLZ_ORT = re.compile(r"^(?:(?P<lk>[A-Z]{1,2})\s?-\s?)?(?P<plz>\d{4,5})\s+(?P<ort>[A-ZÄÖÜ][\wÄÖÜäöüß .()/-]{1,40})$")
_STRASSE = re.compile(r"(?i)^(?P<s>[A-ZÄÖÜ][\wÄÖÜäöüß .'-]*?(?:stra(ß|ss)e|str\.|weg|platz|allee|gasse|ring|damm|ufer|"
                      r"chaussee|markt|steig|pfad|hof|park|feld|berg|graben|zeile|street|st\.|road|rd\.|avenue|ave\.|"
                      r"lane|drive|boulevard|blvd\.|way)\s*\d+\s?[a-z]?(?:\s?[-/]\s?\d+[a-z]?)?)\b")
_STRASSE_LOCKER = re.compile(r"^(?P<s>[A-ZÄÖÜ][\wÄÖÜäöüß.-]+(?:\s[\wÄÖÜäöüß.-]+){0,3}\s\d{1,4}\s?[a-z]?)$")
_NAME = re.compile(r"^(?:(?P<anrede>Herr|Frau|Mr\.?|Mrs\.?|Ms\.?|Dr\.)\s+)?(?:(Dr\.|Prof\.|Dipl\.-\w+\.?|Ing\.)\s+)*"
                   r"(?P<name>[A-ZÄÖÜ][a-zäöüßé'-]+(?:\s+(?:von|van|de|der|zu|di|le|da)?\s*[A-ZÄÖÜ][a-zäöüßé'-]+){1,3})$")


def _zeilen(text: str) -> list[str]:
    return [z.strip(" \t|•·") for z in (text or "").replace("\r", "").split("\n")]


def _ohne_zitat(text: str) -> str:
    m = ZITAT.search(text or "")
    return text[:m.start()] if m else (text or "")


def _land_aus(*hinweise: str) -> str:
    for h in hinweise:
        if h:
            return h
    return ""


def _nummer(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip(" .-/")


def _vorwahl_land(nummer: str) -> str:
    n = re.sub(r"[^\d+]", "", nummer.replace("(0)", ""))
    if n.startswith("00"):
        n = "+" + n[2:]
    if n.startswith("+"):
        for laenge in (3, 2, 1):
            if n[1:1 + laenge] in VORWAHL:
                return VORWAHL[n[1:1 + laenge]]
    return ""


# ------------------------------------------------------------------------ Homepage-Formular

_FORMULAR = re.compile(r"-{3}\s*EPS-Anfrage\s*-{3}(.*?)-{3}\s*Ende\s*-{3}", re.S | re.I)
_FELDER = {"firma": "firma", "company": "firma", "rechtsform": "rechtsform", "anrede": "anrede", "vorname": "vorname",
           "first name": "vorname", "nachname": "nachname", "last name": "nachname", "name": "name", "e-mail": "email",
           "email": "email", "telefon": "telefon", "phone": "telefon", "straße": "strasse", "strasse": "strasse",
           "street": "strasse", "plz": "plz", "zip": "plz", "ort": "ort", "city": "ort", "land": "land",
           "country": "land", "ust-idnr.": "ust_id", "vat id": "ust_id", "produkt": "produkt", "product": "produkt",
           "menge": "menge", "quantity": "menge", "wunschtermin": "termin", "nachricht": "nachricht",
           "message": "nachricht"}


def _formular(text: str) -> dict | None:
    m = _FORMULAR.search(text or "")
    if not m:
        return None
    werte: dict[str, str] = {}
    letzter = ""
    for zeile in m.group(1).strip().split("\n"):
        km = re.match(r"\s*([\w .\-ä-üÄ-Üß]+?)\s*:\s*(.*)$", zeile)
        if km and km.group(1).lower() in _FELDER:
            letzter = _FELDER[km.group(1).lower()]
            werte[letzter] = km.group(2).strip()
        elif letzter == "nachricht":                       # mehrzeilige Nachricht
            werte[letzter] += "\n" + zeile.rstrip()
    return werte


# ------------------------------------------------------------------------ freie Mail

def signatur(text: str) -> tuple[str, str]:
    """(Nachricht, Signaturblock). Ohne Grußformel: die letzten Zeilen gelten als Signatur."""
    kern = _ohne_zitat(text).rstrip()
    gruesse = list(GRUSS.finditer(kern))
    if gruesse:
        g = gruesse[-1]
        return kern[:g.start()].strip(), kern[g.end():].strip()
    zeilen = kern.split("\n")
    return "\n".join(zeilen[:-12]).strip() if len(zeilen) > 14 else kern, "\n".join(zeilen[-12:])


def kunde_aus_signatur(block: str, mail: Mail) -> tuple[Kunde, list[str]]:
    k = Kunde(email=(mail.absender_email or "").lower())
    unsicher: list[str] = []
    zeilen = [z for z in _zeilen(block) if z]
    # Ansprechpartner: erste Namenszeile der Signatur, sonst Anzeigename des Absenders
    for z in zeilen[:4]:
        nm = _NAME.match(z)
        if nm and not _RF.search(z):
            k.anrede = {"herr": "Herr", "mr": "Herr", "mr.": "Herr", "frau": "Frau", "mrs": "Frau", "mrs.": "Frau",
                        "ms": "Frau", "ms.": "Frau"}.get((nm.group("anrede") or "").lower(), "")
            teile = nm.group("name").split()
            k.vorname, k.nachname = " ".join(teile[:-1]), teile[-1]
            break
    if not k.nachname and mail.absender_name:
        n = re.sub(r"\s*\(.*?\)|\s*\[.*?]", "", mail.absender_name).strip(' "\'')
        if "," in n:                                       # „Mustermann, Max“
            nach, vor = [x.strip() for x in n.split(",", 1)]
            k.vorname, k.nachname = vor, nach
        elif "@" not in n and n:
            teile = n.split()
            k.vorname, k.nachname = " ".join(teile[:-1]), teile[-1]
        unsicher.append("Ansprechpartner (aus dem Absendernamen)")
    # Firma + Rechtsform
    for z in zeilen:
        m = _RF.search(z)
        if m and not _TELEFON.search(z) and "@" not in z and len(z) < 90:
            firma = z[:m.start()].strip(" ,-–|")
            if firma:
                k.firma, k.rechtsform = firma, m.group(1)
                break
    if not k.firma:
        domain = k.email.split("@")[-1] if "@" in k.email else ""
        if domain and domain not in FREEMAIL:
            k.firma = domain.rsplit(".", 1)[0].replace("-", " ").title()
            unsicher.append("Firma (nur aus der E-Mail-Domain geraten, Rechtsform fehlt)")
        else:
            unsicher.append("Firma nicht gefunden")
    # Adresse
    for i, z in enumerate(zeilen):
        po = _PLZ_ORT.match(z)
        if po:
            k.plz, k.ort = po.group("plz"), po.group("ort").strip()
            if po.group("lk"):
                k.land = {"D": "DE", "A": "AT", "CH": "CH", "F": "FR", "I": "IT", "NL": "NL"}.get(po.group("lk"), "")
            for vorher in reversed(zeilen[max(0, i - 2):i]):
                sm = _STRASSE.match(vorher) or _STRASSE_LOCKER.match(vorher)
                if sm and not _RF.search(vorher):
                    k.strasse = sm.group("s").strip()
                    break
            break
        sp = re.match(r"^(?P<s>.+?\d+\s?[a-z]?)\s*[,·|]\s*(?:(?P<lk>[A-Z]{1,2})-)?(?P<plz>\d{4,5})\s+(?P<ort>.+)$", z)
        if sp and (_STRASSE.match(sp.group("s")) or _STRASSE_LOCKER.match(sp.group("s"))):
            k.strasse, k.plz, k.ort = sp.group("s").strip(), sp.group("plz"), sp.group("ort").strip(" ,")
            break
    # Land: ausgeschrieben > USt-Präfix > Telefonvorwahl > Domain > PLZ-Länge
    land_text = ""
    for z in zeilen:
        for name, code in LAENDER.items():
            if re.fullmatch(rf"(?i){re.escape(name)}", z.strip(" ,.")) or re.search(rf"(?i)\b{re.escape(name)}\s*$", z):
                land_text = code
                break
        if land_text:
            break
    if k.ort:                                             # „München, Germany“
        for name, code in LAENDER.items():
            if re.search(rf"(?i),?\s*\b{re.escape(name)}$", k.ort):
                land_text = land_text or code
                k.ort = re.sub(rf"(?i),?\s*\b{re.escape(name)}$", "", k.ort).strip()
    # Kontakt
    for z in zeilen:
        if _FAX.search(z):
            z = re.split(r"(?i)\bfax\b", z)[0]
        mm = _MOBIL.search(z)
        if mm and not k.mobil:
            k.mobil = _nummer(mm.group(2))
            z = z.replace(mm.group(0), "")
        tm = _TELEFON.search(z)
        if tm and not k.telefon:
            k.telefon = _nummer(tm.group(2))
        wm = _WEB.search(z)
        if wm and not k.web and not re.search(r"(?i)linkedin|xing|facebook|instagram|twitter", z):
            k.web = wm.group(1).lower().removeprefix("http://").removeprefix("https://")
        um = _UST.search(z) or _UST_FREI.search(z)
        if um and not k.ust_id:
            k.ust_id = re.sub(r"[\s.-]", "", um.group(1)) if um.re is _UST else re.sub(r"\s", "", um.group(1))
    if not k.telefon and k.mobil:
        k.telefon = k.mobil
    if not k.web and "@" in k.email and k.email.split("@")[-1] not in FREEMAIL:
        k.web = "www." + k.email.split("@")[-1]
    domain_land = TLD.get((k.web or k.email).rsplit(".", 1)[-1].lower(), "") if (k.web or k.email) else ""
    ust_land = k.ust_id[:2] if re.match(r"[A-Z]{2}", k.ust_id or "") else ""
    ust_land = {"CH": "CH", "EL": "GR"}.get(ust_land, ust_land) if ust_land != "AT" or k.ust_id.startswith("ATU") else "AT"
    k.land = k.land or _land_aus(land_text, ust_land, _vorwahl_land(k.telefon), domain_land,
                                 "DE" if len(k.plz) == 5 else "")
    if k.land and not (land_text or ust_land):
        unsicher.append("Land (aus Telefonvorwahl/Domain/PLZ geschlossen)")
    if not k.strasse or not k.plz:
        unsicher.append("Adresse unvollständig")
    if not k.ust_id and k.land and k.land != "DE":
        unsicher.append("USt-IdNr. fehlt (wichtig für Kunden im Ausland)")
    return k, unsicher


# ------------------------------------------------------------------------ Anfrage-Inhalt

_MENGE = re.compile(r"(?i)(?:\b(?:menge|anzahl|stückzahl|quantity|qty)\s*[:=]?\s*(\d{1,5})\b|"
                    r"\b(\d{1,5})\s*(?:stk\.?|stück|pcs\.?|pieces|units|einheiten|geräte|devices)\b)")
_TERMIN = re.compile(r"(?i)(?:liefertermin|wunschtermin|lieferung bis|benötigt bis|bis spätestens|delivery(?: date)?|"
                     r"needed by|required by)\s*[:]?\s*([^\n.;]{3,40})")
_BESTELLNR = re.compile(r"\b(?:bestell-?nr\.?|art(?:ikel)?-?nr\.?|best\.-?nr\.?|part\s*no\.?)\s*[:.]?\s*(\d{6})\b", re.I)


def suchtext(nachricht: str) -> str:
    """Kurzer Suchtext aus der Nachricht: Bestellnummer, sonst Gerätetyp + V/A/W + Merkmale."""
    from . import suche as Q
    bm = _BESTELLNR.search(nachricht)
    if bm:
        return bm.group(1)
    teile: list[str] = []
    tl = nachricht.lower()
    for muster, wort in ((r"\be-?last|elektronische last|electronic load|\bsenke\b", "Last"),
                         (r"wechselrichter|inverter", "Wechselrichter"), (r"frequenzwandler|frequency converter", "AC/AC"),
                         (r"ladeger(ä|ae)t|charger", "Ladegerät"),
                         (r"netzger(ä|ae)t|netzteil|stromversorgung|power supply|stromquelle|labornetz", "Quelle")):
        if re.search(muster, tl):
            teile.append(wort)
            break
    rest = nachricht
    for muster in (Q._EINGANG_VOR, Q._EINGANG):          # DC-Eingang zuerst, sonst wird er als Ausgang gelesen
        m = muster.search(rest)
        if m:
            teile.append(f"Eingang {m.group('u')}VDC")
            rest = rest[:m.start()] + (" " + m.group("aus") + " " if muster is Q._EINGANG_VOR else " ") + rest[m.end():]
            break
    for m in Q._TOKEN.finditer(rest):
        teile.append(m.group(0).strip(" ,;()"))
    # Bauform (19 Zoll …) bewusst nicht – sie schließt sonst gleichwertige Geräte aus; steht ja in der Nachricht
    for muster, wort in ((r"bi-?direktional|bidirectional", "bidirektional"),
                         (r"wassergek(ü|ue)hlt|water.?cooled", "wassergekühlt")):
        if re.search(muster, tl):
            teile.append(wort)
    for m in re.finditer(r"\b\d+(?:[.,]\d+)?\s*hz\b", tl):
        teile.append(m.group(0))
    return " ".join(dict.fromkeys(teile))


# ------------------------------------------------------------------------ Weiterleitungen

_KOPF = re.compile(r"^[ \t>]*(?:von|from|de|da|absender)\s*:[ \t]*(?P<von>[^\n]*?)[ \t]*\n"
                   r"(?P<rest>(?:[ \t>]*(?:gesendet|sent|datum|date|an|to|cc|bcc|betreff|subject|envoyé|à|objet|"
                   r"wichtigkeit|importance|antwort an|reply-to)\s*:[^\n]*\n?){1,8})", re.I | re.M)
_MAILTO = re.compile(r"(?:<|\[mailto:|\()?\s*([\w.+-]+@[\w-]+(?:\.[\w-]+)+)\s*(?:>|\]|\))?")


@dataclass
class Block:
    name: str
    email: str
    betreff: str
    text: str


def ist_intern(adresse: str, intern=INTERN) -> bool:
    dom = (adresse or "").lower().rsplit("@", 1)[-1]
    return bool(dom) and any(dom == d or dom.endswith("." + d) for d in intern)


def zerlegen(text: str) -> tuple[str, list[Block]]:
    """Weitergeleitete/zitierte Mails im Text → (eigener Text oben, Blöcke darunter mit Absender und Inhalt)."""
    treffer = list(_KOPF.finditer(text or ""))
    if not treffer:
        return text or "", []
    oben = text[:treffer[0].start()]
    oben = re.sub(r"(?im)^[ \t>]*-{2,}.*(original|forwarded|weitergeleitet|ursprüngliche).*-*\s*$", "", oben).strip()
    bloecke = []
    for i, m in enumerate(treffer):
        ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(text)
        von = m.group("von")
        em = _MAILTO.search(von)
        name = (von[:em.start()] if em else von).strip(' "\'<[(')
        bm = re.search(r"(?im)^[ \t>]*(?:betreff|subject|objet)\s*:\s*(.*)$", m.group("rest"))
        inhalt = re.sub(r"(?m)^[ \t]*>[ \t]?", "", text[m.end():ende]).strip()
        bloecke.append(Block(name, em.group(1).lower() if em else "", bm.group(1).strip() if bm else "", inhalt))
    return oben, bloecke


def original_mail(mail: Mail, intern=INTERN) -> tuple[Mail | None, str]:
    """Bei interner Weiterleitung: die Original-Mail des Kunden (erster Absender von außerhalb) und die Notiz darüber."""
    for inner in mail.eingebettet:                          # als Anhang weitergeleitet
        if inner.absender_email and not ist_intern(inner.absender_email, intern):
            return inner, signatur(mail.text)[0]
        tiefer, _ = original_mail(inner, intern)
        if tiefer:
            return tiefer, signatur(mail.text)[0]
    oben, bloecke = zerlegen(mail.text)
    for b in bloecke:
        if b.email and ist_intern(b.email, intern):
            continue
        if not b.email and re.search(r"(?i)\beps\b", b.name):
            continue
        return Mail(betreff=b.betreff or mail.betreff, absender_name=b.name, absender_email=b.email, text=b.text,
                    anhaenge=mail.anhaenge, quelle=mail.quelle, ordner=mail.ordner), signatur(oben)[0]
    return None, ""


def erkennen(mail: Mail, intern=INTERN) -> Erkennung:
    werte = _formular(mail.text)
    if werte is not None:
        k = Kunde(firma=werte.get("firma", ""), rechtsform=werte.get("rechtsform", ""), anrede=werte.get("anrede", ""),
                  vorname=werte.get("vorname", ""), nachname=werte.get("nachname", ""),
                  email=(werte.get("email") or mail.absender_email).lower(), telefon=werte.get("telefon", ""),
                  strasse=werte.get("strasse", ""), plz=werte.get("plz", ""), ort=werte.get("ort", ""),
                  ust_id=re.sub(r"\s", "", werte.get("ust_id", "")))
        if not k.rechtsform and k.firma:
            m = _RF.search(k.firma)
            if m:
                k.firma, k.rechtsform = k.firma[:m.start()].strip(" ,"), m.group(1)
        if werte.get("name") and not k.nachname:
            teile = werte["name"].split()
            k.vorname, k.nachname = " ".join(teile[:-1]), teile[-1]
        land = werte.get("land", "")
        k.land = land.upper() if re.fullmatch(r"[A-Za-z]{2}", land) else LAENDER.get(land.lower(), land)
        k.web = "www." + k.email.split("@")[-1] if "@" in k.email and k.email.split("@")[-1] not in FREEMAIL else ""
        nachricht = werte.get("nachricht", "")
        produkt = werte.get("produkt", "")
        try:
            menge = int(werte.get("menge", "") or 0) or None
        except ValueError:
            menge = None
        e = Erkennung(kunde=k, anfrage=(produkt + "\n" + nachricht).strip(), formular=True, menge=menge,
                      termin=werte.get("termin") or "ASAP")
        bm = re.search(r"\((\d{6})\)|\b(\d{6})\b", produkt)
        e.suchtext = (bm.group(1) or bm.group(2)) if bm else suchtext(e.anfrage)
        e.unsicher = [f for f, v in (("Firma", k.firma), ("E-Mail", k.email), ("Land", k.land)) if not v]
        return e
    if ist_intern(mail.absender_email, intern) or (not mail.absender_email and mail.eingebettet):
        original, notiz = original_mail(mail, intern)
        if original is not None:
            e = erkennen(original, intern)
            e.weitergeleitet_von = mail.absender_name or mail.absender_email
            e.notiz = notiz
            if not e.kunde.email:
                e.unsicher.append("E-Mail des Kunden fehlt in der Weiterleitung")
            m = _MENGE.search(notiz)                        # Hinweise des Chefs („bitte 3 Stück anbieten“) zählen auch
            if m and not e.menge:
                e.menge = int(m.group(1) or m.group(2))
            return e
    nachricht, block = signatur(mail.text)
    k, unsicher = kunde_aus_signatur(block, mail)
    if ist_intern(mail.absender_email, intern):
        unsicher.insert(0, "Absender ist EPS-intern – Original-Kunde nicht gefunden, bitte Kundendaten eintragen")
    e = Erkennung(kunde=k, anfrage=nachricht, unsicher=unsicher)
    e.suchtext = suchtext(nachricht) or suchtext(mail.betreff)   # Betreff nur, wenn der Text nichts hergibt
    mm = _MENGE.search(nachricht)
    if mm:
        e.menge = int(mm.group(1) or mm.group(2))
    tm = _TERMIN.search(nachricht)
    if tm and not re.search(r"(?i)asap|so schnell|as soon", tm.group(1)):
        e.termin = tm.group(1).strip()
    if not e.suchtext:
        e.unsicher.append("Keine technischen Werte in der Mail – Anhang oder Text prüfen")
    return e
