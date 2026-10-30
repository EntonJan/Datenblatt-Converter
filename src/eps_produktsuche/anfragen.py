"""Seite „Anfragen“ (Outlook) – experimentell (Einstellungen → Experimentelle Funktionen).

Links die Mails der Anfrage-Ordner (klassisches Outlook) bzw. geöffnete .msg/.eml-Dateien, rechts was erkannt wurde:
Kunde mit Stammdaten (änderbar, Unsicheres gelb), Menge, Wunschtermin, Suchtext, Nachricht und Anhänge.
„In Suche übernehmen“ setzt die Anfrage in die Produktsuche (Anhang → Datenblatt-Auslese, sonst Suchtext).
„Erledigt“ verschiebt die Mail in den Unterordner „Erledigt“. In gemeinsamen Postfächern wird eine Mail beim Öffnen
sofort nach „In Bearbeitung“ verschoben, damit niemand dieselbe Anfrage doppelt bearbeitet.
Angelegt wird hier noch nichts – das übernimmt später die Weclapp-Anbindung (nach Klick).
"""
from __future__ import annotations

import tempfile
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, filedialog

import customtkinter as ctk

from . import kunde as K, outlook, thema as TH
from .einstellungen import Anfrageordner
from .mail import Mail, datei_lesen

GELB = "#FFF4D6"
FELDER = [("firma", "Firma"), ("rechtsform", "Rechtsform"), ("anrede", "Anrede"), ("vorname", "Vorname"),
          ("nachname", "Nachname"), ("email", "E-Mail"), ("telefon", "Telefon"), ("mobil", "Mobil"),
          ("strasse", "Straße"), ("plz", "PLZ"), ("ort", "Ort"), ("land", "Land (ISO)"), ("web", "Web"),
          ("ust_id", "USt-IdNr.")]
DATEIEN = "– geöffnete Mail-Dateien –"


