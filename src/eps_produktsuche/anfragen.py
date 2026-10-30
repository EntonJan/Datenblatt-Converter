"""Fenster „Anfragen (Outlook)“ – experimentell (Einstellungen → Experimentelle Funktionen).

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
from tkinter import ttk, messagebox, filedialog

from . import kunde as K, outlook
from .einstellungen import Anfrageordner
from .mail import Mail, datei_lesen

GELB = "#FFF4D6"
FELDER = [("firma", "Firma"), ("rechtsform", "Rechtsform"), ("anrede", "Anrede"), ("vorname", "Vorname"),
          ("nachname", "Nachname"), ("email", "E-Mail"), ("telefon", "Telefon"), ("mobil", "Mobil"),
          ("strasse", "Straße"), ("plz", "PLZ"), ("ort", "Ort"), ("land", "Land (ISO)"), ("web", "Web"),
          ("ust_id", "USt-IdNr.")]
DATEIEN = "– geöffnete Mail-Dateien –"


class AnfragenFenster(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Kundenanfragen (Outlook) – Testphase")
        self.geometry("1280x720")
        self.anhang_ordner = Path(tempfile.mkdtemp(prefix="eps-anfragen-"))
        self.mails: list[Mail] = []
        self.erkennungen: dict[int, K.Erkennung] = {}
        self.ordner_von: dict[int, Anfrageordner | None] = {}
        self.aktuell: int | None = None
        self._aufbauen()
        self._dnd()
        if self.app.einstellungen.anfrageordner and outlook.verfuegbar():
            self.after(100, self.laden)
        else:
            self.ordner_cb.set(DATEIEN)
            self.status.configure(text="Klassisches Outlook nicht verfügbar – Mails als .msg/.eml öffnen oder hineinziehen."
                                  if not outlook.verfuegbar() else "Keine Anfrage-Ordner eingestellt (Einstellungen).")

    # ---------------------------------------------------------------- Aufbau
    def _aufbauen(self):
        oben = ttk.Frame(self, padding=(10, 10, 10, 4))
        oben.pack(fill="x")
        ttk.Label(oben, text="Ordner:").pack(side="left")
        self.ordner_cb = ttk.Combobox(oben, state="readonly", width=70,
                                      values=[o.anzeige for o in self.app.einstellungen.anfrageordner] + [DATEIEN])
        if self.app.einstellungen.anfrageordner:
            self.ordner_cb.current(0)
        self.ordner_cb.pack(side="left", padx=6)
        self.ordner_cb.bind("<<ComboboxSelected>>", lambda e: self.laden())
        ttk.Button(oben, text="Aktualisieren", command=self.laden).pack(side="left")
        ttk.Button(oben, text="Mail-Datei öffnen …", command=self.datei_waehlen).pack(side="left", padx=6)
        self.status = ttk.Label(oben, text="", foreground="#6A7380")
        self.status.pack(side="left", padx=10)

        teil = ttk.PanedWindow(self, orient="horizontal")
        teil.pack(fill="both", expand=True, padx=10, pady=4)
        links = ttk.Frame(teil)
        sp = [("zeit", "Eingang", 110), ("von", "Absender", 170), ("betreff", "Betreff", 230), ("art", "Art", 70),
              ("anh", "Anh.", 40)]
        self.tv = ttk.Treeview(links, columns=[x[0] for x in sp], show="headings", selectmode="browse")
        for k, t, b in sp:
            self.tv.heading(k, text=t)
            self.tv.column(k, width=b, stretch=k == "betreff")
        sb = ttk.Scrollbar(links, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tv.bind("<<TreeviewSelect>>", lambda e: self.auswaehlen())
        self.tv.tag_configure("formular", foreground="#2E7D32")
        teil.add(links, weight=2)

        rechts = ttk.Frame(teil, padding=(10, 0, 0, 0))
        teil.add(rechts, weight=3)
        ttk.Label(rechts, text="Kunde / Interessent", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=4,
                                                                                        sticky="w")
        self.vars: dict[str, tk.StringVar] = {}
        self.entries: dict[str, tk.Entry] = {}
        for i, (key, label) in enumerate(FELDER):
            r, c = 1 + i // 2, (i % 2) * 2
            ttk.Label(rechts, text=label + ":").grid(row=r, column=c, sticky="e", padx=(0, 4), pady=1)
            v = tk.StringVar()
            e = tk.Entry(rechts, textvariable=v, width=30, relief="solid", borderwidth=1)
            e.grid(row=r, column=c + 1, sticky="we", pady=1, padx=(0, 10))
            self.vars[key], self.entries[key] = v, e
        r = 2 + len(FELDER) // 2
        self.unsicher = tk.Label(rechts, text="", bg=GELB, fg="#5A4300", justify="left", anchor="w", wraplength=560)
        self.unsicher.grid(row=r, column=0, columnspan=4, sticky="we", pady=(6, 2))
        ttk.Label(rechts, text="Menge:").grid(row=r + 1, column=0, sticky="e")
        self.menge = tk.StringVar()
        ttk.Entry(rechts, textvariable=self.menge, width=8).grid(row=r + 1, column=1, sticky="w")
        ttk.Label(rechts, text="Wunschtermin:").grid(row=r + 1, column=2, sticky="e")
        self.termin = tk.StringVar()
        ttk.Entry(rechts, textvariable=self.termin, width=20).grid(row=r + 1, column=3, sticky="w")
        ttk.Label(rechts, text="Suchtext:").grid(row=r + 2, column=0, sticky="e", pady=(6, 0))
        self.suchtext = tk.StringVar()
        ttk.Entry(rechts, textvariable=self.suchtext, font=("Segoe UI", 11)).grid(row=r + 2, column=1, columnspan=3,
                                                                                sticky="we", pady=(6, 0))
        self.anh_lbl = ttk.Label(rechts, text="", foreground="#1B4F72", wraplength=560)
        self.anh_lbl.grid(row=r + 3, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.text = tk.Text(rechts, height=10, wrap="word", font=("Segoe UI", 9), relief="solid", borderwidth=1)
        self.text.grid(row=r + 4, column=0, columnspan=4, sticky="nsew", pady=(6, 0))
        rechts.rowconfigure(r + 4, weight=1)
        rechts.columnconfigure(1, weight=1)
        rechts.columnconfigure(3, weight=1)

        unten = ttk.Frame(self, padding=10)
        unten.pack(fill="x")
        self.knopf_suche = ttk.Button(unten, text="In Suche übernehmen", command=self.uebernehmen)
        self.knopf_suche.pack(side="left")
        self.knopf_erledigt = ttk.Button(unten, text="Erledigt (in Unterordner verschieben)", command=self.erledigt)
        self.knopf_erledigt.pack(side="left", padx=8)
        ttk.Label(unten, text="Angelegt wird hier noch nichts – Weclapp folgt.", foreground="#6A7380").pack(side="right")

    def _dnd(self):
        try:
            from tkinterdnd2 import DND_FILES
            for w in (self, self.tv):
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
        self.configure(cursor="watch")

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
            self.configure(cursor="")
            fertig(ergebnis.get("wert"), ergebnis.get("fehler"))

        threading.Thread(target=lauf, daemon=True).start()
        self.after(120, abfragen)

    def _gewaehlter_ordner(self) -> Anfrageordner | None:
        i = self.ordner_cb.current()
        ordner = self.app.einstellungen.anfrageordner
        return ordner[i] if 0 <= i < len(ordner) else None

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
        if kinder:
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
        self.unsicher.configure(text="", bg=self.cget("bg"))
        self.knopf_erledigt.state(["disabled"])

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
            self.entries[key].configure(bg=GELB if (leer or fraglich) else "white")
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
        self.unsicher.configure(text=hinweis, bg=GELB if e.unsicher else ("#E8F5E9" if hinweis else self.cget("bg")))
        o = self.ordner_von.get(i)
        self.knopf_erledigt.state(["!disabled"] if o else ["disabled"])
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
            self.status.configure(text=f"Nach „{ziel}“ verschoben – andere sehen, dass du sie bearbeitest.")

        self._im_hintergrund(arbeit, fertig, "Verschiebe nach „In Bearbeitung“ …")

    # ---------------------------------------------------------------- Aktionen
    def uebernehmen(self):
        if self.aktuell is None:
            return
        self._formular_lesen()
        self.app.vorgang_uebernehmen(self.mails[self.aktuell], self.erkennungen[self.aktuell])
        self.app.lift()

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
            self._leeren()
            self.status.configure(text=f"Nach „{ziel}“ verschoben.")
            rest = self.tv.get_children()
            if rest:
                self.tv.selection_set(rest[0])

        self._im_hintergrund(arbeit, fertig, "Verschiebe nach „Erledigt“ …")
