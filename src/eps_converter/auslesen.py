"""Regelbasiertes Auslesen von Hersteller-Datenblättern (ohne KI).

Grundsatz: Es wird nichts erfunden. Jeder Wert ist eine wörtliche Kopie aus dem PDF, mit
Fundstelle (Seite + Rechteck). Was nicht sicher erkannt wird, bleibt leer.

Erkannte Muster:
  1. Bezeichnung und Wert in einer Zeile        („Technologie      Switching“)
  2. „Bezeichnung: Wert“ in einem Textstück      („Input current: 8.7Arms max“)
  3. Überschrift (fett) mit Wert darunter        (Absopulse, mehrspaltig)
  4. Modelltabellen mit Kopfzeile (Modell/Typ…)  (EA, Trustec, Gustav Klein …) – der Wert wird aus
     der Spalte des gewählten Modells genommen; Zeilen mit nur einem Wert gelten für alle Modelle.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from . import katalog as K

KOPF_WOERTER = {"modell", "model", "typ", "type", "technische daten", "typen / technische daten", "werte",
                "standardgrößen - dc ausgang1", "standardgrößen"}
SPALTEN_LUECKE = 11.0         # pt – größerer Abstand trennt Textstücke in einer Zeile
ZEILEN_TOLERANZ = 2.6         # pt


@dataclass
class Stueck:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    seite: int
    fett: bool
    worte: list = field(default_factory=list)     # (text, x0, x1) der einzelnen Wörter

    @property
    def mitte(self):
        return (self.x0 + self.x1) / 2


@dataclass
class Zeile:
    seite: int
    top: float
    stuecke: list[Stueck]


@dataclass
class Modellspalte:
    tabelle: int
    seite: int
    label: str
    x0: float
    x1: float


@dataclass
class Fund:
    feld_id: str
    text: str
    seite: int
    box: tuple[float, float, float, float]      # x0, top, x1, bottom (PDF-Punkte)
    bezeichnung: str = ""
    teile: list = field(default_factory=list)   # [(text, box)] je Zeile, falls der Wert aus mehreren Zeilen besteht

    def fundstelle(self) -> str:
        x0, t, x1, b = self.box
        return f"{self.seite}|{x0:.1f}|{t:.1f}|{x1:.1f}|{b:.1f}|{self.bezeichnung}"


@dataclass
class Ergebnis:
    funde: dict[str, Fund] = field(default_factory=dict)
    modelle: list[Modellspalte] = field(default_factory=list)
    sprache: str = "de"
    seiten: int = 0
    textlaenge: int = 0
    seitengroessen: list[tuple[float, float]] = field(default_factory=list)

    @property
    def hat_text(self) -> bool:
        return self.textlaenge > 50


# ------------------------------------------------------------------------ PDF → Zeilen/Stücke

def _zeilen(pdf) -> list[Zeile]:
    out = []
    for sn, page in enumerate(pdf.pages, start=1):
        try:
            words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False, use_text_flow=False)
        except Exception:
            continue
        words.sort(key=lambda w: (round(w["top"]), w["x0"]))
        gruppen: list[list[dict]] = []
        for w in words:
            if gruppen and abs(gruppen[-1][0]["top"] - w["top"]) <= ZEILEN_TOLERANZ:
                gruppen[-1].append(w)
            else:
                gruppen.append([w])
        for g in gruppen:
            g.sort(key=lambda w: w["x0"])
            stuecke, akt = [], [g[0]]
            for w in g[1:]:
                luecke = w["x0"] - akt[-1]["x1"]
                if luecke > max(SPALTEN_LUECKE, akt[-1]["size"] * 1.15):
                    stuecke.append(akt); akt = [w]
                else:
                    akt.append(w)
            stuecke.append(akt)
            zs = []
            for st in stuecke:
                zs.append(Stueck(text=" ".join(w["text"] for w in st), x0=st[0]["x0"], x1=st[-1]["x1"],
                                 top=min(w["top"] for w in st), bottom=max(w["bottom"] for w in st), seite=sn,
                                 fett=all("bold" in (w.get("fontname") or "").lower() for w in st),
                                 worte=[(w["text"], w["x0"], w["x1"]) for w in st]))
            out.append(Zeile(seite=sn, top=g[0]["top"], stuecke=zs))
    return out


def _norm(s: str) -> str:
    return K.normalisieren(s)


AUFZAEHLUNG = ("■", "•", "●", "▪", "◦")
_ZUSATZ = {"max", "max.", "min", "min.", "typ", "typ.", "typisch", "nom", "nom.", "nominal", "rated", "ca.", "approx."}


def _bereinigen(text: str) -> str:
    """Fußnoten-Ziffern, Klammern und Zusätze wie „max.“ am Ende einer Bezeichnung entfernen."""
    s = re.sub(r"\(.*?\)", " ", text)
    teile = s.split()
    while teile and (re.fullmatch(r"\d{1,2},?", teile[-1]) or teile[-1].lower() in _ZUSATZ):
        teile.pop()
    return " ".join(teile)


def _passt(text: str, kat: K.Katalog) -> tuple[str | None, str, str]:
    """Prüft, ob ein Textstück eine bekannte Bezeichnung ist.
    Rückgabe: (feld_id, bezeichnung, rest) – rest = Wert hinter einem Doppelpunkt im selben Stück."""
    aufz = text.strip().startswith(AUFZAEHLUNG)
    if aufz:
        # Aufzählungspunkt: nur „■ Bezeichnung: Wert“ ist eine Angabe, sonst Fließtext/Merkmalsliste
        text = text.strip().lstrip("".join(AUFZAEHLUNG)).strip()
        if ":" not in text:
            return None, "", ""
    else:
        for kandidat in (text, _bereinigen(text)):
            n = _norm(kandidat)
            if n and n in kat.synonyme:
                return kat.synonyme[n], text, ""
        # Bezeichnung und Zahlenwert im selben Textstück („Nennspannung & Bereich 0...60 V“)
        worte = text.split()
        for k in range(len(worte) - 1, 0, -1):
            vor, nach = " ".join(worte[:k]), " ".join(worte[k:])
            if _norm(vor) in kat.synonyme and re.match(r"^[<>≤≥±≈~]?\s*-?\d", nach):
                return kat.synonyme[_norm(vor)], vor, f"\x00{k}"     # Markierung: Wert ab Wort k
    if ":" in text:
        vor, nach = text.split(":", 1)
        for kandidat in (vor, _bereinigen(vor)):
            nv = _norm(kandidat)
            if nv in kat.synonyme and nach.strip():
                return kat.synonyme[nv], vor, nach.strip()
    return None, "", ""


# ------------------------------------------------------------------------ Modelltabellen

@dataclass
class _Tabelle:
    nr: int
    seite: int
    top: float
    spalten: list[Modellspalte]
    ende: float = 1e9


def _tabellen(zeilen: list[Zeile]) -> list[_Tabelle]:
    tabs: list[_Tabelle] = []
    i = 0
    while i < len(zeilen):
        z = zeilen[i]
        erst = _norm(z.stuecke[0].text)
        if erst in KOPF_WOERTER and len(z.stuecke) >= 3:
            kopf = z
            # mehrstufiger Kopf: folgende Zeile ebenfalls Kopfwort und mehr Zellen → feinere Spalten
            fein = None
            if i + 1 < len(zeilen) and zeilen[i + 1].seite == z.seite \
                    and _norm(zeilen[i + 1].stuecke[0].text) in KOPF_WOERTER \
                    and sum(len(_aufteilen(s)) for s in zeilen[i + 1].stuecke[1:]) > len(z.stuecke) - 1:
                fein = zeilen[i + 1]
            spalten = []
            nr = len(tabs)
            if fein:
                zellen = []
                for s in fein.stuecke[1:]:
                    zellen += _aufteilen(s)
                for s in zellen:
                    oben = next((o for o in kopf.stuecke[1:] if o.x0 - 30 <= s.mitte <= o.x1 + 30), None)
                    lab = f"{oben.text} / {s.text}" if oben else s.text
                    spalten.append(Modellspalte(nr, z.seite, lab, s.x0, s.x1))
            else:
                for s in kopf.stuecke[1:]:
                    spalten.append(Modellspalte(nr, z.seite, s.text, s.x0, s.x1))
            if tabs and tabs[-1].seite == z.seite:
                tabs[-1].ende = z.top
            tabs.append(_Tabelle(nr, z.seite, z.top, spalten))
            i += 2 if fein else 1
            continue
        i += 1
    return tabs


def _aufteilen(s: Stueck) -> list[Stueck]:
    """Ein Textstück mit mehreren eng stehenden Werten („212 224 248“) in Zellen zerlegen.
    Getrennt wird an Lücken, die größer als ein normaler Wortabstand sind."""
    if not s.worte or len(s.worte) <= 1:
        return [s]
    gruppen = [[s.worte[0]]]
    for w in s.worte[1:]:
        if w[1] - gruppen[-1][-1][2] > 4.5:
            gruppen.append([w])
        else:
            gruppen[-1].append(w)
    if len(gruppen) == 1:
        return [s]
    return [Stueck(" ".join(x[0] for x in g), g[0][1], g[-1][2], s.top, s.bottom, s.seite, s.fett, list(g))
            for g in gruppen]


def _tabelle_fuer(z: Zeile, tabs: list[_Tabelle]) -> _Tabelle | None:
    for t in tabs:
        if t.seite == z.seite and t.top < z.top < t.ende:
            return t
    return None


def _wert_aus_spalte(werte: list[Stueck], spalte: Modellspalte, alle: list[Modellspalte]) -> Stueck | None:
    if not werte:
        return None
    if len(werte) == 1 and not (len(alle) > 2 and len(_aufteilen(werte[0])) >= max(2, len(alle) // 3)):
        return werte[0]                                   # gilt für alle Modelle
    zellen = []
    for w in werte:
        zellen += _aufteilen(w) if len(alle) > len(werte) else [w]
    beste, abstand = None, 1e9
    for w in zellen:
        d = abs(w.mitte - (spalte.x0 + spalte.x1) / 2)
        if d < abstand:
            beste, abstand = w, d
    breite = max(spalte.x1 - spalte.x0, 20)
    return beste if abstand <= breite * 1.6 else None


# ------------------------------------------------------------------------ Hauptfunktion

def analysieren(pfad: Path, kat: K.Katalog) -> tuple[Ergebnis, list[Zeile], list[_Tabelle]]:
    with pdfplumber.open(str(pfad)) as pdf:
        zeilen = _zeilen(pdf)
        groessen = [(float(p.width), float(p.height)) for p in pdf.pages]
        seiten = len(pdf.pages)
    tabs = _tabellen(zeilen)
    erg = Ergebnis(seiten=seiten, seitengroessen=groessen,
                   textlaenge=sum(len(s.text) for z in zeilen for s in z.stuecke))
    erg.modelle = [sp for t in tabs for sp in t.spalten]
    alltext = " ".join(s.text.lower() for z in zeilen for s in z.stuecke)
    de = sum(alltext.count(w) for w in (" und ", " der ", " die ", "spannung", "strom", "gewicht", "leistung"))
    en = sum(alltext.count(w) for w in (" and ", " the ", "voltage", "current", "weight", "power "))
    erg.sprache = "de" if de >= en else "en"
    return erg, zeilen, tabs


ZAHLEN_TYPEN = (K.BEREICH, K.ZAHL)


def auslesen(pfad: Path, kat: K.Katalog, modell: Modellspalte | None = None) -> Ergebnis:
    erg, zeilen, tabs = analysieren(pfad, kat)
    funde = erg.funde

    # Spalten, in denen Bezeichnungen stehen (x-Position von Treffern am Zeilenanfang) – je Seite
    label_x: dict[int, list[float]] = {}
    for z in zeilen:
        s0 = z.stuecke[0]
        if _passt(s0.text, kat)[0] and _norm(s0.text) not in KOPF_WOERTER:
            label_x.setdefault(z.seite, []).append(s0.x0)

    def ist_label_position(st: Stueck, si: int) -> bool:
        if si == 0 or st.fett:
            return True
        return any(abs(st.x0 - x) <= 8 for x in label_x.get(st.seite, []))

    def merken(fid, wert_stuecke: list[Stueck], label: str):
        if fid in funde or not wert_stuecke:
            return
        txt = " ".join(s.text for s in wert_stuecke).strip(" :")
        if not txt or txt in ("-", "–", "—") or txt.startswith(AUFZAEHLUNG):
            return
        if kat.hat(fid) and (kat.feld(fid).typ in ZAHLEN_TYPEN or kat.feld(fid).einheit) and not re.search(r"\d", txt):
            return                                   # Zahlenfeld ohne Zahl → kein sicherer Wert
        box = (min(s.x0 for s in wert_stuecke), min(s.top for s in wert_stuecke),
               max(s.x1 for s in wert_stuecke), max(s.bottom for s in wert_stuecke))
        teile = [(w.text, (w.x0, w.top, w.x1, w.bottom)) for w in wert_stuecke] if len(wert_stuecke) > 1 else []
        funde[fid] = Fund(fid, txt, wert_stuecke[0].seite, box, label, teile)

    for zi, z in enumerate(zeilen):
        if _norm(z.stuecke[0].text) in KOPF_WOERTER and not z.stuecke[0].text.rstrip().endswith(":"):
            continue                                                    # Tabellenkopf, keine Werte („Model:“ dagegen schon)
        for si, st in enumerate(z.stuecke):
            fid, label, rest = _passt(st.text, kat)
            if not fid or fid in funde or not ist_label_position(st, si):
                continue
            vorne = []
            if rest.startswith("\x00"):                                # Bezeichnung + Wert im selben Stück
                k = int(rest[1:])
                ws = st.worte[k:]
                if ws:
                    vorne = [Stueck(" ".join(w[0] for w in ws), ws[0][1], ws[-1][2], st.top, st.bottom, st.seite,
                                    st.fett, list(ws))]
                rest = ""
            if rest:                                                    # Muster 2
                merken(fid, [Stueck(rest, st.x0, st.x1, st.top, st.bottom, st.seite, st.fett)], label)
                continue
            rechts = vorne + z.stuecke[si + 1:]
            # rechte Nachbarn, die selbst Bezeichnungen/Überschriften sind, gehören nicht zum Wert
            werte = []
            doppelpunkt = st.text.rstrip().endswith(":")
            for r in rechts:
                # „Model:  FTC1K…“ – nach einer Bezeichnung mit Doppelpunkt darf der Wert auch fett sein
                if (r.fett and not (doppelpunkt and not werte)) or _passt(r.text, kat)[0]:
                    break
                werte.append(r)
            ja_nein = kat.hat(fid) and kat.feld(fid).typ == K.JA_NEIN
            if ja_nein and werte and not doppelpunkt and not st.fett and werte[0].x0 - st.x1 > 40 \
                    and not _tabelle_fuer(z, tabs):
                werte = []                                              # rechts steht schon die nächste Spalte
            if not werte and not st.fett and not rest and ja_nein:
                merken(fid, [st], label)                                # Merkmal als Aufzählungszeile → „Ja“
                continue
            if st.fett and not doppelpunkt and werte and werte[0].x0 - st.x1 > 40:
                werte = []                                              # fette Überschrift: Wert steht darunter
            tab = _tabelle_fuer(z, tabs)
            if not tab and len(werte) > 1:                              # außerhalb von Tabellen: große Lücke = nächste Spalte
                for i in range(1, len(werte)):
                    if werte[i].x0 - werte[i - 1].x1 > 40:
                        werte = werte[:i]
                        break
            if tab and werte and not st.fett:                           # Muster 4
                if modell is not None and modell.tabelle == tab.nr:
                    w = _wert_aus_spalte(werte, modell, tab.spalten)
                    if w:
                        merken(fid, [w], label)
                elif len(werte) == 1:
                    merken(fid, werte, label)
                continue
            if werte and (not st.fett or si == 0) and not (tab and modell is not None and modell.tabelle != tab.nr):
                merken(fid, werte[:1] if len(werte) > 1 and st.fett else werte, label)   # Muster 1
                continue
            if st.fett or not werte:                                   # Muster 3: Wert darunter
                unten = []
                letzte = st.bottom
                for z2 in zeilen[zi + 1: zi + 8]:
                    if z2.seite != z.seite or z2.top - letzte > (st.bottom - st.top) * 2.2:
                        break
                    kand = [s for s in z2.stuecke if abs(s.x0 - st.x0) <= 8]
                    if not kand:
                        continue
                    s2 = kand[0]
                    if s2.fett or _passt(s2.text, kat)[0]:
                        break
                    unten.append(s2)
                    letzte = s2.bottom
                    if len(unten) >= (5 if fid in AUSGANG_BLOCK else 14 if fid in FLIESSTEXT else 3):
                        break
                merken(fid, unten, label)
    _ausgang_aufteilen(funde, kat)
    _ableiten(funde, zeilen, kat)
    return erg


FLIESSTEXT = ("beschreibung",)
# Merkmale, die oft nur im Fließtext stehen. Treffer → Vorschlag „Ja“ mit Fundstelle.
STICHWORTE_JA = {
    "ueberhitzungsschutz": r"thermal shutdown|over[- ]?temperature protection|overheat protection|übertemperatur|thermische abschaltung",
    "begrenzung_ausgangsstrom": r"current limiting|current limit\b|strombegrenzung",
    "einschaltstrombegrenzung": r"inrush current limit|einschaltstrombegrenzung",
    "robust": r"ruggedi[sz]|conformal coating|schutzlack",
}
# Reihenfolge = Vorrang (19-Zoll-Angaben sind am eindeutigsten)
BAUFORM_STICHWORTE = [r"19\s*(?:[\"”″]|’’|'')?\s*(?:rack|zoll|inch)|rack\s*19\s*(?:[\"”″]|’’|'')?|rackmount|rack[- ]mount|19\s*-?\s*zoll",
                      r"schrank|cabinet", r"tower", r"tischgerät|desktop|benchtop"]


def _stueck_fund(fid, m_text, st: Stueck, label: str) -> Fund:
    return Fund(fid, m_text, st.seite, (st.x0, st.top, st.x1, st.bottom), label)


def _ableiten(funde: dict, zeilen: list[Zeile], kat: K.Katalog) -> None:
    """Werte, die nicht unter einer eigenen Bezeichnung stehen, aus dem übrigen Text ableiten (nur wörtliche Teilstücke)."""
    stuecke = [st for z in zeilen for st in z.stuecke]
    # Eingangsfrequenz aus „230Vac nominal, 47 – 65Hz“
    ein = funde.get("eingangsspannung")
    if ein and "eingangsfrequenz" not in funde and kat.hat("eingangsfrequenz"):
        m = re.search(r"\d+(?:[.,]\d+)?\s*(?:[-–…]|\.\.\.?)\s*\d+(?:[.,]\d+)?\s*Hz\b|\d+(?:[.,]\d+)?(?:/\d+)?\s*Hz\b", ein.text, re.I)
        if m:
            funde["eingangsfrequenz"] = Fund("eingangsfrequenz", m.group(0), ein.seite, ein.box, ein.bezeichnung)
    # Bauform aus Abmessungen oder Text
    if "bauform" not in funde and kat.hat("bauform"):
        q = funde.get("abmessungen")
        for muster in BAUFORM_STICHWORTE:
            m = re.search(muster, q.text, re.I) if q else None
            if m:
                funde["bauform"] = Fund("bauform", m.group(0), q.seite, q.box, q.bezeichnung)
                break
            st = next((x for x in stuecke if re.search(muster, x.text, re.I)), None)
            if st:
                funde["bauform"] = _stueck_fund("bauform", re.search(muster, st.text, re.I).group(0), st, "")
                break
    for fid, muster in STICHWORTE_JA.items():
        if fid in funde or not kat.hat(fid):
            continue
        for st in stuecke:
            m = re.search(muster, st.text, re.I)
            if m:
                funde[fid] = _stueck_fund(fid, m.group(0), st, "")
                break


AUSGANG_BLOCK = ("ausgangsspannung",)
_RE_LEISTUNG = re.compile(r"\d\s*(?:k?W|k?VA)\b")
_RE_STROM = re.compile(r"\d\s*A(?:rms|dc|ac)?\b", re.I)
_RE_SPANNUNG = re.compile(r"\d\s*(?:k?V)(?:ac|dc|rms)?\b", re.I)
_RE_FREQ = re.compile(r"\d+(?:[.,]\d+)?\s*Hz\b", re.I)


def _ausgang_aufteilen(funde: dict, kat: K.Katalog) -> None:
    """Ausgangsangaben, die in einem Block stehen („115Vac, 400Hz / 8.7Arms / 3000W“),
    auf Spannung, Strom, Leistung und Frequenz verteilen. Es werden nur wörtliche Teilstücke übernommen."""
    fu = funde.get("ausgangsspannung")
    if not fu:
        return
    teile = []
    for txt, box in (fu.teile or [(fu.text, fu.box)]):
        # „230Vac/21.7Arms/50Hz“ bzw. „230Vac / 4.5Arms …“ innerhalb einer Zeile weiter zerlegen
        for t in re.split(r"\s+/\s+|(?<=[A-Za-z])/(?=\d)", txt):
            t = t.strip(" ,;")
            if t:
                teile.append((t, box))
    if len(teile) <= 1:
        return
    spannung, strom, leistung, freq = [], None, None, []
    for txt, box in teile:
        if _RE_FREQ.search(txt) and not (_RE_SPANNUNG.search(txt) or _RE_STROM.search(txt) or _RE_LEISTUNG.search(txt)):
            freq.append(txt)                          # „50Hz“ / „at 50Hz“ als eigenes Teilstück
            if strom is None and leistung is None:
                spannung.append((txt, box))
            continue
        if _RE_LEISTUNG.search(txt) and not _RE_SPANNUNG.search(txt):
            leistung = leistung or (txt, box)
        elif _RE_STROM.search(txt) and not _RE_SPANNUNG.search(txt):
            if strom is None and not re.search(r"surge|peak|spitze|inrush", txt, re.I):
                strom = (txt, box)                    # Spitzen-/Einschaltströme gehören nicht in den Nennstrom
        elif strom is None and leistung is None:
            spannung.append((txt, box))
        elif not _RE_SPANNUNG.search(txt):
            break                                     # nach Strom/Leistung: Fließtext eines anderen Absatzes
    if not spannung or (strom is None and leistung is None):
        return

    def box_von(boxen):
        return (min(b[0] for b in boxen), min(b[1] for b in boxen), max(b[2] for b in boxen), max(b[3] for b in boxen))

    fu.text = ", ".join(t for t, _ in spannung)
    fu.box = box_von([b for _, b in spannung])
    fu.teile = []
    neu = []
    if strom and "ausgangsstrom" not in funde:
        neu.append(("ausgangsstrom", strom[0], strom[1]))
    if leistung and "ausgangsleistung" not in funde:
        neu.append(("ausgangsleistung", leistung[0], leistung[1]))
    m = None
    for txt in freq + [t for t, _ in spannung + [x for x in (strom, leistung) if x]]:
        m = m or _RE_FREQ.search(txt)
    if m and "ausgangsfrequenz" not in funde:
        neu.append(("ausgangsfrequenz", m.group(0), fu.box))
    for fid, txt, box in neu:
        if kat.hat(fid):
            funde[fid] = Fund(fid, txt, fu.seite, box, fu.bezeichnung)


# ------------------------------------------------------------------------ Produktbilder

def bilder_finden(pfad: Path, max_seiten: int = 2) -> list[tuple[int, tuple[float, float, float, float]]]:
    """Mögliche Produktfotos: ausreichend große Bilder, keine Logos/Hintergründe.
    Logos erkennt man daran, dass sie auf mehreren Seiten an derselben Stelle stehen."""
    with pdfplumber.open(str(pfad)) as pdf:
        alle = []
        for i, p in enumerate(pdf.pages):
            for im in p.images:
                alle.append((i, float(p.width), (float(im["x0"]), float(im["top"]), float(im["x1"]), float(im["bottom"]))))
    pos = {}
    for i, _, b in alle:
        pos.setdefault(tuple(round(v) for v in b), set()).add(i)
    kand = []
    for i, pw, b in alle:
        x0, t, x1, bo = b
        w, h = x1 - x0, bo - t
        if i >= max_seiten or w * h < 8000 or max(w / h, h / w) > 3 or w > pw * 0.8 or x0 < 0 or t < 0:
            continue
        if len(pos[tuple(round(v) for v in b)]) > 1:
            continue                                            # wiederkehrend → Logo/Kopfgrafik
        kand.append((w * h, i, b))
    kand.sort(key=lambda k: (k[1], -k[0]))                    # Seite 1 zuerst, dann nach Größe
    erg = []
    for _, i, b in kand:
        if any(i == j and not (b[2] < c[0] or c[2] < b[0] or b[3] < c[1] or c[3] < b[1]) for j, c in erg):
            continue                                            # überlappt ein größeres Bild
        erg.append((i, b))
    return erg[:3]


def bilder_extrahieren(pfad: Path, ordner: Path, max_n: int = 3) -> list[str]:
    """Schneidet die gefundenen Produktbilder aus der gerenderten Seite aus (so sehen sie aus wie im PDF)."""
    import pypdfium2 as pdfium
    dateien = []
    funde = bilder_finden(pfad)[:max_n]
    if not funde:
        return dateien
    doc = pdfium.PdfDocument(str(pfad))
    try:
        for n, (i, (x0, t, x1, bo)) in enumerate(funde, start=1):
            skala = 3
            bild = doc[i].render(scale=skala).to_pil()
            r = 1.5                                             # kleiner Rand weg: dort liegen oft Tabellenlinien
            ausschnitt = bild.crop((int((x0 + r) * skala), int((t + r) * skala), int((x1 - r) * skala), int((bo - r) * skala)))
            name = f"pdf_bild_{n}.png"
            ausschnitt.save(ordner / name)
            dateien.append(name)
    finally:
        doc.close()
    return dateien
