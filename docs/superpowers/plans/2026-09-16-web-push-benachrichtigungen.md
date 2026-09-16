# Web-Push-Benachrichtigungen für die Azure-Streamlit-App

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development, task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Stand:** Entwurf 16.09.2026, von Toni beauftragt. Noch nicht begonnen.
Voraussetzung: die Änderungen vom 16.09. (Statistik-Umfeld, Vertretungs-Mail,
Wochenwahl) sind auf Azure getestet.

**Goal:** Nutzer, die die Website **zum Home-Bildschirm hinzugefügt** haben,
bekommen Push-Nachrichten aufs Handy — Buchungsbestätigung, Storno,
Erinnerung am Vortag, Admin-Hinweis; Admins zusätzlich „Neue Buchung" und
„Vertretung gesucht". Die Berechtigung wird **genau einmal** erfragt.

**Architecture:** Standard-Web-Push (Push API + Service Worker + VAPID).
Die Streamlit-App liefert über ihre statische Dateiablage `manifest.json` und
`sw.js` aus; ein kleines, per `components.html` eingebettetes Skript
registriert den Service Worker im Hauptfenster, holt nach einem Tipp des
Nutzers die Berechtigung und schickt die Push-Subscription zurück an die
App, die sie am Nutzer in Firestore ablegt (`users/{id}.push_subscriptions[]`).
Gesendet wird aus der Streamlit-App auf Azure mit `pywebpush` — an denselben
Stellen wie Mail und SMS, plus aus dem Erinnerungs-Job. Kein neuer Dienst,
kein Proxy, keine laufenden Kosten; Push geht direkt an die Push-Dienste der
Browser (Google, Apple, Mozilla).

**Tech Stack:** Streamlit 1.63 (`enableStaticServing`), `pywebpush`,
VAPID-Schlüsselpaar im Key Vault (`secrets.toml`), Firestore, Service Worker.

## Was man vorher wissen muss

1. **iPhone:** Web Push gibt es ab iOS 16.4 und **nur** in der zum
   Home-Bildschirm hinzugefügten Fassung (`display: standalone`). Im
   Safari-Tab kommt nichts an. Android/Chrome kann beides, auch ohne
   Installation. Die Annahme „Home-Bildschirm ist Standard" ist also für
   iOS Pflicht, für Android Komfort.
2. **Einmal fragen — das regelt der Browser.** Die Berechtigung gilt pro
   Website und wird pro Gerät genau einmal entschieden. *Gewährt* bleibt
   gewährt; *abgelehnt* fragt der Browser nie wieder (dann nur noch über die
   Site-Einstellungen). Die Frage darf **nur aus einem Tipp des Nutzers**
   heraus gestellt werden (Safari erzwingt es, Chrome straft es sonst ab) —
   also ein Banner „🔔 Benachrichtigungen aktivieren" mit Button, das
   verschwindet, sobald entschieden ist. Bei jedem späteren Besuch wird die
   bestehende Subscription still abgeglichen, ohne Dialog.
3. **Der Service Worker liegt nicht an der Wurzel.** Streamlit liefert
   statische Dateien nur unter `/app/static/`, sein Scope ist damit
   `/app/static/`. Für Push ist das **unerheblich**: `push`-Ereignisse und
   `showNotification` funktionieren unabhängig vom Scope. Was nicht geht:
   Offline-Caching der Seite — brauchen wir nicht.
4. **Streamlit-Seiten führen kein Skript aus** (`st.markdown` rendert nur
   HTML). Das Skript läuft in einem `components.html`-iframe und greift über
   `window.parent` auf das Hauptfenster zu — derselbe Ursprung, das ist
   erlaubt und in Streamlit-Projekten üblich. Ein Tipp im iframe zählt als
   Nutzeraktion auch fürs Hauptfenster.
