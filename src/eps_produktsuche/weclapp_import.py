"""Weclapp-Stammdatenimport (Verkaufsartikel-Stammdaten, CSV) – Spaltenreihenfolge und Standardwerte.

Quelle: SalesArticleMasterDataWeclapp DemoImportfile / Importfile Columnorder (12.05.2025), von weclapp im Importassistenten
bereitgestellt. Der Import kennt KEINE Zusatzfelder (eps_…); die werden per API geschrieben (weclapp_schreiben).
Pflichtfelder: ARTIKELNAME (A), ARTIKELNUMMER (D), EINHEIT (J, nur beim Anlegen); Preisspalten nur mit Verkaufspreis.
"""
from __future__ import annotations

import csv
from pathlib import Path

KOPF = ['ARTIKELNAME', 'Handelssprache', 'Lokaler Artikelname', 'ARTIKELNUMMER', 'VERTRIEBSWEG', 'Verkaufspreis', 'WÄHRUNG',
 'Exportpreise gültig ab', 'VERKAUF AB', 'EINHEIT', 'Matchcode', 'Artikel ist aktiv', 'Warengruppen-Name',
 'Warengruppen Beschreibung', 'Steuersatz', 'Kurztext 1', 'Handelssprache', 'Lokalisierte Kurztext 1', 'Kurztext 2',
 'Handelssprache', 'Lokalisierte Kurztext 2', 'Artikelbeschreibung', 'Handelssprache',
 'Lokalisierte Artikelbeschreibung', 'Interner Hinweis', 'Handelssprache', 'Lokalisierter interner Hinweis',
 'Artikel-Langbeschreibung', 'Handelssprache', 'Lokalisierte lange Artikelbeschreibung', 'EAN-Nummer', 'Hersteller',
 'Systemcode', 'Katalogcode', 'Verkauf von', 'Verkauf bis', 'Support bis', 'MPN-Nummer', 'Ursprungsland',
 'Bruttogewicht Artikel', 'Nettogewicht Artikel', 'Zolltarifnummer', 'Zollbeschreibung', 'Länge Artikel',
 'Breite Artikel', 'Höhe Artikel', 'Herstellertyp', 'Einführungsdatum', 'Sicherheitstage', 'Mindestlagerbestand',
 'Zielbestand', 'Wiederbeschaffungstage', 'Durchschnittliche Lieferzeit', 'Mindestbestellmenge', 'Fixe Bestellmenge',
 'Margen-Kalkulations-Preis-Typ', 'Ignorieren in Preiskalkulation',
 'Standard-Kalkulationspreis für die Preiskalkulation', 'Interner Verrechnungspreis',
 'Preis-Eintritt Verrechnungspreis', 'UVP netto', 'Preis-Eintritt UVP netto', 'UVP brutto',
 'Preis-Eintritt UVP brutto', 'Auf Lieferschein', 'Artikeltyp', 'Zu produzieren', 'Chargennummer erforderlich',
 'Seriennummer erforderlich', 'LADEHILFSMITTEL BESTANDSFÜHREND', 'ABC-Klassifizierung', 'Aktuelle Herstellkosten',
 'Verkaufsartikel', 'Stücklistenteillieferung möglich', 'Unterpositionen mit Preisen für Verkauf',
 'Unterpositionen mit Preisen für Einkauf', 'In Produktionsaufträgen auflösen', 'Verfallstage',
 'Verfallsdatum von Produktionsauftragspositionen berücksichtigen',
 'Nur aktivierte Vertriebswege im Verkauf erlauben', 'Artikelkennzeichen', 'Kostenstelle Verkauf',
 'Kostenstelle Einkauf', 'Kostenart', 'Erlöskonto', 'Aufwandskonto', 'Skontoabzugsfähig',
 'Geplante Arbeitszeit pro Einheit', 'Abrechnungsart', 'Belegposition Gruppenname', 'Provisionssatz',
 'Dienstleistungsartikel des Kontingents', 'Kontingentsmenge']

# Standardwerte der Beispielzeile „Palette“ (ohne Preis), Spalten-Buchstabe → Wert
STANDARD = {'AX': '0',
 'AY': '0',
 'BB': '0',
 'BC': '0',
 'BD': 'PURCHASE_PRICE_PRODUCTION_COST',
 'BE': 'nein',
 'BF': 'PURCHASE',
 'BM': 'ja',
 'BN': 'STORABLE',
 'BO': 'nein',
 'BP': 'nein',
 'BQ': 'nein',
 'BR': 'nein',
 'BT': '0',
 'BU': 'ja',
 'BV': 'nein',
 'BW': 'nein',
 'BX': 'nein',
 'BY': 'nein',
 'CA': 'ja',
 'CB': 'nein',
 'CI': 'ja',
 'O': 'STANDARD'}


