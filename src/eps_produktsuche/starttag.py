"""Weclapp-Starttag (ab 1.5.3): Checkliste als Seitenleiste rechts im Hauptfenster.

Grün = erledigt, Rot = fehlt noch. Was das Programm selbst sehen kann, hakt es selbst ab (Adresse + Token
eingetragen, „Verbindung testen“ erfolgreich, Probevorgang angelegt, Datenquelle Weclapp); den Rest hakt man von
Hand ab. Gespeichert in weclapp-starttag.json im Datenordner. Steht alles auf Grün, verschwindet die Leiste.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from . import thema as TH

DATEI = "weclapp-starttag.json"


@dataclass(frozen=True)
class Punkt:
    id: str
    gruppe: str
    titel: str
    detail: str
    wer: str
    fest: bool = False                      # schon vorbereitet (immer grün)
    auto: Callable | None = None            # app → bool: vom Programm erkannt


def _eingetragen(app) -> bool:
    e = app.einstellungen
    adresse = (e.weclapp_adresse or "").strip()
    if not adresse or adresse.lower() == "demo":
        return False
    try:
        from . import zugang
        return bool(zugang.laden(adresse))
    except Exception:  # noqa: BLE001 – Anmeldeinformationsverwaltung nicht erreichbar
        return False


def _weclapp_daten(app) -> bool:
    return getattr(app.einstellungen, "datenquelle", "") == "weclapp"


VORBEREITET, KLAEREN, TAG1, DANACH = "Schon vorbereitet", "Vor dem Start klären", "Am ersten Tag", "In den ersten Tagen"

PUNKTE: list[Punkt] = [
    Punkt("v-anbindung", VORBEREITET, "Weclapp-Anbindung", "Kunde, Artikel + EK, Angebot, Herstelleranfrage", "Programm", fest=True),
    Punkt("v-token", VORBEREITET, "Token sicher speichern + Verbindung testen", "Windows-Anmeldeinformationsverwaltung", "Programm", fest=True),
    Punkt("v-feldliste", VORBEREITET, "Feldliste", "Weclapp-Feldliste.xlsx: 117 + 10 Felder", "Datei", fest=True),
    Punkt("v-import", VORBEREITET, "Importdatei der Artikel", "748 Shopgeräte", "Datei", fest=True),
    Punkt("v-selectline", VORBEREITET, "SelectLine-Abgleich", "173 Geräte korrigiert", "Programm", fest=True),
    Punkt("v-frist", VORBEREITET, "Preisfrist 3 Monate", "älterer EK → Herstelleranfrage", "Einstellung", fest=True),
    Punkt("v-testdaten", VORBEREITET, "Testdaten markiert", "[EPS-Produktsuche]", "Programm", fest=True),
    Punkt("paket", KLAEREN, "Paket festlegen", "voraussichtlich ERP Handel", "Chef"),
    Punkt("einrichter", KLAEREN, "Wer richtet Weclapp ein?", "Felder, Import, Benutzer, Rechte", "Chef"),
    Punkt("artnr", KLAEREN, "Shop-Bestellnummern = Artikelnummern?", "Darüber findet die Produktsuche die Artikel", "Chef"),
    Punkt("lieferant", KLAEREN, "Lieferant + Hersteller-Typ je Artikel", "Lieferanten-Export aus SelectLine fehlt", "Enton"),
    Punkt("import-neu", KLAEREN, "Importdatei neu erzeugen", "mit SelectLine-Korrekturen", "Claude"),
    Punkt("vk", KLAEREN, "Verkaufspreis-Formel EK → VK", "in Weclapp am Artikel", "Chef"),
    Punkt("ek", KLAEREN, "Letzte EK-Preise mit Datum", "Woher kommen sie?", "Chef"),
    Punkt("t1", TAG1, "1. 30-Tage-Test starten", "wird später das Echtsystem", "Chef"),
    Punkt("t2", TAG1, "2. Artikelfelder laut Feldliste anlegen", "Kernfelder zuerst", "Einrichter"),
    Punkt("t3", TAG1, "3. Artikel importieren", "Stichprobe 3–5 Artikel prüfen", "Einrichter"),
    Punkt("t4", TAG1, "4. Benutzer + API-Token je Mitarbeiter", "jeder seinen eigenen", "Einrichter"),
    Punkt("t5", TAG1, "5. Adresse + Token eintragen", "Einstellungen → Weclapp", "Enton", auto=_eingetragen),
    Punkt("t6", TAG1, "6. „Verbindung testen“", "hakt sich bei Erfolg selbst ab", "Enton"),
    Punkt("t7", TAG1, "7. Probevorgang anlegen", "„In Weclapp vorbereiten …“ → Anlegen", "Enton"),
    Punkt("t8", TAG1, "8. Feld- und Endpunktnamen abgleichen", "Abweichungen an Claude", "Enton + Claude"),
    Punkt("t9", TAG1, "9. Testdatensätze löschen", "alles mit [EPS-Produktsuche]", "Enton"),
    Punkt("d1", DANACH, "Übersetzungen DE/EN prüfen", "Beschreibungen, Auswahlwerte", "Enton"),
    Punkt("d2", DANACH, "Gerätedaten aus Weclapp", "Datenquelle umstellen", "Claude", auto=_weclapp_daten),
    Punkt("d3", DANACH, "Kollegen einrichten", "Programm, Token, Kurzanleitung", "Enton"),
]
SELBST = {"t6", "t7"}                     # setzt das Programm nach erfolgreichem Test / Probevorgang


class Stand:
    """Abgehakte Punkte (von Hand oder vom Programm gemeldet) in weclapp-starttag.json."""

    def __init__(self, pfad: Path):
        self.pfad = Path(pfad)
        try:
            d = json.loads(self.pfad.read_text(encoding="utf-8"))
            self.erledigt: dict[str, bool] = {k: True for k, v in d.get("erledigt", {}).items() if v}
        except (OSError, ValueError, AttributeError):
            self.erledigt = {}

    def setzen(self, pid: str, an: bool) -> None:
        if an:
            self.erledigt[pid] = True
        else:
            self.erledigt.pop(pid, None)
        try:
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.pfad.with_suffix(".tmp")
            tmp.write_text(json.dumps({"erledigt": self.erledigt}, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.pfad)
        except OSError:
            pass

    def gruen(self, p: Punkt, app) -> bool:
        if p.fest or self.erledigt.get(p.id):
            return True
        if p.auto is not None:
            try:
                return bool(p.auto(app))
            except Exception:  # noqa: BLE001
                return False
        return False

    def zaehlen(self, app) -> tuple[int, int]:
        ok = sum(1 for p in PUNKTE if self.gruen(p, app))
        return ok, len(PUNKTE)


class StarttagLeiste(ctk.CTkFrame):
    """Rechte Seitenleiste. Einklappbar; verschwindet ganz, sobald alles grün ist."""

    BREITE = 300

    def __init__(self, master, app):
        super().__init__(master, fg_color=TH.SEITE, corner_radius=0, width=self.BREITE)
        self.app = app
        self.stand = Stand(app.pfad.parent / DATEI)
        self.offen = True
        kopf = ctk.CTkFrame(self, fg_color="transparent")
        kopf.pack(fill="x", padx=14, pady=(16, 6))
        self.titel = TH.text(kopf, "Weclapp-Start", 15, True, anchor="w")
        self.titel.pack(side="left")
        self.zu_knopf = ctk.CTkButton(kopf, text="›", width=28, height=28, corner_radius=6, fg_color="transparent",
                                      hover_color=TH.KNOPF_HOVER, text_color=TH.GRAU, font=TH.schrift(16, True),
                                      command=self.umschalten)
        self.zu_knopf.pack(side="right")
        self.zahl = TH.text(self, "", 12, farbe=TH.GRAU, anchor="w")
        self.zahl.pack(fill="x", padx=14)
        self.balken = ctk.CTkProgressBar(self, height=6, progress_color=TH.GRUEN_RAND, fg_color=("#FDE2E1", "#4A1616"))
        self.balken.pack(fill="x", padx=14, pady=(6, 8))
        self.liste = ctk.CTkScrollableFrame(self, fg_color="transparent", width=self.BREITE - 20)
        self.liste.pack(fill="both", expand=True, padx=(6, 2), pady=(0, 10))
        self.zeilen: dict[str, tuple] = {}
        gruppe = None
        for p in PUNKTE:
            if p.gruppe != gruppe:
                gruppe = p.gruppe
                TH.text(self.liste, gruppe.upper(), 10, True, farbe=TH.GRAU, anchor="w").pack(fill="x", padx=8, pady=(10, 2))
            z = ctk.CTkFrame(self.liste, fg_color=TH.FLAECHE, corner_radius=8, border_width=1, border_color=TH.RAND)
            z.pack(fill="x", padx=4, pady=2)
            marke = ctk.CTkButton(z, text="", width=22, height=22, corner_radius=6, font=TH.schrift(12, True),
                                  command=lambda pid=p.id: self.klick(pid))
            marke.pack(side="left", padx=(8, 8), pady=8, anchor="n")
            txt = ctk.CTkFrame(z, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True, pady=6, padx=(0, 8))
            TH.text(txt, p.titel, 12, True, anchor="w", justify="left", wraplength=210).pack(fill="x")
            TH.text(txt, f"{p.detail} · {p.wer}", 11, farbe=TH.GRAU, anchor="w", justify="left",
                    wraplength=210).pack(fill="x")
            self.zeilen[p.id] = (p, z, marke)
        self.aktualisieren()

    # ------------------------------------------------------------------
    def klick(self, pid: str):
        p = self.zeilen[pid][0]
        if p.fest or (p.auto is not None and not self.stand.erledigt.get(pid) and self.stand.gruen(p, self.app)):
            return                                    # vom Programm erkannt – nicht von Hand zurücknehmen
        self.stand.setzen(pid, not self.stand.erledigt.get(pid))
        self.aktualisieren()

    def melden(self, pid: str):
        """Das Programm meldet einen erledigten Schritt (Verbindung testen, Probevorgang)."""
        if not self.stand.erledigt.get(pid):
            self.stand.setzen(pid, True)
        self.aktualisieren()

    def umschalten(self):
        self.offen = not self.offen
        if self.offen:
            self.zahl.pack(fill="x", padx=14)
            self.balken.pack(fill="x", padx=14, pady=(6, 8))
            self.liste.pack(fill="both", expand=True, padx=(6, 2), pady=(0, 10))
            self.titel.configure(text="Weclapp-Start")
            self.configure(width=self.BREITE)
            self.zu_knopf.configure(text="›")
        else:
            for w in (self.liste, self.zahl, self.balken):
                w.pack_forget()
            ok, n = self.stand.zaehlen(self.app)
            self.titel.configure(text=f"{ok}/{n}")
            self.configure(width=70)
            self.zu_knopf.configure(text="‹")

    def aktualisieren(self):
        rot_bg, rot_text = ("#FDE2E1", "#4A1616"), ("#8B1A1A", "#FFB4AB")
        for pid, (p, z, marke) in self.zeilen.items():
            ok = self.stand.gruen(p, self.app)
            z.configure(border_color=TH.GRUEN_RAND if ok else rot_text)
            marke.configure(text="✓" if ok else "!", fg_color=TH.GRUEN_BG if ok else rot_bg,
                            hover_color=TH.GRUEN_BG if ok else rot_bg, text_color=TH.GRUEN if ok else rot_text)
        ok, n = self.stand.zaehlen(self.app)
        self.zahl.configure(text=f"{ok} von {n} erledigt · {n - ok} offen")
        self.balken.set(ok / n if n else 1)
        if not self.offen:
            self.titel.configure(text=f"{ok}/{n}")
        self.app.starttag_sichtbar(ok < n)
