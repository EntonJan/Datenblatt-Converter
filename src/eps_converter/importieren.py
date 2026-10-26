"""Import eines Hersteller-PDFs: Modellauswahl, Auslesen, Vorbefüllen, Original-Vorschau."""
from __future__ import annotations

import re
from dataclasses import asdict
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from . import protokoll, auslesen, regeln, eps_altbestand
from . import katalog as K
from .modell import Datensatz, Wert, Bild, Option, Eintrag, HERKUNFT_PDF, REGEL_HAENDLER, REGEL_EPS

QUELLE = "quelle.pdf"

# Schlüsselwörter zum Erkennen des Herstellers (Dateipfad + Text der ersten Seite)
HERSTELLER_HINWEISE = {
    "absopulse": ["absopulse"],
    "ea elektro-automatik": ["elektro-automatik", "ea-ps", "ea-elr", "psbe", "psi 9", "elr 9"],
    "m.c.b": ["m.c.b", "mcb "],
    "trustec": ["trustec"],
    "plating": ["plating"],
    "gustav klein": ["gustav-klein", "gustav klein"],
    "schäfer": ["schäfer", "schaefer"],
    "sht": ["sht-power", "sht power"],
}

# Vorschläge für Auswahlfelder: Stichwort im Herstellertext → Auswahlwert (deutsch)
AUSWAHL_HINWEISE = {
    "kuehlung": [("wasser", "Wasser"), ("water", "Wasser"), ("konvektion", "Konvektion"), ("convection", "Konvektion"),
                 ("natürlich", "Konvektion"), ("lüfter", "Lüfter"), ("fan", "Lüfter"), ("luft", "Lüfter"), ("air", "Lüfter")],
    "bauform": [("19", "19 Zoll"), ("rack", "19 Zoll"), ("desktop", "Desktop"), ("tisch", "Desktop"),
                ("tower", "Tower"), ("schrank", "Schrank"), ("cabinet", "Schrank"), ("einbau", "Einbaumodul"),
                ("built-in", "Einbaumodul"), ("module", "Einbaumodul")],
    "anzeige": [("touch", "TFT-Touch-Display"), ("tft", "TFT-Display"), ("lcd", "LCD"), ("led", "LED"), ("none", "ohne Anzeige (nur Fernsteuerung)")],
    "parallelschaltung": [("master", "Master-Slave"), ("nein", "Nein"), ("no", "Nein"), ("ja", "Ja"), ("yes", "Ja"), ("standard", "Ja")],
    "ausgangsfrequenz": [("400", "400 Hz"), ("50/60", "50/60 Hz"), ("einstell", "einstellbar"), ("adjust", "einstellbar"),
                         (r"60\s*hz", "60 Hz"), (r"50\s*hz", "50 Hz"), ("dc", "DC")],
}
NEIN_WOERTER = ("nein", "no", "none", "nicht", "not available", "–", "-")


def hersteller_erkennen(pfad: Path, text: str, liste: list[str]) -> str:
    quelle = (str(pfad) + " " + text[:3000]).lower()
    for eintrag in liste:
        e = eintrag.lower()
        for key, worte in HERSTELLER_HINWEISE.items():
            if key in e or e.split()[0] in key:
                if any(w in quelle for w in worte):
                    return eintrag
    return ""


def auswahl_vorschlag(feld: K.Feld, text: str) -> list[str]:
    t = text.lower()
    erlaubt = {de for de, _ in feld.auswahl}
    for wort, wert in AUSWAHL_HINWEISE.get(feld.id, []):
        if re.search(r"(?<![a-zäöü0-9])" + wort, t) and wert in erlaubt:
            return [wert]
    return []