def _index(buchstabe: str) -> int:
    n = 0
    for ch in buchstabe:
        n = n * 26 + ord(ch) - 64
    return n - 1


def zeile(**felder: str) -> list[str]:
    """Eine Importzeile; Schlüsselwörter sind Spalten-Buchstaben (A=ARTIKELNAME, D=ARTIKELNUMMER, J=EINHEIT, M=Warengruppen-Name …)."""
    z = [""] * len(KOPF)
    for b, v in STANDARD.items():
        z[_index(b)] = v
    for b, v in felder.items():
        z[_index(b)] = str(v)
    return z


def schreiben(pfad, zeilen: list[list[str]]) -> None:
    """UTF-8 mit BOM, Semikolon, Komma als Dezimaltrenner (Einstellungen im Importassistenten)."""
    with open(Path(pfad), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(KOPF)
        w.writerows(zeilen)


# ---------------------------------------------------------------- Bezugsquellen-Import
# Quelle: SupplySourcesWeclapp DemoImportfile_de / Importfile Columnorder_de (28.10.2024).
# Pflichtfelder: A ARTIKELNAME, D Lieferantenartikelnummer, F LIEFERANTENNUMMER, O Artikel-Mengeneinheit.
# V/W: „Zugehörigen Verkaufsartikel erstellen oder aktualisieren“ + Verkaufsartikel-Nummer (Verknüpfung).
BQ_KOPF = ['ARTIKELNAME', 'Handelssprache', 'Lokaler Artikelname', 'Lieferantenartikelnummer', 'Lieferanten Firmenname',
 'LIEFERANTENNUMMER', 'Bruttokaufpreis', 'Zu- und Abschläge Bezeichnung 1', 'Zu- und Abschläge Preisart 1',
 'Zu- und Abschläge Wert 1', 'Zu- und Abschläge Bezeichnung 2', 'Zu- und Abschläge Preisart 2',
 'Zu- und Abschläge Wert 2', 'Währung', 'Artikel-Mengeneinheit', 'Matchcode', 'Artikel aktiv', 'Preis-Eintritt',
 'Warengruppen-Name', 'Warengruppen Beschreibung', 'Steuersatz',
 'Zugehörigen Verkaufsartikel erstellen oder aktualisieren', 'Verkaufsartikel-Nummer',
 'Bruttopreis des zugehörigen Verkaufsartikels', 'Verkaufsartikel-Währung', 'Vertriebsweg', 'Vertriebsweg-Steuersatz',
 'Kurztext 1', 'Handelssprache', 'Lokalisierte Kurztext 1', 'Kurztext 2', 'Handelssprache', 'Lokalisierte Kurztext 2',
 'Artikelbeschreibung', 'Handelssprache', 'Lokalisierte Artikelbeschreibung', 'Interner Hinweis', 'Handelssprache',
 'Lokalisierter interner Hinweis', 'Artikel-Langbeschreibung', 'Handelssprache',
 'Lokalisierte Lange Artikelbeschreibung', 'EAN-Nummer', 'MPN-Nummer', 'Artikeltyp', 'Serienartikel', 'Hersteller',
 'Bruttogewicht', 'Nettogewicht', 'Zolltarifnummer', 'Länge Artikel', 'Breite Artikel', 'Höhe Artikel',
 'Herstellertyp', 'Einführungsdatum', 'Sicherheitstage', 'Mindestlagerbestand', 'Zielbestand',
 'Wiederbeschaffungstage', 'Durchschnittliche Lieferzeit', 'Mindestbestellmenge', 'Gebindemenge',
 'Lieferantenbestand', 'Dropshipping möglich', 'In Dropshipping-Automatisierung ignorieren', 'Kostenstelle Verkauf',
 'Kostenstelle Einkauf', 'Kostenart', 'Primäre Bezugsquelle']


def bq_zeile(**felder: str) -> list[str]:
    z = [""] * len(BQ_KOPF)
    for b, v in felder.items():
        z[_index(b)] = str(v)
    return z


def bq_schreiben(pfad, zeilen: list[list[str]]) -> None:
    with open(Path(pfad), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(BQ_KOPF)
        w.writerows(zeilen)
