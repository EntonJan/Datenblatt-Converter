"""Zu versorgendes Gerät: Der Kunde schickt das Datenblatt eines Verbrauchers (Waschmaschine, Motor, Pumpe …), den
er mit unserem Gerät betreiben will. Dann ist der EINGANG seines Geräts der AUSGANG des gesuchten EPS-Geräts.

Aus den Anschlusswerten (Spannung, Phasen, Frequenz, Leistung/Strom) wird eine Suche nach einer AC-Quelle bzw. einem
Frequenzumrichter (AC/AC) oder Wechselrichter (DC/AC) – je nachdem, was der Kunde zur Verfügung hat. Reserve für den
Anlauf von Motoren wird aufgeschlagen. Was das Datenblatt nicht beantwortet, kommt als „Klären: …“ in die
Liste der ungeklärten Punkte.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

_ZAHL = r"(\d+(?:[.,]\d+)?)"

# Wörter, die auf einen Verbraucher hindeuten (nicht auf ein Netzgerät)
_VERBRAUCHER = re.compile(
    r"waschmaschine|waschautomat|washing machine|washer|trockner|dryer|geschirrspül|dishwasher|kühlschrank|"
    r"refrigerator|kompressor|compressor|\bpumpe\b|\bpump\b|motorleistung|motor power|antrieb|drehzahl|\brpm\b|"
    r"heizleistung|heating power|heizung|heater|anschlusswert|connected load|nennaufnahme|leistungsaufnahme|"
    r"power consumption|stromaufnahme|current consumption|absicherung|fuse protection|\bfuse\b|"
    r"schleuder|spin speed|füllmenge|fassungsvermögen|capacity\s*\(?kg|trommel|drum|wasseranschluss|"
    r"water connection|schutzart|stecker|plug|netzkabel|power cord|elektrischer anschluss|electrical connection",
    re.I)
# Wörter, die für ein Netzgerät/eine Quelle sprechen (dann ist es eher ein Vergleichsgerät)
_QUELLE = re.compile(r"ausgangsspannung|output voltage|ausgangsstrom|output current|ausgangsleistung|output power|"
                     r"netzgerät|power supply|stromversorgung|labornetz|elektronische last|electronic load|"
                     r"wechselrichter|inverter|restwelligkeit|ripple|regelgenauigkeit|regulation", re.I)

_MOTOR = re.compile(r"motor|kompressor|compressor|pumpe|pump|antrieb|drive|lüfter|fan|waschmaschine|washing|washer|"
                    r"trockner|dryer|schleuder|spin|kühl|refrigerat|klima|air condition", re.I)
_HEIZUNG = re.compile(r"heiz|heater|heating|boiler|warmwasser|waschmaschine|waschtrockner|washing machine|washer|"
                      r"trockner|dryer|trocknen|geschirrspül|dishwasher|dampf|steam", re.I)
# Tabellen-Datenblätter: Einheit im Namen, Wert dahinter („Spannung in V 220-240“, „Gesamtanschlusswert in kW 2,1-2,4“)
_TABELLE = re.compile(r"^(?P<name>.*?\S)\s+(?:in|\[|\()\s*(?P<einheit>kVA|VA|kW|W|V|A|Hz)\s*[\])]?\s+"
                      r"(?P<wert>\d+(?:[.,]\d+)?(?:\s*[-–/]\s*\d+(?:[.,]\d+)?)?)\s*$", re.I)
# Leistungsangaben, die nichts über den Anschluss sagen (Standby, Verbrauch pro Zyklus …)
_NEBENSACHE = re.compile(r"aus-zustand|bereitschaft|standby|stand-by|off[- ]mode|kwh|verbrauch pro|pro 100|"
                         r"energieverbrauch|energy consumption", re.I)

RESERVE = {"motor": 2.0, "gemischt": 1.5, "heizung": 1.2, "unbekannt": 1.5}
LASTART_TEXT = {"motor": "Motor/Kompressor", "gemischt": "Motor + Heizung", "heizung": "Heizung (ohmsch)",
                "unbekannt": "unbekannt"}


@dataclass
class Verbraucher:
    name: str = ""
    spannung: float | None = None       # Nennspannung, bei Drehstrom L-N (so führen die Shopdaten AC-Geräte)
    spannung_text: str = ""
    phasen: int = 1
    frequenzen: list[int] = field(default_factory=list)
    leistung: float | None = None       # Nenn-/Anschlussleistung in W (VA)
    strom: float | None = None          # Nennstrom je Phase
    absicherung: float | None = None    # Sicherung (Obergrenze, kein Bedarf)
    anlaufstrom: float | None = None
    lastart: str = "unbekannt"          # motor / heizung / gemischt / unbekannt
    # Entscheidungen beim Einlesen
    versorgung: str = "unbekannt"       # netz / dc / unbekannt
    dc_spannung: float | None = None    # Batterie-/DC-Spannung, falls versorgung == dc
    reserve: float = 1.5
    zweck: str = "unbekannt"            # dauer / pruefung / notstrom / unbekannt

    @property
    def bedarf(self) -> float | None:
        """Benötigte Leistung des EPS-Geräts (VA) mit Reserve."""
        p = self.leistung
        if not p and self.spannung and self.strom:
            p = self.spannung * self.strom * self.phasen
        return round(p * self.reserve, -1) if p else None

    def geraetetyp(self) -> str:
        return {"netz": "AC/AC", "dc": "DC/AC"}.get(self.versorgung, "")

    def anfrage(self) -> str:
        """Suchtext, z. B. „AC/AC 230VAC 60Hz 4,6kVA“."""
        teile = [self.geraetetyp()] if self.geraetetyp() else []
        if self.spannung:
            teile.append(f"{_z(self.spannung)}VAC")
        p = self.bedarf
        if p:
            teile.append(f"{_z(round(p / 1000, 2))}kVA" if p >= 1000 else f"{_z(p)}VA")
        if self.zweck == "pruefung":                   # Prüfung: beide Netzfrequenzen einstellbar
            teile += [f"{f}Hz" for f in sorted(set(self.frequenzen) | {50, 60})]
        elif len(self.frequenzen) == 1 and self.frequenzen != [50]:
            teile.append(f"{self.frequenzen[0]}Hz")     # nur 60 Hz (USA) oder 400 Hz – mehrere = Maschine kann beides
        if self.phasen == 3:
            teile.append("3-phasig")
        if self.versorgung == "dc" and self.dc_spannung:
            teile.append(f"Eingang {_z(self.dc_spannung)}VDC")
        return " ".join(teile)

    def zusammenfassung(self) -> str:
        teile = []
        if self.spannung_text or self.spannung:
            teile.append((self.spannung_text or f"{_z(self.spannung)} V") + (" (3-phasig)" if self.phasen == 3 else ""))
        if self.frequenzen:
            teile.append("/".join(str(f) for f in self.frequenzen) + " Hz")
        if self.leistung:
            teile.append(f"{_z(self.leistung / 1000)} kW" if self.leistung >= 1000 else f"{_z(self.leistung)} W")
        if self.strom:
            teile.append(f"{_z(self.strom)} A")
        if self.absicherung:
            teile.append(f"Absicherung {_z(self.absicherung)} A")
        teile.append(f"Last: {LASTART_TEXT[self.lastart]}")
        return " · ".join(teile)

    def hinweise(self) -> list[str]:
        """Für das Banner und die Liste der ungeklärten Punkte („Klären: …“ landet in der Warnliste)."""
        h = [f"Zu versorgendes Gerät{(': ' + self.name) if self.name else ''} – gesucht wird ein Gerät, dessen "
             f"AUSGANG den Anschluss dieses Geräts versorgt."]
        if self.bedarf:
            grund = "Anlaufstrom laut Datenblatt" if self.anlaufstrom else f"Reserve ×{_z(self.reserve)} für {LASTART_TEXT[self.lastart]}"
            h.append(f"Leistungsbedarf {_z(round(self.bedarf / 1000, 2))} kVA ({grund}).")
        if self.versorgung == "unbekannt":
            h.append("Klären: Was hat der Kunde zur Verfügung – Stromnetz (welche Spannung/Frequenz?) oder Batterie/DC? "
                     "Davon hängt ab, ob ein Frequenzumrichter/AC-Quelle (AC/AC) oder ein Wechselrichter (DC/AC) passt.")
        elif self.versorgung == "dc" and not self.dc_spannung:
            h.append("Klären: Spannung der Batterie bzw. des DC-Netzes beim Kunden (z. B. 24/48/110 V).")
        if self.zweck == "unbekannt":
            h.append("Klären: Wofür? Dauerbetrieb, Prüfung mit veränderter Spannung/Frequenz (z. B. Exportvariante) "
                     "oder Notstrom – bei Prüfungen muss das Gerät Spannung und Frequenz einstellbar liefern.")
        elif self.zweck == "pruefung":
            h.append("Prüfung: Gerät muss Spannung und Frequenz einstellbar liefern – gesucht wird mit 50 und 60 Hz.")
        if self.lastart in ("motor", "gemischt") and not self.anlaufstrom:
            h.append(f"Klären: Anlaufstrom des Motors/Kompressors (nicht im Datenblatt) – gerechnet mit Reserve "
                     f"×{_z(self.reserve)}; ggf. beim Hersteller der Maschine erfragen.")
        if self.anlaufstrom and self.spannung:
            s = self.spannung * self.anlaufstrom * self.phasen
            h.append(f"Klären: Anlaufstrom {_z(self.anlaufstrom)} A (≈ {_z(round(s / 1000, 1))} kVA kurzzeitig) – "
                     "Überlastfähigkeit des EPS-Geräts im Datenblatt prüfen.")
        if self.phasen == 3:
            h.append("Dreiphasiger Anschluss: gesucht werden Geräte mit dreiphasigem Ausgang (Leistung = Summe aller "
                     "Phasen); Geräte ohne Phasenangabe im Shop bleiben mit Hinweis in der Liste.")
        if not self.spannung:
            h.append("Nicht gefunden: Anschlussspannung – bitte von Hand ins Suchfeld schreiben (z. B. „230VAC“).")
        if not (self.leistung or self.strom):
            grenze = (f" Die Absicherung {_z(self.absicherung)} A erlaubt höchstens ≈ "
                      f"{_z(round(self.spannung * self.absicherung * self.phasen / 1000, 1))} kVA (Obergrenze, kein Bedarf)."
                      if self.absicherung and self.spannung else "")
            h.append("Nicht gefunden: Leistung/Stromaufnahme – bitte von Hand ergänzen (z. B. „3kVA“)." + grenze)
        if not self.frequenzen:
            h.append("Klären: Netzfrequenz der Maschine (50 oder 60 Hz) nicht im Datenblatt.")
        return h

    def kundenfragen(self) -> list[str]:
        """Die offenen „Klären“-Punkte als Fragen, die man dem Kunden so schicken kann."""
        f = []
        if self.versorgung == "unbekannt":
            f.append("Welche Stromversorgung steht am Einsatzort zur Verfügung – Stromnetz (bitte Spannung und "
                     "Frequenz angeben) oder Batterie bzw. DC-Netz (bitte Spannung angeben)?")
        elif self.versorgung == "dc" and not self.dc_spannung:
            f.append("Welche Spannung hat Ihre Batterie bzw. Ihr DC-Netz?")
        if self.zweck == "unbekannt":
            f.append("Wofür soll das Gerät betrieben werden – im Dauerbetrieb, für Prüfungen mit veränderter Spannung "
                     "bzw. Frequenz (z. B. für eine Exportvariante) oder als Notstromversorgung?")
        if self.lastart in ("motor", "gemischt") and not self.anlaufstrom:
            f.append("Ist Ihnen der Anlauf- bzw. Einschaltstrom des Geräts bekannt? (Steht oft im Service-Handbuch "
                     "oder ist beim Hersteller erhältlich.)")
        if not self.frequenzen:
            f.append("Mit welcher Netzfrequenz wird das Gerät betrieben (50 oder 60 Hz)?")
        if not self.spannung:
            f.append("Mit welcher Anschlussspannung wird das Gerät betrieben?")
        if not (self.leistung or self.strom):
            f.append("Wie hoch ist die Leistungs- bzw. Stromaufnahme des Geräts?")
        return f

    def als_dict(self) -> dict:
        return asdict(self)


def _z(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def wahrscheinlich(text: str) -> bool:
    """Spricht das Dokument eher für einen Verbraucher als für ein Netzgerät/eine Anforderung an ein Netzgerät?"""
    t = text or ""
    v = len({m.group(0).lower() for m in _VERBRAUCHER.finditer(t)})
    q = len({m.group(0).lower() for m in _QUELLE.finditer(t)})
    return v >= 2 and v > q


def _zeilen(text: str, muster: str) -> list[str]:
    return [z for z in (text or "").splitlines() if re.search(muster, z, re.I)]


_L_N = {380: 220, 400: 230, 415: 240, 440: 254, 480: 277, 690: 400}   # Außenleiter → Strang (L-N)


def _strang(u: float) -> float:
    """Drehstrom-Außenleiterspannung (L-L) → Strangspannung (L-N), so führen die Shopdaten AC-Geräte."""
    return float(_L_N.get(round(u), round(u / 3 ** 0.5)))


_V = r"\s*V(?:AC|olt|\s*AC|\s*~)?(?![A-Za-z])(?!\s*DC)"   # „230 V“, „230VAC“, „230 V AC“, „230 V~“, nicht „VA“/„V DC“


def _spannung(text: str) -> tuple[float | None, str, int]:
    """(Spannung L-N, Originaltext, Phasen) aus den Anschlussangaben."""
    kandidaten = _zeilen(text, r"spannung|voltage|anschluss|connection|netz|supply|power|elektr|rated|\dV") or \
        (text or "").splitlines()
    t_alle = " ".join(kandidaten)
    drei = bool(re.search(r"3\s*N?\s*~|3\s*/\s*N|3N\s*AC|\b3\s*ph|three[- ]phase|dreiphasig|drehstrom|400\s*V\s*3|"
                          r"3\s*x\s*400|\b(380|400|415|480)\s*V", t_alle, re.I))
    for z in kandidaten:
        m = re.search(_ZAHL + r"\s*(?:-|–|/|\.\.\.|bis|to)\s*" + _ZAHL + _V, z)
        einzel = re.search(_ZAHL + _V, z)
        if m:
            a, b = _f(m.group(1)), _f(m.group(2))
            if 80 <= a <= 690 and 80 <= b <= 690:
                lo, hi = min(a, b), max(a, b)
                if 1.6 <= hi / lo <= 1.85:            # 400/230 V: Außenleiter/Strang
                    return lo, m.group(0), 3
                if lo >= 380:                          # 380-415 V Drehstrom
                    return _strang(400 if lo <= 400 <= hi else hi), m.group(0), 3
                u = 230.0 if lo <= 230 <= hi else (120.0 if lo <= 120 <= hi else hi)
                return u, m.group(0), 1
        if einzel:
            u = _f(einzel.group(1))
            if 80 <= u <= 690:
                if u >= 380:
                    return _strang(u), einzel.group(0), 3
                return u, einzel.group(0), 3 if drei and re.search(r"3\s*N?\s*~|3/N|drehstrom|three", z, re.I) else 1
    return None, "", 3 if drei else 1


def _frequenzen(text: str) -> list[int]:
    werte = set()
    for m in re.finditer(r"(\d{2,3})\s*(?:/\s*(\d{2,3})\s*)?Hz", text or "", re.I):
        for g in m.groups():
            if g and int(g) in (50, 60, 400):
                werte.add(int(g))
    return sorted(werte)


def _leistung(text: str) -> float | None:
    """Größte Anschluss-/Gesamtleistung (W); Einzelleistungen (Motor, Heizung) nur, wenn es keine Gesamtangabe gibt."""
    def werte(zeilen):
        out = []
        for z in zeilen:
            for m in re.finditer(_ZAHL + r"\s*(k?)(W|VA)\b", z):
                w = _f(m.group(1)) * (1000 if m.group(2) else 1)
                if 50 <= w <= 2_000_000:
                    out.append(w)
        return out
    gesamt = werte(_zeilen(text, r"anschlusswert|gesamt|connected load|total|nennaufnahme|leistungsaufnahme|"
                                 r"power consumption|rated (input|power)|nennleistung|max\.? leistung|aufnahme|input power"))
    if gesamt:
        return max(gesamt)
    einzel = werte(_zeilen(text, r"leistung|power|motor|heiz|heat"))
    if einzel:
        return sum(einzel) if len(einzel) <= 3 else max(einzel)
    return None


def _strom(text: str, muster: str) -> float | None:
    for z in _zeilen(text, muster):
        m = re.search(_ZAHL + r"\s*A\b", z)
        if m and 0.1 <= _f(m.group(1)) <= 2000:
            return _f(m.group(1))
    return None


def _normalisieren(text: str) -> str:
    """Tabellenzeilen „Name in Einheit Wert“ → „Name Wert Einheit“; Standby-/Verbrauchszeilen fallen weg;
    Tausenderpunkte („2.300 W“) werden entfernt."""
    zeilen = []
    for z in re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", text or "").splitlines():
        if _NEBENSACHE.search(z):
            continue
        m = _TABELLE.match(z.strip())
        if m:
            einheit = m.group("einheit")
            einheit = {"hz": "Hz", "kva": "kVA", "va": "VA", "kw": "kW", "w": "W", "v": "V", "a": "A"}[einheit.lower()]
            z = f"{m.group('name')} {m.group('wert')} {einheit}"
        zeilen.append(z)
    return "\n".join(zeilen)


def lesen(text: str, name: str = "") -> Verbraucher:
    text = _normalisieren(text)
    v = Verbraucher(name=name)
    v.spannung, v.spannung_text, v.phasen = _spannung(text)
    v.frequenzen = _frequenzen(text)
    v.leistung = _leistung(text)
    v.anlaufstrom = _strom(text, r"anlauf|inrush|starting current|einschaltstrom|locked rotor|LRA")
    v.absicherung = _strom(text, r"absicherung|sicherung|fuse|breaker|\bLS\b")
    v.strom = _strom(text, r"nennstrom|rated current|stromaufnahme|current consumption|\bFLA\b|betriebsstrom")
    motor, heizung = bool(_MOTOR.search(text or "")), bool(_HEIZUNG.search(text or ""))
    v.lastart = "gemischt" if motor and heizung else ("motor" if motor else ("heizung" if heizung else "unbekannt"))
    v.reserve = RESERVE[v.lastart]
    if v.anlaufstrom and v.spannung:                 # Anlaufstrom bekannt: Nennleistung reicht, Spitze extra prüfen
        v.reserve = 1.2
    return v


def aus_dict(d: dict | None) -> Verbraucher | None:
    if not d:
        return None
    felder = Verbraucher.__dataclass_fields__
    return Verbraucher(**{k: w for k, w in d.items() if k in felder})


# ------------------------------------------------------------------------ Angaben aus der Kundenmail

# Schiffe haben meist ein AC-Bordnetz (400 V/60 Hz) – darum hier nur Fahrzeuge mit typischem 12/24-V-Netz
_DC = re.compile(r"batterie|akku|battery|dc[- ]?netz|gleichspannung|gleichstrom|\d\s*v\s*dc|dc[- ]bordnetz|"
                 r"solar|photovoltaik|pv[- ]anlage|lkw|wohnmobil|camper|truck", re.I)
# Nur Wörter für das, was der Kunde HAT – eine bloße Spannungsangabe („Die Maschine hat 230 V“) zählt nicht
_NETZ = re.compile(r"steckdose|stromnetz|\bnetz(?:spannung|anschluss|es)?\b|drehstrom|generator|aggregat|"
                   r"\bmains\b|\bgrid\b|wall socket|ac[- ]bordnetz|landstrom|shore power", re.I)
_ZWECK = [("notstrom", re.compile(r"notstrom|\busv\b|\bups\b|stromausfall|netzausfall|backup|emergency power", re.I)),
          # „Bitte prüfen Sie …“ ist kein Prüfzweck
          ("pruefung", re.compile(r"prüfstand|prüfplatz|prüfling|prüfung(?:en)?\b(?! (?:ihres|unserer|des angebot))|"
                                  r"\b(?:zu|wir|ich|müssen|muss|sollen|soll|wollen|will|möchten|möchte) (?:\S+ ){0,6}?(?:prüfen|testen)\b|"
                                  r"\btests?\b|testlauf|export|zertifizier|abnahme|labor|simulier|nachbild|"
                                  r"verschiedene(?:n)? (?:spannung|frequenz|länder)|andere(?:n)? (?:spannung|frequenz)",
                                  re.I)),
          ("dauer", re.compile(r"dauerbetrieb|dauerhaft|rund um die uhr|24/7|täglich|im (?:alltag|einsatz)|"
                               r"fahrzeug|wohnmobil|camper|boot|schiff|container|baustelle|camping", re.I))]


def _saetze(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text or "") if x.strip()]


def aus_mail(v: Verbraucher, text: str) -> list[str]:
    """Was die Kundenmail zu Versorgung, Zweck und Anlaufstrom sagt, in v eintragen. Gibt die Fundstellen
    (Sätze) zurück, damit man im Dialog sieht, woher die Vorauswahl kommt. Datenblattwerte bleiben unverändert."""
    fund: list[str] = []
    saetze = _saetze(text)

    def merken(satz: str):
        kurz = satz if len(satz) <= 160 else satz[:157] + "…"
        if kurz not in fund:
            fund.append(kurz)

    dc_saetze = [x for x in saetze if _DC.search(x)]
    netz_satz = next((x for x in saetze if _NETZ.search(x) and not _DC.search(x)), "")
    if dc_saetze:
        v.versorgung = "dc"
        for satz in dc_saetze:
            m = re.search(_ZAHL + r"\s*v(?:olt)?\s*(?:dc|=|gleich)", satz, re.I) or \
                re.search(r"(?:batterie|akku|battery|bordnetz)\D{0,25}?" + _ZAHL + r"\s*v", satz, re.I) or \
                re.search(_ZAHL + r"\s*v(?:olt)?[- ]?(?:batterie|akku|battery|bordnetz)", satz, re.I)
            if m and 6 <= _f(m.group(1)) <= 1500:
                v.dc_spannung = _f(m.group(1))
                merken(satz)
                break
        else:
            merken(dc_saetze[0])
    elif netz_satz:
        v.versorgung = "netz"
        merken(netz_satz)
    for zweck, muster in _ZWECK:
        satz = next((x for x in saetze if muster.search(x)), "")
        if satz:
            v.zweck = zweck
            merken(satz)
            break
    for x in saetze:
        m = re.search(r"(?:anlauf|einschalt|inrush|start)\w*[^\d\n]{0,45}?" + _ZAHL + r"\s*a\b", x, re.I)
        if m:
            v.anlaufstrom = _f(m.group(1))
            if v.spannung:
                v.reserve = 1.2
            merken(x)
            break
    return fund