def datensatz_aus_ergebnis(erg: auslesen.Ergebnis, kat: K.Katalog, ds: Datensatz, modell_label: str = "") -> Datensatz:
    for fid, fund in erg.funde.items():
        if not kat.hat(fid):
            continue
        f = kat.feld(fid)
        txt = fund.text
        teil = ""
        if erg.sprache == "en":
            en, de = txt, kat.uebersetze_rueck(txt)
            if de is None:
                de = txt if fid == "beschreibung" else kat.teilweise(txt, "de")
                teil = "de" if de != txt else ""
        else:
            de, en = txt, kat.uebersetze(txt)
            if en is None:
                en = txt if fid == "beschreibung" else kat.teilweise(txt, "en")
                teil = "en" if en != txt else ""
        if fid == "beschreibung" and erg.sprache == "en":
            de = ""             # englischer Fließtext gehört nicht ins deutsche Feld – Übersetzung folgt (KI/von Hand)
        w = Wert(de=de, en=en, herkunft=HERKUNFT_PDF, geprueft=False, fundstelle=fund.fundstelle(), teiluebersetzt=teil)
        if erg.sprache == "en":
            w.en_manuell = True     # Englisch ist hier das Original – Tippen im deutschen Feld überschreibt es nicht
        if f.typ in (K.BEREICH, K.ZAHL) and f.einheit:
            w.min, w.max = regeln.parse_bereich(txt, f.einheit)
        elif f.typ == K.MEHRFACH and fid == "betriebsarten":
            erlaubt = {a.lower(): a for a, _ in f.auswahl}
            w.auswahl = [erlaubt[x.lower()] for x in re.split(r"[\s.,;/+]+", txt) if x.lower() in erlaubt]
            if w.auswahl:
                w.de = w.en = ""
        elif f.typ == K.SCHNITTSTELLE:
            w.if_status, w.if_code = _schnittstelle(txt)
            if w.if_status:
                w.de = w.en = ""
        elif f.typ in (K.AUSWAHL, K.MEHRFACH):
            w.auswahl = auswahl_vorschlag(f, txt)
            if w.auswahl:
                w.de = w.en = ""    # Datenblatt zeigt den sauberen Auswahlwert („Lüfter“); Originaltext über die Fundstelle
        elif f.typ == K.JA_NEIN:
            w.ja = not txt.strip().lower().startswith(NEIN_WOERTER)
            w.de = w.en = ""        # Datenblatt zeigt „Ja“/„Nein“; der Originaltext bleibt über die Fundstelle sichtbar
        ds.werte[fid] = w
    if "netzanschluss" in ds.werte and "eingangsspannung" not in ds.werte and kat.hat("eingangsspannung"):
        n = ds.werte["netzanschluss"]                 # „Netzanschluss“ = Eingangsspannung (EPS- und Hersteller-Blätter)
        e = Wert(de=n.de, en=n.en, herkunft=HERKUNFT_PDF, fundstelle=n.fundstelle, teiluebersetzt=n.teiluebersetzt)
        e.min, e.max = regeln.parse_bereich(n.de, kat.feld("eingangsspannung").einheit or "V")
        ds.werte["eingangsspannung"] = e
    if modell_label:
        ds.werte["hersteller_typ"] = Wert(de=modell_label, en=modell_label, herkunft=HERKUNFT_PDF)
        ds.modell_auswahl = modell_label
    return ds


GERAETETYP_HINWEISE = [("ac/ac", "AC/AC"), ("frequency converter", "AC/AC"), ("frequenzumrichter", "AC/AC"),
                       ("dc/ac", "DC/AC"), ("inverter", "DC/AC"), ("wechselrichter", "DC/AC"),
                       ("dc/dc", "DC/DC"), ("ac/dc", "AC/DC"), ("elektronische last", "Elektronische Last"),
                       ("electronic load", "Elektronische Last"), ("ladegerät", "Ladegeräte"), ("charger", "Ladegeräte")]


def geraetetyp_vorschlag(text: str, kat: K.Katalog) -> list[str]:
    """Vorschlag für den Gerätetyp aus eindeutigen Begriffen im Datenblatt (bleibt ungeprüft)."""
    t = text.lower()
    erlaubt = {de for de, _ in kat.feld("geraetetyp").auswahl} if kat.hat("geraetetyp") else set()
    treffer = []
    for wort, typ in GERAETETYP_HINWEISE:
        if wort in t and typ in erlaubt and typ not in treffer:
            treffer.append(typ)
    return treffer[:1]


# ------------------------------------------------------------------------ Modellauswahl

