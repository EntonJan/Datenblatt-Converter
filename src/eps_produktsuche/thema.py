"""Aussehen der Produktsuche (ab 1.4): EPS-Farben, hell und dunkel umschaltbar.

CustomTkinter-Widgets bekommen Farbpaare (hell, dunkel) und wechseln selbst. Die Tabellen (ttk.Treeview) kennt
CustomTkinter nicht – die färbt `tabellen_stil()` bei jedem Wechsel neu ein.
"""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from . import suche as Q

SCHRIFT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

# (hell, dunkel)
BG = ("#F4F6FA", "#0F1726")
FLAECHE = ("#FFFFFF", "#172238")
SEITE = ("#FFFFFF", "#131D30")
RAND = ("#E3E8F0", "#2A3A58")
TEXT = ("#1C2633", "#E6ECF5")
GRAU = ("#5B6575", "#AEBBD0")
AKZENT = ("#35528C", "#52B4D7")
AKZENT_HOVER = ("#2B4373", "#7CC8E4")
AKZENT_TEXT = ("#FFFFFF", "#0B2A3A")
CHIP = ("#EAF0FA", "#1E2A42")
CHIP_TEXT = ("#253C6A", "#CFE6F2")
KACHEL = ("#F4F6FA", "#0F1726")
EINGABE = ("#FFFFFF", "#0F1726")
KNOPF_HOVER = ("#EEF2F8", "#22314D")
GELB = ("#FFF4D6", "#3A2E12")
GELB_TEXT = ("#5A4300", "#F2D48A")
GRUEN_BG = ("#E3F2E4", "#18331F")
GRUEN = ("#1E5E22", "#7BD88F")
GRUEN_RAND = ("#2E7D32", "#4CAF66")
ORANGE = ("#8E5A00", "#F2C46D")
LINK = ("#35528C", "#7CC8E4")
TEST = ("#B26A00", "#FFD54F")

# Bewertungsfarben in Tabellen: (hell, dunkel)
BEWERTUNG = {Q.PASST: ("#2E7D32", "#7BD88F"), Q.GROESSER: ("#1B4F72", "#8FB4F0"), Q.PARALLEL: ("#8E5A00", "#F2C46D"),
             Q.REIHE: ("#8E5A00", "#F2C46D"), Q.KNAPP_DARUNTER: ("#8A8F98", "#7D889A")}


def dunkel() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def f(paar: tuple[str, str]) -> str:
    """Aktuelle Farbe eines Paares (für Tk-Widgets, die keine Paare kennen)."""
    return paar[1] if dunkel() else paar[0]


def schrift(groesse: int = 13, fett: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(family=SCHRIFT, size=groesse, weight="bold" if fett else "normal")


def modus_setzen(an: bool) -> None:
    ctk.set_appearance_mode("dark" if an else "light")


def tabellen_stil(root: tk.Misc) -> None:
    """ttk-Tabellen, Fortschrittsbalken und Trenner passend zum Modus einfärben."""
    s = ttk.Style(root)
    try:
        s.theme_use("clam")                       # „vista“ lässt keine eigenen Hintergrundfarben zu
    except tk.TclError:
        pass
    fl, tx, rd, gr = f(FLAECHE), f(TEXT), f(RAND), f(GRAU)
    s.configure("Treeview", background=fl, fieldbackground=fl, foreground=tx, bordercolor=rd, lightcolor=fl,
                darkcolor=fl, rowheight=30, font=(SCHRIFT, 10), borderwidth=0)
    s.map("Treeview", background=[("selected", f(("#DCE6F5", "#24406B")))],
          foreground=[("selected", tx)])
    s.configure("Treeview.Heading", background=fl, foreground=gr, font=(SCHRIFT, 9, "bold"), relief="flat",
                bordercolor=rd, lightcolor=fl, darkcolor=fl, padding=(6, 6))
    s.map("Treeview.Heading", background=[("active", f(KNOPF_HOVER))])
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])     # ohne Rahmen
    s.configure("Treeview", indent=14)


def tabelle_tags(tv: ttk.Treeview) -> None:
    for kat, paar in BEWERTUNG.items():
        tv.tag_configure(kat, foreground=f(paar))
    tv.tag_configure("serie", font=(SCHRIFT, 10, "bold"))
    tv.tag_configure("formular", foreground=f(GRUEN))
    tv.tag_configure("grau", foreground=f(GRAU))


# ---------------------------------------------------------------- kleine Bausteine

