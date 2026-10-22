"""Import eines Hersteller-PDFs: Modellauswahl, Auslesen, Vorbefüllen, Original-Vorschau."""
from __future__ import annotations

import re
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from . import auslesen, regeln
from . import katalog as K
from .modell import Datensatz, Wert, HERKUNFT_PDF, REGEL_HAENDLER, REGEL_EPS

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
                ("tower", "Tower"), ("schrank", "Schrank"), ("cabinet", "Schrank")],
    "anzeige": [("touch", "TFT-Touch-Display"), ("tft", "TFT-Display"), ("lcd", "LCD"), ("led", "LED"), ("none", "ohne Anzeige (nur Fernsteuerung)")],
    "parallelschaltung": [("master", "Master-Slave"), ("nein", "Nein"), ("no", "Nein"), ("ja", "Ja"), ("yes", "Ja"), ("standard", "Ja")],
    "ausgangsfrequenz": [("400", "400 Hz"), ("50/60", "50/60 Hz"), ("einstell", "einstellbar"), ("adjust", "einstellbar"),
                         ("60 hz", "60 Hz"), ("50 hz", "50 Hz"), ("dc", "DC")],
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
        if re.search(r"(?<![a-zäöü])" + re.escape(wort), t) and wert in erlaubt:
            return [wert]
    return []


def datensatz_aus_ergebnis(erg: auslesen.Ergebnis, kat: K.Katalog, ds: Datensatz, modell_label: str = "") -> Datensatz:
    for fid, fund in erg.funde.items():
        if not kat.hat(fid):
            continue
        f = kat.feld(fid)
        txt = fund.text
        if erg.sprache == "en":
            en, de = txt, kat.uebersetze_rueck(txt) or txt
        else:
            de, en = txt, kat.uebersetze(txt) or txt
        w = Wert(de=de, en=en, herkunft=HERKUNFT_PDF, geprueft=False, fundstelle=fund.fundstelle())
        if f.typ in (K.BEREICH, K.ZAHL) and f.einheit:
            w.min, w.max = regeln.parse_bereich(txt, f.einheit)
        elif f.typ in (K.AUSWAHL, K.MEHRFACH):
            w.auswahl = auswahl_vorschlag(f, txt)
        elif f.typ == K.JA_NEIN:
            w.ja = not txt.strip().lower().startswith(NEIN_WOERTER)
        ds.werte[fid] = w
    if modell_label:
        ds.werte["hersteller_typ"] = Wert(de=modell_label, en=modell_label, herkunft=HERKUNFT_PDF)
        ds.modell_auswahl = modell_label
    return ds


# ------------------------------------------------------------------------ Modellauswahl

class ModellDialog(tk.Toplevel):
    def __init__(self, master, modelle: list[auslesen.Modellspalte]):
        super().__init__(master)
        self.title("Modell auswählen")
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
    if not pfad:
        return
    pfad = Path(pfad)
    app.configure(cursor="watch"); app.update()
    try:
        erg, zeilen, _ = auslesen.analysieren(pfad, app.kat)
    except Exception as e:
        app.configure(cursor="")
        messagebox.showerror("Import", f"Das PDF konnte nicht gelesen werden:\n{e}")
        return
    app.configure(cursor="")
    ds = Datensatz()
    ordner = app.ablage.ordner(ds.id)
    shutil.copy2(pfad, ordner / QUELLE)
    ds.quelle_pdf = pfad.name

    text = " ".join(s.text for z in zeilen for s in z.stuecke)
    hersteller = hersteller_erkennen(pfad, text, app.einst.hersteller)
    if hersteller:
        ds.werte["hersteller"] = Wert(de=hersteller, en=hersteller, herkunft=HERKUNFT_PDF)

    if not erg.hat_text:
        messagebox.showinfo("Import", "In diesem PDF wurde kein Text gefunden (z. B. eingescanntes Bild).\n\n"
                                      "Es wird ein leeres Datenblatt geöffnet – bitte die Werte von Hand eintragen. "
                                      "Das Original wird daneben angezeigt.")
    else:
        modell = None
        if erg.modelle:
            d = ModellDialog(app, erg.modelle)
            if d.ergebnis is None:
                app.ablage.loeschen(ds.id)
                return
            modell = d.ergebnis or None
        app.configure(cursor="watch"); app.update()
        erg = auslesen.auslesen(pfad, app.kat, modell)
        app.configure(cursor="")
        datensatz_aus_ergebnis(erg, app.kat, ds, modell.label if modell else "")

    haendler = app.einst.ist_haendlerware(hersteller)
    ds.regel = REGEL_HAENDLER if haendler else REGEL_EPS
    typ = ds.text("hersteller_typ")
    if typ:
        name = regeln.eps_name(typ, haendlerware=haendler)
        ds.werte["typbezeichnung"] = Wert(de=name, en=name, herkunft=HERKUNFT_PDF)
    app.ablage.speichern(ds)
    n = sum(1 for w in ds.werte.values() if w.herkunft == HERKUNFT_PDF)
    app.maske_zeigen(ds)
    app.original_zeigen(ordner / QUELLE)
    app.aktuell.hinweis(f"{n} Werte aus dem PDF übernommen (Sprache: {'Deutsch' if erg.sprache == 'de' else 'Englisch'}). "
                        "Alle Werte sind Vorschläge – bitte prüfen. Feld anklicken zeigt die Fundstelle.")