class ModellDialog(tk.Toplevel):
    def __init__(self, master, modelle: list[auslesen.Modellspalte], datei: str = ""):
        super().__init__(master)
        self.title("Modell auswählen" + (f" – {datei}" if datei else ""))
        self.transient(master)
        self.grab_set()
        self.ergebnis = None
        self.modelle = modelle
        ttk.Label(self, text="Dieses Datenblatt enthält mehrere Modelle.\nBitte das Modell zum Auftrag wählen:",
                  padding=10).pack(anchor="w")
        fr = ttk.Frame(self, padding=(10, 0))
        fr.pack(fill="both", expand=True)
        self.lb = tk.Listbox(fr, height=min(18, len(modelle) + 1), width=46, activestyle="dotbox")
        sb = ttk.Scrollbar(fr, command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        for m in modelle:
            self.lb.insert("end", f"{m.label}   (Tabelle {m.tabelle + 1}, Seite {m.seite})")
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.lb.bind("<Double-1>", lambda e: self.ok())
        bf = ttk.Frame(self, padding=10)
        bf.pack(fill="x")
        ttk.Button(bf, text="Ohne Modell (nur allgemeine Werte)", command=self.ohne).pack(side="left")
        ttk.Button(bf, text="Übernehmen", command=self.ok).pack(side="right")
        self.wait_window()

    def ok(self):
        sel = self.lb.curselection()
        if sel:
            self.ergebnis = self.modelle[sel[0]]
            self.destroy()

    def ohne(self):
        self.ergebnis = False
        self.destroy()


# ------------------------------------------------------------------------ Original-Vorschau

class OriginalViewer(tk.Toplevel):
    """Zeigt das Hersteller-PDF und markiert die Fundstelle des gerade bearbeiteten Werts."""

    def __init__(self, master, pdf: Path):
        super().__init__(master)
        self.title(f"Original: {pdf.name}")
        self.geometry("720x900")
        import pypdfium2 as pdfium
        self._pdfium = pdfium
        self.doc = pdfium.PdfDocument(str(pdf))
        self.seiten = len(self.doc)
        self.seite = 0
        self.skala = 1.4
        self._img = None
        leiste = ttk.Frame(self, padding=4)
        leiste.pack(fill="x")
        ttk.Button(leiste, text="◀ Seite", command=lambda: self.gehe(self.seite - 1)).pack(side="left")
        self.lbl = ttk.Label(leiste, text="")
        self.lbl.pack(side="left", padx=8)
        ttk.Button(leiste, text="Seite ▶", command=lambda: self.gehe(self.seite + 1)).pack(side="left")
        ttk.Button(leiste, text="−", width=3, command=lambda: self.zoom(0.8)).pack(side="right")
        ttk.Button(leiste, text="+", width=3, command=lambda: self.zoom(1.25)).pack(side="right")
        self.info = ttk.Label(self, text="Feld anklicken → Fundstelle wird gelb markiert.", foreground="#6A7380", padding=(6, 0))
        self.info.pack(fill="x")
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True)
        self.cv = tk.Canvas(fr, background="#888")
        ys = ttk.Scrollbar(fr, orient="vertical", command=self.cv.yview)
        xs = ttk.Scrollbar(fr, orient="horizontal", command=self.cv.xview)
        self.cv.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y"); xs.pack(side="bottom", fill="x")
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<MouseWheel>", lambda e: self.cv.yview_scroll(int(-e.delta / 120) * 3, "units"))
        self.protocol("WM_DELETE_WINDOW", self.schliessen)
        self.gehe(0)

    def schliessen(self):
        try:
            self.doc.close()
        except Exception:
            pass
        self.destroy()

    def zoom(self, f):
        self.skala = max(0.6, min(3.0, self.skala * f))
        self.gehe(self.seite)

    def gehe(self, n, box=None):
        from PIL import ImageTk
        if not 0 <= n < self.seiten:
            return
        self.seite = n
        bild = self.doc[n].render(scale=self.skala).to_pil()
        self._img = ImageTk.PhotoImage(bild)
        self.cv.delete("all")
        self.cv.create_image(0, 0, image=self._img, anchor="nw")
        self.cv.configure(scrollregion=(0, 0, bild.width, bild.height))
        self.lbl.configure(text=f"{n + 1} / {self.seiten}")
        if box:
            x0, t, x1, b = (v * self.skala for v in box)
            self.cv.create_rectangle(x0 - 3, t - 3, x1 + 3, b + 3, outline="#E0A800", width=3)
            self.cv.create_rectangle(x0 - 3, t - 3, x1 + 3, b + 3, fill="#FFE066", stipple="gray25", outline="")
            self.cv.yview_moveto(max(0, (t - 120) / bild.height))
            self.cv.xview_moveto(max(0, (x0 - 60) / bild.width))

    def zeige(self, fundstelle: str, feldname: str = ""):
        try:
            teile = fundstelle.split("|")
            seite, x0, t, x1, b = int(teile[0]), *map(float, teile[1:5])
            bez = teile[5] if len(teile) > 5 else ""
        except (ValueError, IndexError):
            return
        self.info.configure(text=f"{feldname}: gefunden bei „{bez}“ (Seite {seite})" if bez else f"{feldname}: Seite {seite}")
        self.gehe(seite - 1, (x0, t, x1, b))
        self.lift()


