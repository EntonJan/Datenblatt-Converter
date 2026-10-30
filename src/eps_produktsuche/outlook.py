"""Anfragen aus dem klassischen Outlook lesen und verschieben (Windows, COM über pywin32 – keine Admin-Rechte nötig).

Das neue Outlook hat keine Programmschnittstelle mehr; das klassische Outlook muss installiert und eingerichtet sein
(es darf geschlossen sein, Windows startet es im Hintergrund). Ordnerpfade wie in Outlook, getrennt mit „/“:
    „Posteingang/Anfragen/Automatisch“                   → im eigenen Postfach
    „vertrieb@eps-germany.de/Posteingang/Anfragen“      → im gemeinsamen Postfach (Name wie in der Ordnerliste)
Alle Aufrufe laufen in einem eigenen Thread; die Oberfläche bekommt nur einfache Mail-Objekte zurück.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .mail import Mail, ANHANG_ENDUNGEN, html_zu_text, _sicherer_name

MAIL_KLASSE = 43            # olMail
POSTEINGANG = 6             # olFolderInbox
PR_SMTP = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"


class OutlookFehler(RuntimeError):
    pass


def verfuegbar() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False


class Outlook:
    """Dünne Hülle um das Outlook-Objektmodell. `namespace` kann für Tests durch eine Attrappe ersetzt werden."""

    def __init__(self, namespace=None):
        self._com = False
        if namespace is None:
            if not verfuegbar():
                raise OutlookFehler("Klassisches Outlook ist auf diesem Rechner nicht verfügbar.")
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            self._com = True
            try:
                namespace = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
            except Exception as e:  # noqa: BLE001
                raise OutlookFehler(f"Outlook konnte nicht gestartet werden: {e}") from e
        self.ns = namespace

    def schliessen(self):
        if self._com:
            import pythoncom
            pythoncom.CoUninitialize()
            self._com = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.schliessen()

    # ---------------------------------------------------------------- Ordner
    def _kind(self, ordner, name: str):
        for i in range(1, ordner.Folders.Count + 1):
            f = ordner.Folders.Item(i)
            if f.Name.lower() == name.lower():
                return f
        return None

    def ordner(self, pfad: str, anlegen: bool = False):
        teile = [t for t in pfad.replace("\\", "/").split("/") if t.strip()]
        if not teile:
            raise OutlookFehler("Kein Ordner angegeben.")
        start = None
        for i in range(1, self.ns.Folders.Count + 1):        # Postfächer (eigenes + gemeinsame)
            f = self.ns.Folders.Item(i)
            if f.Name.lower() == teile[0].lower():
                start, teile = f, teile[1:]
                break
        if start is None:
            eingang = self.ns.GetDefaultFolder(POSTEINGANG)
            start = eingang.Parent                               # Wurzel des eigenen Postfachs
            if teile[0].lower() in ("posteingang", "inbox", eingang.Name.lower()):
                start, teile = eingang, teile[1:]
        aktuell = start
        for t in teile:
            kind = self._kind(aktuell, t)
            if kind is None:
                if not anlegen:
                    raise OutlookFehler(f"Ordner „{t}“ in „{pfad}“ nicht gefunden.")
                kind = aktuell.Folders.Add(t)
            aktuell = kind
        return aktuell

    # ---------------------------------------------------------------- Mails
    @staticmethod
    def _smtp(item) -> str:
        adresse = item.SenderEmailAddress or ""
        if "@" in adresse:
            return adresse.lower()
        try:                                                 # Exchange-intern („/O=EXCHANGELABS/…“)
            return item.Sender.GetExchangeUser().PrimarySmtpAddress.lower()
        except Exception:  # noqa: BLE001
            try:
                return item.PropertyAccessor.GetProperty(PR_SMTP).lower()
            except Exception:  # noqa: BLE001
                return adresse

    def mails(self, pfad: str, anhang_ordner: Path | None = None, maximal: int = 200) -> list[Mail]:
        ordner = self.ordner(pfad)
        items = ordner.Items
        try:
            items.Sort("[ReceivedTime]", True)
        except Exception:  # noqa: BLE001
            pass
        anhang_ordner = Path(anhang_ordner or tempfile.mkdtemp(prefix="eps-anfragen-"))
        ergebnis: list[Mail] = []
        for i in range(1, min(items.Count, maximal) + 1):
            item = items.Item(i)
            if getattr(item, "Class", None) != MAIL_KLASSE:
                continue
            ergebnis.append(self._mail(item, anhang_ordner / str(len(ergebnis) + 1), pfad))
        return ergebnis

    def _mail(self, item, anhang_ordner: Path, pfad: str) -> Mail:
        text = item.Body or ""
        if not text.strip() and getattr(item, "HTMLBody", ""):
            text = html_zu_text(item.HTMLBody)
        empfangen = item.ReceivedTime
        m = Mail(betreff=item.Subject or "", absender_name=item.SenderName or "", absender_email=self._smtp(item),
                 empfangen=empfangen.isoformat(timespec="minutes") if isinstance(empfangen, datetime) else str(empfangen),
                 text=text.replace("\r\n", "\n").strip(), quelle=item.EntryID, ordner=pfad)
        for j in range(1, item.Attachments.Count + 1):
            a = item.Attachments.Item(j)
            name = a.FileName or ""
            if name.lower().endswith(ANHANG_ENDUNGEN):
                anhang_ordner.mkdir(parents=True, exist_ok=True)
                ziel = anhang_ordner / _sicherer_name(name)
                a.SaveAsFile(str(ziel))
                m.anhaenge.append(ziel)
        return m

    def verschieben(self, entry_id: str, ziel_pfad: str) -> str:
        """Mail in den Zielordner verschieben (wird bei Bedarf angelegt). Gibt die neue EntryID zurück."""
        try:
            item = self.ns.GetItemFromID(entry_id)
        except Exception as e:  # noqa: BLE001
            raise OutlookFehler("Die Mail wurde nicht mehr gefunden – evtl. schon von jemand anderem verschoben.") from e
        neu = item.Move(self.ordner(ziel_pfad, anlegen=True))
        return neu.EntryID


def unterordner(pfad: str, name: str) -> str:
    """Zielordner: ein Name („Erledigt“) wird Unterordner des Anfrage-Ordners, ein Pfad mit „/“
    („Posteingang/Anfragen/Erledigt“) gilt so, wie er ist – ein gemeinsamer Ordner für alle Anfrage-Ordner."""
    name = name.strip().strip("/\\")
    if "/" in name.replace("\\", "/"):
        return name
    return pfad.rstrip("/\\") + "/" + name
