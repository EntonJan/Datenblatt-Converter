"""Kundenanfragen als E-Mail: einheitliches Mail-Objekt aus Outlook, .msg- oder .eml-Dateien.

Quellen:
  • klassisches Outlook (outlook.py, Ordner „Anfragen/Automatisch“ bzw. „Anfragen/Selbst prüfen“)
  • Datei: aus Outlook gespeicherte .msg (klassisch) oder .eml (neues Outlook: „Speichern unter“)
Anhänge (PDF/Word) werden in einen Arbeitsordner gelegt und laufen durch die bestehende Datenblatt-Auslese.
"""
from __future__ import annotations

import email
import email.policy
import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

ANHANG_ENDUNGEN = (".pdf", ".docx", ".docm")


@dataclass
class Mail:
    betreff: str = ""
    absender_name: str = ""
    absender_email: str = ""
    empfangen: str = ""              # ISO-Zeit
    text: str = ""                   # Klartext (HTML wird umgewandelt)
    anhaenge: list[Path] = field(default_factory=list)   # gespeicherte PDF/Word-Anhänge
    quelle: str = ""                 # Dateipfad oder Outlook-EntryID
    ordner: str = ""                 # Outlook-Ordner (Anzeige)
    eingebettet: list["Mail"] = field(default_factory=list)   # als Anhang weitergeleitete Mails

    @property
    def kennung(self) -> str:
        return self.quelle


def html_zu_text(h: str) -> str:
    h = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", h)
    h = re.sub(r"(?i)</td>", "\t", h)
    h = re.sub(r"<[^>]+>", "", h)
    t = html.unescape(h).replace("\xa0", " ")
    t = re.sub(r"[ \t]+\n", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _sicherer_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name or "anhang").strip(" .")
    return name[:120] or "anhang"


def _ablegen(ordner: Path, name: str, daten: bytes) -> Path:
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / _sicherer_name(name)
    n = 2
    while ziel.exists():
        ziel = ziel.with_name(f"{ziel.stem}_{n}{ziel.suffix}")
        n += 1
    ziel.write_bytes(daten)
    return ziel


def _aus_message(msg, anhang_ordner: Path, quelle: str) -> Mail:
    name, adresse = parseaddr(str(msg.get("From", "")))
    m = Mail(betreff=str(msg.get("Subject", "") or ""), absender_name=name, absender_email=adresse.lower(), quelle=quelle)
    try:
        m.empfangen = parsedate_to_datetime(str(msg.get("Date"))).isoformat(timespec="minutes")
    except (TypeError, ValueError):
        pass
    teil = msg.get_body(preferencelist=("plain", "html"))
    if teil is not None:
        inhalt = teil.get_content()
        m.text = html_zu_text(inhalt) if teil.get_content_type() == "text/html" else inhalt.strip()
    for a in msg.iter_attachments():
        if a.get_content_type() == "message/rfc822":       # als Anhang weitergeleitete Mail
            inneres = a.get_content()
            if hasattr(inneres, "get_body"):
                m.eingebettet.append(_aus_message(inneres, anhang_ordner / f"eingebettet{len(m.eingebettet) + 1}", quelle))
            continue
        dateiname = a.get_filename() or ""
        if dateiname.lower().endswith(ANHANG_ENDUNGEN):
            m.anhaenge.append(_ablegen(anhang_ordner, dateiname, a.get_payload(decode=True) or b""))
        elif dateiname.lower().endswith((".msg", ".eml")):
            p = _ablegen(anhang_ordner, dateiname, a.get_payload(decode=True) or b"")
            try:
                m.eingebettet.append(datei_lesen(p, anhang_ordner / p.stem))
            except Exception:  # noqa: BLE001
                pass
    for inner in m.eingebettet:                              # Anhänge der Original-Mail gehören zur Anfrage
        m.anhaenge.extend(inner.anhaenge)
    return m


def eml_lesen(pfad: Path, anhang_ordner: Path) -> Mail:
    msg = email.message_from_bytes(Path(pfad).read_bytes(), policy=email.policy.default)
    return _aus_message(msg, anhang_ordner, str(pfad))


def msg_lesen(pfad: Path, anhang_ordner: Path) -> Mail:
    import extract_msg
    msg = extract_msg.openMsg(str(pfad))
    try:
        return _aus_extract(msg, anhang_ordner, str(pfad))
    finally:
        msg.close()


def _aus_extract(msg, anhang_ordner: Path, quelle: str) -> Mail:
    name, adresse = parseaddr(msg.sender or "")
    m = Mail(betreff=msg.subject or "", absender_name=name or (msg.sender or ""), absender_email=adresse.lower(),
             quelle=quelle)
    try:
        d = msg.date
        m.empfangen = d.isoformat(timespec="minutes") if isinstance(d, datetime) else ""
    except Exception:  # noqa: BLE001 – Datum ist nur zur Anzeige
        pass
    text = msg.body or ""
    if not text.strip() and msg.htmlBody:
        raw = msg.htmlBody
        text = html_zu_text(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw)
    m.text = text.replace("\r\n", "\n").strip()
    for a in msg.attachments:
        dateiname = getattr(a, "longFilename", None) or getattr(a, "shortFilename", None) or ""
        daten = getattr(a, "data", None)
        if daten is not None and not isinstance(daten, bytes) and hasattr(daten, "subject"):
            m.eingebettet.append(_aus_extract(daten, anhang_ordner / f"eingebettet{len(m.eingebettet) + 1}", quelle))
        elif dateiname.lower().endswith(ANHANG_ENDUNGEN) and isinstance(daten, bytes):
            m.anhaenge.append(_ablegen(anhang_ordner, dateiname, daten))
    for inner in m.eingebettet:
        m.anhaenge.extend(inner.anhaenge)
    return m


def datei_lesen(pfad: Path, anhang_ordner: Path) -> Mail:
    pfad = Path(pfad)
    if pfad.suffix.lower() == ".msg":
        return msg_lesen(pfad, anhang_ordner)
    if pfad.suffix.lower() == ".eml":
        return eml_lesen(pfad, anhang_ordner)
    raise ValueError(f"Unbekanntes Mailformat: {pfad.suffix}")
