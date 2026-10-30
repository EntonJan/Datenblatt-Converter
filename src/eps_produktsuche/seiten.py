"""Seiten der Produktsuche neben der Suche: Verlauf, Gegenüberstellungen, Einstellungen (+ Shop-Änderungen)."""
from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog

import customtkinter as ctk

from . import shop, suche as Q, verlauf, thema as TH
from .einstellungen import Anfrageordner


def kopf(master, titel: str, unter: str = "") -> tuple[ctk.CTkFrame, ctk.CTkLabel]:
    rahmen = ctk.CTkFrame(master, fg_color="transparent")
    rahmen.pack(fill="x", pady=(0, 14))
    links = ctk.CTkFrame(rahmen, fg_color="transparent")
    links.pack(side="left")
    TH.text(links, titel, 24, True, anchor="w").pack(anchor="w")
    u = TH.text(links, unter, 13, farbe=TH.GRAU, anchor="w")
    u.pack(anchor="w")
    return rahmen, u


def _zeit(iso: str, fmt: str = "%d.%m. %H:%M") -> str:
    try:
        return datetime.fromisoformat(iso).strftime(fmt)
    except (TypeError, ValueError):
        return iso or ""


# ====================================================================== Verlauf

class VerlaufSeite(ctk.CTkFrame):
    """Alle gemerkten Suchen mit Kunde, Geräten und Ergebnis; Zahlen der Woche; Shop-Änderungen."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        k, self.unter = kopf(self, "Verlauf", "Gemerkte Suchen (Enter im Suchfeld oder eine Aktion) · Doppelklick öffnet "
                                              "die Suche wieder")
        self.filter = tk.StringVar()
        self.nur_kunde = tk.BooleanVar(value=False)
        TH.schalter(k, "nur mit Kunde", self.nur_kunde, self.fuellen).pack(side="right", padx=(12, 0))
        TH.eingabe(k, textvariable=self.filter, width=280).pack(side="right")
        TH.text(k, "Suchen:", 13, farbe=TH.GRAU).pack(side="right", padx=(0, 8))
        self.filter.trace_add("write", lambda *a: self.fuellen())

        self.zahlen = ctk.CTkFrame(self, fg_color="transparent")
        self.zahlen.pack(fill="x", pady=(0, 14))
        self.kacheln = {}
        for i, (key, titel) in enumerate((("woche", "Suchen diese Woche"), ("mit_kunde", "davon mit Kunde"),
                                         ("empfohlen", "Empfehlung / Gegenüberstellung"), ("shop", "Shopdaten seit "
                                                                                                    "letztem Einlesen"))):
            kachel = TH.karte(self.zahlen)
            kachel.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 14, 0))
            self.zahlen.columnconfigure(i, weight=1, uniform="z")
            t = TH.text(kachel, titel, 12, farbe=TH.GRAU, anchor="w")
            t.pack(fill="x", padx=16, pady=(12, 0))
            w = TH.text(kachel, "–", 26, True, anchor="w")
            w.pack(fill="x", padx=16, pady=(0, 12))
            self.kacheln[key] = (t, w)
        shop_w = self.kacheln["shop"][1]
        shop_w.configure(cursor="hand2")
        shop_w.bind("<Button-1>", lambda e: self.aenderungen_zeigen())

        sp = [("zeit", "Zeit", 110), ("anfrage", "Suche", 300), ("kunde", "Kunde", 200), ("geraete", "Geräte", 280),
              ("aktion", "Ergebnis", 190), ("notiz", "Notiz", 160)]
        rahmen, self.tv = TH.tabelle(self, sp, dehnen=("anfrage", "geraete", "notiz"))
        rahmen.pack(fill="both", expand=True)
        app.tabellen.append(self.tv)
        self.tv.bind("<Double-1>", lambda e: self.uebernehmen())
        self.tv.bind("<Return>", lambda e: self.uebernehmen())

        unten = ctk.CTkFrame(self, fg_color="transparent")
        unten.pack(fill="x", pady=(12, 0))
        TH.knopf(unten, "Suche erneut öffnen", self.uebernehmen, haupt=True).pack(side="left")
        TH.knopf(unten, "Notiz …", self.notiz).pack(side="left", padx=(8, 0))
        TH.knopf(unten, "Eintrag löschen", self.loeschen).pack(side="left", padx=(8, 0))
        TH.knopf(unten, "Shop-Änderungen anzeigen", self.aenderungen_zeigen).pack(side="left", padx=(24, 0))
        self.anzahl = TH.text(unten, "", 12, farbe=TH.GRAU)
        self.anzahl.pack(side="right")
        self.eintraege: list[dict] = []

    def zeigen(self):
        self.fuellen()
        self._zahlen()

    def _zahlen(self):
        z = verlauf.kennzahlen(verlauf.laden(self.app.verlauf_pfad))
        self.kacheln["woche"][1].configure(text=str(z["woche"]))
        self.kacheln["mit_kunde"][1].configure(text=str(z["mit_kunde"]))
        if self.app.einstellungen.experimentell and self.app.einstellungen.weclapp_adresse:
            self.kacheln["empfohlen"][0].configure(text="in Weclapp vorbereitet")
            self.kacheln["empfohlen"][1].configure(text=str(z["weclapp"]))
        else:
            self.kacheln["empfohlen"][0].configure(text="Empfehlung / Gegenüberstellung")
            self.kacheln["empfohlen"][1].configure(text=str(z["empfohlen"]))
        a = self._aenderungen()
        if a is None:
            self.kacheln["shop"][1].configure(text="–")
        else:
            text = f"+{len(a['neu'])} / −{len(a['weg'])}"
            if a["geaendert"]:
                text += f" / ~{len(a['geaendert'])}"
            self.kacheln["shop"][1].configure(text=text)

    def fuellen(self):
        self.eintraege = verlauf.laden(self.app.verlauf_pfad)
        self.tv.delete(*self.tv.get_children())
        n = 0
        for i, e in enumerate(self.eintraege):
            if not verlauf.passt(e, self.filter.get()):
                continue
            kunde = verlauf.kunde_von(e)
            if self.nur_kunde.get() and not kunde:
                continue
            geraete = ", ".join(f"{g['bestellnummer']} {g['name']}" for g in e.get("geraete", []))
            self.tv.insert("", "end", iid=str(i), values=[_zeit(e.get("zeit", "")), e.get("anfrage", ""), kunde or "—",
                                                          geraete or "—", ", ".join(e.get("aktionen", [])),
                                                          e.get("notiz", "")])
            n += 1
        self.anzahl.configure(text=f"{n} von {len(self.eintraege)} Einträgen")

    def _gewaehlt(self) -> int | None:
        sel = self.tv.selection()
        return int(sel[0]) if sel else None

    def uebernehmen(self):
        i = self._gewaehlt()
        if i is not None:
            self.app.verlauf_uebernehmen(self.eintraege[i])

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
            self.zeigen()

    # ---------------------------------------------------------------- Shop-Änderungen
    def _aenderungen(self) -> dict | None:
        vorher_pfad = self.app.pfad.with_name(self.app.pfad.stem + "_vorher.json")
        if not vorher_pfad.exists():
            return None
        alt, _ = shop.laden(vorher_pfad)
        if not alt:
            return None
        a = shop.aenderungen(alt, self.app.geraete)
        a["stand_alt"] = shop.stand_von(vorher_pfad)
        a["stand_neu"] = self.app.stand
        return a

    def aenderungen_zeigen(self):
        a = self._aenderungen()
        if a is None:
            messagebox.showinfo("Shop-Änderungen", "Es gibt noch keinen früheren Stand zum Vergleichen – nach dem "
                                                   "nächsten „Shop neu einlesen“ steht hier, was sich geändert hat.",
                                parent=self)
            return
        ShopAenderungenDialog(self.app, a)


class ShopAenderungenDialog(ctk.CTkToplevel):
    """Was ist seit dem letzten Einlesen neu, weg oder anders? Doppelklick sucht das Gerät."""

    def __init__(self, app, a: dict):
        super().__init__(app, fg_color=TH.BG)
        self.app = app
        self.title("Shop-Änderungen")
        self.geometry("1100x620")
        self.transient(app)
        rahmen = ctk.CTkFrame(self, fg_color="transparent")
        rahmen.pack(fill="both", expand=True, padx=18, pady=16)
        TH.text(rahmen, "Shop-Änderungen", 22, True, anchor="w").pack(anchor="w")
        TH.text(rahmen, f"Stand {_zeit(a['stand_alt'], '%d.%m.%Y %H:%M')} → {_zeit(a['stand_neu'], '%d.%m.%Y %H:%M')} · "
                        f"{len(a['neu'])} neu · {len(a['weg'])} entfernt · {len(a['geaendert'])} geändert",
                13, farbe=TH.GRAU, anchor="w").pack(anchor="w", pady=(0, 12))
        sp = [("nr", "Nr.", 80), ("name", "Gerät", 360), ("serie", "Serie", 220), ("was", "Was", 360)]
        t_rahmen, self.tv = TH.tabelle(rahmen, sp, baum=True, dehnen=("name", "was"))
        t_rahmen.pack(fill="both", expand=True)
        TH.tabelle_tags(self.tv)
        self.tv.tag_configure("neu", foreground=TH.f(TH.GRUEN))
        self.tv.tag_configure("weg", foreground=TH.f(("#B71C1C", "#F28B82")))
        self.text_zeilen = []
        for key, titel, tag in (("neu", "Neu im Shop", "neu"), ("weg", "Nicht mehr im Shop", "weg"),
                                ("geaendert", "Geändert", "")):
            liste = a[key]
            gruppe = self.tv.insert("", "end", text="", open=bool(liste) and len(liste) <= 60, tags=("serie",),
                                    values=["", f"{titel} ({len(liste)})", "", ""])
            self.text_zeilen.append(f"{titel} ({len(liste)}):")
            for eintrag in liste:
                if key == "geaendert":
                    alt, g, felder = eintrag
                    was = "; ".join(f"{f}: {getattr(alt, _FELD[f])} → {getattr(g, _FELD[f])}" for f in felder)
                else:
                    g, was = eintrag, ""
                self.tv.insert(gruppe, "end", values=[g.bestellnummer, g.name, g.serie, was], tags=(tag,) if tag else ())
                self.text_zeilen.append(f"  {g.bestellnummer} {g.name}" + (f" – {was}" if was else ""))
        self.tv.bind("<Double-1>", lambda e: self.suchen())
        unten = ctk.CTkFrame(rahmen, fg_color="transparent")
        unten.pack(fill="x", pady=(12, 0))
        TH.knopf(unten, "Gerät in der Suche öffnen", self.suchen, haupt=True).pack(side="left")
        TH.knopf(unten, "Als Liste kopieren", self.kopieren).pack(side="left", padx=8)
        TH.knopf(unten, "Schließen", self.destroy).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(50, self.lift)

    def suchen(self):
        sel = self.tv.selection()
        if not sel:
            return
        nr = self.tv.item(sel[0], "values")[0]
        if nr:
            self.app.seite_zeigen("suche")
            self.app.typ.set("alle")
            self.app.eingabe.set(nr)
            self.destroy()

    def kopieren(self):
        self.clipboard_clear()
        self.clipboard_append("\n".join(self.text_zeilen))


_FELD = {"Name": "name", "Spannung": "spannung", "Strom": "strom", "Leistung": "leistung", "Serie": "serie"}


# ====================================================================== Gegenüberstellung

ZEILEN = [("bezeichnung", "Gerät"), ("bewertung", "Bewertung"), ("typ", "Gerätetyp"), ("spannung", "Spannung"),
          ("strom", "Strom"), ("leistung", "Leistung"), ("bauform", "Bauform"), ("merkmale", "Merkmale"),
          ("loesung", "Lösung"), ("reserve", "Reserve"), ("hinweis", "Hinweis")]


class GegenueberstellungSeite(ctk.CTkFrame):
    """Ausgewählte Geräte nebeneinander; daraus PDF (DE/EN), Empfehlung oder Weclapp. Darunter die gespeicherten PDFs."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.treffer: list[Q.Treffer] = []
        self.anfrage: Q.Anfrage | None = None
        self.fremd = None
        k, self.unter = kopf(self, "Gegenüberstellung", "Noch keine Geräte – in der Suche auswählen und "
                                                        "„Gegenüberstellung …“ klicken.")
        self.sprache = tk.StringVar(value="Deutsch")
        ctk.CTkSegmentedButton(k, values=["Deutsch", "English"], variable=self.sprache, font=TH.schrift(12),
                               selected_color=TH.AKZENT, selected_hover_color=TH.AKZENT_HOVER,
                               unselected_color=TH.FLAECHE, unselected_hover_color=TH.KNOPF_HOVER,
                               text_color=(("#1C2633"), ("#E6ECF5")), fg_color=TH.RAND).pack(side="right")
        self.tabelle = ctk.CTkScrollableFrame(self, fg_color=TH.FLAECHE, border_color=TH.RAND, border_width=1,
                                              corner_radius=12, height=360)
        self.tabelle.pack(fill="both", expand=True)
        self.knoepfe = ctk.CTkFrame(self, fg_color="transparent")
        self.knoepfe.pack(fill="x", pady=(12, 0))
        TH.knopf(self.knoepfe, "Als PDF speichern", self.pdf, haupt=True).pack(side="left")
        TH.knopf(self.knoepfe, "Empfehlung kopieren", self.empfehlung).pack(side="left", padx=(8, 0))
        self.knopf_weclapp = TH.knopf(self.knoepfe, "In Weclapp vorbereiten …", self.weclapp)
        TH.knopf(self.knoepfe, "Zurück zur Suche", lambda: self.app.seite_zeigen("suche")).pack(side="right")

        TH.text(self, "Gespeicherte Gegenüberstellungen", 16, True, anchor="w").pack(fill="x", pady=(18, 6))
        sp = [("datei", "Datei", 520), ("zeit", "Gespeichert", 150)]
        rahmen, self.tv = TH.tabelle(self, sp, dehnen=("datei",))
        rahmen.configure(height=180)
        rahmen.pack(fill="x")
        rahmen.pack_propagate(False)
        rahmen.grid_propagate(False)
        app.tabellen.append(self.tv)
        self.tv.bind("<Double-1>", lambda e: self.datei_oeffnen())
        u2 = ctk.CTkFrame(self, fg_color="transparent")
        u2.pack(fill="x", pady=(8, 0))
        TH.knopf(u2, "Öffnen", self.datei_oeffnen).pack(side="left")
        TH.knopf(u2, "Ordner öffnen", self.ordner_oeffnen).pack(side="left", padx=8)
        self._tabelle_bauen()

    def weclapp_zeigen(self, an: bool):
        if an:
            self.knopf_weclapp.pack(side="left", padx=(8, 0))
        else:
            self.knopf_weclapp.pack_forget()

    def zeigen(self):
        self.dateien_fuellen()

    def setzen(self, treffer: list[Q.Treffer], anfrage: Q.Anfrage, fremd, kunde: str = ""):
        self.treffer, self.anfrage, self.fremd = list(treffer), anfrage, fremd
        fuer = [x for x in (kunde, (fremd.hersteller_typ or fremd.modell) and f"Alternative zu {fremd.hersteller_typ or fremd.modell}"
                            if fremd else "", anfrage.text.strip()) if x]
        text = ("Für: " + " · ".join(fuer)) if fuer else ""
        if self._wunsch() and len(self.treffer) > 1:
            text += "  ·  grün = gewünschtes Merkmal, das nicht jedes Gerät hat"
        self.unter.configure(text=text)
        self._tabelle_bauen()

    def _sp(self) -> str:
        return "en" if self.sprache.get() == "English" else "de"

    def _tabelle_bauen(self):
        from . import vergleich
        for w in self.tabelle.winfo_children():
            w.destroy()
        if not self.treffer:
            TH.text(self.tabelle, "Noch keine Geräte ausgewählt.\nIn der Suche Karten „Auswählen“ oder Zeilen markieren "
                                  "(Strg + Klick, bis zu vier) und „Gegenüberstellung …“ klicken.",
                    13, farbe=TH.GRAU, justify="left").grid(row=0, column=0, padx=16, pady=24, sticky="w")
            return
        t = self.tabelle
        t.columnconfigure(0, weight=0, minsize=150)
        for j, tr in enumerate(self.treffer, start=1):
            t.columnconfigure(j, weight=1, uniform="g")
            kopfzelle = ctk.CTkFrame(t, fg_color="transparent")
            kopfzelle.grid(row=0, column=j, sticky="new", padx=10, pady=(12, 6))
            genau = tr.kategorie == Q.PASST
            ctk.CTkLabel(kopfzelle, text=tr.bewertung, corner_radius=10, height=22, padx=8, font=TH.schrift(11, True),
                         fg_color=TH.GRUEN_BG if genau else TH.CHIP, text_color=TH.GRUEN if genau else TH.CHIP_TEXT
                         ).pack(anchor="w")
            TH.text(kopfzelle, f"Nr. {tr.g.bestellnummer}", 11, farbe=TH.GRAU, anchor="w").pack(anchor="w", pady=(4, 0))
            weg = TH.text(kopfzelle, "entfernen", 11, farbe=TH.LINK, anchor="w", cursor="hand2")
            weg.pack(anchor="w")
            weg.bind("<Button-1>", lambda e, i=j - 1: self.entfernen(i))
        TH.text(t, "MERKMAL", 11, True, farbe=TH.GRAU, anchor="w").grid(row=0, column=0, sticky="sw", padx=16, pady=(12, 6))
        wunsch = self._wunsch()
        for r, (key, titel) in enumerate(ZEILEN, start=1):
            ctk.CTkFrame(t, fg_color=TH.RAND, height=1).grid(row=2 * r - 1, column=0, columnspan=len(self.treffer) + 1,
                                                            sticky="ew", padx=8)
            TH.text(t, titel, 13, True, farbe=TH.GRAU, anchor="nw").grid(row=2 * r, column=0, sticky="nw", padx=16, pady=8)
            werte = [self._wert(key, tr, vergleich) for tr in self.treffer]
            for j, w in enumerate(werte, start=1):
                lbl = TH.text(t, w or "–", 13, key == "bezeichnung", anchor="nw", justify="left", wraplength=260)
                if key in ("merkmale", "bauform") and any(x in (w or "") for x in wunsch) and len(werte) > 1 and \
                        not all(any(x in (v or "") for x in wunsch) for v in werte):
                    lbl.configure(fg_color=TH.GRUEN_BG, text_color=TH.GRUEN, corner_radius=6)
                lbl.grid(row=2 * r, column=j, sticky="nw", padx=10, pady=8)

    def _wunsch(self) -> list[str]:
        """Merkmale aus der Anfrage – in der Tabelle grün, wenn nicht alle Geräte sie erfüllen."""
        a = self.anfrage
        if a is None:
            return []
        return [x for x, ja in ((a.bauform, a.bauform), ("bidirektional", a.bidirektional),
                                ("Netzrückspeisung", a.rueckspeisung), ("wassergekühlt", a.wasser)) if ja]

    @staticmethod
    def _wert(key: str, tr: Q.Treffer, vergleich) -> str:
        g = tr.g
        return {"bezeichnung": g.name, "bewertung": tr.bewertung,
                "typ": g.geraetetyp + (" (bidirektional)" if g.bidirektional and g.geraetetyp != shop.LAST else ""),
                "spannung": g.spannung or "–", "strom": g.strom or "–", "leistung": g.leistung or "–",
                "bauform": g.bauart or "–", "merkmale": vergleich._merkmale_geraet(g, "de"),
                "loesung": vergleich._loesung(tr, "de", kunde=False), "reserve": tr.reserve_text() or "–",
                "hinweis": tr.hinweis or "–"}[key]

    def entfernen(self, i: int):
        if 0 <= i < len(self.treffer):
            del self.treffer[i]
            self._tabelle_bauen()

    def pdf(self):
        if not self.treffer:
            return
        self.app.gegenueberstellung(self._sp(), self.treffer, self.anfrage, self.fremd)
        self.dateien_fuellen()

    def empfehlung(self):
        if self.treffer:
            self.app.kopieren(self._sp(), self.treffer)
            self.unter.configure(text=self.unter.cget("text").split("  ·  ✓")[0] + "  ·  ✓ Empfehlung kopiert")

    def weclapp(self):
        if self.treffer:
            self.app.weclapp_vorbereiten([t.g for t in self.treffer])

    def dateien_fuellen(self):
        self.tv.delete(*self.tv.get_children())
        ordner = self.app.gegenueberstellungen_ordner()
        try:
            dateien = sorted(ordner.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)[:200]
        except OSError:
            dateien = []
        for p in dateien:
            self.tv.insert("", "end", iid=str(p), values=[p.name, datetime.fromtimestamp(p.stat().st_mtime)
                                                          .strftime("%d.%m.%Y %H:%M")])

    def datei_oeffnen(self):
        from .gui import datei_oeffnen
        sel = self.tv.selection()
        if sel:
            try:
                datei_oeffnen(Path(sel[0]))
            except OSError as e:
                messagebox.showerror("Gegenüberstellung", str(e), parent=self)

    def ordner_oeffnen(self):
        from .gui import datei_oeffnen
        ordner = self.app.gegenueberstellungen_ordner()
        ordner.mkdir(parents=True, exist_ok=True)
        try:
            datei_oeffnen(ordner)
        except OSError as e:
            messagebox.showerror("Gegenüberstellung", str(e), parent=self)


