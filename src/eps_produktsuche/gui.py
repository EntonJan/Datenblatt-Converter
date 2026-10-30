"""Oberfläche der EPS-Produktsuche (Tkinter, keine Installation nötig)."""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog

from . import __version__, shop, suche as Q, verlauf, aktualisierung
from .einstellungen import Einstellungen, Anfrageordner

TESTVERSION = "dev" in __version__        # Test-Builds vom Branch: kein Selbst-Update, keine Aufräumaktion

NAVY, CYAN, GRAU = "#35528C", "#52B4D7", "#6A7380"
FARBEN = {Q.PASST: "#2E7D32", Q.GROESSER: "#1B4F72", Q.PARALLEL: "#8E5A00", Q.REIHE: "#8E5A00", Q.KNAPP_DARUNTER: "#8A8F98"}
BEISPIELE = ("z. B. „Stromquelle 0-30V 1kA 30kW“ · „E-Last 500V 100A“ · „230VAC 3kVA 400Hz“ · „19 Zoll bidirektional 80V 300A“"
             " · „ELR 10080“")


def _zentrieren(fenster: tk.Toplevel, master: tk.Misc) -> None:
    fenster.update_idletasks()
    x = master.winfo_rootx() + (master.winfo_width() - fenster.winfo_reqwidth()) // 2
    y = master.winfo_rooty() + (master.winfo_height() - fenster.winfo_reqheight()) // 3
    fenster.geometry(f"+{max(x, 0)}+{max(y, 0)}")


