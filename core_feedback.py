"""
Problem melden: Rueckmeldungen von Nutzern als E-Mail an das Postfach des
Hermes-Agenten (Standard mex100bot@gmail.com).

Hermes erkennt die Mails am Betreff "[Feedback][WaWa]" und liest den
maschinenlesbaren Block zwischen "--- HERMES-FEEDBACK v1 ---" und
"--- ENDE ---". Aufbau nicht aendern, ohne den Hermes-Skill
private/app-feedback (Skript feedback_mail.py) mitzuziehen.

Bewusst frei von Streamlit und Firestore, damit sich alles ohne App pruefen
laesst.
"""
import re
import secrets
from datetime import timedelta

FEEDBACK_EMAIL_DEFAULT = "mex100bot@gmail.com"
PROJECT = "wawa-shiftplanner"
SUBJECT_TAG = "[Feedback][WaWa]"

ARTEN = {
    "bug": "Fehler",
    "idee": "Verbesserung",
    "frage": "Frage",
}

# Seiten, die Nutzer auswaehlen koennen ("wo ist es passiert?").
SEITEN = {
    "unbekannt": "Weiß ich nicht",
    "kalender": "Kalender / Buchen",
    "meine_buchungen": "Meine Termine",
    "profil": "Mein Profil",
    "statistik": "Statistik",
    "verwaltung": "Verwaltung",
    "benutzer": "Benutzer",
    "anmeldung": "Anmeldung / Passwort",
    "mail": "E-Mails / Erinnerungen",
    "sonstiges": "Sonstiges",
}

MIN_LAENGE = 10
MAX_LAENGE = 2000
LIMIT_PRO_TAG = 5


def neue_id(jetzt):
    """Kurze, eindeutige Kennung, z. B. FB-20261026-3f9a."""
    return f"FB-{jetzt.strftime('%Y%m%d')}-{secrets.token_hex(2)}"


def text_bereinigen(text):
    """Steuerzeichen raus (ausser Zeilenumbruch und Tab), Laenge begrenzen."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c in "\n\t" or ord(c) >= 32)
    return text.strip()[:MAX_LAENGE]


def pruefen(art, text):
    """Fehlermeldung fuer das Formular oder None, wenn alles passt."""
    if art not in ARTEN:
        return "Bitte auswählen, worum es geht."
    if len(text_bereinigen(text)) < MIN_LAENGE:
        return f"Bitte kurz beschreiben, was passiert ist (mindestens {MIN_LAENGE} Zeichen)."
    return None


def limit_erreicht(zeitpunkte, jetzt, limit=LIMIT_PRO_TAG):
    """True, wenn in den letzten 24 Stunden schon `limit` Meldungen kamen."""
    grenze = jetzt - timedelta(hours=24)
    return sum(1 for t in zeitpunkte if t and t >= grenze) >= limit


def _einzeilig(text, laenge):
    """Fuer Kopfzeilen: keine Zeilenumbrueche (Header-Injection), gekuerzt."""
    zeile = re.sub(r"\s+", " ", text or "").strip()
    return zeile if len(zeile) <= laenge else zeile[: laenge - 1].rstrip() + "…"


def betreff(fb):
    titel = _einzeilig(fb["text"].split("\n", 1)[0], 60)
    return f"{SUBJECT_TAG} {ARTEN[fb['art']]}: {titel} ({fb['id']})"


def mailtext(fb):
    """Lesbarer Teil fuer Menschen plus Block fuer Hermes."""
    seite = SEITEN.get(fb.get("seite"), SEITEN["unbekannt"])
    kopf = (
        f"Neue Rückmeldung aus dem Wasserwacht-Dienstplan\n\n"
        f"Art:     {ARTEN[fb['art']]}\n"
        f"Seite:   {seite}\n"
        f"Von:     {_einzeilig(fb.get('name'), 80)} <{_einzeilig(fb.get('email'), 120)}>\n"
        f"Zeit:    {fb['zeit']}\n\n"
        f"{fb['text']}\n\n"
        "Antworten geht direkt an die meldende Person (Reply-To).\n\n"
    )
    block = "\n".join([
        "--- HERMES-FEEDBACK v1 ---",
        f"id: {fb['id']}",
        f"projekt: {PROJECT}",
        f"art: {fb['art']}",
        f"seite: {fb.get('seite') or 'unbekannt'}",
        f"version: {_einzeilig(fb.get('version'), 20)}",
        f"zeit: {fb['zeit']}",
        f"rolle: {_einzeilig(fb.get('rolle'), 20)}",
        f"nutzer_id: {_einzeilig(fb.get('nutzer_id'), 64)}",
        f"browser: {_einzeilig(fb.get('browser'), 200)}",
        "--- BESCHREIBUNG ---",
        fb["text"],
        "--- ENDE ---",
    ])
    return kopf + block + "\n"


def datensatz(fb):
    """Was in Firestore (Collection 'feedback') gespeichert wird."""
    return {k: fb.get(k) for k in (
        "id", "art", "seite", "text", "version", "rolle", "nutzer_id",
        "email", "name", "browser", "zeit")} | {"projekt": PROJECT}
