#!/usr/bin/env bash
# Safe opt-in original-artwork producer installer. Never changes the Instagram publisher.
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "ERROR: Run from the Hostinger VPS root console." >&2
  exit 1
fi

REPO=/srv/oddnews73/repo
ENVFILE=/etc/oddnews73/secrets.env
PRODUCER=oddnews73-producer

if [[ ! -f "$ENVFILE" || ! -f "$REPO/vps/producer.py" ]]; then
  echo "ERROR: ODD News 73 deployment missing; existing publisher not touched." >&2
  exit 1
fi

# Exact key/value existence only. Do not source, display, or copy any secrets.
if ! grep -Eq '^GEMINI_API_KEY=.{12,}$' "$ENVFILE"; then
  echo "ERROR: Gemini key missing from the private VPS environment file." >&2
  exit 1
fi
if ! grep -Eq '^PRODUCER_ENABLED=true$' "$ENVFILE"; then
  echo "ERROR: Set PRODUCER_ENABLED=true in the private env file after approval." >&2
  exit 1
fi
if ! grep -Eq '^ODDNEWS73_VISUAL_QA_APPROVED=yes$' "$ENVFILE"; then
  echo "ERROR: The owner must explicitly approve the sample visuals before activation." >&2
  exit 1
fi

if grep -Eq '^PRODUCER_IMAGE_MODE=paid_gemini$' "$ENVFILE"; then
  if ! grep -Eq '^GEMINI_IMAGE_PAID_OK=yes$' "$ENVFILE"; then
    echo "ERROR: Paid image generation not authorized." >&2
    exit 1
  fi
fi

# Pull only after checking conditions, and run safety tests before enabling timer.
sudo -u oddnews73 git -C "$REPO" pull --ff-only origin main
sudo -u oddnews73 /srv/oddnews73/.venv/bin/python -m pip install -r "$REPO/requirements.txt"
sudo -u oddnews73 /srv/oddnews73/.venv/bin/python -m py_compile "$REPO/vps/producer.py"
sudo -u oddnews73 /srv/oddnews73/.venv/bin/python -m unittest discover -s "$REPO/tests" -v

install -m 0644 "$REPO/vps/$PRODUCER.service" "/etc/systemd/system/$PRODUCER.service"
install -m 0644 "$REPO/vps/$PRODUCER.timer" "/etc/systemd/system/$PRODUCER.timer"
systemctl daemon-reload
systemctl enable --now "$PRODUCER.timer"
systemctl is-active "$PRODUCER.timer"
systemctl list-timers "$PRODUCER.timer" --no-pager

echo "Production timer enabled; existing Instagram publisher and trading service unchanged."
