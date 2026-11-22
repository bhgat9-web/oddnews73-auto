#!/usr/bin/env bash
# Explicit cutover: only activate after public deploy key and both API tokens are configured.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run with sudo" >&2; exit 1; }

REPO=/srv/oddnews73/repo
VENV=/srv/oddnews73/.venv
ENVFILE=/etc/oddnews73/secrets.env

# Confirm repository-scoped SSH key works, including write permission.
runuser -u oddnews73 -- git -C "$REPO" ls-remote --exit-code origin HEAD >/dev/null
runuser -u oddnews73 -- git -C "$REPO" push --dry-run origin HEAD:main >/dev/null

# Read the root-controlled service env file locally and do not display secrets.
set -a
# shellcheck disable=SC1090
source "$ENVFILE"
set +a
runuser -u oddnews73 -- "$VENV/bin/python" "$REPO/vps/runner.py" check
runuser -u oddnews73 -- bash -c \
  'cd /srv/oddnews73/repo && /srv/oddnews73/.venv/bin/python -m unittest discover -s tests -q'

runuser -u oddnews73 -- git -C "$REPO" pull --ff-only origin main

# Stop the GitHub publisher at the source before enabling this VPS timer.
runuser -u oddnews73 -- "$VENV/bin/python" - <<'PY'
from pathlib import Path
p = Path("/srv/oddnews73/repo/.github/workflows/oddnews73.yml")
content = p.read_text()
first = content.find("  schedule:\n")
last = content.find("  workflow_dispatch:\n", first)
if first >= 0:
    if last < 0:
        raise SystemExit("Cannot safely locate old GitHub schedule. Not activated.")
    content = (
        content[:first]
        + "  # Live scheduling moved to the isolated VPS timer.\n"
        + content[last:]
    )
    p.write_text(content)
PY
runuser -u oddnews73 -- git -C "$REPO" add .github/workflows/oddnews73.yml
if ! runuser -u oddnews73 -- git -C "$REPO" diff --cached --quiet; then
  runuser -u oddnews73 -- git -C "$REPO" commit \
    -m "Move live publishing schedule from GitHub to VPS"
  runuser -u oddnews73 -- git -C "$REPO" push origin HEAD:main
fi

systemctl enable --now oddnews73-publisher.timer
echo
echo "ACTIVATED: VPS has its own ODD News 73 timer."
echo "Legacy GitHub publishing cron has been removed."
systemctl list-timers oddnews73-publisher.timer --no-pager
echo "Logs: sudo journalctl -u oddnews73-publisher.service -n 80 --no-pager"
