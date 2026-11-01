"""
Tests des Zwischenspeichers. Laufen ohne Firebase und ohne Streamlit:

    python -m pytest test_core_cache.py -v
"""
import threading

import pytest

from core_cache import TtlCache, einstellungen_aus_dokumenten


class Uhr:
    """Steuerbare Uhr statt time.monotonic."""
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Zaehler:
    """Ladefunktion, die mitzaehlt, wie oft Firestore gefragt wuerde."""
    def __init__(self, werte):
        self.werte = list(werte)
        self.aufrufe = 0

    def __call__(self):
        self.aufrufe += 1
        return self.werte[min(self.aufrufe, len(self.werte)) - 1]


def test_laedt_einmal_innerhalb_der_ttl():
    uhr = Uhr()
    c = TtlCache(ttl=60, uhr=uhr)
    laden = Zaehler([{'a': 1}])
    for _ in range(10):
        assert c.get(laden) == {'a': 1}
        uhr.t += 5
    # 10 Abrufe ueber 45 s: ein einziger Lesezugriff
    assert laden.aufrufe == 1


def test_laedt_nach_ablauf_neu():
    uhr = Uhr()
    c = TtlCache(ttl=60, uhr=uhr)
    laden = Zaehler([{'a': 1}, {'a': 2}])
    assert c.get(laden) == {'a': 1}
    uhr.t = 59.9
    assert c.get(laden) == {'a': 1}
    uhr.t = 60
    assert c.get(laden) == {'a': 2}
    assert laden.aufrufe == 2


def test_leeren_wirkt_sofort():
    """Eigene Schreibzugriffe (set_setting, Termin sperren) sind sofort sichtbar."""
    uhr = Uhr()
    c = TtlCache(ttl=60, uhr=uhr)
    laden = Zaehler([{'frist': 24}, {'frist': 48}])
    assert c.get(laden) == {'frist': 24}
    c.leeren()
    assert c.get(laden) == {'frist': 48}


def test_fehler_beim_laden_wird_nicht_gespeichert():
    """Ein Firestore-Aussetzer darf keinen leeren Stand festschreiben."""
    c = TtlCache(ttl=60, uhr=Uhr())

    def kaputt():
        raise RuntimeError('Firestore nicht erreichbar')

    with pytest.raises(RuntimeError):
        c.get(kaputt)
    laden = Zaehler([{'a': 1}])
    assert c.get(laden) == {'a': 1}
    assert laden.aufrufe == 1


def test_gleichzeitige_sitzungen_laden_nur_einmal():
    c = TtlCache(ttl=60)
    laden = Zaehler([{'a': 1}])
    start = threading.Barrier(8)
    ergebnisse = []

    def sitzung():
        start.wait()
        ergebnisse.append(c.get(laden))

    threads = [threading.Thread(target=sitzung) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ergebnisse == [{'a': 1}] * 8
    assert laden.aufrufe == 1


class Dok:
    def __init__(self, id, daten):
        self.id = id
        self._daten = daten

    def to_dict(self):
        return self._daten


def test_einstellungen_aus_dokumenten():
    werte = einstellungen_aus_dokumenten([
        Dok('cancel_deadline_hours', {'value': 48, 'updated_at': 'x'}),
        Dok('season_pause_start', {'value': '10-15'}),
        Dok('leer', {'value': ''}),
        Dok('ohne_wert', {'updated_at': 'x'}),
        Dok('kaputt', None),
    ])
    assert werte == {'cancel_deadline_hours': 48, 'season_pause_start': '10-15', 'leer': ''}
    # Wie das alte get_setting: fehlender Wert -> Vorgabe, leerer Wert bleibt leer
    assert werte.get('ohne_wert', 'vorgabe') == 'vorgabe'
    assert werte.get('leer', 'vorgabe') == ''
