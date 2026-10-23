"""Bedienoberfläche (Tkinter): Startseite, Prüfmaske, Einstellungen."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from . import __version__, katalog as K, regeln, pdf_export, einstellungen as E, pfade, darstellung
from .ablage import LokaleAblage
from .modell import Datensatz, Wert, Option, Eintrag, Bild, ENTWURF, FREIGEGEBEN, REGEL_EPS, REGEL_HAENDLER, jetzt

NAVY = "#35528C"
CYAN = "#52B4D7"
KERN_BG = "#E3F1F8"
WARN_BG = "#FFF2B3"
OK_FG = "#1F7A3A"
ERR_FG = "#B3261E"

JN_WERTE = ["", "Ja", "Nein"]


def oeffnen(pfad: Path):
    """Datei oder Ordner mit dem Standardprogramm öffnen."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(pfad))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(pfad)])
        else:
            subprocess.Popen(["xdg-open", str(pfad)])
    except OSError as e:
        messagebox.showerror("Öffnen fehlgeschlagen", str(e))


# ======================================================================== Hilfs-Widgets

AUTOSAVE_MS = 2 * 60 * 1000          # automatisch speichern alle 2 Minuten (nur wenn sich etwas geändert hat)


class Scrollbereich(ttk.Frame):
    """Rahmen mit senkrechter Bildlaufleiste; Inhalte kommen in self.inhalt."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, background="white")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inhalt = tk.Frame(self.canvas, background="white")
        self.inhalt.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inhalt, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.inhalt.bind("<Enter>", lambda e: self._binden(True))
        self.inhalt.bind("<Leave>", lambda e: self._binden(False))

    def _binden(self, an):
        if an:
            self.canvas.bind_all("<MouseWheel>", self._rad)
            self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
            self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))
        else:
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")

    def _rad(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units")


class Eingabe(tk.Entry):
    def __init__(self, master, breite=30, **kw):
        super().__init__(master, width=breite, relief="solid", borderwidth=1, highlightthickness=0, **kw)


def _fmt(z: float | None) -> str:
    if z is None:
        return ""
    s = f"{z:.6g}"
    return s.replace(".", ",")


def _zahl(s: str) -> float | None:
    s = (s or "").strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ======================================================================== Feld-Editoren

class FeldEditor:
    """Eine Zeile der Prüfmaske für ein Feld aus dem Katalog."""

    def __init__(self, maske: "Maske", parent: tk.Frame, zeile: int, feld: K.Feld):
        self.m = maske
        self.f = feld
        self.kat = maske.app.kat
        bg = KERN_BG if feld.kern else "white"
        self.bg = bg
        self.geprueft = tk.BooleanVar(value=False)
        self.en_manuell = False
        self._lade = False

        txt = feld.de + (" *" if feld.pflicht else "")
        lab = tk.Label(parent, text=txt, anchor="w", background=bg,
                       font=("Segoe UI", 9, "bold" if feld.kern else "normal"))
        lab.grid(row=zeile, column=0, sticky="nwe", padx=(6, 4), pady=2)
        if feld.bemerkung:
            lab.bind("<Enter>", lambda e: maske.hinweis(f"{feld.de}: {feld.bemerkung}"))
            lab.bind("<Leave>", lambda e: maske.hinweis(""))
        self.lab = lab
        self.sb = None                                  # Scrollbereich des Reiters (für „hinspringen“)
        self.box = tk.Frame(parent, background=bg, highlightthickness=2, highlightbackground=bg, highlightcolor=bg)
        self.box.grid(row=zeile, column=1, sticky="we", pady=2)
        self.pruef = None
        if feld.kern:
            self.pruef = tk.Checkbutton(parent, text="geprüft", variable=self.geprueft, background=bg,
                                        highlightthickness=2, highlightbackground=bg, highlightcolor=bg,
                                        command=lambda: (self.markieren(None), maske.zaehler_aktualisieren()))
            self.pruef.grid(row=zeile, column=2, sticky="nw", padx=6)
        else:
            tk.Label(parent, text="", background=bg).grid(row=zeile, column=2)
        self.info = tk.Label(parent, text=feld.einheit, anchor="w", background=bg, foreground="#6A7380")
        self.info.grid(row=zeile, column=3, sticky="nw", padx=4)
        self.bauen()
        self._markierung_loesen_binden(self.box)

    # ---- Rote Markierung bei Freigabe-Problemen
    def markieren(self, art: str | None):
        """art = "wert" (Wertefeld rot umrandet), "geprueft" (Prüfhaken rot umrandet) oder None (zurücksetzen)."""
        rot = "#D62828"
        self.box.configure(highlightbackground=rot if art == "wert" else self.bg,
                           highlightcolor=rot if art == "wert" else self.bg)
        if self.pruef is not None:
            self.pruef.configure(highlightbackground=rot if art == "geprueft" else self.bg,
                                 highlightcolor=rot if art == "geprueft" else self.bg)
        self.lab.configure(foreground=rot if art else "black")

    def _markierung_loesen_binden(self, w):
        for ev in ("<KeyRelease>", "<<ComboboxSelected>>", "<ButtonRelease-1>"):
            w.bind(ev, lambda e: self._wert_markierung_loesen(), add="+")
        for c in w.winfo_children():
            self._markierung_loesen_binden(c)

    def _wert_markierung_loesen(self):
        if self.box.cget("highlightbackground") != self.bg:
            self.markieren(None)

    def fokus(self):
        """Zum Feld springen: Reiter wählen, hinscrollen, Cursor ins erste Eingabefeld."""
        if self.sb is not None:
            self.m.nb.select(self.sb)
            self.m.update_idletasks()
            hoehe = max(self.sb.inhalt.winfo_height(), 1)
            self.sb.canvas.yview_moveto(max(0.0, (self.box.winfo_y() - 60) / hoehe))
        ziel = self._erstes_eingabefeld(self.box)
        (ziel or self.box).focus_set()

    def _erstes_eingabefeld(self, w):
        for c in w.winfo_children():
            if isinstance(c, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text)) and str(c.cget("state")) != "disabled":
                return c
            t = self._erstes_eingabefeld(c)
            if t is not None:
                return t
        return None

    # -- Bausteine
    def _de_en(self, breite=34):
        self.de = Eingabe(self.box, breite)
        self.en = Eingabe(self.box, breite)
        self.de.grid(row=0, column=0, sticky="we", padx=(0, 4))
        self.en.grid(row=0, column=1, sticky="we")
        tk.Label(self.box, text="DE", fg="#6A7380", bg=self.bg, font=("Segoe UI", 7)).grid(row=1, column=0, sticky="w")
        tk.Label(self.box, text="EN", fg="#6A7380", bg=self.bg, font=("Segoe UI", 7)).grid(row=1, column=1, sticky="w")
        self.de.bind("<KeyRelease>", lambda e: self._de_geaendert())
        self.en.bind("<KeyRelease>", lambda e: self._en_geaendert())
        for w in (self.de, self.en):
            w.bind("<FocusIn>", lambda e: self.m.fundstelle_zeigen(self.f.id), add="+")

    def _de_geaendert(self):
        if self._lade:
            return
        if not self.en_manuell:
            de = self.de.get()
            ue = self.kat.uebersetze(de)
            self.en.delete(0, "end")
            self.en.insert(0, ue if ue is not None else de)
            # Gelb = Text wurde nur kopiert, nicht übersetzt (bitte prüfen)
            braucht = ue is None and any(len(w) > 3 and w.isalpha() for w in de.replace("-", " ").split())
            self.en.configure(background=WARN_BG if braucht else "white")
        self.nach_aenderung()

    def _en_geaendert(self):
        if self._lade:
            return
        self.en_manuell = True
        self.en.configure(background="white")

    def nach_aenderung(self):
        self.m.geaendert = True

    def bauen(self):
        self._de_en()

    # -- Laden / Speichern
    def laden(self, w: Wert):
        self._lade = True
        self.fundstelle = w.fundstelle
        if w.fundstelle:
            seite = w.fundstelle.split("|")[0]
            self.info.configure(text=f"{self.f.einheit}  PDF S.{seite}".strip(), foreground=NAVY, cursor="hand2")
            self.info.bind("<Button-1>", lambda e: self.m.fundstelle_zeigen(self.f.id))
        self.en_manuell = w.en_manuell
        if hasattr(self, "de"):
            self.de.delete(0, "end"); self.de.insert(0, w.de)
            self.en.delete(0, "end"); self.en.insert(0, w.en)
            if isinstance(self.en, tk.Entry):
                ungeprueft = (not w.en_manuell and w.de and w.en == w.de and self.kat.uebersetze(w.de) is None
                              and self.kat.uebersetze_rueck(w.en) is None
                              and any(len(x) > 3 and x.isalpha() for x in w.de.replace("-", " ").split()))
                self.en.configure(background=WARN_BG if ungeprueft else "white")
        self.geprueft.set(w.geprueft)
        self._lade = False

    def speichern(self, w: Wert):
        if hasattr(self, "de"):
            w.de = self.de.get().strip()
            w.en = self.en.get().strip()
        w.en_manuell = self.en_manuell
        w.geprueft = self.geprueft.get()


class BereichEditor(FeldEditor):
    def bauen(self):
        self._de_en(26)
        sub = tk.Frame(self.box, background=self.bg)
        sub.grid(row=0, column=2, padx=(8, 0))
        tk.Label(sub, text="von", bg=self.bg, fg="#6A7380").pack(side="left")
        self.vmin = Eingabe(sub, 8); self.vmin.pack(side="left", padx=2)
        tk.Label(sub, text="bis", bg=self.bg, fg="#6A7380").pack(side="left")
        self.vmax = Eingabe(sub, 8); self.vmax.pack(side="left", padx=2)
        self.zahlen_manuell = False
        for e in (self.vmin, self.vmax):
            e.bind("<KeyRelease>", lambda ev: setattr(self, "zahlen_manuell", True))

    def nach_aenderung(self):
        super().nach_aenderung()
        if not self.zahlen_manuell and self.f.einheit:
            mn, mx = regeln.parse_bereich(self.de.get(), self.f.einheit)
            for e, v in ((self.vmin, mn), (self.vmax, mx)):
                e.delete(0, "end"); e.insert(0, _fmt(v))
            erkannt = mx is not None or not self.de.get().strip()
            self.vmax.configure(background="white" if erkannt else WARN_BG)

    def laden(self, w):
        super().laden(w)
        self.vmin.delete(0, "end"); self.vmin.insert(0, _fmt(w.min))
        self.vmax.delete(0, "end"); self.vmax.insert(0, _fmt(w.max))
        self.zahlen_manuell = w.min is not None or w.max is not None

    def speichern(self, w):
        super().speichern(w)
        w.min, w.max = _zahl(self.vmin.get()), _zahl(self.vmax.get())


class JaNeinEditor(FeldEditor):
    def bauen(self):
        self.jn = ttk.Combobox(self.box, values=JN_WERTE, width=6, state="readonly")
        self.jn.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.jn.bind("<<ComboboxSelected>>", lambda e: self._jn())
        inner = tk.Frame(self.box, background=self.bg)
        inner.grid(row=0, column=1, sticky="we")
        self.box, alt = inner, self.box
        self._de_en(26)
        self.box = alt
        tk.Label(self.box, text="Zusatztext fürs Datenblatt (optional)", fg="#6A7380", bg=self.bg,
                 font=("Segoe UI", 7)).grid(row=1, column=1, sticky="w")

    def _jn(self):
        self.nach_aenderung()
        if self.f.id == "bidirektional" and self.jn.get() == "Ja":
            self.m.bidirektional_ja()

    def laden(self, w):
        super().laden(w)
        self.jn.set("Ja" if w.ja is True else "Nein" if w.ja is False else "")

    def speichern(self, w):
        super().speichern(w)
        v = self.jn.get()
        w.ja = True if v == "Ja" else False if v == "Nein" else None


class AuswahlEditor(FeldEditor):
    def bauen(self):
        werte = [""] + [de for de, _ in self.f.auswahl]
        self.cb = ttk.Combobox(self.box, values=werte, width=24, state="readonly")
        self.cb.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.cb.bind("<<ComboboxSelected>>", lambda e: self.nach_aenderung())
        inner = tk.Frame(self.box, background=self.bg)
        inner.grid(row=0, column=1, sticky="we")
        self.box, alt = inner, self.box
        self._de_en(22)
        self.box = alt
        tk.Label(self.box, text="Text fürs Datenblatt (leer = Auswahlwert)", fg="#6A7380", bg=self.bg,
                 font=("Segoe UI", 7)).grid(row=1, column=1, sticky="w")

    def laden(self, w):
        super().laden(w)
        self.cb.set(w.auswahl[0] if w.auswahl else "")

    def speichern(self, w):
        super().speichern(w)
        v = self.cb.get()
        w.auswahl = [v] if v else []


class MehrfachEditor(FeldEditor):
    def bauen(self):
        self.vars = {}
        for i, (de, _) in enumerate(self.f.auswahl):
            v = tk.BooleanVar()
            tk.Checkbutton(self.box, text=de, variable=v, bg=self.bg, command=self.nach_aenderung).grid(
                row=i // 4, column=i % 4, sticky="w", padx=(0, 10))
            self.vars[de] = v
        if not self.f.auswahl:
            tk.Label(self.box, text="(keine Auswahlwerte im Katalog)", bg=self.bg, fg="#6A7380").grid(row=0, column=0)

    def laden(self, w):
        super().laden(w)
        for de, v in self.vars.items():
            v.set(de in w.auswahl)

    def speichern(self, w):
        super().speichern(w)
        w.auswahl = [de for de, v in self.vars.items() if v.get()]

    def setzen(self, de, an=True):
        if de in self.vars:
            self.vars[de].set(an)


class SchnittstelleEditor(FeldEditor):
    def bauen(self):
        self.st = ttk.Combobox(self.box, values=["", "Standard", "Option"], width=10, state="readonly")
        self.st.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.st.bind("<<ComboboxSelected>>", lambda e: self.nach_aenderung())
        tk.Label(self.box, text="Optionscode:", bg=self.bg, fg="#6A7380").grid(row=0, column=1)
        self.code = Eingabe(self.box, 24)
        self.code.grid(row=0, column=2, sticky="w", padx=4)

    def laden(self, w):
        super().laden(w)
        self.st.set(w.if_status)
        self.code.delete(0, "end"); self.code.insert(0, w.if_code)

    def speichern(self, w):
        super().speichern(w)
        w.if_status = self.st.get()
        w.if_code = self.code.get().strip()


class AbgeleitetEditor(FeldEditor):
    """Feld, das automatisch gebildet wird (z. B. Schnittstellen-Filter)."""

    def bauen(self):
        self.lbl = tk.Label(self.box, text="", bg=self.bg, anchor="w", justify="left", wraplength=520)
        self.lbl.grid(row=0, column=0, sticky="w")

    def aktualisieren(self, ds):
        self.lbl.configure(text=darstellung.text(ds, self.f, self.kat, "de") or "(noch keine Schnittstelle eingetragen)")


class HerstellerEditor(FeldEditor):
    def bauen(self):
        self.de = ttk.Combobox(self.box, values=self.m.app.einst.hersteller, width=40)
        self.de.grid(row=0, column=0, sticky="w")
        self.en = Eingabe(self.box, 1)          # unsichtbar, Hersteller ist sprachneutral
        self.de.bind("<<ComboboxSelected>>", lambda e: (self.nach_aenderung(), self.m.regel_pruefen()))

    def speichern(self, w):
        super().speichern(w)
        w.en = w.de


class TypbezeichnungEditor(FeldEditor):
    def bauen(self):
        self._de_en(28)
        ttk.Button(self.box, text="EPS-Name aus Hersteller-Typ", command=self.m.eps_name_setzen).grid(row=0, column=2, padx=6)


EDITOREN = {K.TEXT: FeldEditor, K.ZAHL: BereichEditor, K.BEREICH: BereichEditor, K.JA_NEIN: JaNeinEditor,
            K.AUSWAHL: AuswahlEditor, K.MEHRFACH: MehrfachEditor, K.SCHNITTSTELLE: SchnittstelleEditor}


# ======================================================================== Listen (Optionen, Lieferumfang, Bilder)

class ListenEditor(ttk.Frame):
    def __init__(self, master, spalten: list[tuple[str, str, int]], uebersetzen=None):
        super().__init__(master)
        self.spalten = spalten
        self.uebersetzen = uebersetzen
        self.tv = ttk.Treeview(self, columns=[s[0] for s in spalten], show="headings", height=7)
        for key, titel, breite in spalten:
            self.tv.heading(key, text=titel)
            self.tv.column(key, width=breite, stretch=True)
        self.tv.grid(row=0, column=0, sticky="nsew")
        self.tv.bind("<Double-1>", lambda e: self.bearbeiten())
        btn = ttk.Frame(self)
        btn.grid(row=0, column=1, sticky="n", padx=6)
        for t, c in (("Hinzufügen", self.hinzufuegen), ("Bearbeiten", self.bearbeiten), ("Entfernen", self.entfernen),
                     ("Nach oben", lambda: self.verschieben(-1)), ("Nach unten", lambda: self.verschieben(1))):
            ttk.Button(btn, text=t, command=c, width=11).pack(fill="x", pady=1)
        self.columnconfigure(0, weight=1)

    def werte(self) -> list[list[str]]:
        return [list(self.tv.item(i, "values")) for i in self.tv.get_children()]

    def setzen(self, zeilen):
        self.tv.delete(*self.tv.get_children())
        for z in zeilen:
            self.tv.insert("", "end", values=z)

    def _dialog(self, vorgabe=None):
        d = tk.Toplevel(self)
        d.title("Eintrag")
        d.transient(self.winfo_toplevel())
        d.grab_set()
        felder = []
        for i, (key, titel, _) in enumerate(self.spalten):
            ttk.Label(d, text=titel).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            e = Eingabe(d, 60)
            e.grid(row=i, column=1, padx=8, pady=4)
            if vorgabe:
                e.insert(0, vorgabe[i])
            felder.append(e)
        if self.uebersetzen:
            de_i, en_i = self.uebersetzen

            def auto(_e=None):
                if not felder[en_i].get() or felder[en_i].get() == getattr(auto, "zuletzt", None):
                    ue = self.winfo_toplevel().kat.uebersetze(felder[de_i].get())
                    neu = ue if ue is not None else felder[de_i].get()
                    felder[en_i].delete(0, "end"); felder[en_i].insert(0, neu)
                    auto.zuletzt = neu
            felder[de_i].bind("<KeyRelease>", auto)
        erg = {}

        def ok():
            erg["v"] = [e.get().strip() for e in felder]
            d.destroy()
        ttk.Button(d, text="OK", command=ok).grid(row=len(self.spalten), column=1, sticky="e", padx=8, pady=8)
        felder[0].focus_set()
        d.bind("<Return>", lambda e: ok())
        d.wait_window()
        return erg.get("v")

    def hinzufuegen(self):
        v = self._dialog()
        if v and any(v):
            self.tv.insert("", "end", values=v)
            self.event_generate("<<Geaendert>>")

    def bearbeiten(self):
        sel = self.tv.selection()
        if not sel:
            return
        v = self._dialog(list(self.tv.item(sel[0], "values")))
        if v:
            self.tv.item(sel[0], values=v)
            self.event_generate("<<Geaendert>>")

    def entfernen(self):
        for s in self.tv.selection():
            self.tv.delete(s)
        self.event_generate("<<Geaendert>>")

    def verschieben(self, d):
        sel = self.tv.selection()
        if sel:
            i = self.tv.index(sel[0])
            self.tv.move(sel[0], "", max(0, i + d))


# ======================================================================== Prüfmaske

class Maske(ttk.Frame):
    TABS = [("Kopfdaten & Kernfelder", None), ("Allgemeine Daten", K.ALLG), ("Schnittstellen", K.SCHN),
            ("Technische Daten", K.TECH), ("Optionen & Lieferumfang", "listen"), ("Beschreibung & Bilder", "text"),
            ("Intern", K.INTERN)]

    def __init__(self, app: "App", ds: Datensatz):
        super().__init__(app)
        self.app = app
        self.ds = ds
        self.geaendert = False
        self.editoren: dict[str, FeldEditor] = {}
        self._kopf()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        for titel, art in self.TABS:
            if art == "listen":
                self._tab_listen(titel)
            elif art == "text":
                self._tab_text(titel)
            else:
                self._tab_felder(titel, art)
        self.statuszeile = tk.Label(self, text="", anchor="w", fg="#6A7380")
        self.statuszeile.pack(fill="x", padx=10, pady=(0, 6))
        self.laden()
        self.uebernehmen()                      # Maske → Datensatz einmal angleichen, sonst meldet „ungespeichert“ falsch
        self.geaendert = False
        self._schnappschuss = self._stand()
        self._auto_id = self.after(AUTOSAVE_MS, self._autosave)

    # ---- Aufbau
    def _kopf(self):
        k = tk.Frame(self, background=NAVY)
        k.pack(fill="x")
        ttk.Button(k, text="← Zurück", command=self.zurueck).pack(side="left", padx=8, pady=8)
        tf = tk.Frame(k, background=NAVY)      # Titel + Status; wird zuletzt gepackt und bei Platzmangel gekürzt
        self.titel = tk.Label(tf, text="", fg="white", bg=NAVY, font=("Segoe UI", 13, "bold"), anchor="w", width=1)
        self.statuslabel = tk.Label(tf, text="", fg=CYAN, bg=NAVY, font=("Segoe UI", 10, "bold"))
        self.statuslabel.grid(row=0, column=0, padx=(10, 6), sticky="w")
        self.titel.grid(row=0, column=1, sticky="ew")
        tf.columnconfigure(1, weight=1)
        self.btn_frei = ttk.Button(k, text="Freigeben ✔", command=self.freigeben)
        self.btn_frei.pack(side="right", padx=8)
        ttk.Button(k, text="Vorschau EN", command=lambda: self.vorschau("en")).pack(side="right", padx=2)
        ttk.Button(k, text="Vorschau DE", command=lambda: self.vorschau("de")).pack(side="right", padx=2)
        ttk.Button(k, text="Speichern (Strg+S)", command=self.zwischenspeichern).pack(side="right", padx=8)
        if self.ds.quelle_pdf:
            ttk.Button(k, text="Original", command=self.original).pack(side="right", padx=2)
        self.btn_alle = ttk.Button(k, text="Alle geprüft ☑", command=self.alle_geprueft)
        self.btn_alle.pack(side="right", padx=2)
        self.zaehler = tk.Label(k, text="", fg="white", bg=NAVY)
        self.zaehler.pack(side="right", padx=10)
        # Titel zuletzt packen: bei schmalem Fenster wird der Titel gekürzt, nicht Zähler/Knöpfe
        tf.pack(side="left", fill="x", expand=True)

    def _tabellenkopf(self, inhalt):
        for i, t in enumerate(["Feld", "Wert  (Deutsch | Englisch)", "Kernfeld", "Einheit"]):
            tk.Label(inhalt, text=t, bg="white", fg=NAVY, font=("Segoe UI", 9, "bold"), anchor="w").grid(
                row=0, column=i, sticky="w", padx=6, pady=(6, 4))
        inhalt.columnconfigure(1, weight=1)

    def _tab_felder(self, titel, abschnitt):
        sb = Scrollbereich(self.nb)
        self.nb.add(sb, text=titel)
        inh = sb.inhalt
        self._tabellenkopf(inh)
        kat = self.app.kat
        if abschnitt is None:
            felder = kat.abschnitt(K.KOPF) + [f for f in kat.kernfelder if f.abschnitt != K.KOPF and f.typ != K.LISTE]
        else:
            felder = [f for f in kat.abschnitt(abschnitt) if not f.kern]
        for z, f in enumerate(felder, start=1):
            if f.id == "beschreibung":
                continue
            if f.id == "schnittstellen":
                cls = AbgeleitetEditor
            elif f.id == "typbezeichnung":
                cls = TypbezeichnungEditor
            elif f.id == "hersteller":
                cls = HerstellerEditor
            else:
                cls = EDITOREN.get(f.typ, FeldEditor)
            self.editoren[f.id] = cls(self, inh, z, f)
            self.editoren[f.id].sb = sb
        if abschnitt == K.INTERN:
            self._intern_extras(inh, len(felder) + 1)

    def _intern_extras(self, inh, z):
        ed = self.editoren.get("hersteller")
        if ed:
            ed.de.bind("<FocusOut>", lambda e: self.regel_pruefen(), add="+")
        ed = self.editoren.get("hersteller_bestellnummer")
        if ed:
            ed.de.bind("<FocusOut>", lambda e: self.doppelte_pruefen(), add="+")

    def _tab_listen(self, titel):
        fr = ttk.Frame(self.nb, padding=10)
        self.nb.add(fr, text=titel)
        kopf = ttk.Frame(fr)
        kopf.pack(fill="x")
        ttk.Label(kopf, text="Optionen", font=("Segoe UI", 11, "bold"), foreground=NAVY).pack(side="left")
        self.opt_geprueft = tk.BooleanVar()
        self.opt_tab = fr
        self.opt_check = tk.Checkbutton(kopf, text="Kernfeld „Optionen“ geprüft", variable=self.opt_geprueft, bg=KERN_BG,
                                        highlightthickness=2, highlightbackground=KERN_BG, highlightcolor=KERN_BG,
                                        command=lambda: (self._opt_markieren(False), self.zaehler_aktualisieren()))
        self.opt_check.pack(side="left", padx=12)
        ttk.Label(fr, text="Optionsnummer bleibt leer, bis die einheitliche Stammliste in Weclapp existiert.",
                  foreground="#6A7380").pack(anchor="w")
        self.optionen = ListenEditor(fr, [("nr", "Opt.-Nr.", 70), ("code", "EPS-Code", 160),
                                          ("de", "Beschreibung DE", 300), ("en", "Beschreibung EN", 300)],
                                     uebersetzen=(2, 3))
        self.optionen.pack(fill="x", pady=(4, 14))
        ttk.Label(fr, text="Lieferumfang", font=("Segoe UI", 11, "bold"), foreground=NAVY).pack(anchor="w")
        self.lieferumfang = ListenEditor(fr, [("de", "Deutsch", 380), ("en", "Englisch", 380)], uebersetzen=(0, 1))
        self.lieferumfang.pack(fill="x", pady=4)

    def _tab_text(self, titel):
        fr = ttk.Frame(self.nb, padding=10)
        self.nb.add(fr, text=titel)
        ttk.Label(fr, text="Beschreibung (Absätze durch Leerzeile trennen)", font=("Segoe UI", 11, "bold"),
                  foreground=NAVY).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(fr, text="Deutsch").grid(row=1, column=0, sticky="w")
        ttk.Label(fr, text="Englisch").grid(row=1, column=1, sticky="w")
        self.besch_de = tk.Text(fr, height=12, wrap="word", relief="solid", borderwidth=1)
        self.besch_en = tk.Text(fr, height=12, wrap="word", relief="solid", borderwidth=1)
        self.besch_de.grid(row=2, column=0, sticky="nsew", padx=(0, 6))
        self.besch_en.grid(row=2, column=1, sticky="nsew")
        ttk.Label(fr, text="Herstellernamen und Herstellertexte (z. B. „our plant“) gehören nicht in die Beschreibung.",
                  foreground=ERR_FG).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 10))
        ttk.Label(fr, text="Produktbilder (das erste Bild steht auf Seite 1)", font=("Segoe UI", 11, "bold"),
                  foreground=NAVY).grid(row=4, column=0, columnspan=2, sticky="w")
        self.bilder = ListenEditor(fr, [("datei", "Datei", 220), ("de", "Bildunterschrift DE", 260),
                                        ("en", "Bildunterschrift EN", 260)], uebersetzen=(1, 2))
        self.bilder.grid(row=5, column=0, columnspan=2, sticky="we")
        ttk.Button(fr, text="Bild aus Datei hinzufügen …", command=self.bild_hinzufuegen).grid(row=6, column=0, sticky="w", pady=4)
        fr.columnconfigure(0, weight=1); fr.columnconfigure(1, weight=1); fr.rowconfigure(2, weight=1)

    # ---- Aktionen
    def original(self):
        p = self.app.ablage.ordner(self.ds.id) / "quelle.pdf"
        if p.exists():
            self.app.original_zeigen(p)

    def fundstelle_zeigen(self, fid):
        ed = self.editoren.get(fid)
        fs = getattr(ed, "fundstelle", "") if ed else ""
        v = self.app.viewer
        if fs and v is not None and v.winfo_exists():
            v.zeige(fs, ed.f.de)

    def hinweis(self, text):
        self.statuszeile.configure(text=text, fg="#6A7380")

    def zaehler_aktualisieren(self):
        kern = [e for e in self.editoren.values() if e.f.kern]
        n = sum(1 for e in kern if e.geprueft.get()) + (1 if self.opt_geprueft.get() else 0)
        gesamt = len(kern) + 1
        self.zaehler.configure(text=f"Geprüft: {n}/{gesamt}", fg="white" if n < gesamt else "#9BE29B")
        if hasattr(self, "btn_alle"):
            self.btn_alle.configure(text="Haken entfernen ☐" if n == gesamt else "Alle geprüft ☑")

    def _opt_markieren(self, an: bool):
        f = "#D62828" if an else KERN_BG
        self.opt_check.configure(highlightbackground=f, highlightcolor=f, fg="#D62828" if an else "black")

    def probleme_markieren(self, felder: list[tuple[str, str, str]]):
        """Alle Problemfelder rot umranden und zum ersten springen (Reihenfolge der Reiter)."""
        for e in self.editoren.values():
            e.markieren(None)
        self._opt_markieren(False)
        art_je_feld: dict[str, str] = {}
        for fid, art, _ in felder:
            if art_je_feld.get(fid) != "wert":          # fehlender Wert ist wichtiger als fehlender Haken
                art_je_feld[fid] = art
        for fid, art in art_je_feld.items():
            if fid == "optionen":
                self._opt_markieren(True)
            elif fid in self.editoren:
                self.editoren[fid].markieren(art)
        reihenfolge = list(self.editoren)               # Editoren wurden in Reiter-Reihenfolge angelegt
        erste = sorted((reihenfolge.index(f) for f in art_je_feld if f in self.editoren))
        if erste:
            self.editoren[reihenfolge[erste[0]]].fokus()
        elif "optionen" in art_je_feld:
            self.nb.select(self.opt_tab)
        self.statuszeile.configure(text=f"{len(art_je_feld)} Feld(er) rot markiert – Cursor steht im ersten.",
                                   fg="#D62828")

    def spuren_markieren(self, spuren: list[tuple[str, str, str]]):
        """Herstellerspuren rot hervorheben (Felder umranden, Fundstellen in der Beschreibung einfärben)."""
        for t in (self.besch_de, self.besch_en):
            t.tag_remove("spur", "1.0", "end")
            t.tag_configure("spur", background="#F8C6C6", foreground="#D62828")
            t.configure(highlightthickness=2 if spuren else 0, highlightbackground="#D62828", highlightcolor="#D62828")
        if not spuren:
            return
        felder = [(fid, "wert", "") for fid, _, _ in spuren if fid in self.editoren]
        if felder:
            self.probleme_markieren(felder)
        for fid, fund, _ in spuren:
            if fid != "beschreibung":
                continue
            for t in (self.besch_de, self.besch_en):
                pos = "1.0"
                while True:
                    pos = t.search(fund, pos, stopindex="end", nocase=True)
                    if not pos:
                        break
                    ende = f"{pos}+{len(fund)}c"
                    t.tag_add("spur", pos, ende)
                    pos = ende
        if not felder and any(fid in ("beschreibung", "bilder") for fid, _, _ in spuren):
            self.nb.select(self.besch_de.master)
            ziel = self.besch_en if self.besch_en.tag_ranges("spur") and not self.besch_de.tag_ranges("spur") else self.besch_de
            r = ziel.tag_ranges("spur")
            if r:
                ziel.see(r[0])
        elif not felder and any(fid in ("optionen", "lieferumfang") for fid, _, _ in spuren):
            self.nb.select(self.opt_tab)
        self.statuszeile.configure(text=f"{len(spuren)} mögliche Herstellerspur(en) rot markiert.", fg="#D62828")

    def alle_geprueft(self):
        """Setzt alle Prüfhaken der Kernfelder auf einmal – oder entfernt sie, wenn schon alle gesetzt sind."""
        kern = [e for e in self.editoren.values() if e.f.kern]
        alle = all(e.geprueft.get() for e in kern) and self.opt_geprueft.get()
        if not alle and not messagebox.askyesno(
                "Alle Kernfelder geprüft?",
                "Damit werden alle Kernfelder als geprüft markiert.\n\n"
                "Hast du die Werte mit dem Original-Datenblatt verglichen?", parent=self):
            return
        for e in kern:
            e.geprueft.set(not alle)
            if e.pruef is not None and e.pruef.cget("highlightbackground") != e.bg:
                e.markieren(None)
        self.opt_geprueft.set(not alle)
        self._opt_markieren(False)
        self.geaendert = True
        self.zaehler_aktualisieren()

    def eps_name_setzen(self):
        ed_typ = self.editoren["typbezeichnung"]
        orig = self.editoren["hersteller_typ"].de.get().strip() if "hersteller_typ" in self.editoren else ""
        if not orig:
            messagebox.showinfo("EPS-Name", "Bitte zuerst im Reiter „Intern“ die Hersteller-Typbezeichnung eintragen.")
            return
        hw = self.app.einst.ist_haendlerware(self.editoren["hersteller"].de.get()) if "hersteller" in self.editoren else False
        name = regeln.eps_name(orig, haendlerware=hw)
        ed_typ.de.delete(0, "end"); ed_typ.de.insert(0, name)
        ed_typ.en.delete(0, "end"); ed_typ.en.insert(0, name)
        self.geaendert = True

    def bidirektional_ja(self):
        ed = self.editoren.get("geraetetyp")
        if isinstance(ed, MehrfachEditor):
            ed.setzen(regeln.ELEKTRONISCHE_LAST, True)
            self.hinweis("Bidirektional → Gerätetyp „Elektronische Last“ zusätzlich angehakt (abwählbar).")

    def regel_pruefen(self):
        h = self.editoren["hersteller"].de.get() if "hersteller" in self.editoren else ""
        neu = REGEL_HAENDLER if self.app.einst.ist_haendlerware(h) else REGEL_EPS
        if neu != self.ds.regel:
            self.ds.regel = neu
            self.hinweis(f"Regel: {neu}")
        self._statuslabel()

    def doppelte_pruefen(self):
        nr = self.editoren["hersteller_bestellnummer"].de.get()
        tr = self.app.ablage.finde_hersteller_nr(nr, ausser_id=self.ds.id)
        if tr:
            messagebox.showwarning("Bereits vorhanden",
                                   f"Die Hersteller-Bestellnummer „{nr}“ gibt es schon:\n"
                                   f"{tr.titel or '(ohne Namen)'} – Bestellnummer {tr.bestellnummer or '–'} ({tr.status}).")

    def bild_hinzufuegen(self):
        pfad = filedialog.askopenfilename(title="Bild wählen", filetypes=[("Bilder", "*.jpg *.jpeg *.png"), ("Alle", "*.*")])
        if not pfad:
            return
        ordner = self.app.ablage.ordner(self.ds.id)
        ziel = ordner / Path(pfad).name
        if ziel.resolve() != Path(pfad).resolve():
            shutil.copy2(pfad, ziel)
        self.bilder.tv.insert("", "end", values=[ziel.name, "", ""])
        self.geaendert = True

    # ---- Laden / Speichern
    def _statuslabel(self):
        t = self.ds.titel or "Neues Datenblatt"
        self.titel.configure(text=t + (f"  ·  {self.ds.bestellnummer}" if self.ds.bestellnummer else ""))
        regel = "  ·  Händlerware" if self.ds.regel == REGEL_HAENDLER else ""
        self.statuslabel.configure(text=self.ds.status + regel)
        self.btn_frei.configure(text="Änderungen freigeben ✔" if self.ds.status == FREIGEGEBEN else "Freigeben ✔")

    def laden(self):
        ds = self.ds
        for fid, ed in self.editoren.items():
            ed.laden(ds.werte.get(fid, Wert()))
        self.opt_geprueft.set(bool(ds.werte.get("optionen") and ds.werte["optionen"].geprueft))
        self.optionen.setzen([[o.nr, o.code, o.de, o.en] for o in ds.optionen])
        self.lieferumfang.setzen([[e.de, e.en] for e in ds.lieferumfang])
        self.bilder.setzen([[b.datei, b.de, b.en] for b in ds.bilder])
        b = ds.werte.get("beschreibung", Wert())
        self.besch_de.delete("1.0", "end"); self.besch_de.insert("1.0", b.de)
        self.besch_en.delete("1.0", "end"); self.besch_en.insert("1.0", b.en)
        self._abgeleitet()
        self._statuslabel()
        self.zaehler_aktualisieren()
        self.geaendert = False

    def _abgeleitet(self):
        for ed in self.editoren.values():
            if isinstance(ed, AbgeleitetEditor):
                ed.aktualisieren(self.ds)

    def uebernehmen(self):
        ds = self.ds
        for fid, ed in self.editoren.items():
            ed.speichern(ds.wert(fid))
        ds.wert("optionen").geprueft = self.opt_geprueft.get()
        ds.optionen = [Option(nr=v[0], code=v[1], de=v[2], en=v[3]) for v in self.optionen.werte()]
        ds.lieferumfang = [Eintrag(de=v[0], en=v[1]) for v in self.lieferumfang.werte()]
        ds.bilder = [Bild(datei=v[0], de=v[1], en=v[2]) for v in self.bilder.werte()]
        b = ds.wert("beschreibung")
        b.de = self.besch_de.get("1.0", "end").strip()
        b.en = self.besch_en.get("1.0", "end").strip()
        self.regel_pruefen()
        self._abgeleitet()
        self._statuslabel()

    def zwischenspeichern(self, still=False):
        self.uebernehmen()
        self.app.ablage.speichern(self.ds)
        self.geaendert = False
        self._schnappschuss = self._stand()
        if not still:
            self.hinweis(f"Gespeichert ({jetzt()[11:16]} Uhr).")

    # ---- Automatisch speichern
    def _stand(self) -> str:
        d = self.ds.to_dict()
        d.pop("geaendert", None)
        return json.dumps(d, sort_keys=True, ensure_ascii=False)

    def ungespeichert(self) -> bool:
        """Ob die Maske Änderungen enthält, die noch nicht gespeichert sind (auch Beschreibung/Listen)."""
        self.uebernehmen()
        return self.geaendert or self._stand() != self._schnappschuss

    def _autosave(self):
        try:
            if self.winfo_exists() and self.ungespeichert():
                self.zwischenspeichern(still=True)
                if self.statuszeile.cget("fg") != "#D62828":       # rote Hinweise nicht überschreiben
                    self.hinweis(f"Automatisch gespeichert ({jetzt()[11:16]} Uhr).")
        except Exception:
            pass                                                    # Autosave darf die Arbeit nie unterbrechen
        finally:
            try:
                self._auto_id = self.after(AUTOSAVE_MS, self._autosave)
            except tk.TclError:
                pass

    def destroy(self):
        try:
            self.after_cancel(self._auto_id)
        except (AttributeError, tk.TclError):
            pass
        super().destroy()

    def vorschau(self, sprache):
        self.uebernehmen()
        tmp = Path(tempfile.gettempdir()) / "eps-converter-vorschau"
        tmp.mkdir(exist_ok=True)
        try:
            p = pdf_export.erzeugen(self.ds, self.app.kat, tmp / f"vorschau_{sprache}_{self.ds.id}.pdf", sprache,
                                    self.app.ablage.ordner(self.ds.id))
        except PermissionError:
            messagebox.showerror("Vorschau", "Die Vorschau-Datei ist noch geöffnet. Bitte schließen und erneut versuchen.")
            return
        oeffnen(p)

    def freigeben(self):
        self.uebernehmen()
        nr = self.ds.bestellnummer
        felder = regeln.pruefe_freigabe_felder(self.ds, self.app.kat)
        dopp = self.app.ablage.finde_bestellnummer(nr, ausser_id=self.ds.id) if nr else None
        if dopp:
            felder.append(("bestellnummer", "wert", f"Bestellnummer {nr} ist bereits vergeben ({dopp.titel or 'ohne Namen'})."))
        probleme = [t for _, _, t in felder]
        if probleme:
            self.app.ablage.speichern(self.ds)
            messagebox.showwarning("Freigabe noch nicht möglich",
                                   "Bitte zuerst erledigen:\n\n• " + "\n• ".join(probleme[:25]) +
                                   ("\n…" if len(probleme) > 25 else "") +
                                   "\n\nDie betroffenen Felder sind rot umrandet, das Programm springt zum ersten.")
            self.probleme_markieren(felder)
            return
        self.probleme_markieren([])
        self.statuszeile.configure(text="", fg="#6A7380")
        self.spuren_markieren([])
        spuren = [] if self.ds.regel == REGEL_HAENDLER else \
            regeln.herstellerspuren(self.ds, self.app.kat, self.app.einst.hersteller)
        if spuren:
            self.spuren_markieren(spuren)
            liste = "\n• ".join(m for _, _, m in spuren[:15]) + ("\n…" if len(spuren) > 15 else "")
            if not messagebox.askyesno(
                    "Mögliche Herstellerspuren",
                    "Im Datenblatt stehen möglicherweise noch Hinweise auf den Hersteller:\n\n• " + liste +
                    "\n\nDie Stellen sind rot markiert.\n\nTrotzdem freigeben?", icon="warning", default="no", parent=self):
                return
            self.spuren_markieren([])
        if self.ds.regel == REGEL_HAENDLER:
            ziel_pdfs = []
        else:
            try:
                ziel_pdfs = pdf_export.beide(self.ds, self.app.kat, self.app.einst.ausgabe(), self.app.ablage.ordner(self.ds.id))
            except PermissionError:
                messagebox.showerror("Freigabe", "Ein PDF mit dieser Bestellnummer ist noch geöffnet. Bitte schließen.")
                return
            if self.app.einst.archiv_ordner:
                try:
                    a = Path(self.app.einst.archiv_ordner); a.mkdir(parents=True, exist_ok=True)
                    for p in ziel_pdfs:
                        shutil.copy2(p, a / p.name)
                except OSError as e:
                    messagebox.showwarning("Archiv", f"PDFs erzeugt, aber Kopie ins Archiv fehlgeschlagen:\n{e}")
        self.ds.status = FREIGEGEBEN
        self.ds.freigegeben_am = jetzt()
        self.ds.weclapp["status"] = "ausstehend"
        self.app.ablage.speichern(self.ds)
        self.geaendert = False
        self._statuslabel()
        self._schnappschuss = self._stand()
        if ziel_pdfs:
            FreigabeDialog(self, ziel_pdfs)
        else:
            messagebox.showinfo("Freigegeben", "Händlerware: Datensatz freigegeben. Es wird kein EPS-Datenblatt erzeugt "
                                               "(das Original-Datenblatt des Herstellers wird verwendet).")

    def zurueck(self):
        if self.ungespeichert():
            r = messagebox.askyesnocancel("Ungespeicherte Änderungen", "Änderungen speichern?")
            if r is None:
                return
            if r:
                self.zwischenspeichern(still=True)
        self.app.start_zeigen()


TASTENKUERZEL = [
    ("Überall", [("Strg+O", "Hersteller-PDF importieren"), ("Strg+N", "Leeres Datenblatt"), ("F1", "Diese Legende ein/aus")]),
    ("Startliste", [("Strg+F", "Suchen"), ("Esc", "Suche leeren (im Suchfeld)"), ("Enter", "Auswahl öffnen"),
                    ("Doppelklick", "Öffnen"), ("Klick auf Spalte", "Sortieren")]),
    ("Datenblatt", [("Strg+S", "Speichern"), ("Strg+P", "PDF-Vorschau DE"), ("Strg+Umschalt+P", "PDF-Vorschau EN"),
                    ("Feld anklicken", "Fundstelle im Original")]),
]


class Legende(tk.Frame):
    """Leiste rechts mit den Tastenkürzeln (F1 blendet ein/aus)."""

    BG = "#EEF2F7"

    def __init__(self, app: "App"):
        super().__init__(app, background=self.BG, width=210, highlightthickness=1, highlightbackground="#C9D3E0")
        self.app = app
        kopf = tk.Frame(self, background=NAVY)
        kopf.pack(fill="x")
        tk.Label(kopf, text="Tastenkürzel", fg="white", bg=NAVY, font=("Segoe UI", 10, "bold")).pack(side="left", padx=8, pady=6)
        x = tk.Label(kopf, text="✕", fg="white", bg=NAVY, cursor="hand2", font=("Segoe UI", 10))
        x.pack(side="right", padx=8)
        x.bind("<Button-1>", lambda e: app.legende_umschalten())
        for gruppe, eintraege in TASTENKUERZEL:
            tk.Label(self, text=gruppe, fg=NAVY, bg=self.BG, font=("Segoe UI", 9, "bold"), anchor="w").pack(
                fill="x", padx=10, pady=(10, 2))
            for taste, was in eintraege:
                z = tk.Frame(self, background=self.BG)
                z.pack(fill="x", padx=10, pady=1)
                tk.Label(z, text=taste, bg="white", fg="#1F2A37", font=("Consolas", 8), relief="solid", borderwidth=1,
                         padx=3).pack(anchor="w")
                tk.Label(z, text=was, bg=self.BG, fg="#4A5563", font=("Segoe UI", 8), anchor="w",
                         wraplength=185, justify="left").pack(anchor="w", padx=(2, 0))
        tk.Label(self, text="F1 blendet diese Leiste aus.", bg=self.BG, fg="#8A94A3", font=("Segoe UI", 8),
                 anchor="w").pack(side="bottom", fill="x", padx=10, pady=8)
        self.pack_propagate(False)


class FreigabeDialog(tk.Toplevel):
    """Nach der Freigabe: erzeugte PDFs direkt öffnen."""

    def __init__(self, master, pdfs: list[Path]):
        super().__init__(master)
        self.title("Freigegeben")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        fr = ttk.Frame(self, padding=16)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text="Datenblatt freigegeben ✔", font=("Segoe UI", 12, "bold"), foreground=NAVY).pack(anchor="w")
        ttk.Label(fr, text="Gespeichert in:\n" + str(pdfs[0].parent), foreground="#6A7380").pack(anchor="w", pady=(6, 12))
        knoepfe = ttk.Frame(fr)
        knoepfe.pack(fill="x")
        erster = None
        for p in pdfs:
            sprache = "Englisches" if p.name.lower().startswith("e") else "Deutsches"
            b = ttk.Button(knoepfe, text=f"{sprache} PDF öffnen ({p.name})", command=lambda p=p: oeffnen(p))
            b.pack(fill="x", pady=2)
            erster = erster or b
        ttk.Button(knoepfe, text="Ordner öffnen", command=lambda: oeffnen(pdfs[0].parent)).pack(fill="x", pady=2)
        ttk.Button(knoepfe, text="Schließen", command=self.destroy).pack(fill="x", pady=(10, 0))
        self.bind("<Escape>", lambda e: self.destroy())
        if erster:
            erster.focus_set()
        self.update_idletasks()
        top = master.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()


# ======================================================================== Startseite

class Start(ttk.Frame):
    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        k = tk.Frame(self, background=NAVY)
        k.pack(fill="x")
        tk.Label(k, text="EPS Datenblatt-Converter", fg="white", bg=NAVY, font=("Segoe UI", 15, "bold")).pack(side="left", padx=14, pady=12)
        tk.Label(k, text=f"Version {__version__}", fg=CYAN, bg=NAVY).pack(side="left")
        ttk.Button(k, text="Einstellungen", command=app.einstellungen_zeigen).pack(side="right", padx=10)
        leiste = ttk.Frame(self, padding=(10, 10, 10, 4))
        leiste.pack(fill="x")
        ttk.Button(leiste, text="Hersteller-PDF importieren …", command=app.import_pdf).pack(side="left")
        ttk.Button(leiste, text="Leeres Datenblatt", command=app.neu_leer).pack(side="left", padx=6)
        ttk.Button(leiste, text="Öffnen", command=self.oeffnen).pack(side="left", padx=6)
        ttk.Button(leiste, text="Duplizieren", command=self.duplizieren).pack(side="left", padx=6)
        ttk.Button(leiste, text="Entwurf löschen", command=self.loeschen).pack(side="left", padx=6)
        ttk.Button(leiste, text="Ausgabeordner öffnen", command=lambda: oeffnen(app.einst.ausgabe())).pack(side="right")

        such = ttk.Frame(self, padding=(10, 2, 10, 0))
        such.pack(fill="x")
        ttk.Label(such, text="Suchen:").pack(side="left")
        self.suche = tk.StringVar()
        self.such_feld = ttk.Entry(such, textvariable=self.suche, width=40)
        self.such_feld.pack(side="left", padx=6)
        ttk.Label(such, text="Status:").pack(side="left", padx=(12, 0))
        self.status_filter = tk.StringVar(value="Alle")
        cb = ttk.Combobox(such, textvariable=self.status_filter, values=["Alle", ENTWURF, FREIGEGEBEN],
                          state="readonly", width=14)
        cb.pack(side="left", padx=6)
        self.anzahl = ttk.Label(such, text="", foreground="#6A7380")
        self.anzahl.pack(side="right")
        self.suche.trace_add("write", lambda *a: self.filtern())
        cb.bind("<<ComboboxSelected>>", lambda e: self.filtern())
        self.such_feld.bind("<Escape>", lambda e: self.suche.set(""))

        sp = [("nr", "Bestellnummer", 110), ("titel", "Typbezeichnung", 260), ("hersteller", "Hersteller", 200),
              ("status", "Status", 110), ("weclapp", "Weclapp", 100), ("geaendert", "Geändert", 140)]
        self.tv = ttk.Treeview(self, columns=[s[0] for s in sp], show="headings")
        self._sortierung = ("geaendert", True)
        for key, t, w in sp:
            self.tv.heading(key, text=t, command=lambda k=key: self.sortieren(k))
            self.tv.column(key, width=w)
        self.tv.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.tv.bind("<Double-1>", lambda e: self.oeffnen())
        self.tv.bind("<Return>", lambda e: self.oeffnen())
        self.aktualisieren()

    def aktualisieren(self):
        self._zeilen = []
        for ds in self.app.ablage.alle():
            self._zeilen.append((ds.id, [ds.bestellnummer, ds.titel, ds.text("hersteller"), ds.status,
                                         ds.weclapp.get("status", "") if ds.status == FREIGEGEBEN else "",
                                         ds.geaendert.replace("T", " ")],
                                 " ".join([ds.text("hersteller_typ"), ds.text("hersteller_bestellnummer"),
                                           ds.text("serie"), ds.text("produkttyp")])))
        self.filtern()

    def filtern(self):
        """Suchbegriffe (mehrere Wörter = alle müssen vorkommen) in Name, Nummern, Hersteller, Typ, Serie."""
        worte = self.suche.get().lower().split()
        st = self.status_filter.get()
        spalten = ["nr", "titel", "hersteller", "status", "weclapp", "geaendert"]
        key, absteigend = self._sortierung
        i = spalten.index(key)
        zeilen = sorted(self._zeilen, key=lambda z: (z[1][i] or "").lower(), reverse=absteigend)
        self.tv.delete(*self.tv.get_children())
        n = 0
        for iid, werte, extra in zeilen:
            if st != "Alle" and werte[3] != st:
                continue
            heu = " ".join(werte + [extra]).lower()
            if all(w in heu for w in worte):
                self.tv.insert("", "end", iid=iid, values=werte)
                n += 1
        self.anzahl.configure(text=f"{n} von {len(self._zeilen)} Datenblättern")

    def sortieren(self, key):
        alt, absteigend = self._sortierung
        self._sortierung = (key, not absteigend if alt == key else False)
        self.filtern()

    def duplizieren(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo("Duplizieren", "Bitte zuerst ein Datenblatt in der Liste auswählen.")
            return
        neu = self.app.ablage.duplizieren(sel[0])
        self.aktualisieren()
        self.app.maske_zeigen(neu)
        self.app.aktuell.hinweis("Kopie angelegt (Entwurf). Bestellnummern und Prüfhaken wurden zurückgesetzt – "
                                 "bitte die abweichenden Werte anpassen.")

    def oeffnen(self):
        sel = self.tv.selection()
        if sel:
            self.app.maske_zeigen(self.app.ablage.laden(sel[0]))

    def loeschen(self):
        sel = self.tv.selection()
        if not sel:
            return
        ds = self.app.ablage.laden(sel[0])
        if ds.status != ENTWURF:
            messagebox.showinfo("Löschen", "Freigegebene Datenblätter können nicht gelöscht werden.")
            return
        if messagebox.askyesno("Löschen", f"Entwurf „{ds.titel or ds.id}“ endgültig löschen?"):
            self.app.ablage.loeschen(ds.id)
            self.aktualisieren()


# ======================================================================== Einstellungen

class EinstellungenDialog(tk.Toplevel):
    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        self.title("Einstellungen")
        self.transient(app)
        self.grab_set()
        e = app.einst
        fr = ttk.Frame(self, padding=14)
        fr.pack(fill="both", expand=True)
        r = 0

        def zeile(text, widget, hilfe=""):
            nonlocal r
            ttk.Label(fr, text=text).grid(row=r, column=0, sticky="nw", pady=4, padx=(0, 10))
            widget.grid(row=r, column=1, sticky="we", pady=4)
            if hilfe:
                ttk.Label(fr, text=hilfe, foreground="#6A7380", wraplength=420).grid(row=r + 1, column=1, sticky="w")
                r += 1
            r += 1

        self.api = Eingabe(fr, 52, show="•"); self.api.insert(0, e.anthropic_api_key)
        zeile("Claude-API-Schlüssel", self.api, "Nur nötig für die KI-Auswertung (nach Kostenfreigabe). Bleibt auf diesem Rechner.")
        self.benutzer = Eingabe(fr, 52); self.benutzer.insert(0, e.benutzer)
        zeile("Benutzername", self.benutzer)
        self.ausgabe = self._ordnerfeld(fr, e.ausgabe_ordner)
        zeile("Ausgabeordner PDFs", self.ausgabe.master, f"Leer = {pfade.AUSGABE_DIR}")
        self.archiv = self._ordnerfeld(fr, e.archiv_ordner)
        zeile("Archivordner (optional)", self.archiv.master, "Zusätzliche Kopie jeder freigegebenen PDF, z. B. Netzlaufwerk.")
        self.hersteller = tk.Text(fr, height=6, width=52, relief="solid", borderwidth=1)
        self.hersteller.insert("1.0", "\n".join(e.hersteller))
        zeile("Hersteller (einer pro Zeile)", self.hersteller)
        hw = ", ".join(e.haendlerware_hersteller) or "– keine –"
        self.hw_lbl = ttk.Label(fr, text=hw)
        zeile("Händlerware (Originalname + Original-PDF)", self.hw_lbl)
        ttk.Button(fr, text="Händlerware freischalten / ändern …", command=self.haendlerware).grid(row=r, column=1, sticky="w"); r += 1
        ttk.Button(fr, text="Feldkatalog öffnen (Excel)", command=lambda: oeffnen(app.kat.quelle)).grid(row=r, column=1, sticky="w", pady=(10, 0)); r += 1
        bf = ttk.Frame(fr); bf.grid(row=r, column=1, sticky="e", pady=(14, 0))
        ttk.Button(bf, text="Abbrechen", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(bf, text="Speichern", command=self.speichern).pack(side="right")
        self._hw = list(e.haendlerware_hersteller)

    def _ordnerfeld(self, master, wert):
        f = ttk.Frame(master)
        ent = Eingabe(f, 44); ent.insert(0, wert); ent.pack(side="left")
        ttk.Button(f, text="…", width=3, command=lambda: self._waehle(ent)).pack(side="left", padx=4)
        return ent

    def _waehle(self, ent):
        p = filedialog.askdirectory()
        if p:
            ent.delete(0, "end"); ent.insert(0, p)

    def haendlerware(self):
        if not messagebox.askyesno("Händlerware", "Achtung: Geräte dieser Hersteller werden danach NICHT mehr umbenannt "
                                                  "und bekommen kein EPS-Datenblatt.\n\nNur freischalten, wenn der Händlervertrag gilt.\n\nFortfahren?"):
            return
        d = tk.Toplevel(self); d.title("Händlerware"); d.transient(self); d.grab_set()
        vars_ = {}
        alle = [x.strip() for x in self.hersteller.get("1.0", "end").splitlines() if x.strip()]
        for h in alle:
            v = tk.BooleanVar(value=h in self._hw)
            ttk.Checkbutton(d, text=h, variable=v).pack(anchor="w", padx=14, pady=2)
            vars_[h] = v

        def ok():
            self._hw = [h for h, v in vars_.items() if v.get()]
            self.hw_lbl.configure(text=", ".join(self._hw) or "– keine –")
            d.destroy()
        ttk.Button(d, text="OK", command=ok).pack(pady=10)

    def speichern(self):
        e = self.app.einst
        e.anthropic_api_key = self.api.get().strip()
        e.benutzer = self.benutzer.get().strip()
        e.ausgabe_ordner = self.ausgabe.get().strip()
        e.archiv_ordner = self.archiv.get().strip()
        e.hersteller = [x.strip() for x in self.hersteller.get("1.0", "end").splitlines() if x.strip()]
        e.haendlerware_hersteller = self._hw
        E.speichern(e)
        self.destroy()


# ======================================================================== Anwendung

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EPS Datenblatt-Converter")
        self.geometry("1280x820")
        self.minsize(1000, 640)
        try:
            ttk.Style(self).theme_use("vista" if sys.platform.startswith("win") else "clam")
        except tk.TclError:
            pass
        # Auf Windows ändert das Mausrad über einer Auswahlliste sonst unbemerkt den Wert.
        # Stattdessen wird das Rad an den Bildlaufbereich weitergegeben.
        def _rad_umleiten(e):
            w = e.widget
            while w is not None and not isinstance(w, tk.Canvas):
                w = w.master
            if w is not None:
                delta = -1 if (getattr(e, "num", 0) == 4 or e.delta > 0) else 1
                w.yview_scroll(delta * 3, "units")
            return "break"
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_class("TCombobox", seq, _rad_umleiten)
        self.einst = E.laden()
        try:
            self.kat = K.laden()
        except K.KatalogFehler as e:
            messagebox.showerror("Feldkatalog", str(e))
            self.destroy()
            raise SystemExit(1)
        self.ablage = LokaleAblage()
        self.aktuell = None
        self.viewer = None
        self.legende = Legende(self)
        if self.einst.legende_anzeigen:
            self.legende.pack(side="right", fill="y")
        self.start_zeigen()
        self.protocol("WM_DELETE_WINDOW", self.beenden)
        self._kuerzel()
        if self.einst.update_pruefen:
            from . import updates
            updates.im_hintergrund(self)

    def _kuerzel(self):
        """Tastenkürzel: Strg+S speichern, Strg+P / Strg+Umschalt+P Vorschau DE/EN, Strg+O importieren,
        Strg+N leeres Datenblatt, Strg+F suchen (Startseite)."""
        def in_maske(fn):
            def h(e=None):
                if isinstance(self.aktuell, Maske):
                    fn(self.aktuell)
                    return "break"
            return h

        def speichern(m):
            m.zwischenspeichern()
        self.bind_all("<Control-s>", in_maske(speichern))
        self.bind_all("<Control-S>", in_maske(speichern))
        self.bind_all("<Control-p>", in_maske(lambda m: m.vorschau("de")))
        self.bind_all("<Control-Shift-P>", in_maske(lambda m: m.vorschau("en")))
        self.bind_all("<Control-o>", lambda e: (self.import_pdf(), "break")[1])
        self.bind_all("<Control-n>", lambda e: (self.neu_leer(), "break")[1])
        self.bind_all("<F1>", self.legende_umschalten)

        # Tk-Textfelder haben eigene Emacs-Kürzel (Strg+O fügt z. B. eine Zeile ein) – hier abschalten
        for seq in ("<Control-o>", "<Control-p>", "<Control-n>", "<Control-f>"):
            self.bind_class("Text", seq, lambda e: None)

        def suchen(e=None):
            if isinstance(self.aktuell, Start):
                self.aktuell.such_feld.focus_set()
                return "break"
        self.bind_all("<Control-f>", suchen)

    def legende_umschalten(self, e=None):
        an = not self.einst.legende_anzeigen
        if not an:
            self.legende.pack_forget()
        elif self.aktuell is not None:
            self.legende.pack(side="right", fill="y", before=self.aktuell)
        else:
            self.legende.pack(side="right", fill="y")
        self.einst.legende_anzeigen = an
        try:
            E.speichern(self.einst)
        except OSError:
            pass
        return "break"

    def _wechseln(self, frame):
        if self.aktuell is not None:
            self.aktuell.destroy()
        self.aktuell = frame
        frame.pack(fill="both", expand=True)

    def start_zeigen(self):
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.schliessen()
        self.viewer = None
        self._wechseln(Start(self))

    def original_zeigen(self, pfad: Path):
        from .importieren import OriginalViewer
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.schliessen()
        try:
            self.viewer = OriginalViewer(self, pfad)
            x = self.winfo_rootx() + self.winfo_width() - 40
            self.viewer.geometry(f"720x{max(600, self.winfo_height())}+{min(x, self.winfo_screenwidth() - 720)}+{self.winfo_rooty()}")
        except Exception as e:
            messagebox.showwarning("Original", f"Vorschau nicht möglich: {e}")

    def maske_zeigen(self, ds: Datensatz):
        self._wechseln(Maske(self, ds))

    def maske_verlassen(self) -> bool:
        """Vor dem Wechsel aus einer Maske: ungespeicherte Änderungen abfragen. False = abbrechen."""
        if isinstance(self.aktuell, Maske) and self.aktuell.ungespeichert():
            r = messagebox.askyesnocancel("Ungespeicherte Änderungen", "Änderungen am aktuellen Datenblatt speichern?")
            if r is None:
                return False
            if r:
                self.aktuell.zwischenspeichern(still=True)
        return True

    def neu_leer(self):
        if not self.maske_verlassen():
            return
        ds = Datensatz()
        self.ablage.speichern(ds)
        self.maske_zeigen(ds)

    def import_pdf(self):
        if not self.maske_verlassen():
            return
        try:
            from . import importieren
        except ImportError:
            messagebox.showinfo("Import", "Der PDF-Import folgt in Etappe 3. Bitte vorerst „Leeres Datenblatt“ verwenden.")
            return
        importieren.dialog(self)

    def einstellungen_zeigen(self):
        EinstellungenDialog(self)

    def beenden(self):
        if isinstance(self.aktuell, Maske) and self.aktuell.ungespeichert():
            r = messagebox.askyesnocancel("Beenden", "Ungespeicherte Änderungen speichern?")
            if r is None:
                return
            if r:
                self.aktuell.zwischenspeichern(still=True)
        self.destroy()


def main():
    App().mainloop()
