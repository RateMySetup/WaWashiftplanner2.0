#!/usr/bin/env bash
#
# Startbefehl der Azure Web App.
#
# Zwei Schritte: erst die Zugangsdaten aus der App-Einstellung
# STREAMLIT_SECRETS_B64 (Verweis auf den Key Vault) als Datei ablegen, dann
# Streamlit starten. App Service gibt den Port ueber $PORT vor; wird darauf
# nicht gelauscht, gilt die App als nicht gestartet.
#
# server.enableCORS wird bewusst NICHT abgeschaltet: Streamlit uebersteuert
# den Wert nicht selbst und wuerde dann WebSocket-Verbindungen von jeder
# Herkunft annehmen. App Service braucht die Ausnahme nicht.
#
# server.fileWatcherType none: In Produktion aendert sich der Code nur per
# Deploy (mit Neustart). Ohne watchdog pollt Streamlit sonst alle 0,2 s die
# Quelldateien und prueft bei jedem Rerun alle geladenen Module.
set -euo pipefail

python core_secrets.py || echo "startup: weiter ohne Zugangsdaten - die App wird Fehler melden" >&2

exec python -m streamlit run streamlit_app.py \
    --server.port "${PORT:-8000}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.fileWatcherType none \
    --server.enableXsrfProtection true
