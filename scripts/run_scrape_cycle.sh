#!/usr/bin/env bash

set -euo pipefail

APP_DIR="${APP_DIR:-/home/saevar/apps/hlaupatimar}"
MODE="${1:-full}"

DISCOVER_LIMIT="${DISCOVER_LIMIT:-200}"
EVENT_LIMIT="${EVENT_LIMIT:-120}"
RESULT_LIMIT="${RESULT_LIMIT:-300}"

cd "$APP_DIR"

COMPOSE=(sudo docker compose --env-file .env.server -f docker-compose.server.yml)

# Ensure web service is up before running management commands.
"${COMPOSE[@]}" up -d web >/dev/null

run_discovery() {
  "${COMPOSE[@]}" exec -T web python manage.py timataka_discover_events --limit "$DISCOVER_LIMIT"
  "${COMPOSE[@]}" exec -T web python manage.py corsa_discover_events --limit "$DISCOVER_LIMIT"
}

run_processing() {
  "${COMPOSE[@]}" exec -T web python manage.py timataka_process_events --limit "$EVENT_LIMIT"
  "${COMPOSE[@]}" exec -T web python manage.py timataka_process_results --limit "$RESULT_LIMIT"
}

case "$MODE" in
  discovery)
    run_discovery
    ;;
  process|processing)
    run_processing
    ;;
  full)
    run_discovery
    run_processing
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    echo "Usage: $0 [discovery|process|full]" >&2
    exit 1
    ;;
esac