class AnfragenSeite(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.anhang_ordner = Path(tempfile.mkdtemp(prefix="eps-anfragen-"))
        self.mails: list[Mail] = []
        self.erkennungen: dict[int, K.Erkennung] = {}
        self.ordner_von: dict[int, Anfrageordner | None] = {}
        self.aktuell: int | None = None
        self.geladen = False
        self._aufbauen()
        self._dnd()

    def zeigen(self):
        """Beim ersten Öffnen der Seite den ersten Ordner lesen (Outlook wird erst dann angesprochen)."""
        if self.geladen:
            return
        self.geladen = True
        if self.app.einstellungen.anfrageordner and outlook.verfuegbar():
            self.after(100, self.laden)
        else:
            self.ordner_cb.set(DATEIEN)
            self.status.configure(text="Klassisches Outlook nicht verfügbar – Mails als .msg/.eml öffnen oder hineinziehen."
                                  if not outlook.verfuegbar() else "Keine Anfrage-Ordner eingestellt (Einstellungen).")

    def ordner_aktualisieren(self):
        werte = [o.anzeige for o in self.app.einstellungen.anfrageordner] + [DATEIEN]
        self.ordner_cb.configure(values=werte)
        if self.ordner_cb.get() not in werte:
            self.ordner_cb.set(werte[0])

    # ---------------------------------------------------------------- Aufbau
    def _aufbauen(self):
        kopf = ctk.CTkFrame(self, fg_color="transparent")
        kopf.pack(fill="x", pady=(0, 14))
        TH.text(kopf, "Anfragen", 24, True, anchor="w").pack(anchor="w")
        self.status = TH.text(kopf, "", 13, farbe=TH.GRAU, anchor="w")
        self.status.pack(anchor="w")

        teil = ctk.CTkFrame(self, fg_color="transparent")
        teil.pack(fill="both", expand=True)
        teil.columnconfigure(0, weight=2, uniform="t")
        teil.columnconfigure(1, weight=3, uniform="t")
        teil.rowconfigure(0, weight=1)

        links = TH.karte(teil)
        links.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        oben = ctk.CTkFrame(links, fg_color="transparent")
        oben.pack(fill="x", padx=12, pady=(12, 6))
        werte = [o.anzeige for o in self.app.einstellungen.anfrageordner] + [DATEIEN]
        self.ordner_cb = TH.auswahl(oben, werte, command=lambda v: self.laden(), breite=260)
        self.ordner_cb.set(werte[0])
        self.ordner_cb.pack(side="left", fill="x", expand=True)
        TH.knopf(oben, "Aktualisieren", self.laden, height=34, width=110).pack(side="left", padx=(6, 0))
        sp = [("zeit", "Eingang", 95), ("von", "Absender", 150), ("betreff", "Betreff", 220), ("art", "Art", 75)]
        t_rahmen, self.tv = TH.tabelle(links, sp, dehnen=("betreff",))
        t_rahmen.configure(border_width=0)
        t_rahmen.pack(fill="both", expand=True, padx=4)
        self.app.tabellen.append(self.tv)
        self.tv.bind("<<TreeviewSelect>>", lambda e: self.auswaehlen())
        ablage = ctk.CTkButton(links, text="Mail-Datei öffnen … oder .msg / .eml hierher ziehen", height=44,
                               fg_color="transparent", hover_color=TH.KNOPF_HOVER, text_color=TH.GRAU,
                               border_color=TH.RAND, border_width=1, corner_radius=10, font=TH.schrift(12),
                               command=self.datei_waehlen)
        ablage.pack(fill="x", padx=12, pady=12)
        self.ablage = ablage

        rechts = ctk.CTkFrame(teil, fg_color="transparent")
        rechts.grid(row=0, column=1, sticky="nsew")
        kunde = TH.karte(rechts)
        kunde.pack(fill="x")
        kk = ctk.CTkFrame(kunde, fg_color="transparent")
        kk.pack(fill="x", padx=16, pady=(12, 4))
        TH.text(kk, "Kunde", 16, True).pack(side="left")
        self.herkunft = ctk.CTkLabel(kk, text="", fg_color=TH.CHIP, text_color=TH.CHIP_TEXT, corner_radius=12, height=24,
                                     padx=10, font=TH.schrift(12))
        TH.text(kk, "gelb = bitte prüfen", 11, farbe=TH.GRAU).pack(side="right")
        raster = ctk.CTkFrame(kunde, fg_color="transparent")
        raster.pack(fill="x", padx=16, pady=(0, 6))
        self.vars: dict[str, tk.StringVar] = {}
        self.entries: dict[str, ctk.CTkEntry] = {}
        for i, (key, label) in enumerate(FELDER):
            r, c = (i // 4) * 2, i % 4
            raster.columnconfigure(c, weight=1, uniform="f")
            TH.text(raster, label, 11, farbe=TH.GRAU, anchor="w").grid(row=r, column=c, sticky="w", padx=(0, 8))
            v = tk.StringVar()
            e = TH.eingabe(raster, textvariable=v, height=30)
            e.grid(row=r + 1, column=c, sticky="we", padx=(0, 8), pady=(0, 6))
            self.vars[key], self.entries[key] = v, e
        self.unsicher = ctk.CTkLabel(kunde, text="", fg_color="transparent", text_color=TH.GELB_TEXT, corner_radius=8,
                                     anchor="w", justify="left", wraplength=640, font=TH.schrift(12))
        self.unsicher.pack(fill="x", padx=16, pady=(0, 12))

        such = TH.karte(rechts)
        such.pack(fill="x", pady=(12, 0))
        sz = ctk.CTkFrame(such, fg_color="transparent")
        sz.pack(fill="x", padx=16, pady=12)
        sz.columnconfigure(0, weight=1)
        TH.text(sz, "Suchtext", 11, farbe=TH.GRAU, anchor="w").grid(row=0, column=0, sticky="w")
        TH.text(sz, "Menge", 11, farbe=TH.GRAU, anchor="w").grid(row=0, column=1, sticky="w", padx=(10, 0))
        TH.text(sz, "Wunschtermin", 11, farbe=TH.GRAU, anchor="w").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.suchtext = tk.StringVar()
        ctk.CTkEntry(sz, textvariable=self.suchtext, height=40, font=TH.schrift(15), fg_color=TH.EINGABE,
                     border_color=TH.AKZENT, border_width=2, text_color=TH.TEXT, corner_radius=8
                     ).grid(row=1, column=0, sticky="we")
        self.menge = tk.StringVar()
        TH.eingabe(sz, textvariable=self.menge, width=70, height=40).grid(row=1, column=1, padx=(10, 0))
        self.termin = tk.StringVar()
        TH.eingabe(sz, textvariable=self.termin, width=140, height=40).grid(row=1, column=2, padx=(10, 0))

        nachricht = TH.karte(rechts)
        nachricht.pack(fill="both", expand=True, pady=(12, 0))
        self.anh_lbl = TH.text(nachricht, "", 12, farbe=TH.LINK, anchor="w", justify="left", wraplength=640)
        self.anh_lbl.pack(fill="x", padx=16, pady=(10, 0))
        self.text = ctk.CTkTextbox(nachricht, wrap="word", font=TH.schrift(12), fg_color="transparent",
                                   text_color=TH.TEXT, height=120)
        self.text.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        unten = ctk.CTkFrame(rechts, fg_color="transparent")
        unten.pack(fill="x", pady=(12, 0))
        self.knopf_suche = TH.knopf(unten, "In Suche übernehmen", self.uebernehmen, haupt=True)
        self.knopf_suche.pack(side="left")
        self.knopf_bearbeitung = TH.knopf(unten, "Nach „In Bearbeitung“", self.in_bearbeitung)
        self.knopf_bearbeitung.pack(side="left", padx=(8, 0))
        self.knopf_erledigt = TH.knopf(unten, "Erledigt", self.erledigt)
        self.knopf_erledigt.pack(side="left", padx=(8, 0))
        TH.text(unten, "Angelegt wird hier nichts.", 11, farbe=TH.GRAU).pack(side="right")

    def _dnd(self):
        try:
            from tkinterdnd2 import DND_FILES
            for w in (self.tv, self.ablage):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._drop)
        except Exception:  # noqa: BLE001
            pass

    def _drop(self, e):
        pfade = [Path(p) for p in self.tk.splitlist(e.data) if p.lower().endswith((".msg", ".eml"))]
        if pfade:
            self.after(10, lambda: self.dateien_laden(pfade))
        return "copy"

    # ---------------------------------------------------------------- Hintergrund
    def _im_hintergrund(self, arbeit, fertig, text: str):
        ergebnis: dict = {}
        self.status.configure(text=text)
        tk.Tk.configure(self.app, cursor="watch")

        def lauf():
            try:
                ergebnis["wert"] = arbeit()
            except Exception as ex:  # noqa: BLE001
                ergebnis["fehler"] = ex
            ergebnis["fertig"] = True

        def abfragen():
            if not ergebnis.get("fertig"):
                self.after(120, abfragen)
                return
            if not self.winfo_exists():
                return
            tk.Tk.configure(self.app, cursor="")
            fertig(ergebnis.get("wert"), ergebnis.get("fehler"))

        threading.Thread(target=lauf, daemon=True).start()
        self.after(120, abfragen)

    def _gewaehlter_ordner(self) -> Anfrageordner | None:
        wahl = self.ordner_cb.get()
        return next((o for o in self.app.einstellungen.anfrageordner if o.anzeige == wahl), None)

    # ---------------------------------------------------------------- Laden
    def laden(self):
        o = self._gewaehlter_ordner()
        if o is None:
            return
        ziel = self.anhang_ordner / datetime.now().strftime("%H%M%S")

        def arbeit():
            with outlook.Outlook() as ol:
                return ol.mails(o.pfad, ziel)

        def fertig(mails, fehler):
            if fehler:
                self.status.configure(text=f"Outlook: {fehler}")
                return
            self._anzeigen(mails or [], o)
            self.status.configure(text=f"{len(mails)} Mails in „{o.pfad}“")
            self.app.anfragen_anzahl(len(mails or []))

        self._im_hintergrund(arbeit, fertig, f"Lese „{o.pfad}“ …")

    def datei_waehlen(self):
        pfade = filedialog.askopenfilenames(parent=self, title="Anfrage-Mail öffnen",
                                            filetypes=[("E-Mail", "*.msg *.eml"), ("Alle Dateien", "*.*")])
        if pfade:
            self.dateien_laden([Path(p) for p in pfade])

    def dateien_laden(self, pfade: list[Path]):
        mails, fehler = [], []
        for p in pfade:
            try:
                mails.append(datei_lesen(p, self.anhang_ordner / p.stem))
            except Exception as ex:  # noqa: BLE001
                fehler.append(f"{p.name}: {ex}")
        self.ordner_cb.set(DATEIEN)
        self._anzeigen(mails, None)
        self.status.configure(text=f"{len(mails)} Mail-Datei(en) geöffnet" + (f" · Fehler: {'; '.join(fehler)}" if fehler else ""))

    def _anzeigen(self, mails: list[Mail], ordner: Anfrageordner | None):
        self.mails, self.erkennungen, self.ordner_von, self.aktuell = mails, {}, {}, None
        self.tv.delete(*self.tv.get_children())
        for i, m in enumerate(mails):
            e = K.erkennen(m, tuple(self.app.einstellungen.interne_domains))
            self.erkennungen[i], self.ordner_von[i] = e, ordner
            try:
                zeit = datetime.fromisoformat(m.empfangen).strftime("%d.%m. %H:%M")
            except ValueError:
                zeit = m.empfangen
            self.tv.insert("", "end", iid=str(i), tags=("formular",) if e.formular else (),
                           values=[zeit, m.absender_name or m.absender_email, m.betreff,
                                   "Formular" if e.formular else "Mail", len(m.anhaenge) or ""])
        self._leeren()
        kinder = self.tv.get_children()
        if kinder and self.app.aktive_seite == "anfragen":     # Öffnen kann eine Mail verschieben – nur sichtbar
            self.tv.selection_set(kinder[0])

    # ---------------------------------------------------------------- Auswahl
    def _leeren(self):
        for v in self.vars.values():
            v.set("")
        self.menge.set("")
        self.termin.set("")
        self.suchtext.set("")
        self.text.delete("1.0", "end")
        self.anh_lbl.configure(text="")
        self.unsicher.configure(text="", fg_color="transparent")
        self.herkunft.pack_forget()
        for e in self.entries.values():
            e.configure(fg_color=TH.EINGABE)
        self.knopf_erledigt.configure(state="disabled")
        self.knopf_bearbeitung.configure(state="disabled")

    def _formular_lesen(self):
        if self.aktuell is None:
            return
        e = self.erkennungen[self.aktuell]
        for key, v in self.vars.items():
            setattr(e.kunde, key, v.get().strip())
        try:
            e.menge = int(self.menge.get()) if self.menge.get().strip() else None
        except ValueError:
            pass
        e.termin = self.termin.get().strip() or "ASAP"
        e.suchtext = self.suchtext.get().strip()

    def auswaehlen(self):
        sel = self.tv.selection()
        if not sel:
            return
        self._formular_lesen()
        i = int(sel[0])
        self.aktuell = i
        m, e = self.mails[i], self.erkennungen[i]
        unsicher_felder = " ".join(e.unsicher).lower()
        for key, label in FELDER:
            self.vars[key].set(getattr(e.kunde, key, ""))
            leer = not getattr(e.kunde, key, "")
            fraglich = label.split(" ")[0].lower() in unsicher_felder or (key in ("strasse", "plz") and "adresse" in
                                                                          unsicher_felder)
            self.entries[key].configure(fg_color=TH.GELB if (leer or fraglich) else TH.EINGABE)
        self.menge.set(str(e.menge or ""))
        self.termin.set(e.termin)
        self.suchtext.set(e.suchtext)
        self.text.delete("1.0", "end")
        kopf = f"{m.betreff}\n\n"
        if e.weitergeleitet_von:
            kopf += f"▶ Weitergeleitet von {e.weitergeleitet_von}" + (f":\n{e.notiz}\n" if e.notiz else "\n") + \
                "\n▶ Original-Anfrage des Kunden:\n"
        self.text.insert("1.0", kopf + e.anfrage)
        self.anh_lbl.configure(text=("Anhänge: " + ", ".join(p.name for p in m.anhaenge)) if m.anhaenge else
                               "Keine PDF/Word-Anhänge")
        if e.weitergeleitet_von:
            e.unsicher = [u for u in e.unsicher if not u.startswith("Weitergeleitet")]
        hinweis = (f"Weitergeleitet von {e.weitergeleitet_von} – Kunde aus der Original-Mail. " if e.weitergeleitet_von
                   else "") + (("Bitte prüfen: " + " · ".join(e.unsicher)) if e.unsicher else "")
        hinweis = hinweis or \
            ("Homepage-Formular – vollständig erkannt" if e.formular else "")
        self.unsicher.configure(text=hinweis, fg_color=TH.GELB if e.unsicher else (TH.GRUEN_BG if hinweis else "transparent"),
                                text_color=TH.GELB_TEXT if e.unsicher else TH.GRUEN)
        self.herkunft.configure(text="Homepage-Formular" if e.formular else ("weitergeleitet" if e.weitergeleitet_von
                                                                            else "aus Mail/Signatur"))
        self.herkunft.pack(side="left", padx=10)
        o = self.ordner_von.get(i)
        self.knopf_erledigt.configure(state="normal" if o else "disabled")
        self.knopf_bearbeitung.configure(state="normal" if o and not getattr(m, "_in_bearbeitung", False) else "disabled")
        if o and o.gemeinsam and not getattr(m, "_in_bearbeitung", False):
            self._in_bearbeitung(i, o)

    def _in_bearbeitung(self, i: int, o: Anfrageordner):
        m = self.mails[i]
        ziel = outlook.unterordner(o.pfad, self.app.einstellungen.ordner_in_bearbeitung)

        def arbeit():
            with outlook.Outlook() as ol:
                return ol.verschieben(m.quelle, ziel)

        def fertig(neue_id, fehler):
            if fehler:
                messagebox.showwarning("Anfragen", f"Konnte die Mail nicht nach „In Bearbeitung“ verschieben:\n{fehler}",
                                       parent=self)
                return
            m.quelle, m._in_bearbeitung = neue_id, True
            if self.aktuell == i:
                self.knopf_bearbeitung.configure(state="disabled")
            self.status.configure(text=f"Nach „{ziel}“ verschoben – andere sehen, dass du sie bearbeitest.")

        self._im_hintergrund(arbeit, fertig, "Verschiebe nach „In Bearbeitung“ …")

    # ---------------------------------------------------------------- Aktionen
    def in_bearbeitung(self):
        if self.aktuell is not None and self.ordner_von.get(self.aktuell):
            self._in_bearbeitung(self.aktuell, self.ordner_von[self.aktuell])

    def uebernehmen(self):
        if self.aktuell is None:
            return
        self._formular_lesen()
        self.app.vorgang_uebernehmen(self.mails[self.aktuell], self.erkennungen[self.aktuell])

    def erledigt(self):
        if self.aktuell is None:
            return
        i = self.aktuell
        o = self.ordner_von.get(i)
        if not o:
            return
        self._formular_lesen()
        m = self.mails[i]
        ziel = outlook.unterordner(o.pfad, self.app.einstellungen.ordner_erledigt)

        def arbeit():
            with outlook.Outlook() as ol:
                return ol.verschieben(m.quelle, ziel)

        def fertig(_, fehler):
            if fehler:
                messagebox.showerror("Anfragen", f"Verschieben fehlgeschlagen:\n{fehler}", parent=self)
                return
            self.tv.delete(str(i))
            self.aktuell = None
            self.app.anfragen_anzahl(len(self.tv.get_children()))
            self._leeren()
            self.status.configure(text=f"Nach „{ziel}“ verschoben.")
            rest = self.tv.get_children()
            if rest:
                self.tv.selection_set(rest[0])

        self._im_hintergrund(arbeit, fertig, "Verschiebe nach „Erledigt“ …")
