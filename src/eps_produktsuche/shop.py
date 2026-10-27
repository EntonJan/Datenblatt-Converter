"""Produktdaten aus dem EPS-Onlineshop (www.eps-germany.de/shop, modified eCommerce) lesen.

Aufbau des Shops:
  Startseite → Hauptkategorien (AC-DC:::1.html, E-Last:::76.html …) → Serien (…:::1_500.html, Seite 2 = …:::1_500:2.html)
  Jede Serienseite listet die Geräte als <div class="listingrow"> mit Titel (.lr_title) und Kenndaten (.lr_desc):
  „Bestellnr.“, „Spannung“, „Strom“, „Ausgangsleistung“ bzw. „Eingangsleistung“ (Lasten), „Bauart“, „Betriebseigenschaft“.
  Das Datenblatt liegt unter /shop/media/products/a<Bestellnr>_0.pdf.

Die Werte werden in Zahlen umgerechnet (Umax, Imax, Pmax). Fehlen Spannung/Strom (z. B. bei E-Lasten), werden sie aus der
Typbezeichnung abgeleitet (ELR 10080-510 → 80 V / 510 A; TSDCR 06003000200 → 60 kW / 300 V / 200 A).
"""
from __future__ import annotations

import html
import http.cookiejar
import json
import re
import time
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path

BASIS = "https://www.eps-germany.de/shop/"
KATEGORIEN = {"AC-DC": "AC/DC", "AC-AC": "AC/AC", "DC-AC": "DC/AC", "DC-DC": "DC/DC", "E-Last": "Elektronische Last",
              "Ladegeraete": "Ladegeräte"}
LAST = "Elektronische Last"
AC_AUSGANG = {"AC/AC", "DC/AC"}
USER_AGENT = "EPS-Produktsuche (intern, EPS Stromversorgung GmbH)"


@dataclass
class Geraet:
    bestellnummer: str
    name: str
    serie: str = ""
    geraetetyp: str = ""            # AC/DC, AC/AC, DC/AC, DC/DC, Elektronische Last, Ladegeräte
    bidirektional: bool = False
    spannung: str = ""              # Originaltexte aus dem Shop
    strom: str = ""
    leistung: str = ""
    bauart: str = ""
    umin: float | None = None
    umax: float | None = None
    imax: float | None = None
    pmax: float | None = None
    ac: bool = False                # Wechselspannungsausgang
    u_fest: list[float] = field(default_factory=list)              # AC: feste Spannungen (200/115 VAC)
    u_bereiche: list[list[float]] = field(default_factory=list)    # AC: einstellbare Bereiche (0-300 VAC)
    aus_name: str = ""              # „U, I“ = aus der Typbezeichnung abgeleitet
    parallel: bool = False
    parallel_max: int | None = None
    reihe: bool = False
    shop_url: str = ""
    pdf_url: str = ""

    @property
    def kann_senken(self) -> bool:
        return self.geraetetyp == LAST or self.bidirektional


# ------------------------------------------------------------------------ Zahlen aus Shop-Texten

_ZAHL = r"\d+(?:[.,]\d+)?"
_TOKEN = re.compile(r"(" + _ZAHL + r")\s*([a-zA-Zµ°]*)")
_PRAEFIX = {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3}


def _z(s: str) -> float:
    return float(s.replace(",", "."))


def _tokens(text: str) -> list[tuple[float, str, int, int]]:
    """Zahlen mit Einheit; Zahlen ohne Einheit erben die Einheit der nächsten Zahl, wenn nur „-“, „/“ oder „bis“ dazwischen
    steht („0-750 VDC“, „200/115 VAC“)."""
    t = (text or "").replace("−", "-")
    roh = [[_z(m.group(1)), m.group(2), m.start(), m.end()] for m in _TOKEN.finditer(t)]
    for i in range(len(roh) - 2, -1, -1):
        if not roh[i][1] and re.fullmatch(r"\s*(?:-|–|/|bis|to|\.\.\.?)\s*", t[roh[i][3]:roh[i + 1][2]]):
            roh[i][1] = roh[i + 1][1]
    return [tuple(x) for x in roh]


