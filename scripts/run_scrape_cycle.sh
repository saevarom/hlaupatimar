#!/usr/bin/env bash

set -euo pipefail

APP_DIR="${APP_DIR:-/home/saevar/apps/hlaupatimar}"
MODE="${1:-full}"

DISCOVER_LIMIT="${DISCOVER_LIMIT:-200}"
EVENT_LIMIT="${EVENT_LIMIT:-120}"
RESULT_LIMIT="${RESULT_LIMIT:-300}"
DISCOVERY_TIMEOUT_SECONDS="${DISCOVERY_TIMEOUT_SECONDS:-900}"
PROCESS_EVENTS_TIMEOUT_SECONDS="${PROCESS_EVENTS_TIMEOUT_SECONDS:-1200}"
PROCESS_RESULTS_TIMEOUT_SECONDS="${PROCESS_RESULTS_TIMEOUT_SECONDS:-1800}"

cd "$APP_DIR"

COMPOSE=(sudo docker compose --env-file .env.server -f docker-compose.server.yml)

# Ensure web service is up before running management commands.
"${COMPOSE[@]}" up -d web >/dev/null

run_manage() {
  local timeout_seconds="$1"
  shift

  "${COMPOSE[@]}" exec -T web sh -c '
    timeout_seconds="$1"
    shift

    if command -v timeout >/dev/null 2>&1; then
      timeout --foreground "$timeout_seconds" python manage.py "$@"
    else
      python manage.py "$@"
    fi
  ' sh "$timeout_seconds" "$@"
}

run_discovery_timataka() {
  run_manage "$DISCOVERY_TIMEOUT_SECONDS" timataka_discover_events --limit "$DISCOVER_LIMIT"
}

run_discovery_corsa() {
  run_manage "$DISCOVERY_TIMEOUT_SECONDS" corsa_discover_events --limit "$DISCOVER_LIMIT"
}

run_processing() {
  run_manage "$PROCESS_EVENTS_TIMEOUT_SECONDS" timataka_process_events --limit "$EVENT_LIMIT"
  run_manage "$PROCESS_RESULTS_TIMEOUT_SECONDS" timataka_process_results --limit "$RESULT_LIMIT"
}

case "$MODE" in
  discovery-timataka)
    run_discovery_timataka
    ;;
  discovery-corsa)
    run_discovery_corsa
    ;;
  discovery)
    run_discovery_timataka
    run_discovery_corsa
    ;;
  process|processing)
    run_processing
    ;;
  full)
    run_discovery_timataka
    run_discovery_corsa
    run_processing
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    echo "Usage: $0 [discovery|discovery-timataka|discovery-corsa|process|full]" >&2
    exit 1
    ;;
esac
