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
import io
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

# Bilder (Screenshots) zur Meldung: gehen nur als Mail-Anhang an Hermes, nicht in
# Firestore. Jedes Bild wird neu als JPEG kodiert: kleiner, und Metadaten wie
# GPS-Position oder Kameramodell fallen dabei weg.
MAX_BILDER = 3
MAX_BILD_BYTES = 10 * 1024 * 1024          # Rohdatei vor dem Verkleinern
BILD_MAX_KANTE = 1600
BILD_TYPEN = ["png", "jpg", "jpeg", "webp", "gif"]


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


def bilder_aufbereiten(dateien):
    """[(dateiname, bytes)] -> ([(name, jpeg_bytes, 'image/jpeg')], fehler oder None).

    Der Dateiname des Nutzers wird nicht uebernommen (bild-1.jpg, …)."""
    dateien = [d for d in (dateien or []) if d and d[1]]
    if not dateien:
        return [], None
    if len(dateien) > MAX_BILDER:
        return [], f"Bitte höchstens {MAX_BILDER} Bilder anhängen."
    try:
        from PIL import Image, ImageOps
    except ImportError:                     # ohne Pillow lieber ohne Bilder als gar nicht
        return [], "Bilder können gerade nicht verarbeitet werden. Bitte ohne Bild senden."
    out = []
    for i, (name, daten) in enumerate(dateien, 1):
        if len(daten) > MAX_BILD_BYTES:
            return [], f"„{_einzeilig(name, 40)}“ ist zu groß (höchstens {MAX_BILD_BYTES // 1048576} MB)."
        try:
            with Image.open(io.BytesIO(daten)) as im:
                im = ImageOps.exif_transpose(im)        # Handyfotos richtig herum
                if im.mode not in ("RGB", "L"):
                    hinten = Image.new("RGB", im.size, (255, 255, 255))
                    hinten.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                    im = hinten
                im.thumbnail((BILD_MAX_KANTE, BILD_MAX_KANTE))
                buf = io.BytesIO()
                im.convert("RGB").save(buf, "JPEG", quality=85, optimize=True)
        except Exception:
            return [], f"„{_einzeilig(name, 40)}“ ist kein Bild (erlaubt: {', '.join(BILD_TYPEN)})."
        out.append((f"bild-{i}.jpg", buf.getvalue(), "image/jpeg"))
    return out, None


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


def _bilder_zeile(bilder):
    namen = [b[0] for b in bilder or []]
    return f"{len(namen)} ({', '.join(namen)})" if namen else "0"


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
        f"bilder: {_bilder_zeile(fb.get('bilder'))}",
        "--- BESCHREIBUNG ---",
        fb["text"],
        "--- ENDE ---",
    ])
    return kopf + block + "\n"


def datensatz(fb):
    """Was in Firestore (Collection 'feedback') gespeichert wird."""
    return {k: fb.get(k) for k in (
        "id", "art", "seite", "text", "version", "rolle", "nutzer_id",
        "email", "name", "browser", "zeit")} | {
        "projekt": PROJECT,
        "bilder": [{"name": b[0], "bytes": len(b[1])} for b in fb.get("bilder") or []],
    }