def _faktor(einheit: str, basis: str) -> float | None:
    """Einheit → Faktor zur Grundeinheit, None wenn es nicht diese Größe ist."""
    e = einheit
    f = 1.0
    if len(e) > 1 and e[0] in _PRAEFIX and e[1:2] in ("V", "A", "W"):
        f, e = _PRAEFIX[e[0]], e[1:]
    scheinleistung = e.startswith("VA") and not e.startswith("VAC")
    if basis == "V":
        return f if e.startswith("V") and not scheinleistung else None
    if basis == "A":
        if not e.startswith("A") or e.startswith(("App", "Ap")) and not e.startswith("Aeff"):
            return None
        return f
    if basis == "W":
        return f if e.startswith("W") or scheinleistung else None
    return None


def werte(text: str, basis: str) -> list[float]:
    out = []
    toks = _tokens(text)
    for w, e, _, _ in toks:
        f = _faktor(e, basis)
        if f is not None:
            out.append(w * f)
    if not out and len(toks) == 1 and not toks[0][1]:        # „1,45“ ohne Einheit (einzelner Wert im Feld)
        out.append(toks[0][0])
    return out


def maximum(text: str, basis: str) -> float | None:
    w = werte(text, basis)
    return max(w) if w else None


def spannung_lesen(text: str, ac: bool) -> tuple[float | None, float | None, list[float], list[list[float]]]:
    """(Umin, Umax, feste Werte, Bereiche) – Bereiche „a-b V“, alles andere sind feste Spannungen."""
    t = (text or "").replace("−", "-")
    bereiche, belegt = [], []
    for m in re.finditer(r"(" + _ZAHL + r")\s*(?:V(?:AC|DC)?\s*)?(?:-|–|bis)\s*(" + _ZAHL + r")\s*(k?)V(?!A(?!C))", t):
        f = 1e3 if m.group(3) else 1.0
        a, b = _z(m.group(1)) * f, _z(m.group(2)) * f
        if a < b:
            bereiche.append([a, b])
            belegt.append((m.start(), m.end()))
    fest = []
    for w, e, s, _ in _tokens(t):
        if any(a <= s < b for a, b in belegt):
            continue
        f = _faktor(e, "V")
        if f is not None:
            fest.append(w * f)
    alle = fest + [x for b in bereiche for x in b]
    if not alle:
        return None, None, [], []
    return min(alle), max(alle), sorted(set(fest)), bereiche


_NAME_EA = re.compile(r"\b(?:EL|ELR|PUL|PSB|PSI|PS|PU|PUB|BT)\s?(\d{4,5})-(\d{1,5})\b")
_NAME_TS = re.compile(r"\bTSDCR\s+(\d{3})(\d{4})(\d{4})\b")


def aus_typbezeichnung(name: str) -> tuple[float | None, float | None, float | None]:
    """ELR 10080-510 → (80, 510, None) · EL 9750-40 → (750, 40, None) · TSDCR 06003000200 → (300, 200, 60000)."""
    m = _NAME_TS.search(name)
    if m:
        return float(int(m.group(2))), float(int(m.group(3))), float(int(m.group(1))) * 1000
    m = _NAME_EA.search(name)
    if m:
        n = m.group(1)
        u = int(n) % (10000 if len(n) == 5 else 1000)
        return (float(u) if u else None), float(int(m.group(2))), None
    return None, None, None


# ------------------------------------------------------------------------ HTML auswerten

def _text(fragment: str) -> str:
    t = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def _ohne_sid(url: str) -> str:
    return re.sub(r"[?&]MODsid=[^&#]*", "", url)


@dataclass
class Serie:
    url: str
    titel: str = ""
    geraetetyp: str = ""
    parallel: bool = False
    parallel_max: int | None = None
    reihe: bool = False


