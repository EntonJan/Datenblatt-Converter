"""Weclapp-Token sicher ablegen: Windows-Anmeldeinformationsverwaltung (über keyring), pro Windows-Benutzer.

Nie in der EXE, nie im Repo, nie in einer Datei im Programmordner. Ohne keyring (z. B. Linux-Tests) bleibt der
Token nur bis zum Programmende im Speicher.
"""
from __future__ import annotations

DIENST = "EPS-Produktsuche/Weclapp"
_speicher: dict[str, str] = {}


def _keyring():
    try:
        import keyring
        from keyring.backends import fail
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring
    except Exception:  # noqa: BLE001
        return None


def speichern(adresse: str, token: str) -> bool:
    """True = dauerhaft gespeichert, False = nur für diese Sitzung."""
    kr = _keyring()
    if kr:
        try:
            kr.set_password(DIENST, adresse, token)
            return True
        except Exception:  # noqa: BLE001
            pass
    _speicher[adresse] = token
    return False


def laden(adresse: str) -> str:
    kr = _keyring()
    if kr:
        try:
            return kr.get_password(DIENST, adresse) or _speicher.get(adresse, "")
        except Exception:  # noqa: BLE001
            pass
    return _speicher.get(adresse, "")


def loeschen(adresse: str) -> None:
    _speicher.pop(adresse, None)
    kr = _keyring()
    if kr:
        try:
            kr.delete_password(DIENST, adresse)
        except Exception:  # noqa: BLE001
            pass
