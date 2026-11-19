"""Dialog „Technische Werte in Weclapp schreiben“ (Einstellungen → Weclapp).

Ablauf: Datei Weclapp-eps-Werte.csv wählen → Vorschau (nur lesen) → Einzeltest an EINEM Artikel → erst danach „Alle
schreiben“. Geschrieben wird ausschließlich nach Klick und Bestätigung; die Logik steht in weclapp_schreiben.py."""
from __future__ import annotations

import csv
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import thema as TH, weclapp_dialog as WD, weclapp_schreiben as S

ROT = ("#B71C1C", "#FF8A80")


class WerteDialog(ctk.CTkToplevel):
    def __init__(self, app, einstellungen):
        super().__init__(app, fg_color=TH.BG)
        self.app, self.einst = app, einstellungen
        demo = einstellungen.weclapp_adresse.lower() == "demo"
        self.title("Technische Werte in Weclapp schreiben" + ("  –  DEMO" if demo else ""))
        self.transient(app)
        self.geometry("900x640")
        self.minsize(700, 480)
        self.werte: dict[str, dict[str, str]] = {}
        self.plaene: list[S.ArtikelPlan] = []
        self.einzeltest_ok = False
        self.beschaeftigt = False
        self.abbrechen = False

        fr = ctk.CTkFrame(self, fg_color="transparent")
        fr.pack(fill="both", expand=True, padx=18, pady=(16, 0))
        TH.text(fr, "Schreibt die technischen Werte (eps_…) aus Weclapp-eps-Werte.csv in die Weclapp-Artikel. "
                    "Die Vorschau liest nur. Geschrieben wird erst nach deinem Klick und deiner Bestätigung.",
                12, farbe=TH.GRAU, anchor="w", justify="left", wraplength=840).pack(fill="x")

        z1 = ctk.CTkFrame(fr, fg_color="transparent")
        z1.pack(fill="x", pady=(10, 0))
        TH.knopf(z1, "1. Datei wählen …", self.datei_waehlen, height=32).pack(side="left")
        self.datei_lbl = TH.text(z1, "noch keine Datei", 12, farbe=TH.GRAU, anchor="w")
        self.datei_lbl.pack(side="left", padx=10)

        z2 = ctk.CTkFrame(fr, fg_color="transparent")
        z2.pack(fill="x", pady=(10, 0))
        self.knopf_vorschau = TH.knopf(z2, "2. Vorschau (alle Artikel)", self.vorschau_alle, height=32, state="disabled")
        self.knopf_vorschau.pack(side="left")
        self.knopf_speichern = TH.knopf(z2, "Vorschau als CSV speichern …", self.vorschau_speichern, height=32,
                                        state="disabled")
        self.knopf_speichern.pack(side="left", padx=8)

        z3 = ctk.CTkFrame(fr, fg_color="transparent")
        z3.pack(fill="x", pady=(10, 0))
        TH.text(z3, "3. Einzeltest – Artikelnummer:", 12, anchor="w").pack(side="left")
        self.nummer = ctk.StringVar()
        TH.eingabe(z3, textvariable=self.nummer, width=140, height=32).pack(side="left", padx=8)
        self.knopf_einzel = TH.knopf(z3, "Diesen Artikel schreiben …", self.einzeltest, height=32, state="disabled")
        self.knopf_einzel.pack(side="left")

        z4 = ctk.CTkFrame(fr, fg_color="transparent")
        z4.pack(fill="x", pady=(10, 0))
        self.knopf_alle = TH.knopf(z4, "4. Alle schreiben …", self.alle_schreiben, haupt=True, height=34, state="disabled")
        self.knopf_alle.pack(side="left")
        self.hinweis = TH.text(z4, "erst nach erfolgreichem Einzeltest und Vorschau", 12, farbe=TH.GRAU, anchor="w")
        self.hinweis.pack(side="left", padx=10)

        self.ausgabe = ctk.CTkTextbox(fr, font=TH.schrift(12), fg_color=TH.EINGABE, text_color=TH.TEXT,
                                      border_color=TH.RAND, border_width=1, wrap="word")
        self.ausgabe.pack(fill="both", expand=True, pady=(12, 0))
        unten = ctk.CTkFrame(self, fg_color="transparent")
        unten.pack(fill="x", padx=18, pady=12)
        TH.knopf(unten, "Schließen", self.destroy, width=110).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(80, self.lift)
        self._schreibe("Schritt 1: Weclapp-eps-Werte.csv wählen (liegt im Ordner Weclapp-Vorbereitung).")

    # ---------------------------------------------------------------- Hilfen
    def _schreibe(self, text: str):
        self.ausgabe.configure(state="normal")
        self.ausgabe.delete("1.0", "end")
        self.ausgabe.insert("1.0", text)
        self.ausgabe.configure(state="disabled")

    def _sperren(self, an: bool):
        self.beschaeftigt = an
        for k in (self.knopf_vorschau, self.knopf_einzel, self.knopf_alle, self.knopf_speichern):
            k.configure(state="disabled")
        if not an:
            self._knoepfe()

    def _knoepfe(self):
        if self.beschaeftigt:
            return
        hat = bool(self.werte)
        self.knopf_vorschau.configure(state="normal" if hat else "disabled")
        self.knopf_einzel.configure(state="normal" if hat else "disabled")
        self.knopf_speichern.configure(state="normal" if self.plaene else "disabled")
        bereit = self.einzeltest_ok and bool(self.plaene)
        self.knopf_alle.configure(state="normal" if bereit else "disabled")
        self.hinweis.configure(text="bereit" if bereit else "erst nach erfolgreichem Einzeltest und Vorschau")

    # ---------------------------------------------------------------- 1 Datei
    def datei_waehlen(self):
        basis = self.app.pfad.parent
        start = next((p for p in (basis / "Weclapp-Vorbereitung", basis.parent / "Weclapp-Vorbereitung") if p.exists()), basis)
        pfad = filedialog.askopenfilename(parent=self, title="Weclapp-eps-Werte.csv wählen", initialdir=str(start),
                                          filetypes=[("CSV", "*.csv")])
        if not pfad:
            return
        try:
            self.werte = S.werte_aus_csv(pfad)
        except (OSError, KeyError, csv.Error) as ex:
            messagebox.showerror("Technische Werte", f"Datei nicht lesbar: {ex}", parent=self)
            return
        self.plaene, self.einzeltest_ok = [], False
        self.datei_lbl.configure(text=f"{Path(pfad).name}: {len(self.werte)} Artikel")
        self._schreibe("Datei gelesen. Schritt 2: Vorschau, dann Einzeltest.")
        self._knoepfe()

    # ---------------------------------------------------------------- 2 Vorschau
    def vorschau_alle(self):
        self._plan_holen(None, self._vorschau_fertig)

    def _plan_holen(self, nummern, fertig):
        self._sperren(True)
        self._schreibe("Lese Zusatzfelder und Artikel aus Weclapp … (nur lesen)")

        def arbeit():
            t = WD.verbindung(self.einst, self.app.geraete).t
            return S.planen(t, self.werte, nummern)

        def danach(plaene, fehler):
            self._sperren(False)
            if fehler:
                self._schreibe(f"Fehler: {fehler}")
                return
            fertig(plaene)
        WD._hintergrund(self, arbeit, danach)

    def _vorschau_fertig(self, plaene):
        self.plaene = plaene
        text = S.zusammenfassung(plaene)
        zu = [p for p in plaene if p.fehler]
        if zu:
            text += "\n\nNicht in Weclapp gefunden (erste 15): " + ", ".join(p.nummer for p in zu[:15])
        text += "\n\nNichts wurde verändert. Schritt 3: Einzeltest an einem Artikel."
        self._schreibe(text)
        self._knoepfe()

    def vorschau_speichern(self):
        pfad = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile="Weclapp-Werte-Vorschau.csv",
                                            filetypes=[("CSV", "*.csv")], title="Vorschau speichern")
        if not pfad:
            return
        with open(pfad, "w", encoding="utf-8-sig", newline="") as fh:
            csv.writer(fh, delimiter=";").writerows(S.vorschau_zeilen(self.plaene))
        self._schreibe(f"Vorschau gespeichert: {pfad}")

    # ---------------------------------------------------------------- 3 Einzeltest
    def einzeltest(self):
        nr = self.nummer.get().strip()
        if nr not in self.werte:
            messagebox.showinfo("Einzeltest", f"Die Artikelnummer „{nr}“ steht nicht in der Datei.", parent=self)
            return
        self._plan_holen([nr], lambda plaene: self._einzel_pruefen(nr, plaene[0]))

    def _einzel_pruefen(self, nr: str, p: S.ArtikelPlan):
        if p.fehler:
            self._schreibe(f"{nr}: {p.fehler}")
            return
        zeilen = [f"Artikel {nr} – {p.name}", f"Status: {p.status}"]
        zeilen += [f"  neu: {k} = {self.werte[nr][k]}" for k in p.neu]
        zeilen += [f"  ändern: {k} = {self.werte[nr][k]}" for k in p.geaendert]
        if p.fehlt_feld:
            zeilen.append("Zusatzfeld fehlt in Weclapp (übersprungen): " + ", ".join(p.fehlt_feld))
        zeilen += [f"Auswahlwert fehlt (übersprungen): {k} = {w}" for k, w in p.fehlt_wert]
        self._schreibe("\n".join(zeilen))
        if not p.aenderungen:
            self.einzeltest_ok = True
            self._schreibe("\n".join(zeilen) + "\n\nNichts zu schreiben – der Artikel hat die Werte schon.")
            self._knoepfe()
            return
        if not messagebox.askyesno("Einzeltest", f"{p.aenderungen} Werte bei Artikel {nr} in Weclapp schreiben?\n\n"
                                   f"Weclapp: {self.einst.weclapp_adresse}", parent=self):
            return
        self._sperren(True)
        self._schreibe("\n".join(zeilen) + "\n\nSchreibe …")

        def arbeit():
            t = WD.verbindung(self.einst, self.app.geraete).t
            S.schreiben(t, p)
            return S.kontrolle(t, p, self.werte[nr], S.definitionen_lesen(t))

        def danach(abweichungen, fehler):
            self._sperren(False)
            if fehler:
                self._schreibe("\n".join(zeilen) + f"\n\nFEHLER beim Schreiben:\n{fehler}\n\n"
                               "Bitte den Text an Claude schicken – so sehen wir, was Weclapp ablehnt.")
                return
            if abweichungen:
                self._schreibe("\n".join(zeilen) + "\n\nGeschrieben, aber nicht alles ist angekommen:\n" +
                               "\n".join(abweichungen))
                return
            self.einzeltest_ok = True
            self._schreibe("\n".join(zeilen) + f"\n\nGeschrieben und kontrolliert: alle {p.aenderungen} Werte sind in "
                           f"Weclapp angekommen. Bitte den Artikel in Weclapp öffnen und die Zusatzfelder ansehen.")
            self._knoepfe()
        WD._hintergrund(self, arbeit, danach)

    # ---------------------------------------------------------------- 4 Alle
    def alle_schreiben(self):
        zu = [p for p in self.plaene if p.aenderungen and not p.fehler]
        if not zu:
            self._schreibe("Nichts zu schreiben – alle Artikel haben ihre Werte schon.")
            return
        if not messagebox.askyesno(
                "Alle schreiben",
                f"{len(zu)} Artikel ({sum(p.aenderungen for p in zu)} Werte) in Weclapp schreiben?\n\n"
                f"Weclapp: {self.einst.weclapp_adresse}\n\nDer Lauf kann ohne Schaden wiederholt werden "
                f"(fertige Artikel werden dann übersprungen).", icon="warning", parent=self):
            return
        self._sperren(True)
        self._schreibe(f"Schreibe {len(zu)} Artikel …")

        def arbeit():
            t = WD.verbindung(self.einst, self.app.geraete).t
            return S.alle_schreiben(t, zu)

        def danach(lauf, fehler):
            self._sperren(False)
            if fehler:
                self._schreibe(f"FEHLER: {fehler}")
                return
            text = f"Fertig: {lauf.geschrieben} Artikel geschrieben, {lauf.unveraendert} unverändert."
            if lauf.fehler:
                text += f"\n\n{len(lauf.fehler)} Fehler:\n" + "\n".join(lauf.fehler[:40])
            self._schreibe(text + "\n\nZur Kontrolle die Vorschau noch einmal laufen lassen: sie sollte nur noch "
                           "„unverändert“ zeigen.")
            self.plaene = []
            self._knoepfe()
        WD._hintergrund(self, arbeit, danach)