def serie_lesen(seite: str, url: str) -> Serie:
    s = Serie(url=_ohne_sid(url))
    m = re.search(r"<h1[^>]*>(.*?)</h1>", seite, re.S)
    s.titel = _text(m.group(1)) if m else ""
    if not s.titel or "nicht gefunden" in s.titel.lower():
        slug = re.search(r"/([^/]+):::", s.url)
        s.titel = slug.group(1).replace("-", " ") if slug else ""
    teil = re.search(r"/shop/([^/:]+)/", s.url)
    s.geraetetyp = KATEGORIEN.get(teil.group(1), "") if teil else ""
    # Beschreibung: Text vor der Artikelliste
    ende = seite.find("listingrow")
    t = _text(seite[:ende if ende > 0 else len(seite)]).lower()
    s.parallel = bool(re.search(r"parallel|master-?slave", t))
    m = re.search(r"bis zu (\d+) (?:geräte|einheiten|module|units)", t)
    s.parallel_max = int(m.group(1)) if m and s.parallel else None
    s.reihe = bool(re.search(r"reihenschaltung (?:ist )?(?:ebenfalls )?möglich|in reihe geschaltet|serienschaltung möglich", t))
    return s


def geraete_lesen(seite: str, serie: Serie) -> list[Geraet]:
    out = []
    bloecke = re.split(r'<div class="listingrow', seite)[1:]
    for b in bloecke:
        tm = re.search(r'class="lr_title[^"]*"[^>]*>(.*?)</div>', b, re.S)
        name = _text(tm.group(1)) if tm else ""
        dm = re.search(r'class="lr_desc[^"]*"[^>]*>(.*?)</div>', b, re.S)
        felder = {}
        for sm in re.finditer(r"<strong>(.*?)</strong>(.*?)(?:<br|</span>)", dm.group(1) if dm else "", re.S):
            felder[_text(sm.group(1)).rstrip(":").strip()] = _text(sm.group(2))
        nr = felder.get("Bestellnr.", "")
        if not nr or not name:
            continue
        pm = re.search(r'href="([^"]*media/products/[^"]+\.pdf)', b)
        bm = re.search(r'itemprop="description"[^>]*>(.*?)</div>', b, re.S)
        beschreibung = [_text(z) for z in re.split(r"<br\s*/?>", bm.group(1))] if bm else []
        for feld, muster in (("Spannung", r"(?:last|ausgangs)?(?:gleich|wechsel)?spannung"),
                             ("Strom", r"(?:last|ausgangs)?(?:gleich|wechsel)?strom")):
            if not felder.get(feld):
                z = next((z for z in beschreibung if re.match(muster + r"\s*:", z, re.I)), "")
                if z:
                    felder[feld] = z.split(":", 1)[1].strip()
        g = Geraet(bestellnummer=nr, name=name, serie=serie.titel, geraetetyp=serie.geraetetyp,
                   spannung=felder.get("Spannung", ""), strom=felder.get("Strom", ""),
                   leistung=felder.get("Ausgangsleistung", "") or felder.get("Eingangsleistung", ""),
                   bauart=felder.get("Bauart", ""), shop_url=serie.url,
                   pdf_url=urllib.request.urljoin(BASIS, _ohne_sid(pm.group(1))) if pm else "",
                   parallel=serie.parallel or any("parallel" in z.lower() for z in beschreibung),
                   parallel_max=serie.parallel_max, reihe=serie.reihe)
        g.bidirektional = "bidirektional" in (felder.get("Betriebseigenschaft", "") + " " + name).lower()
        auswerten(g)
        out.append(g)
    return out


def auswerten(g: Geraet) -> None:
    """Zahlenwerte aus den Shop-Texten (und notfalls aus der Typbezeichnung) berechnen."""
    g.ac = g.geraetetyp in AC_AUSGANG or (bool(re.search(r"VAC|V AC|\bAC\b", g.spannung)) and "VDC" not in g.spannung)
    g.umin, g.umax, g.u_fest, g.u_bereiche = spannung_lesen(g.spannung, g.ac)
    g.imax = maximum(g.strom, "A")
    g.pmax = maximum(re.sub(r"\d+(?:[.,]\d+)?\s*k?(?:VA|W)\s*,?\s*1\s*min", "", g.leistung), "W")   # Kurzzeitwerte („…VA 1 min“) nicht
    abgeleitet = []
    if g.umax is None or g.imax is None:
        u, i, p = aus_typbezeichnung(g.name)
        if g.umax is None and u:
            g.umin, g.umax = 0.0, u
            abgeleitet.append("U")
        if g.imax is None and i:
            g.imax = i
            abgeleitet.append("I")
        if g.pmax is None and p:
            g.pmax = p
            abgeleitet.append("P")
    g.aus_name = ", ".join(abgeleitet)