# ====================================================================== Einstellungen

class EinstellungenSeite(ctk.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        k, self.unter = kopf(self, "Einstellungen", "Gilt für diesen Rechner · „Speichern“ übernimmt die Änderungen")
        spalten = ctk.CTkFrame(self, fg_color="transparent")
        spalten.pack(fill="both", expand=True)
        spalten.columnconfigure(0, weight=2, uniform="s")
        spalten.columnconfigure(1, weight=3, uniform="s")
        links = ctk.CTkFrame(spalten, fg_color="transparent")
        links.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        rechts = ctk.CTkFrame(spalten, fg_color="transparent")
        rechts.grid(row=0, column=1, sticky="nsew")

        e = app.einstellungen
        # Darstellung
        g = self._gruppe(links, "Darstellung")
        self.dunkel_var = tk.BooleanVar(value=e.dunkelmodus)
        self._zeile(g, "Dunkelmodus", "Gilt sofort und bleibt nach dem Neustart erhalten",
                    ctk.CTkSwitch(g, text="", variable=self.dunkel_var, width=46, progress_color=("#52B4D7", "#52B4D7"),
                                  command=lambda: app.dunkel_setzen(self.dunkel_var.get())))
        # Funktionen
        g = self._gruppe(links, "Funktionen")
        self.experimentell = tk.BooleanVar(value=e.experimentell)
        self._zeile(g, "Kundenanfragen aus Outlook", "Testphase: Seite „Anfragen“ und Weclapp-Vorbereitung",
                    ctk.CTkSwitch(g, text="", variable=self.experimentell, width=46,
                                  progress_color=("#52B4D7", "#52B4D7")))
        # Datenquelle
        g = self._gruppe(links, "Datenquelle")
        self.quelle = tk.StringVar(value="Weclapp" if e.datenquelle == "weclapp" else "Shop")
        self._zeile(g, "Gerätedaten für die Suche", "Weclapp erst, wenn die Artikel dort angelegt sind",
                    ctk.CTkSegmentedButton(g, values=["Shop", "Weclapp"], variable=self.quelle, font=TH.schrift(12),
                                           selected_color=TH.AKZENT, selected_hover_color=TH.AKZENT_HOVER,
                                           unselected_color=TH.FLAECHE, unselected_hover_color=TH.KNOPF_HOVER,
                                           text_color=("#1C2633", "#E6ECF5"), fg_color=TH.RAND))
        self.frist = tk.StringVar(value=str(e.preisfrist_monate))
        self._zeile(g, "Einkaufspreis gilt als zu alt nach", "Monate – ältere Preise → Herstelleranfrage (Weclapp)",
                    TH.auswahl(g, [str(x) for x in (1, 2, 3, 6, 9, 12, 18, 24, 36)], self.frist, breite=90))
        # Programm
        g = self._gruppe(links, "Programm")
        from . import __version__, aktualisierung
        self._zeile(g, f"Version {__version__}", f"Build {aktualisierung.build()}" if "dev" in __version__ else "",
                    TH.knopf(g, "Nach Updates suchen", lambda: app.updates_suchen(still=False), height=32))
        self._zeile(g, "Datenordner", str(app.pfad.parent),
                    TH.knopf(g, "Öffnen", self._datenordner, height=32))

        # Outlook
        g = self._gruppe(rechts, "Outlook-Anfragen")
        TH.text(g, "Anfrage-Ordner im klassischen Outlook (Pfad mit „/“; gemeinsames Postfach: dessen Name vorn, "
                   "z. B. „vertrieb@eps-germany.de/Posteingang/Anfragen“)", 12, farbe=TH.GRAU, anchor="w",
                justify="left", wraplength=560).pack(fill="x", padx=18)
        self.ordner_rahmen = ctk.CTkFrame(g, fg_color="transparent")
        self.ordner_rahmen.pack(fill="x", padx=18, pady=(6, 0))
        self.zeilen: list[tuple[tk.StringVar, tk.StringVar, tk.BooleanVar]] = []
        self.erledigt = tk.StringVar()
        self.bearbeitung = tk.StringVar()
        self.domains = tk.StringVar()
        self._zeile(g, "Erledigte Mails nach", "Name = Unterordner, mit „/“ = fester Ordner",
                    TH.eingabe(g, textvariable=self.erledigt, width=300))
        self._zeile(g, "„In Bearbeitung“", "für gemeinsame Postfächer (Name oder Pfad)",
                    TH.eingabe(g, textvariable=self.bearbeitung, width=300))
        self._zeile(g, "Eigene Domains", "Mails von dort = Weiterleitung, der Kunde steht darunter",
                    TH.eingabe(g, textvariable=self.domains, width=300))
        # Weclapp
        g = self._gruppe(rechts, "Weclapp")
        self.weclapp = tk.StringVar()
        self._zeile(g, "Adresse", "z. B. „firma.weclapp.com“ · „demo“ = nachgebautes Weclapp zum Ausprobieren",
                    TH.eingabe(g, textvariable=self.weclapp, width=300))
        wk = ctk.CTkFrame(g, fg_color="transparent")
        TH.knopf(wk, "Token eintragen …", self.token_eintragen, height=32).pack(side="left")
        TH.knopf(wk, "Verbindung testen", self.verbindung_testen, height=32).pack(side="left", padx=(8, 0))
        self._zeile(g, "Zugang", "Token liegt nur in der Windows-Anmeldeinformationsverwaltung", wk)
        self.weclapp_status = TH.text(g, "", 12, farbe=TH.GRAU, anchor="w", justify="left", wraplength=560)
        self.weclapp_status.pack(fill="x", padx=18, pady=(0, 14))

        unten = ctk.CTkFrame(self, fg_color="transparent")
        unten.pack(fill="x", pady=(14, 4))
        TH.knopf(unten, "Speichern", self.speichern, haupt=True, width=140).pack(side="left")
        TH.knopf(unten, "Verwerfen", self.zeigen).pack(side="left", padx=8)
        self.gespeichert = TH.text(unten, "", 12, farbe=TH.GRUEN)
        self.gespeichert.pack(side="left", padx=8)
        self.zeigen()

    # ---------------------------------------------------------------- Bausteine
    @staticmethod
    def _gruppe(master, titel: str) -> ctk.CTkFrame:
        g = TH.karte(master)
        g.pack(fill="x", pady=(0, 14))
        TH.text(g, titel, 16, True, anchor="w").pack(fill="x", padx=18, pady=(14, 6))
        return g

    @staticmethod
    def _zeile(g, titel: str, unter: str, widget) -> None:
        z = ctk.CTkFrame(g, fg_color="transparent")
        z.pack(fill="x", padx=18, pady=6)
        links = ctk.CTkFrame(z, fg_color="transparent")
        links.pack(side="left", fill="x", expand=True)
        TH.text(links, titel, 13, anchor="w").pack(anchor="w")
        if unter:
            TH.text(links, unter, 11, farbe=TH.GRAU, anchor="w", justify="left", wraplength=320).pack(anchor="w")
        widget.pack(in_=z, side="right")
        widget.lift(z)

    def _ordner_zeilen(self, ordner: list[Anfrageordner]):
        for w in self.ordner_rahmen.winfo_children():
            w.destroy()
        self.zeilen = []
        liste = list(ordner) + [Anfrageordner("", "pruefen")] * max(0, 3 - len(ordner))
        for o in liste[:6]:
            pfad = tk.StringVar(value=o.pfad)
            art = tk.StringVar(value="automatisch" if o.art == "automatisch" else "selbst prüfen")
            gem = tk.BooleanVar(value=o.gemeinsam)
            z = ctk.CTkFrame(self.ordner_rahmen, fg_color="transparent")
            z.pack(fill="x", pady=3)
            TH.eingabe(z, textvariable=pfad, placeholder_text="Posteingang/Anfragen/…").pack(side="left", fill="x",
                                                                                          expand=True)
            TH.auswahl(z, ["automatisch", "selbst prüfen"], art, breite=130).pack(side="left", padx=(6, 0))
            ctk.CTkCheckBox(z, text="gemeinsam", variable=gem, font=TH.schrift(12), text_color=TH.TEXT, width=20,
                            fg_color=TH.AKZENT).pack(side="left", padx=(8, 0))
            TH.knopf(z, "Aus Outlook …", lambda v=pfad: self.waehlen(v), height=32, width=110).pack(side="left",
                                                                                                   padx=(6, 0))
            self.zeilen.append((pfad, art, gem))

    def zeigen(self):
        e = self.app.einstellungen
        self.dunkel_var.set(e.dunkelmodus)
        self.experimentell.set(e.experimentell)
        self.quelle.set("Weclapp" if e.datenquelle == "weclapp" else "Shop")
        self.frist.set(str(e.preisfrist_monate))
        self._ordner_zeilen(e.anfrageordner)
        self.erledigt.set(e.ordner_erledigt)
        self.bearbeitung.set(e.ordner_in_bearbeitung)
        self.domains.set(", ".join(e.interne_domains))
        self.weclapp.set(e.weclapp_adresse)
        self.gespeichert.configure(text="")

    def _datenordner(self):
        from .gui import datei_oeffnen
        try:
            datei_oeffnen(self.app.pfad.parent)
        except OSError as ex:
            messagebox.showerror("Einstellungen", str(ex), parent=self)

    # ---------------------------------------------------------------- Weclapp / Outlook
    def token_eintragen(self):
        from . import zugang
        adresse = self.weclapp.get().strip()
        if not adresse or adresse.lower() == "demo":
            messagebox.showinfo("Weclapp", "Erst die Weclapp-Adresse eintragen (für „demo“ ist kein Token nötig).",
                                parent=self)
            return
        token = simpledialog.askstring("Weclapp-Token", "API-Token aus Weclapp (Meine Einstellungen → API).\n"
                                       "Wird nur in der Windows-Anmeldeinformationsverwaltung gespeichert:",
                                       show="*", parent=self)
        if token:
            dauerhaft = zugang.speichern(adresse, token.strip())
            self.weclapp_status.configure(text="Token gespeichert." if dauerhaft else
                                          "Token nur für diese Sitzung (keine Windows-Anmeldeinformationsverwaltung).")

    def verbindung_testen(self):
        from . import weclapp_dialog
        from .einstellungen import Einstellungen
        e = Einstellungen(weclapp_adresse=self.weclapp.get().strip())
        self.weclapp_status.configure(text="Teste …")

        def arbeit():
            return weclapp_dialog.verbindung(e, self.app.geraete).verbindung_testen()

        def fertig(text, fehler):
            self.weclapp_status.configure(text=str(fehler) if fehler else text)
        weclapp_dialog._hintergrund(self, arbeit, fertig)

    def waehlen(self, var: tk.StringVar):
        """Outlook-Ordnerdialog (im Hintergrund, Outlook braucht einen eigenen COM-Thread)."""
        from . import outlook
        if not outlook.verfuegbar():
            messagebox.showinfo("Einstellungen", "Klassisches Outlook ist auf diesem Rechner nicht verfügbar.", parent=self)
            return
        ergebnis: dict = {}

        def lauf():
            try:
                with outlook.Outlook() as ol:
                    ergebnis["pfad"] = ol.ordner_waehlen()
            except Exception as ex:  # noqa: BLE001
                ergebnis["fehler"] = ex
            ergebnis["fertig"] = True

        def abfragen():
            if not ergebnis.get("fertig"):
                self.after(150, abfragen)
                return
            if "fehler" in ergebnis:
                messagebox.showerror("Einstellungen", f"Outlook: {ergebnis['fehler']}", parent=self)
            elif ergebnis.get("pfad"):
                var.set(ergebnis["pfad"])

        threading.Thread(target=lauf, daemon=True).start()
        self.after(150, abfragen)

    def speichern(self):
        e = self.app.einstellungen
        e.experimentell = self.experimentell.get()
        e.anfrageordner = [Anfrageordner(p.get().strip(), "automatisch" if a.get() == "automatisch" else "pruefen",
                                         g.get()) for p, a, g in self.zeilen if p.get().strip()]
        e.ordner_erledigt = self.erledigt.get().strip() or "Erledigt"
        e.weclapp_adresse = self.weclapp.get().strip()
        alte_quelle = e.datenquelle
        e.datenquelle = "weclapp" if self.quelle.get() == "Weclapp" and e.weclapp_adresse else "shop"
        e.interne_domains = [d.strip().lower().lstrip("@") for d in self.domains.get().replace(";", ",").split(",")
                             if d.strip()] or ["eps-germany.de"]
        e.ordner_in_bearbeitung = self.bearbeitung.get().strip() or "In Bearbeitung"
        try:
            e.preisfrist_monate = max(1, int(self.frist.get()))
        except ValueError:
            pass
        try:
            e.speichern(self.app.einstellungen_pfad)
        except OSError as ex:
            messagebox.showerror("Einstellungen", f"Konnte nicht gespeichert werden:\n{ex}", parent=self)
            return
        self.app._experimentell_zeigen()
        anfragen = self.app.seiten.get("anfragen")
        if anfragen is not None:
            anfragen.ordner_aktualisieren()
        if e.datenquelle != alte_quelle:
            self.app.datenquelle_wechseln()
        self.gespeichert.configure(text="✓ Gespeichert")
        if self.quelle.get() == "Weclapp" and not e.weclapp_adresse:
            self.gespeichert.configure(text="✓ Gespeichert – Datenquelle bleibt Shop, solange keine Weclapp-Adresse "
                                            "eingetragen ist")
