"""Weclapp-Starttag: Stand speichern, automatisch erkannte Punkte, alles grün → Leiste weg."""
from types import SimpleNamespace

from eps_produktsuche import starttag as ST


def _app(adresse="", datenquelle="shop"):
    return SimpleNamespace(einstellungen=SimpleNamespace(weclapp_adresse=adresse, datenquelle=datenquelle))


def test_stand_speichert_und_zaehlt(tmp_path):
    st = ST.Stand(tmp_path / ST.DATEI)
    app = _app()
    ok, n = st.zaehlen(app)
    assert ok == sum(1 for p in ST.PUNKTE if p.fest) == 7 and n == len(ST.PUNKTE)
    st.setzen("paket", True)
    assert ST.Stand(tmp_path / ST.DATEI).erledigt == {"paket": True}        # nach Neustart noch da
    st.setzen("paket", False)
    assert ST.Stand(tmp_path / ST.DATEI).erledigt == {}


def test_automatisch_erkannt(tmp_path, monkeypatch):
    from eps_produktsuche import zugang
    st = ST.Stand(tmp_path / ST.DATEI)
    p = {x.id: x for x in ST.PUNKTE}
    monkeypatch.setattr(zugang, "laden", lambda adresse: "geheim" if adresse == "https://eps.weclapp.com" else "")
    assert not st.gruen(p["t5"], _app("demo"))
    assert st.gruen(p["t5"], _app("https://eps.weclapp.com"))
    assert st.gruen(p["d2"], _app(datenquelle="weclapp")) and not st.gruen(p["d2"], _app())


def test_alles_gruen(tmp_path, monkeypatch):
    from eps_produktsuche import zugang
    monkeypatch.setattr(zugang, "laden", lambda adresse: "geheim")
    st = ST.Stand(tmp_path / ST.DATEI)
    for x in ST.PUNKTE:
        if not x.fest and x.auto is None:
            st.setzen(x.id, True)
    ok, n = st.zaehlen(_app("https://eps.weclapp.com", "weclapp"))
    assert ok == n
