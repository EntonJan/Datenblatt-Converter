"""Oberfläche der EPS-Produktsuche (Tkinter, keine Installation nötig)."""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox

from . import __version__, shop, suche as Q

NAVY, CYAN, GRAU = "#35528C", "#52B4D7", "#6A7380"
FARBEN = {Q.PASST: "#2E7D32", Q.GROESSER: "#1B4F72", Q.PARALLEL: "#8E5A00", Q.REIHE: "#8E5A00", Q.KNAPP_DARUNTER: "#8A8F98"}
BEISPIELE = "z. B. „Stromquelle 0-30V 1kA 30kW“ · „E-Last 500V 100A“ · „230VAC 3kVA“ · „Wechselrichter 400V 6kVA“ · „ELR 10080“"


def programmordner() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(os.environ.get("EPS_PRODUKTSUCHE_HOME", Path.home() / ".eps-produktsuche"))


def datenpfad() -> Path:
    return programmordner() / "EPS-Produktsuche-Daten" / "shopdaten.json"


def ressource(name: str) -> Path:
    basis = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return basis / "assets" / name


class App(tk.Tk):
    def __init__(self, pfad: Path | None = None, automatisch_laden: bool = True):
        super().__init__()
        self.title(f"EPS-Produktsuche {__version__}")
        self.geometry("1280x720")
        self.minsize(980, 520)
        try:
            self.iconbitmap(str(ressource("icon.ico")))
        except tk.TclError:
            pass
        self.pfad = pfad or datenpfad()
        self.geraete, self.stand = shop.laden(self.pfad)
        self.treffer: list[Q.Treffer] = []
        self.zeilen_geraete: list[shop.Geraet] = []
        self.laedt = False
        self._stil()
        self._aufbauen()
        self._status()
        self.suchen()
        if automatisch_laden and (not self.geraete or shop.veraltet(self.stand)):
            self.after(300, lambda: self.einlesen(still=bool(self.geraete)))

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
        self.knopf_laden.pack(side="right", padx=10)
        self.stand_lbl = tk.Label(kopf, text="", fg="white", bg=NAVY)
        self.stand_lbl.pack(side="right", padx=6)

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

        opt = ttk.Frame(self, padding=(12, 4, 12, 0))
        opt.pack(fill="x")
        self.erkannt = ttk.Label(opt, text=BEISPIELE, foreground=GRAU)
        self.erkannt.pack(side="left")
        self.max_par = tk.IntVar(value=10)
        ttk.Spinbox(opt, from_=1, to=64, width=4, textvariable=self.max_par, command=self.suchen).pack(side="right")
        ttk.Label(opt, text="max. Geräte parallel/in Reihe:").pack(side="right", padx=(16, 4))
        self.knapp = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="auch knapp darunter (bis −10 %)", variable=self.knapp, command=self.suchen).pack(side="right")

        sp = [("bew", "Bewertung", 100), ("nr", "Bestellnr.", 70), ("name", "Gerät", 270), ("typ", "Gerätetyp", 105),
              ("u", "Spannung", 115), ("i", "Strom", 85), ("p", "Leistung", 115), ("res", "Reserve", 150), ("hin", "Hinweis", 220)]
        tf = ttk.Frame(self, padding=(12, 8, 12, 0))
        tf.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(tf, columns=[x[0] for x in sp], show="headings", selectmode="extended")
        for k, t, b in sp:
            self.tv.heading(k, text=t)
            self.tv.column(k, width=b, minwidth=50, stretch=k in ("name", "hin"))
        for kat, farbe in FARBEN.items():
            self.tv.tag_configure(kat, foreground=farbe)
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
        ttk.Label(unten, text="Enter/Doppelklick: Datenblatt · Strg+C: Empfehlung kopieren · Esc: Eingabe leeren",
                  foreground=GRAU).pack(side="right")

        self.eingabe.trace_add("write", lambda *a: self.suchen())
        self.typ_cb.bind("<<ComboboxSelected>>", lambda e: self.suchen())
        self.max_par.trace_add("write", lambda *a: self.after_idle(self.suchen))
        self.tv.bind("<Double-1>", lambda e: self.pdf())
        self.tv.bind("<Return>", lambda e: self.pdf())
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._details())
        self.bind_all("<Control-c>", lambda e: self.kopieren("de") if self.focus_get() is not self.feld else None)
        self.feld.bind("<Escape>", lambda e: self.eingabe.set(""))
        self.feld.bind("<Down>", lambda e: self._in_liste())
        self.feld.focus_set()

    def _in_liste(self):
        k = self.tv.get_children()
        if k:
            self.tv.focus_set()
            self.tv.selection_set(k[0])
            self.tv.focus(k[0])
        return "break"

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
        self.treffer, self.zeilen_geraete = [], []
        text = self.eingabe.get().strip()
        a = self.anfrage()
        if not self.geraete:
            self.erkannt.configure(text="Noch keine Shopdaten – „Shop neu einlesen“ (dauert ca. 1–3 Minuten).")
            return
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
        for t in self.treffer:
            self._zeile(t.bewertung, t.g, t.reserve_text(), t.hinweis, (t.kategorie,))
        n = {k: sum(1 for t in self.treffer if t.kategorie == k) for k in FARBEN}
        self.info.configure(text=f"{len(self.treffer)} Treffer: {n[Q.PASST]} passen genau, {n[Q.GROESSER]} größer, "
                                 f"{n[Q.PARALLEL] + n[Q.REIHE]} mit mehreren Geräten, {n[Q.KNAPP_DARUNTER]} knapp darunter")

    def _zeile(self, bew, g: shop.Geraet, reserve, hinweis, tags):
        iid = str(len(self.zeilen_geraete))
        self.zeilen_geraete.append(g)
        typ = g.geraetetyp + (" (bidir.)" if g.bidirektional and g.geraetetyp != shop.LAST else "")
        self.tv.insert("", "end", iid=iid, tags=tags, values=[bew, g.bestellnummer, g.name, typ, g.spannung or "–",
                                                              g.strom or "–", g.leistung or "–", reserve, hinweis])

    def _auswahl(self) -> list[int]:
        return [int(i) for i in self.tv.selection()]

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
            self.info.configure(text=f"{len(sel)} Geräte ausgewählt – „Empfehlung kopieren“ übernimmt alle.")

    # ------------------------------------------------------------------ Aktionen
    def pdf(self):
        sel = self._auswahl()
        if sel:
            g = self.zeilen_geraete[sel[0]]
            webbrowser.open(g.pdf_url or g.shop_url)

    def shopseite(self):
        sel = self._auswahl()
        if sel and self.zeilen_geraete[sel[0]].shop_url:
            webbrowser.open(self.zeilen_geraete[sel[0]].shop_url)

    def kopieren(self, sprache: str):
        sel = self._auswahl()
        if sel:
            ausgewaehlt = [self.zeilen_geraete[i] for i in sel]
            tr = [next((t for t in self.treffer if t.g is g), None) or Q.Treffer(g, Q.PASST) for g in ausgewaehlt]
        else:
            tr = [t for t in self.treffer if t.kategorie == Q.PASST][:3]
        if not tr:
            self.info.configure(text="Bitte zuerst ein oder mehrere Geräte auswählen (Strg/Umschalt + Klick).")
            return
        self.clipboard_clear()
        self.clipboard_append(Q.empfehlung(tr, self.anfrage(), sprache))
        self.info.configure(text=f"Empfehlung mit {len(tr)} Gerät(en) in die Zwischenablage kopiert ({sprache.upper()}).")

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

    def einlesen(self, still: bool = False):
        if self.laedt:
            return
        self.laedt = True
        self.knopf_laden.state(["disabled"])
        self.fortschritt.pack(fill="x", padx=12, before=self.info)
        self.fortschritt.configure(value=0, maximum=100)
        ergebnis: dict = {}
        meldungen: queue.Queue = queue.Queue()      # Tk darf nur aus dem Hauptthread angefasst werden

        def melden(text, erledigt, gesamt):
            meldungen.put((text, erledigt, gesamt))

        def lauf():
            try:
                ergebnis["geraete"] = shop.einlesen(fortschritt=melden)
            except Exception as e:  # noqa: BLE001 – Netzwerkfehler o. Ä. sauber melden
                ergebnis["fehler"] = e
            ergebnis["fertig"] = True

        def abfragen():
            try:
                while True:
                    text, erledigt, gesamt = meldungen.get_nowait()
                    self.fortschritt.configure(maximum=max(gesamt, 1), value=erledigt)
                    self.info.configure(text=f"Lese Shop … {erledigt}/{gesamt}  {text}")
            except queue.Empty:
                pass
            if ergebnis.get("fertig"):
                fertig()
            else:
                self.after(150, abfragen)

        def fertig():
            self.laedt = False
            self.knopf_laden.state(["!disabled"])
            self.fortschritt.pack_forget()
            if "fehler" in ergebnis or not ergebnis.get("geraete"):
                fehler = ergebnis.get("fehler", "keine Geräte gefunden")
                self.info.configure(text=f"Shop konnte nicht gelesen werden: {fehler}")
                if not still:
                    messagebox.showerror("Shop einlesen", f"Der Onlineshop konnte nicht gelesen werden:\n{fehler}\n\n"
                                                          "Internetverbindung prüfen. Die bisherigen Daten bleiben erhalten.")
                return
            self.geraete = ergebnis["geraete"]
            try:
                shop.speichern(self.geraete, self.pfad)
            except OSError as e:
                messagebox.showwarning("Shop einlesen", f"Daten gelesen, aber nicht gespeichert:\n{e}")
            self.stand = datetime.now().isoformat(timespec="minutes")
            self._status()
            self.suchen()
            if not self.eingabe.get().strip():
                self.info.configure(text=f"Shop eingelesen: {len(self.geraete)} Geräte.")

        self.after(150, abfragen)
        threading.Thread(target=lauf, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--selbsttest"]:
        from .selbsttest import selbsttest
        return selbsttest(Path(argv[1]) if len(argv) > 1 else Path.cwd())
    App().mainloop()
    return 0