def links(seite: str) -> list[str]:
    return [_ohne_sid(urllib.request.urljoin(BASIS, html.unescape(h))) for h in re.findall(r'href="([^"]+)"', seite)]


def ist_serie(url: str) -> bool:
    return bool(re.search(r":::\d+_\d+(?:_\d+)*\.html$", url))


def ist_hauptkategorie(url: str) -> bool:
    return bool(re.search(r"/shop/[^/]+:::\d+\.html$", url))


# ------------------------------------------------------------------------ Shop einlesen

class Leser:
    def __init__(self, pause: float = 0.15, timeout: float = 30):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.pause, self.timeout = pause, timeout

    def holen(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "de"})
        with self.opener.open(req, timeout=self.timeout) as r:
            daten = r.read()
            cs = r.headers.get_content_charset() or "utf-8"
        time.sleep(self.pause)
        try:
            return daten.decode(cs)
        except (LookupError, UnicodeDecodeError):
            return daten.decode("latin-1")


def einlesen(leser: Leser | None = None, fortschritt=None) -> list[Geraet]:
    """Liest alle Serien des Shops. fortschritt(text, erledigt, gesamt) wird zwischendurch aufgerufen."""
    leser = leser or Leser()
    start = leser.holen(BASIS)
    alle = links(start)
    haupt = sorted({u for u in alle if ist_hauptkategorie(u)})
    serien = [u for u in dict.fromkeys(alle) if ist_serie(u)]
    for h in haupt:                                       # Unterkategorien, die nicht im Menü stehen
        try:
            for u in links(leser.holen(h)):
                if ist_serie(u) and u not in serien:
                    serien.append(u)
        except OSError:
            continue
    geraete: dict[str, Geraet] = {}
    for n, url in enumerate(serien):
        if fortschritt:
            fortschritt(url.rsplit("/", 1)[-1], n, len(serien))
        try:
            seite = leser.holen(url)
        except OSError:
            continue
        serie = serie_lesen(seite, url)
        seite_nr = 1
        while True:
            for g in geraete_lesen(seite, serie):
                geraete.setdefault(g.bestellnummer + "|" + g.name, g)
            m = re.search(r"Zeige\s*<strong>\d+</strong>\s*bis\s*<strong>(\d+)</strong>\s*\(von insgesamt\s*<strong>(\d+)", seite)
            if not m or int(m.group(1)) >= int(m.group(2)) or seite_nr >= 20:
                break
            seite_nr += 1
            try:
                seite = leser.holen(url[:-5] + f":{seite_nr}.html")
            except OSError:
                break
    if fortschritt:
        fortschritt("fertig", len(serien), len(serien))
    return list(geraete.values())


# ------------------------------------------------------------------------ Zwischenspeicher

def speichern(geraete: list[Geraet], pfad: Path) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(".tmp")
    tmp.write_text(json.dumps({"stand": datetime.now().isoformat(timespec="minutes"), "quelle": BASIS,
                               "geraete": [asdict(g) for g in geraete]}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(pfad)


def laden(pfad: Path) -> tuple[list[Geraet], str]:
    """(Geräte, Stand) – leere Liste, wenn noch nichts gespeichert ist."""
    try:
        d = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], ""
    felder = Geraet.__dataclass_fields__
    return [Geraet(**{k: v for k, v in g.items() if k in felder}) for g in d.get("geraete", [])], d.get("stand", "")


def veraltet(stand: str, tage: int = 7) -> bool:
    try:
        return (date.today() - datetime.fromisoformat(stand).date()).days >= tage
    except ValueError:
        return True
