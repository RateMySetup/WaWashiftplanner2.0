"""Problem melden: Betreff, Mailblock fuer Hermes, Pruefung, Tageslimit."""
from datetime import datetime, timedelta, timezone

import core_feedback as fb

JETZT = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)


def _meldung(**extra):
    daten = {
        'id': 'FB-20261026-ab12', 'art': 'bug', 'seite': 'kalender',
        'text': 'Buchen am Samstag geht nicht\nEs kommt eine rote Meldung.',
        'version': '9.0', 'rolle': 'user', 'nutzer_id': 'u1',
        'email': 'max@example.org', 'name': 'Max', 'browser': 'Safari',
        'zeit': '2026-10-26T11:00:00+01:00',
    }
    daten.update(extra)
    return daten


def test_betreff_und_block_fuer_hermes():
    m = _meldung()
    assert fb.betreff(m) == '[Feedback][WaWa] Fehler: Buchen am Samstag geht nicht (FB-20261026-ab12)'
    text = fb.mailtext(m)
    block = text.split('--- HERMES-FEEDBACK v1 ---\n', 1)[1]
    assert block.startswith('id: FB-20261026-ab12\nprojekt: wawa-shiftplanner\nart: bug\nseite: kalender\n')
    assert '--- BESCHREIBUNG ---\nBuchen am Samstag geht nicht\nEs kommt eine rote Meldung.\n--- ENDE ---' in block
    # Kopfzeilen-Felder bleiben einzeilig, auch wenn jemand Umbrueche einschleust.
    boese = _meldung(text='Titel\r\nBcc: x@y.de\nmehr Text', browser='a\nb')
    assert '\n' not in fb.betreff(fb.datensatz(boese) | {'text': fb.text_bereinigen(boese['text'])})
    assert 'browser: a b' in fb.mailtext(boese)


def test_pruefen_und_bereinigen():
    assert fb.pruefen('bug', 'kurz') is not None
    assert fb.pruefen('zahlung', 'lange genug beschrieben') is not None
    assert fb.pruefen('idee', 'Bitte Dunkelmodus für Admins') is None
    assert fb.text_bereinigen('a\x00b\r\nc' + 'x' * 3000).startswith('ab\nc')
    assert len(fb.text_bereinigen('x' * 3000)) == fb.MAX_LAENGE
    assert fb.neue_id(JETZT).startswith('FB-20261026-')


def test_tageslimit():
    frueher = [JETZT - timedelta(hours=h) for h in (1, 2, 3, 4)]
    assert not fb.limit_erreicht(frueher, JETZT)
    assert fb.limit_erreicht(frueher + [JETZT - timedelta(minutes=5)], JETZT)
    assert not fb.limit_erreicht([JETZT - timedelta(hours=30)] * 9, JETZT)


def _bild(fmt='JPEG', groesse=(3000, 2000), gps=False):
    import io
    from PIL import Image
    im = Image.new('RGB', groesse, (200, 30, 30))
    buf = io.BytesIO()
    kw = {}
    if gps:
        exif = Image.Exif()
        exif[0x010F] = 'Testkamera'                       # Make
        exif[0x0132] = '2026:11:16 19:24:00'              # DateTime
        kw['exif'] = exif
    im.save(buf, fmt, **kw)
    return buf.getvalue()


def test_bilder_verkleinert_ohne_metadaten_und_begrenzt():
    import io
    from PIL import Image
    bilder, fehler = fb.bilder_aufbereiten([
        ('Screenshot 1.jpg', _bild(gps=True)),
        ('../../etc/passwd.png', _bild('PNG', (400, 900))),
    ])
    assert fehler is None and len(bilder) == 2
    name, daten, mime = bilder[0]
    assert (name, mime) == ('bild-1.jpg', 'image/jpeg')
    im = Image.open(io.BytesIO(daten))
    assert max(im.size) == fb.BILD_MAX_KANTE
    assert len(im.getexif()) == 0, 'Metadaten (EXIF, inkl. GPS) muessen weg'
    assert bilder[1][0] == 'bild-2.jpg'
    # Kein Bild (Text mit Bild-Endung), zu viele Bilder, zu gross
    _, f = fb.bilder_aufbereiten([('x.png', b'kein bild')])
    assert 'kein Bild' in f
    _, f = fb.bilder_aufbereiten([('a.jpg', _bild(groesse=(100, 100)))] * (fb.MAX_BILDER + 1))
    assert str(fb.MAX_BILDER) in f
    _, f = fb.bilder_aufbereiten([('a.jpg', b'\xff\xd8' + b'0' * (fb.MAX_BILD_BYTES + 1))])
    assert 'zu groß' in f
    assert fb.bilder_aufbereiten([]) == ([], None)


def test_bilder_im_block_und_datensatz():
    m = _meldung(bilder=[('bild-1.jpg', b'x' * 2048, 'image/jpeg')])
    assert 'bilder: 1 (bild-1.jpg)\n--- BESCHREIBUNG ---' in fb.mailtext(m)
    d = fb.datensatz(m)
    assert d['bilder'] == [{'name': 'bild-1.jpg', 'bytes': 2048}]
    assert 'bilder: 0' in fb.mailtext(_meldung())