5. **Manifest per Skript nachreichen.** Streamlits `index.html` hat kein
   `<link rel="manifest">` und keine `apple-mobile-web-app-*`-Metas. Beides
   wird vom Skript in den `<head>` des Hauptfensters eingefügt. Chrome
   akzeptiert das sicher; **für Safari ist das der erste Punkt, der
   gemessen werden muss** (Task 0) — Safari liest das Manifest beim Tippen
   auf „Zum Home-Bildschirm", also nach dem Einfügen; falls nicht, bleibt
   der Weg über `startup.sh`, das Streamlits `index.html` beim
   Containerstart um die zwei Zeilen ergänzt (das Verzeichnis liegt in
   `site-packages/streamlit/static`).
6. **Rückweg Subscription → Python.** Streamlit hat keinen Endpunkt für
   POSTs. Die Subscription (ein JSON mit `endpoint` und zwei Schlüsseln) geht
   über `Streamlit.setComponentValue()` aus dem iframe als Rückgabewert der
   Komponente an Python — dafür braucht es das kleine
   `streamlit-component-lib`-Handshake (drei Zeilen JS) statt
   `components.html`. Alternative ohne Handshake: `st.query_params` per
   `window.parent.location` setzen und `st.rerun` — hässlicher. Task 2
   entscheidet nach einem Versuch.

## Global Constraints

- Ein Dialog, aus einem Tipp heraus, nur solange `Notification.permission ===
  'default'`. Danach nie wieder ein Banner; bei *denied* ein stiller Hinweis
  im Profil unter Benachrichtigungen.
- Subscriptions idempotent (Schlüssel `endpoint`): gleiche Subscription
  zweimal → ein Eintrag. Ein Gerät = eine Subscription; Logout löscht sie
  **nicht** (Push soll auch ausgeloggt kommen — die Erinnerung ist der
  wichtigste Fall). Erst ein Abschalten im Profil entfernt sie.
- Schalter `push_notifications` am Nutzer (Profil → Benachrichtigungen),
  Standard **an**, sobald eine Subscription existiert.
- Push läuft **parallel** zu Mail/SMS; kein Ersatz. Später zu entscheiden,
  ob Push die SMS ablöst (Twilio-Kosten).
- Inhalte kurz, ohne Markdown, ohne IBAN/Telefonnummern.
- Antwort `404`/`410` vom Push-Dienst → Subscription serverseitig entfernen.
- Ein Push-Fehler darf nie eine Buchung scheitern lassen (`try/except`,
  Zeitlimit 10 s).
- Nur Azure. Streamlit Community Cloud spielt keine Rolle mehr.

---

### Task 0: Spike — geht das in Streamlit 1.63 auf Azure? (½ Tag, vor allem anderen)

**Files:**
- Create: `static/sw.js` (minimal: `push` → `showNotification`, `notificationclick` → `clients.openWindow`)
- Create: `static/manifest.json` (`name`, `short_name`, `start_url: "/"`, `display: "standalone"`, `background_color: "#E0F7FA"`, `theme_color: "#00C2D1"`, Icons 192/512 aus `assets/`)
- Modify: `.streamlit/config.toml` — `[server] enableStaticServing = true`
- Create: `scripts/push_spike.py` — Mini-Streamlit-Seite mit dem Einbettungsskript (SW registrieren, Manifest/Metas in den Parent-Head, Button → Berechtigung → Subscription als JSON anzeigen)
- Create: `scripts/push_send_test.py` — schickt mit `pywebpush` eine Testnachricht an eine eingefügte Subscription

- [ ] VAPID-Schlüsselpaar erzeugen (`vapid --gen` aus `py-vapid`), **nur lokal**, Werte später in Key Vault
- [ ] Android/Chrome: Subscription entsteht, Testnachricht kommt an — im Tab **und** als Home-Screen-App
- [ ] iPhone/Safari: Manifest per Skript reicht für „Zum Home-Bildschirm" mit Standalone? Wenn ja: Berechtigung und Testnachricht in der Home-Screen-Fassung. Wenn nein: `startup.sh`-Weg (Punkt 5 oben) und erneut messen
- [ ] Ergebnis in diesem Plan festhalten; **erst danach** Task 1 ff.

### Task 1: Versandlogik ohne Netz, mit Tests