def karte(master, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(master, fg_color=FLAECHE, border_color=RAND, border_width=1, corner_radius=12, **kw)


def knopf(master, text: str, command=None, haupt: bool = False, **kw) -> ctk.CTkButton:
    kw.setdefault("height", 36)
    if haupt:
        return ctk.CTkButton(master, text=text, command=command, fg_color=AKZENT, hover_color=AKZENT_HOVER,
                             text_color=AKZENT_TEXT, corner_radius=8, font=schrift(13, True), **kw)
    return ctk.CTkButton(master, text=text, command=command, fg_color=FLAECHE, hover_color=KNOPF_HOVER,
                         text_color=TEXT, border_color=RAND, border_width=1, corner_radius=8,
                         font=schrift(13), **kw)


def text(master, inhalt: str = "", groesse: int = 13, fett: bool = False, farbe=TEXT, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=inhalt, font=schrift(groesse, fett), text_color=farbe, **kw)


def eingabe(master, **kw) -> ctk.CTkEntry:
    kw.setdefault("height", 34)
    return ctk.CTkEntry(master, fg_color=EINGABE, border_color=RAND, text_color=TEXT, corner_radius=6,
                        font=schrift(13), **kw)


def schalter(master, text_: str, variable, command=None) -> ctk.CTkSwitch:
    return ctk.CTkSwitch(master, text=text_, variable=variable, command=command, progress_color=("#52B4D7", "#52B4D7"),
                         font=schrift(12), text_color=TEXT, onvalue=True, offvalue=False)


def auswahl(master, werte: list[str], variable=None, command=None, breite: int = 160) -> ctk.CTkOptionMenu:
    return ctk.CTkOptionMenu(master, values=werte, variable=variable, command=command, width=breite, height=34,
                             fg_color=FLAECHE, button_color=FLAECHE, button_hover_color=KNOPF_HOVER, text_color=TEXT,
                             dropdown_fg_color=FLAECHE, dropdown_text_color=TEXT, dropdown_hover_color=KNOPF_HOVER,
                             font=schrift(13), dropdown_font=schrift(12), corner_radius=8)


def tabelle(master, spalten: list[tuple[str, str, int]], baum: bool = False, mehrfach: bool = False,
            dehnen: tuple[str, ...] = ()) -> tuple[ctk.CTkFrame, ttk.Treeview]:
    """Tabelle in einer Karte mit CustomTkinter-Bildlaufleisten. Gibt (Karte, Treeview) zurück."""
    rahmen = karte(master)
    tv = ttk.Treeview(rahmen, columns=[k for k, _, _ in spalten], show="tree headings" if baum else "headings",
                      selectmode="extended" if mehrfach else "browse")
    if baum:
        tv.column("#0", width=30, minwidth=30, stretch=False)
    for k, t, b in spalten:
        tv.heading(k, text=t.upper(), anchor="w")
        tv.column(k, width=b, minwidth=40, stretch=k in dehnen)
    sy = ctk.CTkScrollbar(rahmen, command=tv.yview, button_color=RAND, fg_color="transparent")
    sx = ctk.CTkScrollbar(rahmen, command=tv.xview, orientation="horizontal", button_color=RAND, fg_color="transparent",
                          height=12)
    tv.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    tv.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(6, 0))
    sy.grid(row=0, column=1, sticky="ns", pady=6)
    sx.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
    rahmen.rowconfigure(0, weight=1)
    rahmen.columnconfigure(0, weight=1)
    tabelle_tags(tv)
    return rahmen, tv


class Fortschritt(ctk.CTkProgressBar):
    """CTkProgressBar mit der Bedienung des alten ttk.Progressbar (value/maximum/mode)."""

    def __init__(self, master, **kw):
        super().__init__(master, height=6, progress_color=("#52B4D7", "#52B4D7"), fg_color=RAND, **kw)
        self._max = 100.0
        self.set(0)

    def configure(self, require_redraw=False, **kw):  # noqa: D401
        wert = kw.pop("value", None)
        maximum = kw.pop("maximum", None)
        if maximum is not None:
            self._max = float(maximum) or 1.0
        if kw:
            super().configure(require_redraw, **kw)
        if wert is not None:
            self.set(max(0.0, min(1.0, float(wert) / self._max)))

    def start(self, _intervall=None):
        super().start()

    def cget(self, name):
        if name == "mode":
            return self._mode
        return super().cget(name)
