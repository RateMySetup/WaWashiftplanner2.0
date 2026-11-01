"""
Zwischenspeicher fuer selten geaenderte Daten (Einstellungen, gesperrte Termine).

Warum: streamlit_app.py laeuft bei jedem Klick komplett neu durch und las
dabei dieselben Einstellungen bis zu zehnmal aus Firestore - jeder Zugriff
ein Netzwerk-Roundtrip von Azure zu Google und ein Lesezugriff vom
Free-Tier-Kontingent.

Der Speicher steht hier auf Modulebene, weil Streamlit nur das Hauptskript
bei jedem Rerun neu ausfuehrt; importierte Module (und damit diese Caches)
bleiben fuer alle Sitzungen des Prozesses erhalten. Schreibt die App selbst,
leert sie den passenden Cache sofort - Aenderungen im Admin-Bereich wirken
also ohne Wartezeit. Nur Aenderungen von aussen (Firebase-Konsole, Skripte)
erscheinen erst nach Ablauf von TTL_SEKUNDEN.

Bewusst frei von Streamlit- und Firestore-Abhaengigkeiten, damit die Logik
ohne laufende App getestet werden kann. Buchungen werden NICHT gecacht:
dort muss jeder Klick den aktuellen Stand sehen.
"""
import threading
import time

TTL_SEKUNDEN = 60


class TtlCache:
    """Ein Wert, der nach `ttl` Sekunden neu geladen wird.

    Schlaegt das Laden fehl, wird nichts gespeichert und der Fehler
    weitergereicht - ein kurzer Firestore-Aussetzer darf keinen leeren
    Stand fuer eine Minute festschreiben.
    """

    def __init__(self, ttl=TTL_SEKUNDEN, uhr=time.monotonic):
        self.ttl = ttl
        self._uhr = uhr
        # Ein Lock fuer Laden und Lesen: kommen mehrere Sitzungen gleichzeitig,
        # laedt nur eine, die anderen bekommen danach deren Ergebnis.
        self._lock = threading.Lock()
        self._wert = None
        self._stand = None

    def get(self, laden):
        """Gespeicherten Wert liefern, bei Bedarf vorher `laden()` aufrufen."""
        with self._lock:
            jetzt = self._uhr()
            if self._stand is None or jetzt - self._stand >= self.ttl:
                self._wert = laden()
                self._stand = jetzt
            return self._wert

    def leeren(self):
        """Beim naechsten get() neu laden (nach eigenen Schreibzugriffen)."""
        with self._lock:
            self._wert = None
            self._stand = None


# Gemeinsame Caches des Prozesses
einstellungen = TtlCache()      # {schluessel: wert} aus der Collection 'settings'
gesperrte_termine = TtlCache()  # {'YYYY-MM-TT': grund} aus 'blocked_dates'

# Admin-Konto wird nur einmal je Prozessstart geprueft bzw. angelegt.
admin_geprueft = threading.Event()


def einstellungen_aus_dokumenten(dokumente):
    """{id: value} aus Firestore-Dokumenten der Collection 'settings'.

    Dokumente ohne Feld 'value' fehlen im Ergebnis - get_setting() liefert
    dafuer wie bisher den Vorgabewert.
    """
    ergebnis = {}
    for doc in dokumente:
        daten = doc.to_dict() or {}
        if 'value' in daten:
            ergebnis[doc.id] = daten['value']
    return ergebnis