# ------------------------------------------------------------------------ Ablauf

def dialog(app):
    pfad = filedialog.askopenfilename(title="Hersteller-Datenblatt (PDF) wählen", filetypes=[("PDF", "*.pdf")])
    if pfad:
        importieren_datei(app, Path(pfad))


def stapel_dialog(app):
    pfade = filedialog.askopenfilenames(title="Mehrere Hersteller-Datenblätter (PDF) wählen", filetypes=[("PDF", "*.pdf")])
    if pfade:
        stapel(app, [Path(p) for p in pfade])


def importieren_datei(app, pfad: Path, einzeln: bool = True) -> tuple[Datensatz | None, str]:
    """Liest ein Hersteller-PDF ein und legt einen Entwurf an.
    einzeln=True: danach Maske + Original öffnen. Rückgabe (Datensatz oder None, Hinweis)."""
    if eps_altbestand.ist_eps_datenblatt(pfad):
        return altbestand_importieren(app, pfad, einzeln)
    app.configure(cursor="watch"); app.update()
    try:
        erg, zeilen, _ = auslesen.analysieren(pfad, app.kat)
    except Exception as e:
        app.configure(cursor="")
        if einzeln:
            messagebox.showerror("Import", f"Das PDF konnte nicht gelesen werden:\n{e}")
        return None, f"nicht lesbar ({e})"
    app.configure(cursor="")
    ds = Datensatz()
    ordner = app.ablage.ordner(ds.id)
    shutil.copy2(pfad, ordner / QUELLE)
    ds.quelle_pdf = pfad.name

    text = " ".join(s.text for z in zeilen for s in z.stuecke)
    hersteller = hersteller_erkennen(pfad, text, app.einst.hersteller)
    if hersteller:
        ds.werte["hersteller"] = Wert(de=hersteller, en=hersteller, herkunft=HERKUNFT_PDF)

    hinweis = ""
    if not erg.hat_text:
        hinweis = "kein Text im PDF (Scan) – leeres Datenblatt angelegt"
        if einzeln:
            messagebox.showinfo("Import", "In diesem PDF wurde kein Text gefunden (z. B. eingescanntes Bild).\n\n"
                                          "Es wird ein leeres Datenblatt geöffnet – bitte die Werte von Hand eintragen. "
                                          "Das Original wird daneben angezeigt.")
    else:
        modell = None
        if erg.modelle:
            d = ModellDialog(app, erg.modelle, "" if einzeln else pfad.name)
            if d.ergebnis is None:
                app.ablage.loeschen(ds.id, endgueltig=True)
                return None, "übersprungen (kein Modell gewählt)"
            modell = d.ergebnis or None
        app.configure(cursor="watch"); app.update()
        erg = auslesen.auslesen(pfad, app.kat, modell)
        app.configure(cursor="")
        datensatz_aus_ergebnis(erg, app.kat, ds, modell.label if modell else "")
        ds.import_werte = {fid: asdict(w) for fid, w in ds.werte.items()}
        try:                                            # Produktfotos aus dem PDF als Vorschlag übernehmen
            ds.bilder = [Bild(datei=d) for d in auslesen.bilder_extrahieren(pfad, ordner)]
        except Exception:
            ds.bilder = []
        gt = geraetetyp_vorschlag(text, app.kat)
        if gt and "geraetetyp" not in ds.werte:
            ds.werte["geraetetyp"] = Wert(auswahl=gt, herkunft=HERKUNFT_PDF)

    haendler = app.einst.ist_haendlerware(hersteller)
    ds.regel = REGEL_HAENDLER if haendler else REGEL_EPS
    typ = ds.text("hersteller_typ")
    if typ:
        name = regeln.eps_name(typ, haendlerware=haendler)
        ds.werte["typbezeichnung"] = Wert(de=name, en=name, herkunft=HERKUNFT_PDF)
    n = sum(1 for w in ds.werte.values() if w.herkunft == HERKUNFT_PDF)
    protokoll.eintragen(ds, app.einst, "Importiert", [["Quelle", "", pfad.name], ["Werte aus dem PDF", "", str(n)]])
    app.ablage.speichern(ds)
    hinweis = hinweis or f"{n} Werte" + (f", {len(ds.bilder)} Bild(er)" if ds.bilder else "")
    if einzeln:
        app.maske_zeigen(ds)
        app.original_zeigen(ordner / QUELLE)
        app.aktuell.hinweis(f"{n} Werte aus dem PDF übernommen (Sprache: {'Deutsch' if erg.sprache == 'de' else 'Englisch'}). "
                            "Alle Werte sind Vorschläge – bitte prüfen. Feld anklicken zeigt die Fundstelle."
                            + (f" {len(ds.bilder)} Bild(er) aus dem PDF übernommen – auf Herstellerlogos prüfen." if ds.bilder else ""))
    return ds, hinweis