class VariantenDialog(tk.Toplevel):
    """Auswahl einer Variante aus einer Zahlenreihe ohne Modellnamen (z. B. „0-30 V / 0-40 A / 1,2 kW“)."""

    def __init__(self, master, varianten, datei: str = ""):
        super().__init__(master)
        self.title("Variante auswählen" + (f" – {datei}" if datei else ""))
        self.transient(master)
        self.grab_set()
        self.ergebnis = None
        self.varianten = varianten
        ttk.Label(self, text="Das Dokument enthält mehrere Varianten bzw. Ausbaustufen ohne Modellnamen.\n"
                             "Welche braucht der Kunde?", padding=10).pack(anchor="w")
        fr = ttk.Frame(self, padding=(10, 0))
        fr.pack(fill="both", expand=True)
        self.lb = tk.Listbox(fr, height=min(16, len(varianten) + 1), width=52, activestyle="dotbox", font=("Segoe UI", 10))
        sb = ttk.Scrollbar(fr, command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        for v in varianten:
            self.lb.insert("end", v.label)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.lb.bind("<Double-1>", lambda e: self.ok())
        self.lb.bind("<Return>", lambda e: self.ok())
        self.lb.selection_set(0)
        self.lb.focus_set()
        bf = ttk.Frame(self, padding=10)
        bf.pack(fill="x")
        ttk.Button(bf, text="Ohne Variante (Höchstwerte)", command=self.ohne).pack(side="left")
        ttk.Button(bf, text="Übernehmen", command=self.ok).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        _zentrieren(self, master)
        self.wait_window()

    def ok(self):
        sel = self.lb.curselection()
        if sel:
            self.ergebnis = self.varianten[sel[0]]
            self.destroy()

    def ohne(self):
        self.ergebnis = False
        self.destroy()


class OffenePunkteDialog(tk.Toplevel):
    """Warnung nach dem Einlesen einer Anfrage: Punkte, die das Programm nicht prüfen konnte – zum Abhaken/Kopieren."""

    def __init__(self, master, punkte: list[str], datei: str = ""):
        super().__init__(master)
        self.title("Ungeklärte Punkte" + (f" – {datei}" if datei else ""))
        self.transient(master)
        self.geometry("900x460")
        kopf = tk.Frame(self, bg="#FFF4D6")
        kopf.pack(fill="x")
        tk.Label(kopf, text=f"⚠  {len(punkte)} Punkte konnte das Programm nicht anhand der Shopdaten prüfen.\n"
                            "Markierte Stellen (Pflicht) müssen genau erfüllt sein – vor dem Angebot im EPS-Datenblatt "
                            "nachsehen oder mit der Technik/dem Hersteller klären.",
                 bg="#FFF4D6", fg="#5A4300", justify="left", anchor="w", padx=12, pady=10).pack(fill="x")
        fr = ttk.Frame(self, padding=10)
        fr.pack(fill="both", expand=True)
        self.vars: list[tk.BooleanVar] = []
        leinwand = tk.Canvas(fr, highlightthickness=0)
        sb = ttk.Scrollbar(fr, orient="vertical", command=leinwand.yview)
        innen = ttk.Frame(leinwand)
        innen.bind("<Configure>", lambda e: leinwand.configure(scrollregion=leinwand.bbox("all")))
        leinwand.create_window((0, 0), window=innen, anchor="nw")
        leinwand.configure(yscrollcommand=sb.set)
        leinwand.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.punkte = punkte
        for p in punkte:
            v = tk.BooleanVar(value=False)
            self.vars.append(v)
            tk.Checkbutton(innen, text=p, variable=v, wraplength=820, justify="left", anchor="w",
                           font=("Segoe UI", 10)).pack(anchor="w", fill="x", pady=2)
        unten = ttk.Frame(self, padding=10)
        unten.pack(fill="x")
        ttk.Button(unten, text="Als Liste kopieren", command=self.kopieren).pack(side="left")
        ttk.Button(unten, text="OK", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        _zentrieren(self, master)

    def kopieren(self):
        text = "\n".join(("[x] " if v.get() else "[ ] ") + p for p, v in zip(self.punkte, self.vars))
        self.clipboard_clear()
        self.clipboard_append(text)


class EinstellungenDialog(tk.Toplevel):
    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        self.title("Einstellungen")
        self.transient(app)
        self.grab_set()
        e = app.einstellungen
        fr = ttk.Frame(self, padding=14)
        fr.pack(fill="both", expand=True)
        self.experimentell = tk.BooleanVar(value=e.experimentell)
        ttk.Checkbutton(fr, text="Experimentelle Funktionen: Kundenanfragen aus Outlook (Testphase)",
                        variable=self.experimentell).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(fr, text="Anfrage-Ordner im klassischen Outlook (Pfad wie in der Ordnerliste, mit „/“ getrennt; "
                           "gemeinsames Postfach: dessen Name vorn, z. B. „vertrieb@eps-germany.de/Posteingang/Anfragen“):",
                  wraplength=640, foreground=GRAU).grid(row=1, column=0, columnspan=3, sticky="w", pady=(12, 4))
        ttk.Label(fr, text="Ordner").grid(row=2, column=0, sticky="w")
        ttk.Label(fr, text="Art").grid(row=2, column=1, sticky="w")
        ttk.Label(fr, text="gemeinsam").grid(row=2, column=2, sticky="w")
        self.zeilen = []
        ordner = list(e.anfrageordner) + [Anfrageordner("", "pruefen")] * max(0, 4 - len(e.anfrageordner))
        for i, o in enumerate(ordner[:6]):
            pfad, art, gem = tk.StringVar(value=o.pfad), tk.StringVar(value="Automatisch" if o.art == "automatisch"
                                                                      else "Selbst prüfen"), tk.BooleanVar(value=o.gemeinsam)
            ttk.Entry(fr, textvariable=pfad, width=58).grid(row=3 + i, column=0, sticky="we", pady=2)
            ttk.Combobox(fr, textvariable=art, values=["Automatisch", "Selbst prüfen"], state="readonly",
                         width=14).grid(row=3 + i, column=1, padx=6)
            ttk.Checkbutton(fr, variable=gem).grid(row=3 + i, column=2)
            self.zeilen.append((pfad, art, gem))
        r = 3 + len(self.zeilen)
        ttk.Label(fr, text="Unterordner für erledigte Mails:").grid(row=r, column=0, sticky="w", pady=(12, 2))
        self.erledigt = tk.StringVar(value=e.ordner_erledigt)
        ttk.Entry(fr, textvariable=self.erledigt, width=20).grid(row=r, column=1, columnspan=2, sticky="w", pady=(12, 2))
        ttk.Label(fr, text="Unterordner „in Bearbeitung“ (gemeinsame Postfächer):").grid(row=r + 1, column=0, sticky="w")
        self.bearbeitung = tk.StringVar(value=e.ordner_in_bearbeitung)
        ttk.Entry(fr, textvariable=self.bearbeitung, width=20).grid(row=r + 1, column=1, columnspan=2, sticky="w")
        ttk.Label(fr, text="Einkaufspreis gilt als zu alt nach (Monaten, für Weclapp):").grid(row=r + 2, column=0, sticky="w")
        self.frist = tk.IntVar(value=e.preisfrist_monate)
        ttk.Spinbox(fr, from_=1, to=36, width=5, textvariable=self.frist).grid(row=r + 2, column=1, sticky="w")
        bf = ttk.Frame(self, padding=(14, 0, 14, 14))
        bf.pack(fill="x")
        ttk.Button(bf, text="Speichern", command=self.speichern).pack(side="right")
        ttk.Button(bf, text="Abbrechen", command=self.destroy).pack(side="right", padx=6)
        self.bind("<Escape>", lambda ev: self.destroy())
        _zentrieren(self, app)

    def speichern(self):
        e = self.app.einstellungen
        e.experimentell = self.experimentell.get()
        e.anfrageordner = [Anfrageordner(p.get().strip(), "automatisch" if a.get() == "Automatisch" else "pruefen",
                                         g.get()) for p, a, g in self.zeilen if p.get().strip()]
        e.ordner_erledigt = self.erledigt.get().strip() or "Erledigt"
        e.ordner_in_bearbeitung = self.bearbeitung.get().strip() or "In Bearbeitung"
        try:
            e.preisfrist_monate = max(1, int(self.frist.get()))
        except (tk.TclError, ValueError):
            pass
        try:
            e.speichern(self.app.einstellungen_pfad)
        except OSError as ex:
            messagebox.showerror("Einstellungen", f"Konnte nicht gespeichert werden:\n{ex}", parent=self)
            return
        self.app._experimentell_zeigen()
        self.destroy()


class VerlaufDialog(tk.Toplevel):
    """Letzte Anfragen: Doppelklick/„Übernehmen“ holt Anfrage und Kunden-Datenblatt zurück."""

    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        self.title("Verlauf der Anfragen")
        self.geometry("1100x520")
        self.transient(app)
        oben = ttk.Frame(self, padding=(10, 10, 10, 4))
        oben.pack(fill="x")
        ttk.Label(oben, text="Suchen:").pack(side="left")
        self.filter = tk.StringVar()
        e = ttk.Entry(oben, textvariable=self.filter, width=40)
        e.pack(side="left", padx=6)
        self.anzahl = ttk.Label(oben, text="", foreground=GRAU)
        self.anzahl.pack(side="right")
        sp = [("zeit", "Zeit", 115), ("anfrage", "Anfrage", 300), ("datei", "Kunden-Datenblatt", 220),
              ("geraete", "Empfohlene Geräte", 280), ("aktion", "Aktion", 130), ("notiz", "Notiz", 200)]
        fr = ttk.Frame(self, padding=(10, 0))
        fr.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(fr, columns=[x[0] for x in sp], show="headings", selectmode="browse")
        for k, t, b in sp:
            self.tv.heading(k, text=t)
            self.tv.column(k, width=b, stretch=k in ("anfrage", "geraete", "notiz"))
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        unten = ttk.Frame(self, padding=10)
        unten.pack(fill="x")
        ttk.Button(unten, text="Übernehmen", command=self.uebernehmen).pack(side="left")
        ttk.Button(unten, text="Notiz …", command=self.notiz).pack(side="left", padx=6)
        ttk.Button(unten, text="Eintrag löschen", command=self.loeschen).pack(side="left", padx=6)
        ttk.Button(unten, text="Schließen", command=self.destroy).pack(side="right")
        self.tv.bind("<Double-1>", lambda ev: self.uebernehmen())
        self.tv.bind("<Return>", lambda ev: self.uebernehmen())
        self.filter.trace_add("write", lambda *a: self.fuellen())
        self.bind("<Escape>", lambda ev: self.destroy())
        e.focus_set()
        self.fuellen()

    def fuellen(self):
        self.eintraege = verlauf.laden(self.app.verlauf_pfad)
        self.tv.delete(*self.tv.get_children())
        n = 0
        for i, e in enumerate(self.eintraege):
            if not verlauf.passt(e, self.filter.get()):
                continue
            f = e.get("fremd") or {}
            try:
                zeit = datetime.fromisoformat(e["zeit"]).strftime("%d.%m.%Y %H:%M")
            except (KeyError, ValueError):
                zeit = e.get("zeit", "")
            geraete = ", ".join(f"{g['bestellnummer']} {g['name']}" for g in e.get("geraete", []))
            self.tv.insert("", "end", iid=str(i), values=[zeit, e.get("anfrage", ""), f.get("datei", ""), geraete,
                                                          ", ".join(e.get("aktionen", [])), e.get("notiz", "")])
            n += 1
        self.anzahl.configure(text=f"{n} von {len(self.eintraege)} Einträgen")

    def _gewaehlt(self) -> int | None:
        sel = self.tv.selection()
        return int(sel[0]) if sel else None

    def uebernehmen(self):
        i = self._gewaehlt()
        if i is not None:
            self.app.verlauf_uebernehmen(self.eintraege[i])
            self.destroy()

    def notiz(self):
        i = self._gewaehlt()
        if i is None:
            return
        neu = simpledialog.askstring("Notiz", "Notiz zu dieser Anfrage (z. B. Kunde, Angebotsnummer):",
                                     initialvalue=self.eintraege[i].get("notiz", ""), parent=self)
        if neu is not None:
            verlauf.notiz_setzen(self.app.verlauf_pfad, i, neu)
            self.fuellen()

    def loeschen(self):
        i = self._gewaehlt()
        if i is not None and messagebox.askyesno("Verlauf", "Diesen Eintrag löschen?", parent=self):
            verlauf.loeschen(self.app.verlauf_pfad, i)
            self.fuellen()


def _fehlertext(e: Exception) -> str:
    t = str(e)
    if "timed out" in t or isinstance(e, TimeoutError):
        return "Zeitüberschreitung – der Shop hat nicht rechtzeitig geantwortet"
    return t


def programmordner() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(os.environ.get("EPS_PRODUKTSUCHE_HOME", Path.home() / ".eps-produktsuche"))


def datenpfad() -> Path:
    return programmordner() / "EPS-Produktsuche-Daten" / "shopdaten.json"


def ressource(name: str) -> Path:
    basis = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return basis / "assets" / name


def datei_oeffnen(pfad: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(pfad))  # noqa: S606 – eigene Datei im Programmordner
    else:
        webbrowser.open(Path(pfad).resolve().as_uri())


class App(tk.Tk):
    def __init__(self, pfad: Path | None = None, automatisch_laden: bool = True, update_pruefen: bool | None = None):
        super().__init__()
        self.title(f"EPS-Produktsuche {__version__}")
        self.geometry("1320x740")
        self.minsize(1000, 540)
        try:
            self.iconbitmap(str(ressource("icon.ico")))
        except tk.TclError:
            pass
        self.pfad = pfad or datenpfad()
        self.verlauf_pfad = self.pfad.parent / "verlauf.json"
        self.einstellungen_pfad = self.pfad.parent / "einstellungen.json"
        self.einstellungen = Einstellungen.laden(self.einstellungen_pfad)
        self.vorgang = None                     # aktuelle Kundenanfrage aus Outlook/Mail (kunde.Erkennung + Mail)
        self.geraete, self.stand = shop.laden(self.pfad)
        self.treffer: list[Q.Treffer] = []
        self.zeilen_geraete: list[shop.Geraet] = []
        self.iid_index: dict[str, int] = {}
        self.fremd = None
        self.fremd_anfrage = ""
        self.laedt = False
        self.beschaeftigt = False
        self._stil()
        self._aufbauen()
        self._status()
        self.suchen()
        veraltetes_format = bool(self.geraete) and shop.datenformat(self.pfad) < shop.DATENFORMAT
        if automatisch_laden and (not self.geraete or shop.veraltet(self.stand) or veraltetes_format):
            self.after(300, lambda: self.einlesen(still=bool(self.geraete)))
        if update_pruefen is None:
            update_pruefen = aktualisierung.ist_exe() and not TESTVERSION
        if aktualisierung.ist_exe() and not TESTVERSION:
            threading.Thread(target=aktualisierung.alte_entfernen, daemon=True).start()
        if update_pruefen:
            self.after(2500, lambda: self.updates_suchen(still=True))

    # ------------------------------------------------------------------ Aufbau
    def _stil(self):
        s = ttk.Style(self)
        try:
            s.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            pass
        s.configure("Treeview", rowheight=24)
        s.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _aufbauen(self):
        kopf = tk.Frame(self, bg=NAVY)
        kopf.pack(fill="x")
        tk.Label(kopf, text="EPS-Produktsuche", fg="white", bg=NAVY, font=("Segoe UI", 15, "bold")).pack(side="left", padx=14, pady=10)
        tk.Label(kopf, text=f"Version {__version__} · intern", fg=CYAN, bg=NAVY).pack(side="left")
        self.knopf_laden = ttk.Button(kopf, text="Shop neu einlesen", command=lambda: self.einlesen(still=False))
        self.knopf_laden.pack(side="right", padx=(4, 10))
        ttk.Button(kopf, text="Updates", command=lambda: self.updates_suchen(still=False)).pack(side="right", padx=4)
        ttk.Button(kopf, text="Verlauf …", command=lambda: VerlaufDialog(self)).pack(side="right", padx=4)
        ttk.Button(kopf, text="Einstellungen …", command=lambda: EinstellungenDialog(self)).pack(side="right", padx=4)
        self.knopf_anfragen = ttk.Button(kopf, text="Anfragen (Outlook) …", command=self.anfragen_oeffnen)
        self.kopf = kopf
        self._experimentell_zeigen()
        self.stand_lbl = tk.Label(kopf, text="", fg="white", bg=NAVY)
        self.stand_lbl.pack(side="right", padx=10)

        oben = ttk.Frame(self, padding=(12, 10, 12, 0))
        oben.pack(fill="x")
        ttk.Label(oben, text="Kundenanfrage:", font=("Segoe UI", 10, "bold"), foreground=NAVY).pack(side="left")
        self.eingabe = tk.StringVar()
        self.feld = ttk.Entry(oben, textvariable=self.eingabe, font=("Segoe UI", 13))
        self.feld.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(oben, text="Gerätetyp:").pack(side="left")
        self.typ = tk.StringVar(value="automatisch")
        self.typ_cb = ttk.Combobox(oben, textvariable=self.typ, state="readonly", width=20,
                                   values=["automatisch", "alle", *Q.GERAETETYPEN])
        self.typ_cb.pack(side="left", padx=(4, 0))
        self.knopf_pdf = ttk.Button(oben, text="Kunden-Dokument (PDF/Word) …", command=self.datenblatt_waehlen)
        self.knopf_pdf.pack(side="left", padx=(12, 0))

        self.fremd_lbl = tk.Label(self, text="", anchor="w", justify="left", bg="#EEF4FA", fg="#1C2633",
                                  padx=12, pady=6, wraplength=1250, cursor="hand2")
        self.fremd_lbl.bind("<Button-1>", lambda e: self.offene_punkte() and
                            OffenePunkteDialog(self, self.offene_punkte(), self.fremd.datei))

        opt = ttk.Frame(self, padding=(12, 4, 12, 0))
        opt.pack(fill="x")
        self.erkannt = ttk.Label(opt, text=BEISPIELE, foreground=GRAU)
        self.erkannt.pack(side="left")
        self.max_par = tk.IntVar(value=10)
        ttk.Spinbox(opt, from_=1, to=64, width=4, textvariable=self.max_par, command=self.suchen).pack(side="right")
        ttk.Label(opt, text="max. Geräte parallel/in Reihe:").pack(side="right", padx=(16, 4))
        self.knapp = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="auch knapp darunter (bis −10 %)", variable=self.knapp, command=self.suchen).pack(side="right")
        self.gruppieren = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="nach Serie gruppieren", variable=self.gruppieren, command=self.suchen).pack(side="right", padx=12)

        sp = [("bew", "Bewertung", 100), ("nr", "Bestellnr.", 70), ("name", "Gerät", 270), ("typ", "Gerätetyp", 105),
              ("u", "Spannung", 115), ("i", "Strom", 85), ("p", "Leistung", 115), ("res", "Reserve", 150), ("hin", "Hinweis", 230)]
        tf = ttk.Frame(self, padding=(12, 8, 12, 0))
        tf.pack(fill="both", expand=True)
        self.tabelle_rahmen = tf
        self.tv = ttk.Treeview(tf, columns=[x[0] for x in sp], show="tree headings", selectmode="extended")
        self.tv.column("#0", width=28, minwidth=28, stretch=False)
        for k, t, b in sp:
            self.tv.heading(k, text=t)
            self.tv.column(k, width=b, minwidth=50, stretch=k in ("name", "hin"))
        for kat, farbe in FARBEN.items():
            self.tv.tag_configure(kat, foreground=farbe)
        self.tv.tag_configure("serie", font=("Segoe UI", 9, "bold"))
        sy = ttk.Scrollbar(tf, orient="vertical", command=self.tv.yview)
        sx = ttk.Scrollbar(tf, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tv.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)

        self.info = ttk.Label(self, text="", foreground=GRAU, padding=(12, 4, 12, 0))
        self.info.pack(fill="x")
        self.fortschritt = ttk.Progressbar(self, mode="determinate")

        unten = ttk.Frame(self, padding=12)
        unten.pack(fill="x")
        ttk.Button(unten, text="Datenblatt (PDF)", command=self.pdf).pack(side="left")
        ttk.Button(unten, text="Shopseite", command=self.shopseite).pack(side="left", padx=6)
        ttk.Button(unten, text="Empfehlung kopieren (DE)", command=lambda: self.kopieren("de")).pack(side="left", padx=(18, 0))
        ttk.Button(unten, text="(EN)", width=5, command=lambda: self.kopieren("en")).pack(side="left", padx=4)
        ttk.Button(unten, text="Gegenüberstellung PDF (DE)", command=lambda: self.gegenueberstellung("de")).pack(side="left", padx=(18, 0))
        ttk.Button(unten, text="(EN)", width=5, command=lambda: self.gegenueberstellung("en")).pack(side="left", padx=4)
        ttk.Label(unten, text="Enter: im Verlauf merken · Doppelklick: Datenblatt · Strg+C: Empfehlung · Strg+O: Kunden-Dokument",
                  foreground=GRAU).pack(side="right")

        self.eingabe.trace_add("write", lambda *a: self.suchen())
        self.typ_cb.bind("<<ComboboxSelected>>", lambda e: self.suchen())
        self.max_par.trace_add("write", lambda *a: self.after_idle(self.suchen))
        self.tv.bind("<Double-1>", self._doppelklick)
        self.tv.bind("<Return>", lambda e: self.pdf())
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._details())
        self.bind_all("<Control-c>", lambda e: self.kopieren("de") if self.focus_get() is not self.feld else None)
        self.feld.bind("<Escape>", lambda e: self.eingabe.set(""))
        self.feld.bind("<Down>", lambda e: self._in_liste())
        self.feld.bind("<Return>", lambda e: self._merken("Suche"))
        self.bind_all("<Control-o>", lambda e: (self.datenblatt_waehlen(), "break")[1])
        self._dnd_einrichten()
        self.feld.focus_set()

    def _in_liste(self):
        k = self.tv.get_children()
        if k:
            self.tv.focus_set()
            self.tv.selection_set(k[0])
            self.tv.focus(k[0])
        return "break"

    def _doppelklick(self, e):
        if self.tv.identify_region(e.x, e.y) == "tree":
            return                                    # Klick auf den Aufklapp-Pfeil
        self.pdf()

    # ------------------------------------------------------------------ Hintergrundarbeit
    def _hintergrund(self, arbeit, fertig, text: str):
        """arbeit() läuft in einem Thread, fertig(wert, fehler) danach im Hauptthread (Tk ist nicht threadsicher)."""
        ergebnis: dict = {}
        self.beschaeftigt = True
        self.knopf_pdf.state(["disabled"])
        self.info.configure(text=text)
        self.fortschritt.configure(mode="indeterminate")
        self.fortschritt.pack(fill="x", padx=12, before=self.info)
        self.fortschritt.start(12)
        self.configure(cursor="watch")

        def lauf():
            try:
                ergebnis["wert"] = arbeit()
            except Exception as ex:  # noqa: BLE001
                ergebnis["fehler"] = ex
            ergebnis["fertig"] = True

        def abfragen():
            if not ergebnis.get("fertig"):
                self.after(100, abfragen)
                return
            self.fortschritt.stop()
            self.fortschritt.configure(mode="determinate")
            self.fortschritt.pack_forget()
            self.configure(cursor="")
            self.knopf_pdf.state(["!disabled"])
            self.beschaeftigt = False
            fertig(ergebnis.get("wert"), ergebnis.get("fehler"))

        threading.Thread(target=lauf, daemon=True).start()
        self.after(100, abfragen)

    # ------------------------------------------------------------------ Suche
    def anfrage(self) -> Q.Anfrage:
        a = Q.anfrage_lesen(self.eingabe.get())
        wahl = self.typ.get()
        if wahl == "alle":
            a.geraetetyp, a.last = "", False
        elif wahl != "automatisch":
            a.geraetetyp, a.last = wahl, wahl == shop.LAST
        return a

    def suchen(self):
        self.tv.delete(*self.tv.get_children())
        self.treffer, self.zeilen_geraete, self.iid_index = [], [], {}
        text = self.eingabe.get().strip()
        a = self.anfrage()
        if not self.geraete:
            self.erkannt.configure(text="Noch keine Shopdaten – „Shop neu einlesen“ (dauert ca. 1–3 Minuten).")
            return
        if self.fremd and text != self.fremd_anfrage:
            self.fremd_lbl.configure(text=self.fremd_lbl.cget("text").split("  ·  Anfrage geändert")[0]
                                     + "  ·  Anfrage geändert")
        if a.leer():
            self.erkannt.configure(text=BEISPIELE if not text else "Keine V/A/W erkannt – Suche nach Name/Bestellnummer:")
            if text:
                for g in Q.textsuche(self.geraete, text)[:300]:
                    self._zeile("", g, "", "", ())
                self.info.configure(text=f"{len(self.zeilen_geraete)} Geräte mit „{text}“")
            else:
                self.info.configure(text=f"{len(self.geraete)} Geräte aus dem Shop durchsuchbar.")
            return
        self.erkannt.configure(text="Erkannt: " + " · ".join(a.erkannt))
        try:
            maxp = max(1, int(self.max_par.get()))
        except (tk.TclError, ValueError):
            maxp = 10
        self.treffer = Q.suchen(self.geraete, a, self.knapp.get(), maxp)
        if self.gruppieren.get():
            gruppen = Q.nach_serie(self.treffer)
            for serie, liste in gruppen:
                erster = liste[0]
                hinweis = erster.hinweis
                # weitere Geräte der Serie, die ebenfalls genau passen (z. B. gleiche Ausgangswerte, anderer Eingang):
                # nicht im zugeklappten Teil verstecken
                gleich = [t for t in liste[1:] if t.kategorie == Q.PASST] if erster.kategorie == Q.PASST else []
                if len(liste) > 1:
                    hinweis = f"+{len(liste) - 1} weitere der Serie" + \
                        (f", davon {len(gleich)} ebenfalls „passt genau“ (aufgeklappt)" if gleich else "") + \
                        (self._eingang_hinweis([erster, *gleich], a) if gleich else "") + \
                        (f"; {hinweis}" if hinweis else "")
                eltern = self._zeile(erster.bewertung, erster.g, erster.reserve_text(), hinweis, (erster.kategorie,))
                if gleich:
                    self.tv.item(eltern, open=True)
                for t in liste[1:]:
                    self._zeile(t.bewertung, t.g, t.reserve_text(), t.hinweis, (t.kategorie,), eltern=eltern)
            serien_text = f" in {len(gruppen)} Serien"
        else:
            for t in self.treffer:
                self._zeile(t.bewertung, t.g, t.reserve_text(), t.hinweis, (t.kategorie,))
            serien_text = ""
        n = {k: sum(1 for t in self.treffer if t.kategorie == k) for k in FARBEN}
        self.info.configure(text=f"{len(self.treffer)} Treffer{serien_text}: {n[Q.PASST]} passen genau, {n[Q.GROESSER]} größer, "
                                 f"{n[Q.PARALLEL] + n[Q.REIHE]} mit mehreren Geräten, {n[Q.KNAPP_DARUNTER]} knapp darunter"
                                 + (" – Gerätetyp auf „alle“ stellen?" if not self.treffer and a.geraetetyp else ""))

    @staticmethod
    def _eingang_hinweis(treffer: list[Q.Treffer], a: Q.Anfrage) -> str:
        eingaenge = sorted({t.g.u_eingang for t in treffer if t.g.u_eingang})
        if len(eingaenge) > 1 and not a.eingang:
            return (" – unterscheiden sich im DC-Eingang (" + "/".join(f"{e:g}" for e in eingaenge) +
                    " V): „Eingang …VDC“ ins Suchfeld schreiben")
        return ""

    def _zeile(self, bew, g: shop.Geraet, reserve, hinweis, tags, eltern: str = "") -> str:
        iid = str(len(self.zeilen_geraete))
        self.zeilen_geraete.append(g)
        self.iid_index[iid] = int(iid)
        typ = g.geraetetyp + (" (bidir.)" if g.bidirektional and g.geraetetyp != shop.LAST else "")
        self.tv.insert(eltern, "end", iid=iid, tags=tags, open=False,
                       values=[bew, g.bestellnummer, g.name, typ, g.spannung or "–", g.strom or "–", g.leistung or "–",
                               reserve, hinweis])
        return iid

    def _auswahl(self) -> list[int]:
        return [self.iid_index[i] for i in self.tv.selection() if i in self.iid_index]

    def _treffer_zu(self, g: shop.Geraet) -> Q.Treffer:
        return next((t for t in self.treffer if t.g is g), None) or Q.Treffer(g, Q.PASST)

    def _ausgewaehlte_treffer(self, standard: int = 3) -> list[Q.Treffer]:
        sel = self._auswahl()
        if sel:
            return [self._treffer_zu(self.zeilen_geraete[i]) for i in sel]
        genau = [t for t in self.treffer if t.kategorie == Q.PASST]
        return (genau or [t for t in self.treffer if t.kategorie != Q.KNAPP_DARUNTER])[:standard]

    def _details(self):
        sel = self._auswahl()
        if len(sel) == 1:
            g = self.zeilen_geraete[sel[0]]
            t = next((t for t in self.treffer if t.g is g), None)
            teile = [g.name, g.serie]
            if t:
                teile += [t.bewertung, t.reserve_text(), t.hinweis]
            self.info.configure(text=" · ".join(x for x in teile if x))
        elif sel:
            self.info.configure(text=f"{len(sel)} Geräte ausgewählt – Empfehlung und Gegenüberstellung übernehmen alle.")

    # ------------------------------------------------------------------ Aktionen
    def pdf(self):
        sel = self._auswahl()
        if sel:
            g = self.zeilen_geraete[sel[0]]
            webbrowser.open(g.pdf_url or g.shop_url)

    def shopseite(self):
        sel = self._auswahl()
        if not sel:
            return
        g = self.zeilen_geraete[sel[0]]
        url = g.seite_url or g.shop_url
        if url:
            webbrowser.open(url)
        if not g.seite_url:
            self.info.configure(text="Shopdaten sind älter – es öffnet die Serienseite. Nach „Shop neu einlesen“ "
                                     "springt der Link direkt zum Gerät.")

    def _alternative_zu(self) -> str:
        if self.fremd and self.eingabe.get().strip() == self.fremd_anfrage:
            return self.fremd.hersteller_typ or self.fremd.modell
        return ""

    def kopieren(self, sprache: str):
        tr = self._ausgewaehlte_treffer()
        if not tr:
            self.info.configure(text="Bitte zuerst ein oder mehrere Geräte auswählen (Strg/Umschalt + Klick).")
            return
        self.clipboard_clear()
        self.clipboard_append(Q.empfehlung(tr, self.anfrage(), sprache, alternative_zu=self._alternative_zu()))
        self.info.configure(text=f"Empfehlung mit {len(tr)} Gerät(en) in die Zwischenablage kopiert ({sprache.upper()}).")
        self._merken(f"Empfehlung {sprache.upper()}", tr)

    def gegenueberstellung(self, sprache: str):
        from . import vergleich
        tr = self._ausgewaehlte_treffer(standard=3)[:vergleich.MAX_VORSCHLAEGE]
        if not tr:
            self.info.configure(text="Bitte zuerst bis zu vier Geräte auswählen (Strg + Klick).")
            return
        a = self.anfrage()
        fremd = self.fremd if self._alternative_zu() else None
        ordner = self.pfad.parent / "Gegenueberstellungen"
        ziel = ordner / vergleich.dateiname(fremd, a, sprache)
        for n in range(2, 50):
            try:
                vergleich.erzeugen(ziel, tr, a, fremd, sprache)
                break
            except PermissionError:                     # gleichnamiges PDF ist noch geöffnet
                ziel = ziel.with_name(f"{ziel.stem.rsplit('_(', 1)[0]}_({n}).pdf")
        else:
            messagebox.showerror("Gegenüberstellung", "Das PDF konnte nicht gespeichert werden.", parent=self)
            return
        self.info.configure(text=f"Gegenüberstellung gespeichert: {ziel}")
        self._merken(f"Gegenüberstellung {sprache.upper()}", tr)
        try:
            datei_oeffnen(ziel)
        except OSError:
            pass

    # ------------------------------------------------------------------ Verlauf
    def _merken(self, aktion: str, treffer: list[Q.Treffer] | None = None):
        text = self.eingabe.get().strip()
        if not text:
            return
        fremd = asdict(self.fremd) if self.fremd and text == self.fremd_anfrage else None
        geraete = [{"bestellnummer": t.g.bestellnummer, "name": t.g.name} for t in (treffer or [])]
        try:
            verlauf.hinzufuegen(self.verlauf_pfad, text, aktion, geraete, self.typ.get(), fremd)
        except OSError:
            pass

    # ------------------------------------------------------------------ Anfragen (experimentell)
    def _experimentell_zeigen(self):
        if self.einstellungen.experimentell:
            self.knopf_anfragen.pack(side="right", padx=4)
        else:
            self.knopf_anfragen.pack_forget()

    def anfragen_oeffnen(self):
        fenster = getattr(self, "_anfragen_fenster", None)
        if fenster is not None and fenster.winfo_exists():
            fenster.lift()
            return
        from .anfragen import AnfragenFenster
        self._anfragen_fenster = AnfragenFenster(self)

    def vorgang_uebernehmen(self, mail, erkennung):
        """Anfrage aus dem Anfragen-Fenster in die Suche holen. Anhang (PDF/Word) hat Vorrang vor dem Mailtext."""
        self.vorgang = (mail, erkennung)
        self.fremd, self.fremd_anfrage = None, ""
        self.fremd_lbl.pack_forget()
        self.typ.set("automatisch")
        if mail.anhaenge:
            self.datenblatt_laden(mail.anhaenge[0])
        else:
            self.eingabe.set(erkennung.suchtext)
        k = erkennung.kunde
        self.info.configure(text=f"Anfrage von {k.firmenname or k.email} übernommen"
                                 + (f" – {len(mail.anhaenge)} Anhang/Anhänge" if mail.anhaenge else ""))
        self.feld.focus_set()

    def verlauf_uebernehmen(self, e: dict):
        from . import datenblatt
        f = e.get("fremd")
        if f:
            felder = datenblatt.Fremdgeraet.__dataclass_fields__
            self._fremd_anzeigen(datenblatt.Fremdgeraet(**{k: v for k, v in f.items() if k in felder}), aus_verlauf=True)
        else:
            self.fremd, self.fremd_anfrage = None, ""
            self.fremd_lbl.pack_forget()
        typ = e.get("typ") or "automatisch"
        self.typ.set(typ if typ in self.typ_cb["values"] else "automatisch")
        self.eingabe.set(e.get("anfrage", ""))
        if f:
            self._offene_punkte_zeigen(still=True)
        if e.get("geraete"):
            nummern = {g["bestellnummer"] for g in e["geraete"]}
            sel = [iid for iid, i in self.iid_index.items() if self.zeilen_geraete[i].bestellnummer in nummern]
            for iid in sel:
                self.tv.see(iid)
            self.tv.selection_set(sel)
        self.feld.focus_set()

    # ------------------------------------------------------------------ Kunden-Datenblatt
    def _dnd_einrichten(self):
        """PDF ins Fenster ziehen (tkinterdnd2; fehlt die Bibliothek, gibt es nur den Button)."""
        try:
            from tkinterdnd2 import TkinterDnD, DND_FILES
            TkinterDnD._require(self)
            for w in (self, self.tv, self.feld):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._drop)
        except Exception:  # noqa: BLE001
            pass

    def _drop(self, e):
        pfade = [Path(p) for p in self.tk.splitlist(e.data) if p.lower().endswith((".pdf", ".docx", ".docm"))]
        if pfade:
            self.after(10, lambda: self.datenblatt_laden(pfade[0]))
        return "copy"

    def datenblatt_waehlen(self):
        from tkinter import filedialog
        pfad = filedialog.askopenfilename(parent=self, title="Datenblatt des Kunden öffnen",
                                          filetypes=[("PDF oder Word", "*.pdf *.docx *.docm"), ("PDF", "*.pdf"),
                                                     ("Word", "*.docx *.docm"), ("Alle Dateien", "*.*")])
        if pfad:
            self.datenblatt_laden(Path(pfad))

    def datenblatt_laden(self, pfad: Path, fertig_cb=None):
        """Kunden-/Fremddatenblatt auslesen (im Hintergrund), Modell/Variante wählen lassen, Anfrage ins Suchfeld setzen."""
        from . import datenblatt
        if self.beschaeftigt:
            return

        def fehler_melden(fehler):
            messagebox.showerror("Kunden-Datenblatt", f"Das PDF konnte nicht gelesen werden:\n{fehler}", parent=self)
            self.info.configure(text="")

        def nach_analyse(analyse, fehler):
            if fehler:
                return fehler_melden(fehler)
            modell = variante = None
            if analyse.modelle and analyse.hat_text:
                from eps_converter.importieren import ModellDialog
                d = ModellDialog(self, analyse.modelle, pfad.name)
                if d.ergebnis is None:
                    self.info.configure(text="Abgebrochen – kein Modell gewählt.")
                    return
                modell = d.ergebnis or None
            elif len(analyse.varianten) > 1:
                d = VariantenDialog(self, analyse.varianten, pfad.name)
                if d.ergebnis is None:
                    self.info.configure(text="Abgebrochen – keine Variante gewählt.")
                    return
                variante = d.ergebnis or None
            self._hintergrund(lambda: datenblatt.lesen(pfad, modell, variante), nach_lesen, f"Werte aus {pfad.name} …")

        def nach_lesen(fg, fehler):
            if fehler:
                return fehler_melden(fehler)
            self._fremd_anzeigen(fg)
            self.typ.set("automatisch")
            self.eingabe.set(self.fremd_anfrage)
            self.feld.focus_set()
            self.feld.icursor("end")
            if fg.leer():
                self.info.configure(text="Keine Werte erkannt – bitte Spannung/Strom/Leistung von Hand ins Suchfeld eintragen.")
            self._merken("Kunden-Datenblatt")
            self._offene_punkte_zeigen(still=False)
            if fertig_cb:
                fertig_cb(fg)

        self._hintergrund(lambda: datenblatt.analysieren(pfad), nach_analyse, f"Lese {pfad.name} …")

    def offene_punkte(self) -> list[str]:
        from . import anforderung
        if not self.fremd:
            return []
        hinweise = [t.hinweis for t in self.treffer[:3] if t.hinweis]
        return anforderung.offene_punkte(self.fremd, hinweise)

    def _offene_punkte_zeigen(self, still: bool = True):
        """Warnung am Ende des Einlesens: was die Suche nicht selbst klären konnte."""
        offen = self.offene_punkte()
        if offen:
            self.fremd_lbl.configure(text=self.fremd_lbl.cget("text") +
                                     f"\n⚠ {len(offen)} ungeklärte Punkte – vor dem Angebot klären (hier klicken für die Liste)")
        if offen and not still:
            OffenePunkteDialog(self, offen, self.fremd.datei)

    def _fremd_anzeigen(self, fg, aus_verlauf: bool = False):
        self.fremd = fg
        self.fremd_anfrage = fg.anfrage()
        werte = " · ".join(f"{n}: {t}" for n, t in (("Spannung", fg.spannung), ("Strom", fg.strom), ("Leistung", fg.leistung)) if t)
        word = fg.datei.lower().endswith((".docx", ".docm"))
        kopf = (f"Kunden-Dokument: {fg.datei}" if word else f"Kunden-Datenblatt: {fg.datei}") + \
            (f" – {'Ausbaustufe' if word else 'Modell'} {fg.modell}" if fg.modell else "")
        if fg.geraetetyp:
            kopf += f" – {', '.join(fg.geraetetyp)}"
        if aus_verlauf:
            kopf += "  (aus dem Verlauf)"
        self.fremd_lbl.configure(text="\n".join([kopf, werte or "Keine Werte gefunden."] + fg.hinweise))
        self.fremd_lbl.pack(fill="x", padx=12, pady=(6, 0), before=self.tabelle_rahmen)

    # ------------------------------------------------------------------ Shopdaten
    def _status(self):
        if self.stand:
            try:
                st = datetime.fromisoformat(self.stand).strftime("%d.%m.%Y %H:%M")
            except ValueError:
                st = self.stand
            self.stand_lbl.configure(text=f"Shopdaten: {len(self.geraete)} Geräte · Stand {st}")
        else:
            self.stand_lbl.configure(text="Shopdaten: noch nicht eingelesen")

    def _alter_stand(self) -> list[shop.Geraet]:
        """Aktuelle Daten plus Geräte aus shopdaten_vorher.json, die darin fehlen (falls schon einmal etwas verloren ging)."""
        vorher, _ = shop.laden(self.pfad.with_name("shopdaten_vorher.json"))
        bekannt = {g.bestellnummer + "|" + g.name for g in self.geraete}
        return self.geraete + [g for g in vorher if g.bestellnummer + "|" + g.name not in bekannt]

    def einlesen(self, still: bool = False):
        if self.laedt:
            return
        self.laedt = True
        self.knopf_laden.state(["disabled"])
        self.knopf_laden.configure(text="Shop wird gelesen …")
        self.fortschritt.pack(fill="x", padx=12, before=self.info)
        self.fortschritt.configure(value=0, maximum=100, mode="indeterminate")   # bis die Serienliste steht
        self.fortschritt.start(12)
        grund_text = "automatisch" if still else "neu"
        self.stand_lbl.configure(text=f"Shop wird {grund_text} eingelesen – verbinde …")
        ergebnis: dict = {}
        meldungen: queue.Queue = queue.Queue()      # Tk darf nur aus dem Hauptthread angefasst werden

        def melden(text, erledigt, gesamt):
            meldungen.put((text, erledigt, gesamt))

        bekannte = self._alter_stand()

        def lauf():
            try:
                fehlend: list[str] = []
                bekannt = sorted({g.shop_url for g in bekannte if g.shop_url})
                neu = shop.einlesen(fortschritt=melden, unvollstaendig=fehlend, bekannte_serien=bekannt)
                if bekannt and len(neu) < 50:          # praktisch nichts erreicht: nicht den alten Stand „neu“ nennen
                    raise OSError(f"Der Shop antwortet nicht (nur {len(neu)} Geräte gelesen)")
                ergebnis["geraete"] = neu
                ergebnis["fehlend"] = fehlend
            except Exception as e:  # noqa: BLE001 – Netzwerkfehler o. Ä. sauber melden
                ergebnis["fehler"] = e
            ergebnis["fertig"] = True

        def abfragen():
            try:
                while True:
                    text, erledigt, gesamt = meldungen.get_nowait()
                    if str(self.fortschritt.cget("mode")) == "indeterminate":
                        self.fortschritt.stop()
                        self.fortschritt.configure(mode="determinate")
                    self.fortschritt.configure(maximum=max(gesamt, 1), value=erledigt)
                    # in der Kopfzeile: die Infozeile unten wird beim Tippen von der Suche überschrieben
                    self.stand_lbl.configure(text=f"Shop wird eingelesen … Serie {erledigt}/{gesamt}")
            except queue.Empty:
                pass
            if ergebnis.get("fertig"):
                fertig()
            else:
                self.after(150, abfragen)

        def fertig():
            self.laedt = False
            self.knopf_laden.state(["!disabled"])
            self.knopf_laden.configure(text="Shop neu einlesen")
            self.fortschritt.stop()
            self.fortschritt.configure(mode="determinate")
            self.fortschritt.pack_forget()
            self._status()
            if "fehler" in ergebnis:
                fehler = ergebnis["fehler"]
                self.info.configure(text=f"Shop nicht erreichbar ({_fehlertext(fehler)}) – es wird mit dem bisherigen Stand gesucht.")
                self.stand_lbl.configure(text=self.stand_lbl.cget("text") + " · Shop nicht erreichbar")
                if not still:
                    messagebox.showerror("Shop einlesen", f"Der Onlineshop konnte nicht gelesen werden:\n{_fehlertext(fehler)}\n\n"
                                                          "Öffnet www.eps-germany.de/shop im Browser normal, ist der Shop "
                                                          "gerade nur für Programme langsam – später noch einmal versuchen.\n"
                                                          "Die bisherigen Daten bleiben erhalten.")
                return
            neu = ergebnis.get("geraete") or []
            fehlend = ergebnis.get("fehlend") or []
            uebernommen = 0
            alt = self._alter_stand()
            if alt and len(neu) >= 50:              # Serien, die diesmal gar nicht auftauchten (Link-Seite nicht geladen)
                neu_serien = {g.shop_url for g in neu}
                fehlend = fehlend + sorted({g.shop_url for g in alt if g.shop_url and g.shop_url not in neu_serien}
                                           - set(fehlend))
            if fehlend and alt:                     # nicht erreichbare Serien: alter Stand statt Lücke
                neu, uebernommen = shop.ergaenzen(neu, alt, fehlend)
            grund = shop.pruefen(neu, alt)
            if grund:
                try:                                      # zur Fehlersuche aufheben
                    shop.speichern(neu, self.pfad.with_name("shopdaten_abgelehnt.json"))
                except OSError:
                    pass
                bleibt = f"Die bisherigen Daten ({len(self.geraete)} Geräte) bleiben erhalten." if self.geraete else ""
                if not messagebox.askyesno("Shop einlesen – Ergebnis unplausibel",
                                           f"{grund}\n\n{bleibt}\n\nTrotzdem die neuen Daten übernehmen?",
                                           icon="warning", default="no", parent=self):
                    self.info.configure(text=f"Neue Shopdaten verworfen: {grund}")
                    self.stand_lbl.configure(text=self.stand_lbl.cget("text") + " · neues Einlesen verworfen")
                    return
            self.geraete = neu
            try:
                shop.speichern(self.geraete, self.pfad)
            except OSError as e:
                messagebox.showwarning("Shop einlesen", f"Daten gelesen, aber nicht gespeichert:\n{e}")
            self.stand = datetime.now().isoformat(timespec="minutes")
            self._status()
            if fehlend:
                self.stand_lbl.configure(text=self.stand_lbl.cget("text") + f" · {len(fehlend)} Serien unvollständig")
                messagebox.showwarning(
                    "Shop einlesen",
                    f"{len(fehlend)} Serie(n) konnten nicht vollständig gelesen werden (Shop langsam) "
                    "oder wurden diesmal nicht gefunden.\n"
                    + (f"Dafür wurden {uebernommen} Geräte aus dem letzten Stand übernommen.\n" if uebernommen else "")
                    + "\nBitte später noch einmal „Shop neu einlesen“. Bleibt eine Serie dauerhaft in dieser Liste, "
                    "wurde sie vermutlich aus dem Shop genommen.\n\n"
                    + "\n".join("• " + u.rsplit("/", 1)[-1].split(":::")[0].replace("-", " ") for u in fehlend[:12]),
                    parent=self)
            self.suchen()
            if not self.eingabe.get().strip():
                self.info.configure(text=f"Shop eingelesen: {len(self.geraete)} Geräte.")

        self.after(150, abfragen)
        threading.Thread(target=lauf, daemon=True).start()

    # ------------------------------------------------------------------ Updates
    def updates_suchen(self, still: bool = True):
        ergebnis: dict = {}

        def lauf():
            ergebnis["neu"] = aktualisierung.neueste(timeout=8.0)
            ergebnis["fertig"] = True

        def abfragen():
            if not ergebnis.get("fertig"):
                self.after(200, abfragen)
                return
            neu = ergebnis.get("neu")
            if not neu:
                if not still:
                    messagebox.showinfo("Updates", f"Version {__version__} ist aktuell "
                                                   "(oder GitHub ist gerade nicht erreichbar).", parent=self)
                return
            version, url = neu
            if not aktualisierung.ist_exe():
                if messagebox.askyesno("Update verfügbar", f"Version {version} ist verfügbar (installiert: {__version__}).\n\n"
                                                           "Download-Seite öffnen?", parent=self):
                    webbrowser.open(aktualisierung.SEITE)
                return
            if messagebox.askyesno("Update verfügbar",
                                   f"Version {version} ist verfügbar (installiert: {__version__}).\n\n"
                                   "Jetzt automatisch aktualisieren?\n\nDie neue Version wird in den Programmordner geladen "
                                   "und gestartet, die alte danach entfernt. Shopdaten und Verlauf bleiben erhalten.",
                                   parent=self):
                self._update_laden(version, url)

        threading.Thread(target=lauf, daemon=True).start()
        self.after(200, abfragen)

    def _update_laden(self, version: str, url: str):
        ziel = aktualisierung.zieldatei(aktualisierung.exe_pfad().parent, version)
        stand: dict = {"geladen": 0, "gesamt": 0}
        ergebnis: dict = {}
        self.fortschritt.configure(mode="determinate", value=0, maximum=100)
        self.fortschritt.pack(fill="x", padx=12, before=self.info)

        def fortschritt(geladen, gesamt):
            stand.update(geladen=geladen, gesamt=gesamt)

        def lauf():
            try:
                aktualisierung.herunterladen(url, ziel, fortschritt)
            except Exception as e:  # noqa: BLE001
                ergebnis["fehler"] = e
            ergebnis["fertig"] = True

        def abfragen():
            if stand["gesamt"]:
                self.fortschritt.configure(value=stand["geladen"] * 100 / stand["gesamt"])
            self.info.configure(text=f"Lade Version {version} … {stand['geladen'] // 1_000_000} MB")
            if not ergebnis.get("fertig"):
                self.after(200, abfragen)
                return
            self.fortschritt.pack_forget()
            if "fehler" in ergebnis:
                messagebox.showerror("Update", f"Das Update konnte nicht geladen werden:\n{ergebnis['fehler']}\n\n"
                                               "Das Programm läuft normal weiter.", parent=self)
                return
            try:
                aktualisierung.starten(ziel)
            except OSError as e:
                messagebox.showerror("Update", f"Neue Version geladen, konnte aber nicht gestartet werden:\n{e}\n\n{ziel}",
                                     parent=self)
                return
            self.destroy()
            os._exit(0)

        threading.Thread(target=lauf, daemon=True).start()
        self.after(200, abfragen)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--selbsttest"]:
        from .selbsttest import selbsttest
        return selbsttest(Path(argv[1]) if len(argv) > 1 else Path.cwd())
    App().mainloop()
    return 0
