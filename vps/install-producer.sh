#!/usr/bin/env bash
# Isolated news and original-artwork producer. Does not touch Instagram timer.
set -euo pipefail

if [[ "$(id -u)" != 0 ]]; then
  echo "ERROR: This setup must run in the Hostinger root web console." >&2
  exit 1
fi

REPO=/srv/oddnews73/repo
ENVFILE=/etc/oddnews73/secrets.env
PRODUCER=oddnews73-producer
if [[ ! -f "$ENVFILE" ]] || [[ ! -f "$REPO/vps/producer.py" ]]; then
  echo "ERROR: Existing ODD News 73 deployment not found. Publisher untouched." >&2
  exit 1
fi

# Never reveal or source secrets; just confirm the required settings.
if ! grep -Eq '^GEMINI_API_KEY=.{12,}$' "$ENVFILE"; then
  echo "ERROR: GEMINI_API_KEY is missing from the existing private VPS env file." >&2
  exit 1
fi
if ! grep -Eq '^GEMINI_IMAGE_PAID_OK=yes$' "$ENVFILE"; then
  echo "ERROR: Paid image generation requires GEMINI_IMAGE_PAID_OK=yes." >&2
  exit 1
fi
if ! grep -Eq '^PRODUCER_ENABLED=true$' "$ENVFILE"; then
  echo "ERROR: Producer requires the explicit PRODUCER_ENABLED=true flag." >&2
  exit 1
fi

echo "VPS production authorization settings present (values hidden)."
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
echo "ENABLED: opt-in producer only. Existing publisher and trading services untouched."