def stapel(app, pfade: list[Path]):
    """Mehrere PDFs nacheinander importieren; jedes wird ein Entwurf. Am Ende eine Zusammenfassung."""
    fenster = tk.Toplevel(app)
    fenster.title("Stapel-Import")
    fenster.transient(app)
    fenster.geometry("520x120")
    lbl = ttk.Label(fenster, text="", padding=12)
    lbl.pack(fill="x")
    bar = ttk.Progressbar(fenster, maximum=len(pfade), length=480)
    bar.pack(padx=12)
    ergebnisse = []
    for i, p in enumerate(pfade, start=1):
        lbl.configure(text=f"{i} / {len(pfade)}: {p.name}")
        bar["value"] = i - 1
        fenster.update()
        try:
            ds, hinweis = importieren_datei(app, p, einzeln=False)
        except Exception as e:                          # ein defektes PDF darf den Stapel nicht abbrechen
            ds, hinweis = None, f"Fehler: {e}"
        ergebnisse.append((p.name, ds, hinweis))
    fenster.destroy()
    ok = [e for e in ergebnisse if e[1] is not None]
    zeilen = [f"✔ {name}: {h}" if ds else f"✖ {name}: {h}" for name, ds, h in ergebnisse]
    messagebox.showinfo("Stapel-Import", f"{len(ok)} von {len(pfade)} PDFs als Entwurf angelegt.\n\n" + "\n".join(zeilen[:30])
                        + ("\n…" if len(zeilen) > 30 else ""))
    app.start_zeigen()


# ------------------------------------------------------------------------ EPS-Altbestand

JA_TEXTE = ("standard", "ja", "yes", "vorhanden", "included")
NEIN_TEXTE = ("nein", "no", "none", "keine", "–", "-", "—", "nicht", "not")


def _schnittstelle(text: str) -> tuple[str, str]:
    """„Option EPS/IF-AB R“ → (Option, EPS/IF-AB R); „Standard, Opt.IF-ETH1P/2P“ → (Standard, IF-ETH1P/2P)."""
    t = text.strip()
    tl = t.lower()
    status = "Standard" if tl.startswith("standard") else "Option" if tl.startswith("opt") else ""
    m = re.search(r"((?:EPS/|E/|IF-)[\w/\-.]+(?:\s+[A-Z0-9][A-Z0-9/\-.]*)?)", t)
    return status, (m.group(1).strip() if m else "")


