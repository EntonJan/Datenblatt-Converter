"""Dialog „In Weclapp vorbereiten“: zeigt den Plan (Kunde, Positionen, Einkaufspreis-Alter, was angelegt wird),
legt nach „Anlegen“ Angebotsentwurf und ggf. Herstelleranfrage an und zeigt die Links. Verschickt nichts."""
from __future__ import annotations

import threading
import webbrowser

import customtkinter as ctk

from . import thema as TH, weclapp as W, zugang

ROT = ("#B71C1C", "#FF8A80")
ROT_BG = ("#FDECEA", "#3A1A1A")
INFO_BG = ("#EEF4FA", "#1E2A42")


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


class WeclappDialog(ctk.CTkToplevel):
    def __init__(self, app, kunde, positionen: list[tuple[str, str, int]], termin: str, notiz: str = ""):
        """positionen: (Bestellnummer, Name, Menge)."""
        super().__init__(app, fg_color=TH.BG)
        self.app, self.kunde, self.termin, self.notiz = app, kunde, termin or "ASAP", notiz
        self.title("In Weclapp vorbereiten" + ("  –  DEMO" if app.einstellungen.weclapp_adresse.lower() == "demo" else ""))
        self.transient(app)
        self.geometry("920x560")
        self.minsize(640, 400)
        self.plan: W.Plan | None = None
        fr = ctk.CTkFrame(self, fg_color="transparent")
        fr.pack(fill="both", expand=True, padx=18, pady=(16, 0))
        self.kunde_lbl = TH.text(fr, "Kunde: …", 15, True, anchor="w")
        self.kunde_lbl.pack(anchor="w")
        TH.text(fr, "Mengen hier anpassen (Doppelklick auf die Menge):", 12, farbe=TH.GRAU).pack(anchor="w", pady=(6, 6))
        sp = [("nr", "Bestellnr.", 80), ("name", "Gerät", 300), ("menge", "Menge", 60), ("ek", "Letzter EK-Preis", 120),
              ("status", "Preis", 170), ("lief", "Lieferant", 160)]
        rahmen, self.tv = TH.tabelle(fr, sp, dehnen=("name",))
        self.tv.tag_configure("alt", foreground=TH.f(TH.ORANGE))
        self.tv.tag_configure("fehler", foreground=TH.f(ROT))
        rahmen.pack(fill="both", expand=True)
        self.tv.bind("<Double-1>", self._menge_aendern)
        self.mengen = {nr: menge for nr, _, menge in positionen}
        self.namen = {nr: name for nr, name, _ in positionen}
        self.plan_box = ctk.CTkFrame(fr, fg_color=INFO_BG, corner_radius=10)
        self.plan_box.pack(fill="x", pady=(10, 0))
        self.plan_lbl = TH.text(self.plan_box, "Prüfe Kunde und Artikel in Weclapp …", 12, anchor="w", justify="left",
                                wraplength=840)
        self.plan_lbl.pack(fill="x", padx=12, pady=10)
        self.leiste_rahmen = fr
        unten = ctk.CTkFrame(self, fg_color="transparent")
        unten.pack(fill="x", padx=18, pady=14)
        self.knopf = TH.knopf(unten, "Anlegen", self.anlegen, haupt=True, width=130, state="disabled")
        self.knopf.pack(side="right")
        TH.knopf(unten, "Abbrechen", self.destroy, width=110).pack(side="right", padx=8)
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(80, self.lift)
        self.planen()

    def _meldung(self, text: str, bg=INFO_BG, fg=TH.TEXT):
        self.plan_box.configure(fg_color=bg)
        self.plan_lbl.configure(text=text, text_color=fg)

    def planen(self):
        einst = self.app.einstellungen
        pos = [(nr, self.mengen[nr]) for nr in self.mengen]

        def arbeit():
            wc = verbindung(einst, self.app.geraete)
            return wc, wc.planen(self.kunde, pos, einst.preisfrist_monate, self.termin)

        _hintergrund(self, arbeit, self._plan_zeigen)

    def _plan_zeigen(self, wert, fehler):
        if fehler:
            self._meldung(f"Weclapp: {fehler}", ROT_BG, ROT)
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
            self._meldung("Nicht anlegbar:\n" + "\n".join(p.fehler), ROT_BG, ROT)
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
        self._meldung("Wird angelegt:\n" + "\n".join(teile))
        self.knopf.configure(state="normal")

    def _menge_aendern(self, e):
        iid = self.tv.identify_row(e.y)
        if not iid or self.tv.identify_column(e.x) != "#3":
            return
        eingabe = ctk.CTkInputDialog(title="Menge", text=f"Menge für {iid} (bisher {self.mengen.get(iid, 1)}):",
                                     fg_color=TH.BG, button_fg_color=TH.AKZENT, button_hover_color=TH.AKZENT_HOVER,
                                     button_text_color=TH.AKZENT_TEXT, entry_fg_color=TH.EINGABE, text_color=TH.TEXT)
        try:
            neu = int((eingabe.get_input() or "").strip())
        except ValueError:
            neu = 0
        if neu >= 1:
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
        self._meldung("Lege in Weclapp an …")
        _hintergrund(self, lambda: self.wc.ausfuehren(self.plan, self.kunde, self.notiz), self._fertig)

    def _fertig(self, erg: W.Ergebnis, fehler):
        if fehler:
            self._meldung(f"Fehler beim Anlegen: {fehler}", ROT_BG, ROT)
            self.knopf.configure(state="normal")
            return
        text = [f"Angelegt: Angebotsentwurf {erg.angebot_nummer or erg.angebot_id}"]
        if erg.kunde_neu:
            text.append("Neuer Kunde angelegt")
        if erg.anfrage_ids:
            text.append(f"{len(erg.anfrage_ids)} Herstelleranfrage(n) erzeugt")
        self._meldung(" · ".join(text), TH.GRUEN_BG, TH.GRUEN)
        leiste = ctk.CTkFrame(self.leiste_rahmen, fg_color="transparent")
        leiste.pack(fill="x", pady=(8, 0))
        if not erg.links:
            TH.text(leiste, "Demo-Modus: angelegt wurde nur im nachgebauten Weclapp (bis zum Programmende).", 12,
                    farbe=TH.GRAU).pack(side="left")
        for name, url in erg.links.items():
            TH.knopf(leiste, f"{name} öffnen", lambda u=url: webbrowser.open(u)).pack(side="left", padx=(0, 6))
        self.knopf.configure(text="Schließen", state="normal", command=self.destroy)
        try:
            self.app._merken(f"Weclapp: Angebot {erg.angebot_nummer or erg.angebot_id}")
        except Exception:  # noqa: BLE001
            pass