**Files:**
- Create: `core_push.py` — `nachricht(kind, **felder)` → `{title, body, data}` je Ereignis; `empfaenger(nutzer)` (Schalter + Subscriptions); `subscription_hinzufuegen(liste, neue)`, `subscription_entfernen(liste, endpoint)` — alles rein
- Create: `test_core_push.py`
- Modify: `requirements.txt` — `pywebpush`

- [ ] Tests zuerst: Idempotenz, Filter nach Schalter, Texte je Ereignis ohne Markdown/IBAN
- [ ] Ereignisse: `booking`, `cancellation`, `reminder`, `note`, `admin_new_booking`, `admin_replacement`; `data` enthält `url` (Ziel beim Antippen: `/?seite=meine_termine` bzw. Kalender-Woche)

### Task 2: Einbettung in die App — Service Worker, Manifest, Berechtigung, Rückweg

**Files:**
- Create: `core_push_client.py` — baut das HTML/JS-Snippet (Public-VAPID-Key als Parameter), eine Funktion `push_banner(user)` die in `show_navigation()` oder oben in `meine_buchungen_page()` gerendert wird
- Modify: `streamlit_app.py` — `push_banner()` aufrufen; Rückgabewert (Subscription-JSON) → `ww_db.add_push_subscription(user_id, sub)`; Profil → Benachrichtigungen: Schalter `push_notifications`, Hinweis bei *denied*
- Modify: `WaWaDB` — `add_push_subscription`, `remove_push_subscription`, `set_push_pref`

- [ ] Rückweg nach Task-0-Erkenntnis umsetzen (Component-Handshake bevorzugt)
- [ ] Banner nur bei `permission === 'default'` und nur, wenn im Firestore noch keine Subscription dieses Geräts liegt
- [ ] Bei jedem Besuch: bestehende Subscription still abgleichen (`getSubscription()` → falls nicht in Firestore, nachtragen)
- [ ] Manuell auf Android und iPhone (Home-Screen) prüfen: Frage kommt genau einmal

### Task 3: Versand an den Ereignisstellen

**Files:**
- Modify: `streamlit_app.py` — Klasse `Push` neben `Mailer`/`TwilioSMS`: `send(user, kind, **felder)`; liest VAPID aus `st.secrets`; ruft `pywebpush.webpush` je Subscription, räumt `404/410` ab. Aufrufe direkt neben `mailer.send_*`: Bestätigung, Storno (auch Admin-Storno), Admin-Hinweis, Vertretung gesucht, neue Buchung — die beiden letzten an **alle aktiven Admins mit Subscription**, nicht an `ADMIN_EMAIL_RECEIVER`
- Modify: `scripts/send_reminders.py` — Erinnerung zusätzlich als Push
- Modify: `.streamlit/secrets.toml.example` — `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CLAIMS_EMAIL`
- Toni: die drei Werte in die base64-kodierte `secrets.toml` im Key Vault `kv-wawa-web-hzb` aufnehmen (siehe `docs/BETRIEB-AZURE.md`)

- [ ] Ende-zu-Ende auf Azure: Buchung → Push innerhalb weniger Sekunden, Antippen öffnet „Meine Termine"
- [ ] Vertretung ausschreiben → Push bei Admin
- [ ] Erinnerungs-Job manuell auslösen (`workflow_dispatch`) → Push am Vortag

### Task 4: Abschluss

- [ ] `docs/BETRIEB-AZURE.md`: Abschnitt „Push" (VAPID-Rotation, Fehlerbilder, iOS-Bedingung)
- [ ] Handbuch-Seite in der App: „So bekommst du Benachrichtigungen aufs Handy" (iPhone: Teilen → Zum Home-Bildschirm → App öffnen → Glocke tippen)
- [ ] `TODO.md` nachziehen; Entscheidung SMS parallel oder ablösen

## Bewusst nicht in diesem Plan

- Offline-Fähigkeit / Caching der Seite (Scope-Problem, kein Bedarf).
- Action-Buttons in der Nachricht („Übernehmen" direkt aus dem Banner) —
  möglich, zweiter Schritt.
- Die Expo-Mobile-App (`MobileAPP/`) — eigener Strang, unabhängig hiervon.