def _wert_altbestand(f: K.Feld, kat: K.Katalog, de: str, en: str, fundstelle: str) -> Wert:
    w = Wert(de=de, en=en, herkunft=HERKUNFT_PDF, geprueft=False, fundstelle=fundstelle, en_manuell=bool(en))
    if f.typ in (K.BEREICH, K.ZAHL) and f.einheit:
        w.min, w.max = regeln.parse_bereich(de, f.einheit)
    elif f.typ == K.AUSWAHL:
        erlaubt = {a.lower(): a for a, _ in f.auswahl}
        treffer = erlaubt.get(de.strip().lower()) or (auswahl_vorschlag(f, de) or [None])[0]
        if treffer:
            w.auswahl = [treffer]
            if de.strip().lower() == treffer.lower():
                w.de = w.en = ""                              # sauberer Auswahlwert, kein Zusatztext nötig
    elif f.typ == K.MEHRFACH:
        erlaubt = {a.lower(): a for a, _ in f.auswahl}
        w.auswahl = [erlaubt[x.lower()] for x in re.split(r"[\s.,;/+]+", de) if x.lower() in erlaubt]
        if w.auswahl:
            w.de = w.en = ""
    elif f.typ == K.JA_NEIN:
        tl = de.strip().lower()
        w.ja = True if tl.startswith(JA_TEXTE) else False if tl.startswith(NEIN_TEXTE) else None
    elif f.typ == K.SCHNITTSTELLE:
        w.if_status, w.if_code = _schnittstelle(de)
        w.de = w.en = ""
    return w


