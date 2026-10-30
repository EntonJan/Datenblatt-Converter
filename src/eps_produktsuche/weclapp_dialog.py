"""Dialog „In Weclapp vorbereiten“: zeigt den Plan (Kunde, Positionen, Einkaufspreis-Alter, was angelegt wird),
legt nach „Anlegen“ Angebotsentwurf und ggf. Herstelleranfrage an und zeigt die Links. Verschickt nichts."""
from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

from . import weclapp as W, zugang

GRAU, ROT, GRUEN = "#6A7380", "#B71C1C", "#2E7D32"


def verbindung(einstellungen, geraete=()) -> W.Weclapp:
    adresse = (einstellungen.weclapp_adresse or "").strip()
    if not adresse:
        raise W.WeclappFehler("Keine Weclapp-Adresse eingestellt (Einstellungen).")
    if adresse.lower() == "demo":
        from .weclapp_attrappe import Attrappe
        global _DEMO
        if _DEMO is None:                               # Demo-Daten bleiben bis zum Programmende erhalten
            _DEMO = Attrappe.mit_importdaten(geraete)   # wie nach Feldliste + Artikelimport
            _DEMO.kunde("DEMO Bestandskunde GmbH", "einkauf@demo-bestandskunde.de", "86150")
        return W.Weclapp(_DEMO)
    token = zugang.laden(adresse)
    if not token:
        raise W.WeclappFehler("Kein Weclapp-Token hinterlegt (Einstellungen → „Token eintragen …“).")
    return W.Weclapp(W.Http(adresse, token))


_DEMO = None


def _hintergrund(widget, arbeit, fertig):
    erg: dict = {}

    def lauf():
        try:
            erg["wert"] = arbeit()
        except Exception as ex:  # noqa: BLE001
            erg["fehler"] = ex
        erg["fertig"] = True

    def abfragen():
        if not erg.get("fertig"):
            widget.after(120, abfragen)
            return
        if widget.winfo_exists():
            fertig(erg.get("wert"), erg.get("fehler"))

    threading.Thread(target=lauf, daemon=True).start()
    widget.after(120, abfragen)


