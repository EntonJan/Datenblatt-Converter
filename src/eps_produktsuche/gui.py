"""Oberfläche der EPS-Produktsuche (CustomTkinter, hell/dunkel, keine Installation nötig).

Aufbau ab 1.4: links eine Seitenleiste (Suche, Anfragen, Verlauf, Gegenüberstellungen, Einstellungen), rechts die
jeweilige Seite. Auf der Suche stehen oben die drei besten Treffer aus verschiedenen Serien als Karten, darunter alle
weiteren als Liste (nach Serie gruppiert, aufklappbar).
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox

import customtkinter as ctk

from . import __version__, shop, suche as Q, verlauf, aktualisierung, thema as TH
from .einstellungen import Einstellungen

TESTVERSION = "dev" in __version__        # Test-Builds vom Branch: kein Selbst-Update, keine Aufräumaktion

NAVY, CYAN, GRAU = "#35528C", "#52B4D7", "#6A7380"
FARBEN = {k: v[0] for k, v in TH.BEWERTUNG.items()}
TYPEN = ["automatisch", "alle", *Q.GERAETETYPEN]
TASTEN = "Enter: im Verlauf merken · Doppelklick: Datenblatt · Strg+C: Empfehlung · Strg+O: Kunden-Dokument"
BEISPIELE = ("z. B. „Stromquelle 0-30V 1kA 30kW“ · „E-Last 500V 100A“ · „230VAC 3kVA 400Hz“ · „19 Zoll bidirektional 80V 300A“"
             " · „ELR 10080“")


def _zentrieren(fenster: tk.Toplevel, master: tk.Misc) -> None:
    fenster.update_idletasks()
    x = master.winfo_rootx() + (master.winfo_width() - fenster.winfo_reqwidth()) // 2
    y = master.winfo_rooty() + (master.winfo_height() - fenster.winfo_reqheight()) // 3
    fenster.geometry(f"+{max(x, 0)}+{max(y, 0)}")


class AuswahlDialog(ctk.CTkToplevel):
    """Liste zum Auswählen (Variante oder Modell aus einem Kunden-Dokument) im Stil der Produktsuche.

    ergebnis: Index der Auswahl, False = „ohne“, None = abgebrochen."""

    def __init__(self, master, titel: str, frage: str, eintraege: list[str], ohne_text: str):
        super().__init__(master, fg_color=TH.BG)
        self.title(titel)
        self.transient(master)
        self.ergebnis = None
        hoehe = min(560, 230 + 32 * len(eintraege))
        self.geometry(f"560x{hoehe}")
        self.minsize(420, 300)
        TH.text(self, frage, 13, anchor="w", justify="left", wraplength=520).pack(fill="x", padx=18, pady=(16, 10))
        rahmen, self.tv = TH.tabelle(self, [("wert", "Auswahl", 480)], dehnen=("wert",))
        self.tv.configure(show="tree")
        self.tv.column("#0", width=0, stretch=False)
        rahmen.pack(fill="both", expand=True, padx=18)
        for i, e in enumerate(eintraege):
            self.tv.insert("", "end", iid=str(i), values=[e])
        unten = ctk.CTkFrame(self, fg_color="transparent")
        unten.pack(fill="x", padx=18, pady=14)
        TH.knopf(unten, ohne_text, self.ohne).pack(side="left")
        TH.knopf(unten, "Übernehmen", self.ok, haupt=True, width=120).pack(side="right")
        TH.knopf(unten, "Abbrechen", self.destroy, width=100).pack(side="right", padx=8)
        self.tv.bind("<Double-1>", lambda e: self.ok())
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.destroy())
        if eintraege:
            self.tv.selection_set("0")
            self.tv.focus("0")
        _zentrieren(self, master)
        self.after(80, self._modal)
        self.wait_window()

    def _modal(self):
        try:
            self.lift()
            self.grab_set()
            self.tv.focus_set()
        except tk.TclError:                       # Fenster noch nicht sichtbar
            self.after(80, self._modal)

    def ok(self):
        sel = self.tv.selection()
        if sel:
            self.ergebnis = int(sel[0])
            self.destroy()

    def ohne(self):
        self.ergebnis = False
        self.destroy()


def variante_waehlen(master, varianten, datei: str = ""):
    """Variante aus einer Zahlenreihe ohne Modellnamen (z. B. „0-30 V / 0-40 A / 1,2 kW“)."""
    d = AuswahlDialog(master, "Variante auswählen" + (f" – {datei}" if datei else ""),
                      "Das Dokument enthält mehrere Varianten bzw. Ausbaustufen ohne Modellnamen. Welche braucht der Kunde?",
                      [v.label for v in varianten], "Ohne Variante (Höchstwerte)")
    return d.ergebnis if d.ergebnis in (None, False) else varianten[d.ergebnis]


def modell_waehlen(master, modelle, datei: str = ""):
    """Modell aus einem Datenblatt mit mehreren Modellspalten."""
    d = AuswahlDialog(master, "Modell auswählen" + (f" – {datei}" if datei else ""),
                      "Dieses Datenblatt enthält mehrere Modelle. Welches braucht der Kunde?",
                      [f"{m.label}   (Tabelle {m.tabelle + 1}, Seite {m.seite})" for m in modelle],
                      "Ohne Modell (nur allgemeine Werte)")
    return d.ergebnis if d.ergebnis in (None, False) else modelle[d.ergebnis]


class OffenePunkteDialog(ctk.CTkToplevel):
    """Warnung nach dem Einlesen einer Anfrage: Punkte, die das Programm nicht prüfen konnte – zum Abhaken/Kopieren."""

    def __init__(self, master, punkte: list[str], datei: str = ""):
        super().__init__(master, fg_color=TH.BG)
        self.title("Ungeklärte Punkte" + (f" – {datei}" if datei else ""))
        self.transient(master)
        self.geometry("900x480")
        kopf = ctk.CTkFrame(self, fg_color=TH.GELB, corner_radius=10)
        kopf.pack(fill="x", padx=12, pady=(12, 6))
        TH.text(kopf, f"⚠  {len(punkte)} Punkte konnte das Programm nicht anhand der Gerätedaten prüfen.\n"
                      "Markierte Stellen (Pflicht) müssen genau erfüllt sein – vor dem Angebot im EPS-Datenblatt "
                      "nachsehen oder mit der Technik/dem Hersteller klären.",
                farbe=TH.GELB_TEXT, justify="left", anchor="w", wraplength=840).pack(fill="x", padx=12, pady=10)
        innen = ctk.CTkScrollableFrame(self, fg_color=TH.FLAECHE, corner_radius=10)
        innen.pack(fill="both", expand=True, padx=12)
        self.vars: list[tk.BooleanVar] = []
        self.punkte = punkte
        for p in punkte:
            v = tk.BooleanVar(value=False)
            self.vars.append(v)
            ctk.CTkCheckBox(innen, text=p, variable=v, font=TH.schrift(12), text_color=TH.TEXT,
                            fg_color=TH.AKZENT).pack(anchor="w", fill="x", pady=3, padx=6)
        unten = ctk.CTkFrame(self, fg_color="transparent")
        unten.pack(fill="x", padx=12, pady=12)
        TH.knopf(unten, "Als Liste kopieren", self.kopieren).pack(side="left")
        TH.knopf(unten, "OK", self.destroy, haupt=True).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        _zentrieren(self, master)
        self.after(50, self.lift)

    def kopieren(self):
        text = "\n".join(("[x] " if v.get() else "[ ] ") + p for p, v in zip(self.punkte, self.vars))
        self.clipboard_clear()
        self.clipboard_append(text)


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


def _prozent(f: float | None) -> str:
    if f is None:
        return "–"
    d = (f - 1) * 100
    return "±0 %" if abs(d) < 0.5 else f"{'+' if d > 0 else '−'}{abs(d):.0f} %"


class TrefferKarte(ctk.CTkFrame):
    """Eine der drei Top-Karten: Bewertung, Nr., Name, U/I/P mit Abweichung, Merkmale, Auswählen/Datenblatt."""

    def __init__(self, master, app: "App", nr: int):
        super().__init__(master, fg_color=TH.FLAECHE, border_color=TH.RAND, border_width=1, corner_radius=12)
        self.app, self.nr, self.t = app, nr, None
        oben = ctk.CTkFrame(self, fg_color="transparent")
        oben.pack(fill="x", padx=14, pady=(12, 0))
        self.badge = ctk.CTkLabel(oben, text="", font=TH.schrift(12, True), corner_radius=10, height=24, padx=10)
        self.badge.pack(side="left")
        self.nummer = TH.text(oben, "", 12, farbe=TH.GRAU)
        self.nummer.pack(side="right")
        self.name = TH.text(self, "", 15, True, anchor="w", justify="left", wraplength=320)
        self.name.pack(fill="x", padx=14, pady=(6, 6))
        kacheln = ctk.CTkFrame(self, fg_color="transparent")
        kacheln.pack(fill="x", padx=14)
        self.werte = []
        for i in range(3):
            k = ctk.CTkFrame(kacheln, fg_color=TH.KACHEL, corner_radius=10)
            k.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            kacheln.columnconfigure(i, weight=1, uniform="k")
            w = TH.text(k, "", 16, True)
            w.pack(pady=(6, 0))
            d = TH.text(k, "", 11, farbe=TH.GRAU)
            d.pack(pady=(0, 6))
            self.werte.append((w, d))
        self.info = TH.text(self, "", 11, farbe=TH.GRAU, anchor="w", justify="left", wraplength=320)
        self.info.pack(fill="x", padx=14, pady=(8, 0))
        self.serie = TH.text(self, "", 11, farbe=TH.LINK, anchor="w", cursor="hand2")
        self.serie.pack(fill="x", padx=14)
        self.serie.bind("<Button-1>", lambda e: self.app.serie_zeigen(self.t))
        self.hinweis = TH.text(self, "", 11, farbe=TH.ORANGE, anchor="w", justify="left", wraplength=320)
        knoepfe = ctk.CTkFrame(self, fg_color="transparent")
        knoepfe.pack(fill="x", padx=14, pady=(8, 12), side="bottom")
        self.knopf = TH.knopf(knoepfe, "Auswählen", lambda: self.app.karte_waehlen(self.nr), haupt=True, width=110, height=32)
        self.knopf.pack(side="left")
        TH.knopf(knoepfe, "Datenblatt", lambda: self.app.datenblatt_oeffnen(self.t.g), width=100, height=32
                 ).pack(side="left", padx=6)
        self.bind("<Configure>", self._breite)

    def _breite(self, e):
        w = max(200, e.width - 30)
        for lbl in (self.name, self.info, self.hinweis):
            lbl.configure(wraplength=w)

    def zeigen(self, t: Q.Treffer, weitere: int, gleich: int, gewaehlt: bool):
        self.t = t
        g = t.g
        genau = t.kategorie == Q.PASST
        self.badge.configure(text=t.bewertung,
                             fg_color=TH.GRUEN_BG if genau else (TH.GELB if t.kategorie in (Q.PARALLEL, Q.REIHE) else TH.CHIP),
                             text_color=TH.GRUEN if genau else (TH.ORANGE if t.kategorie in (Q.PARALLEL, Q.REIHE)
                                                                 else TH.CHIP_TEXT))
        self.nummer.configure(text=f"Nr. {g.bestellnummer}")
        self.name.configure(text=g.name)
        werte = [(Q.zahl_text(g.umax, "V") if g.umax else (g.spannung or "–"), t.reserve.get("U")),
                 (Q.zahl_text(g.imax, "A") if g.imax else (g.strom or "–"), t.reserve.get("I")),
                 (Q.zahl_text(g.pmax, "W") if g.pmax else (g.leistung or "–"), t.reserve.get("P"))]
        for (w, d), (wert, res) in zip(self.werte, werte):
            w.configure(text=wert)
            d.configure(text=_prozent(res) if res is not None else "nicht gefragt")
        merkmale = [g.geraetetyp + (" bidirektional" if g.bidirektional and g.geraetetyp != shop.LAST else "")]
        merkmale += [x for x in (g.bauart, "wassergekühlt" if g.wasser == "ja" else "", "Netzrückspeisung" if g.rueckspeisung
                                 else "", f"bis {g.parallel_max} parallel" if g.parallel_max else "") if x]
        self.info.configure(text=" · ".join(merkmale))
        serie = f"▸ +{weitere} weitere der Serie" if weitere else ""
        if gleich:
            serie += f" · davon {gleich}× ebenfalls passt genau"
        self.serie.configure(text=serie)
        hinweis = t.hinweis
        self.hinweis.configure(text=hinweis)
        if hinweis:
            self.hinweis.pack(fill="x", padx=14, after=self.serie)
        else:
            self.hinweis.pack_forget()
        rand = TH.AKZENT if gewaehlt else (TH.GRUEN_RAND if genau else TH.RAND)
        self.configure(border_color=rand, border_width=3 if gewaehlt else (2 if genau else 1))
        self.knopf.configure(text="✓ Ausgewählt" if gewaehlt else "Auswählen")


class App(ctk.CTk):
    def __init__(self, pfad: Path | None = None, automatisch_laden: bool = True, update_pruefen: bool | None = None):
        self.pfad = pfad or datenpfad()
        self.verlauf_pfad = self.pfad.parent / "verlauf.json"
        self.einstellungen_pfad = self.pfad.parent / "einstellungen.json"
        self.einstellungen = Einstellungen.laden(self.einstellungen_pfad)
        TH.modus_setzen(self.einstellungen.dunkelmodus)
        super().__init__(fg_color=TH.BG)
        self.title(f"EPS-Produktsuche {__version__}")
        self.geometry("1440x900")
        self.minsize(1100, 680)
        if sys.platform == "win32":                 # CustomTkinter setzt kurz nach dem Start sein eigenes Symbol
            self.after(300, self._symbol)
        self.vorgang = None                     # aktuelle Kundenanfrage aus Outlook/Mail (kunde.Erkennung + Mail)
        self.shop_pfad = self.pfad                # Shopdaten (auch Grundlage für den Weclapp-Demo-Modus)
        if self.einstellungen.datenquelle == "weclapp":
            self.pfad = self.pfad.with_name("weclappdaten.json")
        self.geraete, self.stand = shop.laden(self.pfad)
        self.treffer: list[Q.Treffer] = []
        self.zeilen_geraete: list[shop.Geraet] = []
        self.iid_index: dict[str, int] = {}
        self.karten_treffer: list[tuple[Q.Treffer, int, int]] = []     # (Treffer, weitere der Serie, davon genau)
        self.karten_gewaehlt: set[int] = set()
        self.karten_index: list[int] = []
        self.serie_iid: dict[str, str] = {}
        self.fremd = None
        self.fremd_anfrage = ""
        self.laedt = False
        self.beschaeftigt = False
        self.tabellen: list[ttk.Treeview] = []
        self.seiten: dict[str, ctk.CTkFrame] = {}
        TH.tabellen_stil(self)
        self._aufbauen()
        self._status()
        self.suchen()
        veraltetes_format = bool(self.geraete) and shop.datenformat(self.pfad) < shop.DATENFORMAT
        if automatisch_laden and (not self.geraete or shop.veraltet(self.stand) or veraltetes_format):
            self.after(300, lambda: self.einlesen(still=bool(self.geraete)))
        if update_pruefen is None:
            update_pruefen = aktualisierung.ist_exe()
        if aktualisierung.ist_exe() and not TESTVERSION:
            threading.Thread(target=aktualisierung.alte_entfernen, daemon=True).start()
        if aktualisierung.ist_exe() and TESTVERSION:
            threading.Thread(target=aktualisierung.test_aufraeumen, daemon=True).start()
        if update_pruefen:
            self.after(2500, lambda: self.updates_suchen(still=True))

    def _symbol(self):
        try:
            self.iconbitmap(str(ressource("icon.ico")))
        except tk.TclError:
            pass

    def _cursor(self, name: str):
        tk.Tk.configure(self, cursor=name)

    # ------------------------------------------------------------------ Aufbau
    def _aufbauen(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._seitenleiste()
        haupt = ctk.CTkFrame(self, fg_color="transparent")
        haupt.grid(row=0, column=1, sticky="nsew")
        haupt.rowconfigure(1, weight=1)
        haupt.columnconfigure(0, weight=1)
        self.haupt = haupt
        self.fortschritt = TH.Fortschritt(haupt)
        inhalt = ctk.CTkFrame(haupt, fg_color="transparent")
        inhalt.grid(row=1, column=0, sticky="nsew", padx=24, pady=(16, 16))
        self.inhalt = inhalt
        self._suchseite(inhalt)
        from .anfragen import AnfragenSeite
        from .seiten import VerlaufSeite, GegenueberstellungSeite, EinstellungenSeite
        self.seiten["anfragen"] = AnfragenSeite(inhalt, self)
        self.seiten["verlauf"] = VerlaufSeite(inhalt, self)
        self.seiten["vergleich"] = GegenueberstellungSeite(inhalt, self)
        self.seiten["einstellungen"] = EinstellungenSeite(inhalt, self)
        self._experimentell_zeigen()
        self.seite_zeigen("suche")

        self.eingabe.trace_add("write", lambda *a: self.suchen())
        self.max_par.trace_add("write", lambda *a: self.after_idle(self.suchen))
        self.tv.bind("<Double-1>", self._doppelklick)
        self.tv.bind("<Return>", lambda e: self.pdf())
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._details())
        self.bind_all("<Control-c>", lambda e: self.kopieren("de") if self._auf_suche_ohne_eingabefokus() else None)
        self.feld.bind("<Escape>", lambda e: self.eingabe.set(""))
        self.feld.bind("<Down>", lambda e: self._in_liste())
        self.feld.bind("<Return>", lambda e: self._merken("Suche"))
        self.bind_all("<Control-o>", lambda e: (self.datenblatt_waehlen(), "break")[1])
        self._dnd_einrichten()
        self.feld.focus_set()

    def _auf_suche_ohne_eingabefokus(self) -> bool:
        fokus = self.focus_get()
        return self.aktive_seite == "suche" and not isinstance(fokus, (tk.Entry, tk.Text))

    def _seitenleiste(self):
        leiste = ctk.CTkFrame(self, fg_color=TH.SEITE, corner_radius=0, width=232, border_width=0)
        leiste.grid(row=0, column=0, sticky="nsw")
        leiste.grid_propagate(False)
        leiste.pack_propagate(False)
        ctk.CTkFrame(self, fg_color=TH.RAND, width=1, corner_radius=0).grid(row=0, column=0, sticky="nse")
        logo = ctk.CTkFrame(leiste, fg_color="transparent")
        logo.pack(fill="x", padx=16, pady=(20, 18))
        ctk.CTkLabel(logo, text="EPS", width=38, height=38, corner_radius=9, fg_color=NAVY, text_color="#FFFFFF",
                     font=TH.schrift(13, True)).pack(side="left")
        namen = ctk.CTkFrame(logo, fg_color="transparent")
        namen.pack(side="left", padx=10)
        TH.text(namen, "Produktsuche", 15, True, anchor="w").pack(anchor="w")
        TH.text(namen, f"Version {__version__.split('.dev')[0]}" + (f" · TEST {aktualisierung.build()}" if TESTVERSION
                                                                     else " · intern"),
                11, farbe=TH.TEST if TESTVERSION else TH.GRAU, anchor="w").pack(anchor="w")
        self.nav: dict[str, ctk.CTkButton] = {}
        self.nav_rahmen = ctk.CTkFrame(leiste, fg_color="transparent")
        self.nav_rahmen.pack(fill="x", padx=12)
        for key, titel in (("suche", "Suche"), ("anfragen", "Anfragen"), ("verlauf", "Verlauf"),
                           ("vergleich", "Gegenüberstellungen"), ("einstellungen", "Einstellungen")):
            b = ctk.CTkButton(self.nav_rahmen, text=titel, anchor="w", height=40, corner_radius=8, font=TH.schrift(14),
                              fg_color="transparent", hover_color=TH.KNOPF_HOVER, text_color=TH.TEXT,
                              command=lambda k=key: self.seite_zeigen(k))
            b.pack(fill="x", pady=1)
            self.nav[key] = b
        self.badge = ctk.CTkLabel(self.nav["anfragen"], text="", fg_color=CYAN, text_color="#0B2A3A", corner_radius=9,
                                  height=20, width=26, font=TH.schrift(11, True))

        unten = ctk.CTkFrame(leiste, fg_color="transparent")
        unten.pack(side="bottom", fill="x", padx=12, pady=14)
        self.dunkel_var = tk.BooleanVar(value=self.einstellungen.dunkelmodus)
        zeile = ctk.CTkFrame(unten, fg_color="transparent")
        zeile.pack(fill="x", pady=(0, 10))
        TH.text(zeile, "Dunkelmodus", 13, farbe=TH.GRAU).pack(side="left", padx=4)
        ctk.CTkSwitch(zeile, text="", variable=self.dunkel_var, width=46, progress_color=(CYAN, CYAN),
                      command=lambda: self.dunkel_setzen(self.dunkel_var.get())).pack(side="right")
        box = ctk.CTkFrame(unten, fg_color=TH.BG, corner_radius=10)
        box.pack(fill="x")
        self.stand_lbl = TH.text(box, "", 11, farbe=TH.GRAU, anchor="w", justify="left", wraplength=180)
        self.stand_lbl.pack(fill="x", padx=12, pady=(10, 6))
        self.knopf_laden = TH.knopf(box, self._quelle("Shop neu einlesen", "Weclapp neu laden"),
                                    lambda: self.einlesen(still=False), height=30)
        self.knopf_laden.pack(fill="x", padx=10)
        ctk.CTkButton(box, text="Nach Updates suchen", height=26, fg_color="transparent", hover_color=TH.KNOPF_HOVER,
                      text_color=TH.LINK, font=TH.schrift(12), command=lambda: self.updates_suchen(still=False)
                      ).pack(fill="x", padx=10, pady=(4, 8))

    def _suchseite(self, master):
        seite = ctk.CTkFrame(master, fg_color="transparent")
        self.seiten["suche"] = seite
        such = TH.karte(seite)
        such.pack(fill="x")
        self.such_karte = such
        z1 = ctk.CTkFrame(such, fg_color="transparent")
        z1.pack(fill="x", padx=16, pady=(14, 6))
        self.eingabe = tk.StringVar()
        self.feld = ctk.CTkEntry(z1, textvariable=self.eingabe, height=46, font=TH.schrift(18), fg_color=TH.EINGABE,
                                 border_color=TH.AKZENT, border_width=2, text_color=TH.TEXT, corner_radius=8,
                                 placeholder_text="Kundenanfrage, z. B. Stromquelle 0-30V 1kA 30kW")
        self.feld.pack(side="left", fill="x", expand=True)
        self.typ = tk.StringVar(value="automatisch")
        self.typ_cb = TH.auswahl(z1, TYPEN, self.typ, lambda v: self.suchen(), breite=200)
        self.typ_cb.pack(side="left", padx=(10, 0))
        self.knopf_pdf = TH.knopf(z1, "Kunden-Dokument …", self.datenblatt_waehlen, height=46)
        self.knopf_pdf.pack(side="left", padx=(10, 0))
        z2 = ctk.CTkFrame(such, fg_color="transparent")
        z2.pack(fill="x", padx=16, pady=(0, 12))
        self.chips = ctk.CTkFrame(z2, fg_color="transparent")
        self.chips.pack(side="left", fill="x", expand=True)
        self.erkannt = TH.text(self.chips, BEISPIELE, 12, farbe=TH.GRAU, anchor="w")
        self.zusammenfassung = TH.text(z2, "", 12, farbe=TH.GRAU)
        self.zusammenfassung.pack(side="right")

        self.fremd_rahmen = ctk.CTkFrame(seite, fg_color=TH.CHIP, corner_radius=10)
        self.fremd_lbl = TH.text(self.fremd_rahmen, "", 12, farbe=TH.TEXT, anchor="w", justify="left", wraplength=1100,
                                 cursor="hand2")
        self.fremd_lbl.pack(fill="x", padx=14, pady=8)
        self.fremd_lbl.bind("<Button-1>", lambda e: self.offene_punkte() and
                            OffenePunkteDialog(self, self.offene_punkte(), self.fremd.datei))

        self.top_kopf = ctk.CTkFrame(seite, fg_color="transparent")
        TH.text(self.top_kopf, "Top 3", 16, True).pack(side="left")
        TH.text(self.top_kopf, "die besten Treffer aus verschiedenen Serien", 12, farbe=TH.GRAU).pack(side="left", padx=10)
        self.top_rahmen = ctk.CTkFrame(seite, fg_color="transparent")
        self.karten = []
        for i in range(3):
            k = TrefferKarte(self.top_rahmen, self, i)
            self.top_rahmen.columnconfigure(i, weight=1, uniform="karte")
            self.karten.append(k)

        self.liste_kopf = ctk.CTkFrame(seite, fg_color="transparent")
        self.liste_titel = TH.text(self.liste_kopf, "Weitere Treffer", 16, True)
        self.liste_titel.pack(side="left")
        self.liste_unter = TH.text(self.liste_kopf, "", 12, farbe=TH.GRAU)
        self.liste_unter.pack(side="left", padx=10)
        self.max_par = tk.StringVar(value="10")
        ctk.CTkComboBox(self.liste_kopf, values=["1", "2", "4", "6", "10", "16", "32", "64"], variable=self.max_par,
                        width=70, height=28, fg_color=TH.EINGABE, border_color=TH.RAND, button_color=TH.RAND,
                        text_color=TH.TEXT, dropdown_fg_color=TH.FLAECHE, dropdown_text_color=TH.TEXT,
                        command=lambda v: self.suchen()).pack(side="right")
        TH.text(self.liste_kopf, "max. parallel/in Reihe", 12, farbe=TH.GRAU).pack(side="right", padx=(16, 6))
        self.knapp = tk.BooleanVar(value=True)
        TH.schalter(self.liste_kopf, "knapp darunter (−10 %)", self.knapp, self.suchen).pack(side="right", padx=(16, 0))
        self.gruppieren = tk.BooleanVar(value=True)
        TH.schalter(self.liste_kopf, "nach Serie gruppieren", self.gruppieren, self.suchen).pack(side="right")

        sp = [("bew", "Bewertung", 110), ("nr", "Nr.", 70), ("name", "Gerät", 300), ("typ", "Gerätetyp", 105),
              ("u", "Spannung", 115), ("i", "Strom", 90), ("p", "Leistung", 115), ("res", "Reserve", 170),
              ("hin", "Hinweis", 240)]
        self.tabelle_rahmen, self.tv = TH.tabelle(seite, sp, baum=True, mehrfach=True, dehnen=("name", "hin"))
        self.tabellen.append(self.tv)

        self.info = TH.text(seite, "", 12, farbe=TH.GRAU, anchor="w")
        unten = ctk.CTkFrame(seite, fg_color="transparent")
        self.knopf_weclapp = TH.knopf(unten, "In Weclapp vorbereiten …", self.weclapp_vorbereiten, haupt=True)
        self.unten_links = ctk.CTkFrame(unten, fg_color="transparent")
        self.unten_links.pack(side="left")
        TH.knopf(self.unten_links, "Gegenüberstellung …", self.gegenueberstellung_oeffnen).pack(side="left")
        TH.knopf(self.unten_links, "Empfehlung kopieren (DE)", lambda: self.kopieren("de")).pack(side="left", padx=(8, 0))
        TH.knopf(self.unten_links, "EN", lambda: self.kopieren("en"), width=44).pack(side="left", padx=(4, 0))
        TH.knopf(self.unten_links, "Datenblatt", self.pdf, width=96).pack(side="left", padx=(8, 0))
        TH.knopf(self.unten_links, "Shopseite", self.shopseite, width=96).pack(side="left", padx=(8, 0))
        self.unten = unten
        self._suche_packen()

    def _suche_packen(self, karten: bool = False):
        """Reihenfolge der Suchseite: Suchkarte, (Dokument), (Top 3), Liste, Info, Knöpfe."""
        for w in (self.top_kopf, self.top_rahmen, self.liste_kopf, self.tabelle_rahmen, self.info, self.unten):
            w.pack_forget()
        if karten:
            self.top_kopf.pack(fill="x", pady=(14, 6))
            self.top_rahmen.pack(fill="x")
        self.liste_kopf.pack(fill="x", pady=(14, 6))
        self.unten.pack(fill="x", side="bottom", pady=(8, 0))
        self.info.pack(fill="x", side="bottom", pady=(6, 0))
        self.tabelle_rahmen.pack(fill="both", expand=True)

    def seite_zeigen(self, key: str):
        for k, s in self.seiten.items():
            if k != key:
                s.pack_forget()
        self.seiten[key].pack(fill="both", expand=True)
        for k, b in self.nav.items():
            aktiv = k == key
            b.configure(fg_color=TH.CHIP if aktiv else "transparent", text_color=TH.LINK if aktiv else TH.TEXT,
                        font=TH.schrift(14, aktiv))
        self.aktive_seite = key
        zeigen = getattr(self.seiten[key], "zeigen", None)
        if zeigen:
            zeigen()
        if key == "suche":
            self.feld.focus_set()

    def anfragen_anzahl(self, n: int | None):
        if n:
            self.badge.configure(text=str(n))
            self.badge.place(relx=1.0, rely=0.5, x=-10, anchor="e")
        else:
            self.badge.place_forget()

    def dunkel_setzen(self, an: bool):
        self.dunkel_var.set(an)
        TH.modus_setzen(an)
        TH.tabellen_stil(self)
        for tv in self.tabellen:
            TH.tabelle_tags(tv)
        self.einstellungen.dunkelmodus = an
        try:
            self.einstellungen.speichern(self.einstellungen_pfad)
        except OSError:
            pass
        e = self.seiten.get("einstellungen")
        if e is not None:
            e.dunkel_var.set(an)

    def _balken(self, an: bool):
        if an:
            self.fortschritt.grid(row=0, column=0, sticky="ew", padx=24, pady=(10, 0))
        else:
            self.fortschritt.grid_remove()

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
        self.knopf_pdf.configure(state="disabled")
        self.info.configure(text=text)
        self.fortschritt.configure(mode="indeterminate")
        self._balken(True)
        self.fortschritt.start(12)
        self._cursor("watch")

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
            self._balken(False)
            self._cursor("")
            self.knopf_pdf.configure(state="normal")
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

    def _erkannt_zeigen(self, text: str = "", chips: list[str] | None = None):
        for w in self.chips.winfo_children():
            if w is not self.erkannt:
                w.destroy()
        self.erkannt.pack_forget()
        if chips:
            TH.text(self.chips, "Erkannt:", 12, farbe=TH.GRAU).pack(side="left", padx=(0, 6))
            for c in chips:
                ctk.CTkLabel(self.chips, text=c, fg_color=TH.CHIP, text_color=TH.CHIP_TEXT, corner_radius=12, height=26,
                             font=TH.schrift(12), padx=10).pack(side="left", padx=(0, 6))
        else:
            self.erkannt.configure(text=text)
            self.erkannt.pack(side="left")

    def suchen(self):
        self.tv.delete(*self.tv.get_children())
        self.treffer, self.zeilen_geraete, self.iid_index, self.serie_iid = [], [], {}, {}
        self.karten_treffer, self.karten_gewaehlt = [], set()
        text = self.eingabe.get().strip()
        a = self.anfrage()
        self.zusammenfassung.configure(text="")
        if not self.geraete:
            self._erkannt_zeigen("Noch keine Shopdaten – „Shop neu einlesen“ (dauert ca. 1–3 Minuten).")
            self._karten_zeigen()
            return
        if self.fremd and text != self.fremd_anfrage:
            self.fremd_lbl.configure(text=self.fremd_lbl.cget("text").split("  ·  Anfrage geändert")[0]
                                     + "  ·  Anfrage geändert")
        if a.leer():
            self._erkannt_zeigen(BEISPIELE if not text else "Keine V/A/W erkannt – Suche nach Name/Bestellnummer")
            self._karten_zeigen()
            self.liste_titel.configure(text="Geräte")
            if text:
                for g in Q.textsuche(self.geraete, text)[:300]:
                    self._zeile("", g, "", "", ())
                self.liste_unter.configure(text=f"{len(self.zeilen_geraete)} mit „{text}“")
            else:
                self.liste_unter.configure(text=f"{len(self.geraete)} Geräte durchsuchbar")
            self.info.configure(text=TASTEN)
            return
        self._erkannt_zeigen(chips=a.erkannt)
        try:
            maxp = max(1, int(self.max_par.get()))
        except (tk.TclError, ValueError):
            maxp = 10
        self.treffer = Q.suchen(self.geraete, a, self.knapp.get(), maxp)
        gruppen = Q.nach_serie(self.treffer)
        # Top 3: bester Treffer der drei besten Serien (ohne „knapp darunter“, solange es Besseres gibt)
        gute = [(s, l) for s, l in gruppen if l[0].kategorie != Q.KNAPP_DARUNTER] or gruppen
        for serie, liste in gute[:3]:
            erster = liste[0]
            gleich = sum(1 for t in liste[1:] if t.kategorie == Q.PASST) if erster.kategorie == Q.PASST else 0
            self.karten_treffer.append((erster, len(liste) - 1, gleich))
        oben = {id(t.g) for t, _, _ in self.karten_treffer}
        self.karten_index = []
        for t, _, _ in self.karten_treffer:                 # Kartengeräte zählen für Auswahl/Aktionen mit
            self.karten_index.append(len(self.zeilen_geraete))
            self.zeilen_geraete.append(t.g)
        rest = [t for t in self.treffer if id(t.g) not in oben]
        if self.gruppieren.get():
            rest_gruppen = Q.nach_serie(rest)
            for serie, liste in rest_gruppen:
                erster = liste[0]
                hinweis = erster.hinweis
                # weitere Geräte der Serie, die ebenfalls genau passen: nicht im zugeklappten Teil verstecken
                gleich = [t for t in liste[1:] if t.kategorie == Q.PASST] if erster.kategorie == Q.PASST else []
                if len(liste) > 1:
                    hinweis = f"+{len(liste) - 1} weitere der Serie" + \
                        (f", davon {len(gleich)} ebenfalls „passt genau“ (aufgeklappt)" if gleich else "") + \
                        (self._eingang_hinweis([erster, *gleich], a) if gleich else "") + \
                        (f"; {hinweis}" if hinweis else "")
                eltern = self._zeile(erster.bewertung, erster.g, erster.reserve_text(), hinweis, (erster.kategorie,))
                self.serie_iid[serie] = eltern
                if gleich:
                    self.tv.item(eltern, open=True)
                for t in liste[1:]:
                    self._zeile(t.bewertung, t.g, t.reserve_text(), t.hinweis, (t.kategorie,), eltern=eltern)
            unter = "nach Serie gruppiert · aufklappbar"
        else:
            for t in rest:
                self._zeile(t.bewertung, t.g, t.reserve_text(), t.hinweis, (t.kategorie,))
            unter = "alle Geräte einzeln"
        self._karten_zeigen()
        self.liste_titel.configure(text="Weitere Treffer" if self.karten_treffer else "Treffer")
        self.liste_unter.configure(text=unter)
        n = {k: sum(1 for t in self.treffer if t.kategorie == k) for k in FARBEN}
        self.zusammenfassung.configure(
            text=f"{len(self.treffer)} Treffer in {len(gruppen)} Serien · {n[Q.PASST]} genau · {n[Q.GROESSER]} größer · "
                 f"{n[Q.PARALLEL] + n[Q.REIHE]} mit mehreren Geräten"
                 + (f" · {n[Q.KNAPP_DARUNTER]} knapp darunter" if n[Q.KNAPP_DARUNTER] else ""))
        self.info.configure(text="Keine Treffer – Gerätetyp auf „alle“ stellen?" if not self.treffer and a.geraetetyp else TASTEN)

    def _karten_zeigen(self):
        for i, k in enumerate(self.karten):
            if i < len(self.karten_treffer):
                t, weitere, gleich = self.karten_treffer[i]
                k.zeigen(t, weitere, gleich, i in self.karten_gewaehlt)
                k.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 14, 0))
            else:
                k.grid_forget()
        self._suche_packen(karten=bool(self.karten_treffer))

    def karte_waehlen(self, nr: int):
        if nr in self.karten_gewaehlt:
            self.karten_gewaehlt.discard(nr)
        else:
            self.karten_gewaehlt.add(nr)
        t, weitere, gleich = self.karten_treffer[nr]
        self.karten[nr].zeigen(t, weitere, gleich, nr in self.karten_gewaehlt)
        self._details()

    def serie_zeigen(self, t: Q.Treffer | None):
        """„+n weitere der Serie“ auf einer Karte: die übrigen Geräte der Serie in der Liste zeigen."""
        if t is None:
            return
        serie = t.g.serie or t.g.name
        iid = self.serie_iid.get(serie)
        if iid:
            self.tv.item(iid, open=True)
            kinder = [iid, *self.tv.get_children(iid)]
        else:
            kinder = [i for i, n in self.iid_index.items() if self.tv.exists(i) and
                      (self.zeilen_geraete[n].serie or self.zeilen_geraete[n].name) == serie]
        if kinder:
            self.tv.selection_set(kinder)
            self.tv.see(kinder[-1])
            self.tv.see(kinder[0])
            self.tv.focus_set()

    def datenblatt_oeffnen(self, g: shop.Geraet):
        url = g.pdf_url or g.shop_url
        if url:
            webbrowser.open(url)

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
        karten = [self.karten_index[i] for i in sorted(self.karten_gewaehlt) if i < len(self.karten_index)]
        return karten + [self.iid_index[i] for i in self.tv.selection() if i in self.iid_index]

    def _treffer_zu(self, g: shop.Geraet) -> Q.Treffer:
        return next((t for t in self.treffer if t.g is g), None) or Q.Treffer(g, Q.PASST)

    def _ausgewaehlte_treffer(self, standard: int = 3) -> list[Q.Treffer]:
        sel = self._auswahl()
        if sel:
            return [self._treffer_zu(self.zeilen_geraete[i]) for i in sel]
        if self.karten_treffer:
            return [t for t, _, _ in self.karten_treffer][:standard]
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
        else:
            self.info.configure(text=TASTEN)

    # ------------------------------------------------------------------ Aktionen
    def pdf(self):
        sel = self._auswahl()
        if sel:
            self.datenblatt_oeffnen(self.zeilen_geraete[sel[0]])

    def shopseite(self):
        sel = self._auswahl()
        if not sel:
            self.info.configure(text="Bitte zuerst ein Gerät auswählen.")
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

    def kopieren(self, sprache: str, treffer: list[Q.Treffer] | None = None):
        tr = treffer or self._ausgewaehlte_treffer()
        if not tr:
            self.info.configure(text="Bitte zuerst ein oder mehrere Geräte auswählen (Strg/Umschalt + Klick).")
            return
        self.clipboard_clear()
        self.clipboard_append(Q.empfehlung(tr, self.anfrage(), sprache, alternative_zu=self._alternative_zu()))
        self.info.configure(text=f"Empfehlung mit {len(tr)} Gerät(en) in die Zwischenablage kopiert ({sprache.upper()}).")
        self._merken(f"Empfehlung {sprache.upper()}", tr)

    def gegenueberstellung_oeffnen(self):
        from . import vergleich
        tr = self._ausgewaehlte_treffer(standard=3)[:vergleich.MAX_VORSCHLAEGE]
        if not tr:
            self.info.configure(text="Bitte zuerst bis zu vier Geräte auswählen (Karten „Auswählen“ oder Strg + Klick).")
            return
        fremd = self.fremd if self._alternative_zu() else None
        self.seiten["vergleich"].setzen(tr, self.anfrage(), fremd, self._kunde_name())
        self.seite_zeigen("vergleich")

    def gegenueberstellung(self, sprache: str, tr: list[Q.Treffer] | None = None, a: Q.Anfrage | None = None,
                           fremd=None) -> Path | None:
        """Gegenüberstellung als PDF speichern und öffnen."""
        from . import vergleich
        if tr is None:
            tr = self._ausgewaehlte_treffer(standard=3)[:vergleich.MAX_VORSCHLAEGE]
            a = self.anfrage()
            fremd = self.fremd if self._alternative_zu() else None
        if not tr:
            return None
        a = a or self.anfrage()
        ordner = self.gegenueberstellungen_ordner()
        ziel = ordner / vergleich.dateiname(fremd, a, sprache)
        for n in range(2, 50):
            try:
                vergleich.erzeugen(ziel, tr, a, fremd, sprache)
                break
            except PermissionError:                     # gleichnamiges PDF ist noch geöffnet
                ziel = ziel.with_name(f"{ziel.stem.rsplit('_(', 1)[0]}_({n}).pdf")
        else:
            messagebox.showerror("Gegenüberstellung", "Das PDF konnte nicht gespeichert werden.", parent=self)
            return None
        self.info.configure(text=f"Gegenüberstellung gespeichert: {ziel}")
        self._merken(f"Gegenüberstellung {sprache.upper()}", tr, anfrage_text=a.text)
        try:
            datei_oeffnen(ziel)
        except OSError:
            pass
        return ziel

    def gegenueberstellungen_ordner(self) -> Path:
        return self.pfad.parent / "Gegenueberstellungen"

    # ------------------------------------------------------------------ Verlauf
    def _kunde_name(self) -> str:
        if not self.vorgang:
            return ""
        k = self.vorgang[1].kunde
        return k.firmenname or k.email or ""

    def _merken(self, aktion: str, treffer: list[Q.Treffer] | None = None, anfrage_text: str | None = None):
        text = (anfrage_text if anfrage_text is not None else self.eingabe.get()).strip()
        if not text:
            return
        fremd = asdict(self.fremd) if self.fremd and text == self.fremd_anfrage else None
        geraete = [{"bestellnummer": t.g.bestellnummer, "name": t.g.name} for t in (treffer or [])]
        try:
            verlauf.hinzufuegen(self.verlauf_pfad, text, aktion, geraete, self.typ.get(), fremd, kunde=self._kunde_name())
        except OSError:
            pass

    # ------------------------------------------------------------------ Anfragen / Weclapp (experimentell)
    def _experimentell_zeigen(self):
        e = self.einstellungen
        if e.experimentell:
            self.nav["anfragen"].pack(fill="x", pady=1, after=self.nav["suche"])
        else:
            self.nav["anfragen"].pack_forget()
            if getattr(self, "aktive_seite", "") == "anfragen":
                self.seite_zeigen("suche")
        if e.experimentell and e.weclapp_adresse:
            self.knopf_weclapp.pack(side="left", padx=(0, 12), before=self.unten_links)
        else:
            self.knopf_weclapp.pack_forget()
        vg = self.seiten.get("vergleich")
        if vg is not None:
            vg.weclapp_zeigen(e.experimentell and bool(e.weclapp_adresse))

    def weclapp_vorbereiten(self, geraete_liste: list[shop.Geraet] | None = None):
        """Ausgewählte Geräte + Kunde der übernommenen Anfrage → Plan in Weclapp (Angebot, ggf. Herstelleranfrage)."""
        from .weclapp_dialog import WeclappDialog
        auswahl = geraete_liste if geraete_liste is not None else [self.zeilen_geraete[i] for i in self._auswahl()]
        if not auswahl:
            messagebox.showinfo("Weclapp", "Bitte zuerst das Gerät bzw. die Geräte für das Angebot auswählen "
                                           "(Karte „Auswählen“ oder Strg + Klick in der Liste).", parent=self)
            return
        if not self.vorgang:
            messagebox.showinfo("Weclapp", "Bitte zuerst eine Kundenanfrage übernehmen (Anfragen → "
                                           "„In Suche übernehmen“) – daraus kommt der Kunde.", parent=self)
            return
        mail, erk = self.vorgang
        menge = erk.menge or 1
        geraete = []
        for g in auswahl:
            if g.bestellnummer not in [x[0] for x in geraete]:
                geraete.append((g.bestellnummer, g.name, menge))
        self._merken("In Weclapp vorbereitet", [self._treffer_zu(g) for g in auswahl])
        WeclappDialog(self, erk.kunde, geraete, erk.termin, notiz=(f"Anfrage: {mail.betreff}" if mail.betreff else ""))

    def anfragen_oeffnen(self):
        self.seite_zeigen("anfragen")

    def vorgang_uebernehmen(self, mail, erkennung):
        """Anfrage von der Anfragen-Seite in die Suche holen. Anhang (PDF/Word) hat Vorrang vor dem Mailtext."""
        self.vorgang = (mail, erkennung)
        self.fremd, self.fremd_anfrage = None, ""
        self.fremd_rahmen.pack_forget()
        self.typ.set("automatisch")
        self.seite_zeigen("suche")
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
        self.seite_zeigen("suche")
        f = e.get("fremd")
        if f:
            felder = datenblatt.Fremdgeraet.__dataclass_fields__
            self._fremd_anzeigen(datenblatt.Fremdgeraet(**{k: v for k, v in f.items() if k in felder}), aus_verlauf=True)
        else:
            self.fremd, self.fremd_anfrage = None, ""
            self.fremd_rahmen.pack_forget()
        typ = e.get("typ") or "automatisch"
        self.typ.set(typ if typ in TYPEN else "automatisch")
        self.eingabe.set(e.get("anfrage", ""))
        if f:
            self._offene_punkte_zeigen(still=True)
        if e.get("geraete"):
            nummern = {g["bestellnummer"] for g in e["geraete"]}
            for nr, (t, weitere, gleich) in enumerate(self.karten_treffer):
                if t.g.bestellnummer in nummern:
                    self.karten_gewaehlt.add(nr)
            self._karten_zeigen()
            sel = [iid for iid, i in self.iid_index.items() if self.zeilen_geraete[i].bestellnummer in nummern]
            for iid in sel:
                self.tv.see(iid)
            self.tv.selection_set(sel)
        self.feld.focus_set()

    # ------------------------------------------------------------------ Kunden-Datenblatt
    def _dnd_einrichten(self):
        """PDF/Word (Suche) bzw. .msg/.eml (Anfragen) ins Fenster ziehen (tkinterdnd2; fehlt sie, gibt es die Knöpfe)."""
        try:
            from tkinterdnd2 import TkinterDnD, DND_FILES
            TkinterDnD._require(self)
            for w in (self, self.tv, self.feld._entry):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._drop)
        except Exception:  # noqa: BLE001
            pass

    def _drop(self, e):
        alle = [Path(p) for p in self.tk.splitlist(e.data)]
        mails = [p for p in alle if p.suffix.lower() in (".msg", ".eml")]
        if mails and self.einstellungen.experimentell:
            self.seite_zeigen("anfragen")
            self.after(10, lambda: self.seiten["anfragen"].dateien_laden(mails))
            return "copy"
        pfade = [p for p in alle if p.suffix.lower() in (".pdf", ".docx", ".docm")]
        if pfade:
            self.seite_zeigen("suche")
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
                wahl = modell_waehlen(self, analyse.modelle, pfad.name)
                if wahl is None:
                    self.info.configure(text="Abgebrochen – kein Modell gewählt.")
                    return
                modell = wahl or None
            elif len(analyse.varianten) > 1:
                wahl = variante_waehlen(self, analyse.varianten, pfad.name)
                if wahl is None:
                    self.info.configure(text="Abgebrochen – keine Variante gewählt.")
                    return
                variante = wahl or None
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
            self.fremd_rahmen.configure(fg_color=TH.GELB)
            self.fremd_lbl.configure(text_color=TH.GELB_TEXT)
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
        self.fremd_rahmen.configure(fg_color=TH.CHIP)
        self.fremd_lbl.configure(text="\n".join([kopf, werte or "Keine Werte gefunden."] + fg.hinweise), text_color=TH.TEXT)
        self.fremd_rahmen.pack(fill="x", pady=(10, 0), after=self.such_karte)

    # ------------------------------------------------------------------ Shopdaten
    def datenquelle_wechseln(self):
        """Nach Änderung in den Einstellungen: andere Datei laden (shopdaten.json / weclappdaten.json), ggf. neu lesen."""
        self.pfad = self.shop_pfad.with_name("weclappdaten.json") if self.einstellungen.datenquelle == "weclapp" \
            else self.shop_pfad
        self.geraete, self.stand = shop.laden(self.pfad)
        self.knopf_laden.configure(text=self._quelle("Shop neu einlesen", "Weclapp neu laden"))
        self._status()
        self.suchen()
        if not self.geraete:
            self.einlesen(still=False)

    def _quelle(self, shop_text: str, weclapp_text: str) -> str:
        return weclapp_text if self.einstellungen.datenquelle == "weclapp" else shop_text

    def _status(self):
        if self.stand:
            try:
                st = datetime.fromisoformat(self.stand).strftime("%d.%m.%Y, %H:%M")
            except ValueError:
                st = self.stand
            self.stand_lbl.configure(text=f"{self._quelle('Shopdaten', 'Weclapp')}: {len(self.geraete)} Geräte\nStand {st}")
        else:
            self.stand_lbl.configure(text=self._quelle("Shopdaten: noch nicht eingelesen", "Weclapp: noch nicht geladen"))

    def _alter_stand(self) -> list[shop.Geraet]:
        """Aktuelle Daten plus Geräte aus shopdaten_vorher.json, die darin fehlen (falls schon einmal etwas verloren ging)."""
        vorher, _ = shop.laden(self.pfad.with_name(self.pfad.stem + "_vorher.json"))
        bekannt = {g.bestellnummer + "|" + g.name for g in self.geraete}
        return self.geraete + [g for g in vorher if g.bestellnummer + "|" + g.name not in bekannt]

    def einlesen(self, still: bool = False):
        if self.laedt:
            return
        self.laedt = True
        self.knopf_laden.configure(state="disabled", text=self._quelle("Shop wird gelesen …", "Weclapp wird gelesen …"))
        self._balken(True)
        self.fortschritt.configure(value=0, maximum=100, mode="indeterminate")   # bis die Serienliste steht
        self.fortschritt.start(12)
        grund_text = "automatisch" if still else "neu"
        self.stand_lbl.configure(text=f"{self._quelle('Shop', 'Weclapp')} wird {grund_text} eingelesen – verbinde …")
        ergebnis: dict = {}
        meldungen: queue.Queue = queue.Queue()      # Tk darf nur aus dem Hauptthread angefasst werden

        def melden(text, erledigt, gesamt):
            meldungen.put((text, erledigt, gesamt))

        bekannte = self._alter_stand()

        weclapp_quelle = self.einstellungen.datenquelle == "weclapp"
        einst = self.einstellungen

        def lauf():
            try:
                if weclapp_quelle:                    # Gerätedaten aus Weclapp (eigene Attribute eps_…)
                    from . import datenquelle, weclapp_dialog
                    demo_basis = shop.laden(self.shop_pfad)[0]
                    wc = weclapp_dialog.verbindung(einst, demo_basis)
                    ergebnis["geraete"] = datenquelle.geraete_lesen(wc.t, melden)
                    ergebnis["fehlend"] = []
                    ergebnis["fertig"] = True
                    return
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
                    was = self._quelle("Shop wird eingelesen …\nSerie", "Weclapp wird gelesen …\nArtikel")
                    self.stand_lbl.configure(text=f"{was} {erledigt}/{gesamt}")
            except queue.Empty:
                pass
            if ergebnis.get("fertig"):
                fertig()
            else:
                self.after(150, abfragen)

        def fertig():
            self.laedt = False
            self.knopf_laden.configure(state="normal", text=self._quelle("Shop neu einlesen", "Weclapp neu laden"))
            self.fortschritt.stop()
            self.fortschritt.configure(mode="determinate")
            self._balken(False)
            self._status()
            if "fehler" in ergebnis:
                fehler = ergebnis["fehler"]
                self.info.configure(text=f"Shop nicht erreichbar ({_fehlertext(fehler)}) – es wird mit dem bisherigen Stand gesucht.")
                self.stand_lbl.configure(text=self.stand_lbl.cget("text") + "\nShop nicht erreichbar")
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
                    shop.speichern(neu, self.pfad.with_name(self.pfad.stem + "_abgelehnt.json"))
                except OSError:
                    pass
                bleibt = f"Die bisherigen Daten ({len(self.geraete)} Geräte) bleiben erhalten." if self.geraete else ""
                if not messagebox.askyesno("Shop einlesen – Ergebnis unplausibel",
                                           f"{grund}\n\n{bleibt}\n\nTrotzdem die neuen Daten übernehmen?",
                                           icon="warning", default="no", parent=self):
                    self.info.configure(text=f"Neue Shopdaten verworfen: {grund}")
                    self.stand_lbl.configure(text=self.stand_lbl.cget("text") + "\nneues Einlesen verworfen")
                    return
            self.geraete = neu
            try:
                shop.speichern(self.geraete, self.pfad)
            except OSError as e:
                messagebox.showwarning("Shop einlesen", f"Daten gelesen, aber nicht gespeichert:\n{e}")
            self.stand = datetime.now().isoformat(timespec="minutes")
            self._status()
            if fehlend:
                self.stand_lbl.configure(text=self.stand_lbl.cget("text") + f"\n{len(fehlend)} Serien unvollständig")
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
                self.info.configure(text=f"Shop eingelesen: {len(self.geraete)} Geräte. Änderungen: Verlauf → "
                                         "„Shop-Änderungen anzeigen“.")

        self.after(150, abfragen)
        threading.Thread(target=lauf, daemon=True).start()

    # ------------------------------------------------------------------ Updates
    def updates_suchen(self, still: bool = True):
        if TESTVERSION:
            return self._test_updates(still)
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

    def _test_updates(self, still: bool):
        """Testkanal: nur neuere Testversionen, ersetzt nur EPS-Produktsuche-TEST.exe."""
        ergebnis: dict = {}

        def lauf():
            ergebnis["neu"] = aktualisierung.neueste_test(timeout=8.0)
            ergebnis["fertig"] = True

        def abfragen():
            if not ergebnis.get("fertig"):
                self.after(200, abfragen)
                return
            neu = ergebnis.get("neu")
            if not neu:
                if not still:
                    messagebox.showinfo("Updates", f"Testversion {__version__} (Build {aktualisierung.build()}) ist "
                                                   "aktuell (oder GitHub ist gerade nicht erreichbar).", parent=self)
                return
            nr, url = neu
            if not aktualisierung.ist_exe():
                return
            if messagebox.askyesno("Neue Testversion", f"Neue Testversion verfügbar (Build {nr}, installiert: "
                                                       f"{aktualisierung.build()}).\n\nJetzt aktualisieren? Die Testversion "
                                                       "startet danach neu. Die normale Version bleibt unverändert.",
                                   parent=self):
                self._test_laden(url)

        threading.Thread(target=lauf, daemon=True).start()
        self.after(200, abfragen)

    def _test_laden(self, url: str):
        stand: dict = {"geladen": 0, "gesamt": 0}
        ergebnis: dict = {}
        self.fortschritt.configure(mode="determinate", value=0, maximum=100)
        self._balken(True)

        def lauf():
            try:
                ergebnis["exe"] = aktualisierung.test_ersetzen(url, lambda g, t: stand.update(geladen=g, gesamt=t))
            except Exception as e:  # noqa: BLE001
                ergebnis["fehler"] = e
            ergebnis["fertig"] = True

        def abfragen():
            if stand["gesamt"]:
                self.fortschritt.configure(value=stand["geladen"] * 100 / stand["gesamt"])
            self.info.configure(text=f"Lade Testversion … {stand['geladen'] // 1_000_000} MB")
            if not ergebnis.get("fertig"):
                self.after(200, abfragen)
                return
            self._balken(False)
            if "fehler" in ergebnis:
                messagebox.showerror("Update", f"Die Testversion konnte nicht aktualisiert werden:\n{ergebnis['fehler']}",
                                     parent=self)
                return
            try:
                aktualisierung.starten(ergebnis["exe"])
            except OSError as e:
                messagebox.showerror("Update", f"Neue Testversion geladen, Start fehlgeschlagen:\n{e}", parent=self)
                return
            self.destroy()
            os._exit(0)

        threading.Thread(target=lauf, daemon=True).start()
        self.after(200, abfragen)

    def _update_laden(self, version: str, url: str):
        ziel = aktualisierung.zieldatei(aktualisierung.exe_pfad().parent, version)
        stand: dict = {"geladen": 0, "gesamt": 0}
        ergebnis: dict = {}
        self.fortschritt.configure(mode="determinate", value=0, maximum=100)
        self._balken(True)

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
            self._balken(False)
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
