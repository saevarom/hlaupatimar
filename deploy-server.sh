#!/usr/bin/env bash

set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-saevar}"
DEPLOY_HOST="${DEPLOY_HOST:-46.224.209.26}"
DEPLOY_PORT="${DEPLOY_PORT:-2222}"
DEPLOY_KEY="${DEPLOY_KEY:-$HOME/.ssh/id_rsa}"
DEPLOY_DIR="${DEPLOY_DIR:-/home/saevar/apps/hlaupatimar}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
HEALTH_PATH="${HEALTH_PATH:-/api/races/scrape/supported-types}"
PUSH_FIRST="false"

usage() {
  cat <<'EOF'
Usage: ./deploy-server.sh [--push] [--help]

Options:
  --push   Push local branch to origin before deploying
  --help   Show this help

Environment overrides:
  DEPLOY_USER, DEPLOY_HOST, DEPLOY_PORT, DEPLOY_KEY
  DEPLOY_DIR, DEPLOY_BRANCH, HEALTH_PATH
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      PUSH_FIRST="true"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ ! -f "$DEPLOY_KEY" ]]; then
  echo "SSH key not found: $DEPLOY_KEY" >&2
  exit 1
fi

if [[ "$PUSH_FIRST" == "true" ]]; then
  echo "Pushing local branch to origin/$DEPLOY_BRANCH..."
  git push origin "$DEPLOY_BRANCH"
fi

echo "Deploying to ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PORT}..."

ssh -p "$DEPLOY_PORT" -i "$DEPLOY_KEY" "${DEPLOY_USER}@${DEPLOY_HOST}" \
  "DEPLOY_DIR='$DEPLOY_DIR' DEPLOY_BRANCH='$DEPLOY_BRANCH' HEALTH_PATH='$HEALTH_PATH' bash -se" <<'EOF'
set -euo pipefail

cd "$DEPLOY_DIR"

git fetch origin
git checkout "$DEPLOY_BRANCH"
git reset --hard "origin/$DEPLOY_BRANCH"

sudo docker compose --env-file .env.server -f docker-compose.server.yml up -d --build
sudo docker compose --env-file .env.server -f docker-compose.server.yml ps

curl -fsS "http://localhost${HEALTH_PATH}" >/tmp/hlaupatimar-health.json
echo "Health OK:"
head -c 300 /tmp/hlaupatimar-health.json
echo
EOF

echo "Deploy complete."