class WeclappDialog(tk.Toplevel):
    def __init__(self, app, kunde, positionen: list[tuple[str, str, int]], termin: str, notiz: str = ""):
        """positionen: (Bestellnummer, Name, Menge)."""
        super().__init__(app)
        self.app, self.kunde, self.termin, self.notiz = app, kunde, termin or "ASAP", notiz
        self.title("In Weclapp vorbereiten" + ("  –  DEMO" if app.einstellungen.weclapp_adresse.lower() == "demo" else ""))
        self.transient(app)
        self.geometry("900x520")
        self.plan: W.Plan | None = None
        fr = ttk.Frame(self, padding=12)
        fr.pack(fill="both", expand=True)
        self.kunde_lbl = ttk.Label(fr, text="Kunde: …", font=("Segoe UI", 10, "bold"))
        self.kunde_lbl.pack(anchor="w")
        ttk.Label(fr, text="Mengen hier anpassen (Doppelklick auf die Menge):", foreground=GRAU).pack(anchor="w", pady=(8, 2))
        sp = [("nr", "Bestellnr.", 80), ("name", "Gerät", 300), ("menge", "Menge", 60), ("ek", "Letzter EK-Preis", 120),
              ("status", "Preis", 170), ("lief", "Lieferant", 160)]
        self.tv = ttk.Treeview(fr, columns=[x[0] for x in sp], show="headings", height=8)
        for k, t, b in sp:
            self.tv.heading(k, text=t)
            self.tv.column(k, width=b, stretch=k == "name")
        self.tv.tag_configure("alt", foreground="#8E5A00")
        self.tv.tag_configure("fehler", foreground=ROT)
        self.tv.pack(fill="both", expand=True)
        self.tv.bind("<Double-1>", self._menge_aendern)
        self.mengen = {nr: menge for nr, _, menge in positionen}
        self.namen = {nr: name for nr, name, _ in positionen}
        self.plan_lbl = tk.Label(fr, text="Prüfe Kunde und Artikel in Weclapp …", justify="left", anchor="w",
                                 bg="#EEF4FA", padx=10, pady=8, wraplength=840)
        self.plan_lbl.pack(fill="x", pady=(10, 0))
        unten = ttk.Frame(self, padding=(12, 0, 12, 12))
        unten.pack(fill="x")
        self.knopf = ttk.Button(unten, text="Anlegen", command=self.anlegen, state="disabled")
        self.knopf.pack(side="right")
        ttk.Button(unten, text="Abbrechen", command=self.destroy).pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        self.planen()

    def planen(self):
        einst = self.app.einstellungen
        pos = [(nr, self.mengen[nr]) for nr in self.mengen]

        def arbeit():
            wc = verbindung(einst, self.app.geraete)
            return wc, wc.planen(self.kunde, pos, einst.preisfrist_monate, self.termin)

        _hintergrund(self, arbeit, self._plan_zeigen)

    def _plan_zeigen(self, wert, fehler):
        if fehler:
            self.plan_lbl.configure(text=f"Weclapp: {fehler}", bg="#FDECEA", fg=ROT)
            return
        self.wc, self.plan = wert
        p = self.plan
        self.kunde_lbl.configure(text=f"Kunde: {p.kunde_text}")
        self.tv.delete(*self.tv.get_children())
        frist = self.app.einstellungen.preisfrist_monate
        for x in p.positionen:
            if x.fehler:
                status, tag = x.fehler, "fehler"
            elif x.ek_datum is None:
                status, tag = "kein Preisdatum → anfragen", "alt"
            else:
                status, tag = (f"älter als {frist} Mon. → anfragen", "alt") if x.ek_alt else ("aktuell", "")
            self.tv.insert("", "end", iid=x.bestellnummer, tags=(tag,),
                           values=[x.bestellnummer, x.name or self.namen.get(x.bestellnummer, ""), x.menge,
                                   x.ek_datum.strftime("%d.%m.%Y") if x.ek_datum else "–", status, x.lieferant])
        if p.fehler:
            self.plan_lbl.configure(text="Nicht anlegbar:\n" + "\n".join(p.fehler), bg="#FDECEA", fg=ROT)
            return
        teile = []
        if p.kunde_neu:
            teile.append("• Kunde wird neu angelegt (Stammdaten aus der Anfrage)")
        teile.append(f"• Angebotsentwurf mit {len(p.positionen)} Position(en) – Verkaufspreise aus Weclapp")
        if p.herstelleranfrage:
            teile.append(f"• Herstelleranfrage(n) aus dem Angebot, Wunschtermin: {p.termin}")
        else:
            teile.append("• keine Herstelleranfrage (alle Einkaufspreise aktuell)")
        teile.append("Es wird nichts verschickt – Prüfen und Versand machst du in Weclapp.")
        self.plan_lbl.configure(text="Wird angelegt:\n" + "\n".join(teile), bg="#EEF4FA", fg="#1C2633")
        self.knopf.configure(state="normal")

    def _menge_aendern(self, e):
        iid = self.tv.identify_row(e.y)
        if not iid or self.tv.identify_column(e.x) != "#3":
            return
        from tkinter import simpledialog
        neu = simpledialog.askinteger("Menge", f"Menge für {iid}:", initialvalue=self.mengen.get(iid, 1), minvalue=1,
                                      parent=self)
        if neu:
            self.mengen[iid] = neu
            if self.plan:
                for x in self.plan.positionen:
                    if x.bestellnummer == iid:
                        x.menge = neu
            self.tv.set(iid, "menge", neu)

    def anlegen(self):
        if not self.plan:
            return
        self.knopf.configure(state="disabled")
        self.plan_lbl.configure(text="Lege in Weclapp an …")
        _hintergrund(self, lambda: self.wc.ausfuehren(self.plan, self.kunde, self.notiz), self._fertig)

    def _fertig(self, erg: W.Ergebnis, fehler):
        if fehler:
            self.plan_lbl.configure(text=f"Fehler beim Anlegen: {fehler}", bg="#FDECEA", fg=ROT)
            self.knopf.configure(state="normal")
            return
        text = [f"Angelegt: Angebotsentwurf {erg.angebot_nummer or erg.angebot_id}"]
        if erg.kunde_neu:
            text.append("Neuer Kunde angelegt")
        if erg.anfrage_ids:
            text.append(f"{len(erg.anfrage_ids)} Herstelleranfrage(n) erzeugt")
        self.plan_lbl.configure(text=" · ".join(text), bg="#E8F5E9", fg=GRUEN)
        leiste = ttk.Frame(self.plan_lbl.master)
        leiste.pack(fill="x", pady=(8, 0))
        if not erg.links:
            ttk.Label(leiste, text="Demo-Modus: angelegt wurde nur im nachgebauten Weclapp (bis zum Programmende).",
                      foreground=GRAU).pack(side="left")
        for name, url in erg.links.items():
            ttk.Button(leiste, text=f"{name} öffnen", command=lambda u=url: webbrowser.open(u)).pack(side="left", padx=(0, 6))
        self.knopf.configure(text="Schließen", state="normal", command=self.destroy)
        try:
            self.app._merken(f"Weclapp: Angebot {erg.angebot_nummer or erg.angebot_id}")
        except Exception:  # noqa: BLE001
            pass