def altbestand_importieren(app, pfad: Path, einzeln: bool = True) -> tuple[Datensatz | None, str]:
    """Altes EPS-Datenblatt (d…pdf, optional mit e…pdf daneben) in einen Entwurf übernehmen."""
    kat = app.kat
    app.configure(cursor="watch"); app.update()
    try:
        haupt = eps_altbestand.lesen(pfad, kat)
        partner_pfad = eps_altbestand.partner_datei(pfad)
        partner = eps_altbestand.lesen(partner_pfad, kat) if partner_pfad else None
    except Exception as e:
        app.configure(cursor="")
        if einzeln:
            messagebox.showerror("Import", f"Das EPS-Datenblatt konnte nicht gelesen werden:\n{e}")
        return None, f"nicht lesbar ({e})"
    app.configure(cursor="")
    if partner and partner.sprache == haupt.sprache:
        partner = None
    de_ab, en_ab = (haupt, partner) if haupt.sprache == "de" else (partner, haupt)
    de_pfad = pfad if haupt.sprache == "de" else partner_pfad
    nur_en = de_ab is None
    if nur_en:                                   # nur das englische Blatt vorhanden
        de_ab, en_ab, de_pfad = haupt, None, pfad

    ds = Datensatz()
    ordner = app.ablage.ordner(ds.id)
    shutil.copy2(de_pfad, ordner / QUELLE)
    ds.quelle_pdf = de_pfad.name
    ds.regel = REGEL_EPS

    def text_paar(de_text: str, en_text: str | None, fid: str = "") -> tuple[str, str, str]:
        """(de, en, teiluebersetzt) – EN aus dem englischen Blatt, sonst Wörterbuch/Formulierungen."""
        if nur_en:
            en = de_text
            de = kat.uebersetze_rueck(en)
            if de is None:
                de = en if fid == "beschreibung" else kat.teilweise(en, "de")
                return (de, en, "de" if de != en else "")
            return de, en, ""
        if en_text:
            return de_text, en_text, ""
        en = kat.uebersetze(de_text)
        if en is None:
            en = de_text if fid == "beschreibung" else kat.teilweise(de_text, "en")
            return de_text, en, "en" if en != de_text else ""
        return de_text, en, ""

    for fid, (de_text, seite, box) in de_ab.werte.items():
        if not kat.hat(fid):
            continue
        en_text = en_ab.werte.get(fid, ("",))[0] if en_ab else ""
        de, en, teil = text_paar(de_text, en_text, fid)
        fs = f"{seite}|{box[0]:.1f}|{box[1]:.1f}|{box[2]:.1f}|{box[3]:.1f}|{kat.feld(fid).de}" if box and not nur_en else ""
        w = _wert_altbestand(kat.feld(fid), kat, de, en, fs)
        if teil and (w.de or w.en):
            w.teiluebersetzt = teil
        ds.werte[fid] = w

    for fid, wert_de, wert_en in (("serie", de_ab.serie, en_ab.serie if en_ab else ""),
                                  ("typbezeichnung", de_ab.typbezeichnung, de_ab.typbezeichnung),
                                  ("produkttyp", de_ab.produkttyp, en_ab.produkttyp if en_ab else "")):
        if wert_de:
            de, en, teil = text_paar(wert_de, wert_en, fid)
            ds.werte[fid] = Wert(de=de, en=en, herkunft=HERKUNFT_PDF, teiluebersetzt=teil, en_manuell=bool(wert_en))
    if de_ab.beschreibung:
        de, en, _ = text_paar(de_ab.beschreibung, en_ab.beschreibung if en_ab else "", "beschreibung")
        ds.werte["beschreibung"] = Wert(de=de, en=en if (en_ab or nur_en) else "", herkunft=HERKUNFT_PDF)

    en_liefer = en_ab.lieferumfang if en_ab and len(en_ab.lieferumfang) == len(de_ab.lieferumfang) else []
    for i, t in enumerate(de_ab.lieferumfang):
        de, en, _ = text_paar(t, en_liefer[i] if en_liefer else "")
        ds.lieferumfang.append(Eintrag(de=de, en=en))
    en_opt = {nr: txt for nr, _, txt in (en_ab.optionen if en_ab else [])}
    for nr, code, txt in de_ab.optionen:
        de, en, _ = text_paar(txt, en_opt.get(nr, ""))
        ds.optionen.append(Option(nr=nr, code=code, de=de, en=en))

    # Netzanschluss → Eingangsspannung (EPS nennt die Eingangsspannung „Netzanschluss“)
    if "netzanschluss" in ds.werte and "eingangsspannung" not in ds.werte and kat.hat("eingangsspannung"):
        n = ds.werte["netzanschluss"]
        ds.werte["eingangsspannung"] = _wert_altbestand(kat.feld("eingangsspannung"), kat, n.de, n.en, n.fundstelle)
    if kat.hat("herkunft"):
        ds.werte["herkunft"] = Wert(auswahl=["Altbestand"], herkunft=HERKUNFT_PDF)
    try:
        ds.bilder = [Bild(datei=d) for d in auslesen.bilder_extrahieren(de_pfad, ordner)]
    except Exception:
        ds.bilder = []
    try:
        import pdfplumber
        with pdfplumber.open(str(de_pfad)) as pdf:
            text = " ".join((p.extract_text() or "") for p in pdf.pages)
        gt = geraetetyp_vorschlag(text, kat)
        if gt and "geraetetyp" not in ds.werte:
            ds.werte["geraetetyp"] = Wert(auswahl=gt, herkunft=HERKUNFT_PDF)
    except Exception:
        pass

    ds.import_werte = {fid: asdict(w) for fid, w in ds.werte.items()}
    n = sum(1 for w in ds.werte.values() if w.herkunft == HERKUNFT_PDF)
    en_pfad = (partner_pfad if haupt.sprache == "de" else pfad) if en_ab else None
    quellen = de_pfad.name + (f" + {en_pfad.name}" if en_pfad else "")
    protokoll.eintragen(ds, app.einst, "Importiert", [["Quelle (EPS-Altbestand)", "", quellen],
                                                      ["Werte aus dem PDF", "", str(n)]])
    app.ablage.speichern(ds)
    hinweise = []
    if en_ab:
        hinweise.append(f"englische Texte aus {en_pfad.name}")
    elif nur_en:
        hinweise.append("nur englisches Blatt – Deutsch vorübersetzt (gelb)")
    else:
        hinweise.append("kein englisches Blatt (e…pdf) daneben gefunden – Englisch vorübersetzt (gelb)")
    dopp = app.ablage.finde_bestellnummer(ds.bestellnummer, ausser_id=ds.id) if ds.bestellnummer else None
    if dopp:
        hinweise.append(f"ACHTUNG: Bestellnummer {ds.bestellnummer} gibt es schon ({dopp.titel or 'ohne Namen'}, {dopp.status})")
    kurz = f"EPS-Altbestand, {n} Werte, {len(ds.optionen)} Optionen" + "".join(f"; {h}" for h in hinweise)
    if einzeln:
        app.maske_zeigen(ds)
        app.original_zeigen(ordner / QUELLE)
        app.aktuell.hinweis(f"EPS-Datenblatt erkannt (Altbestand): {n} Werte, {len(ds.optionen)} Optionen, "
                            f"{len(ds.lieferumfang)} Lieferumfang-Positionen übernommen. " + " · ".join(hinweise)
                            + ". Hersteller bitte von Hand eintragen.")
    return ds, kurz
