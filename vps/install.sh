#!/usr/bin/env bash
# One-time bootstrap; does not start publishing.
set -euo pipefail
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo bash vps/install.sh" >&2
  exit 1
fi

APP_USER=oddnews73
APP_HOME=/srv/oddnews73
REPO=$APP_HOME/repo

echo "Setting up isolated ODD News 73 service (Scalper-B73 untouched)."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  git openssh-client python3-venv python3-pip ca-certificates nano

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$APP_HOME" \
    --shell /usr/sbin/nologin "$APP_USER"
fi
install -d -m 0700 -o "$APP_USER" -g "$APP_USER" "$APP_HOME"
install -d -m 0700 -o "$APP_USER" -g "$APP_USER" "$APP_HOME/.ssh"

# Pin GitHub's documented Ed25519 SSH host key.
HOSTS=$APP_HOME/.ssh/known_hosts
if ! grep -q 'github.com ssh-ed25519' "$HOSTS" 2>/dev/null; then
  printf '%s\n' 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl' >> "$HOSTS"
fi
chown "$APP_USER:$APP_USER" "$HOSTS"
chmod 0600 "$HOSTS"
ssh-keygen -lf "$HOSTS" -E sha256 |
  grep -Fq 'SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU' || {
    echo "GitHub host key fingerprint verification failed." >&2
    exit 1
  }

KEY=$APP_HOME/.ssh/id_ed25519
if [[ ! -f "$KEY" ]]; then
  runuser -u "$APP_USER" -- ssh-keygen -q -t ed25519 \
    -N '' -f "$KEY" -C 'oddnews73-vps-deploy'
fi

if [[ ! -d "$REPO/.git" ]]; then
  runuser -u "$APP_USER" -- git clone --depth 1 \
    https://github.com/bhgat9-web/oddnews73-auto.git "$REPO"
fi
runuser -u "$APP_USER" -- git -C "$REPO" remote set-url origin \
  'git@github.com:bhgat9-web/oddnews73-auto.git'
runuser -u "$APP_USER" -- git -C "$REPO" config user.name 'oddnews73-vps'
runuser -u "$APP_USER" -- git -C "$REPO" config user.email \
  'oddnews73-vps@users.noreply.github.com'

if [[ ! -e "$APP_HOME/.venv/bin/python" ]]; then
  runuser -u "$APP_USER" -- python3 -m venv "$APP_HOME/.venv"
fi
runuser -u "$APP_USER" -- "$APP_HOME/.venv/bin/pip" install \
  -q -r "$REPO/requirements.txt"

install -d -m 0750 -o root -g "$APP_USER" /etc/oddnews73
ENVFILE=/etc/oddnews73/secrets.env
if [[ ! -e "$ENVFILE" ]]; then
  cat > "$ENVFILE" <<'SETTINGS'
# Enter tokens on the VPS only; never commit this file.
GEMINI_API_KEY=
INSTAGRAM_ACCESS_TOKEN=
GEMINI_MODEL=gemini-3.5-flash-lite
LIVE_PUBLISH=true
AUTO_PUBLISH=true
STRICT_SCHEDULE=false
IG_API_HOST=graph.facebook.com
IG_API_VERSION=v27.0
SETTINGS
fi
chown root:"$APP_USER" "$ENVFILE"
chmod 0640 "$ENVFILE"

install -o root -g root -m 0644 \
  "$REPO/vps/oddnews73-publisher.service" \
  /etc/systemd/system/oddnews73-publisher.service
install -o root -g root -m 0644 \
  "$REPO/vps/oddnews73-publisher.timer" \
  /etc/systemd/system/oddnews73-publisher.timer
systemctl daemon-reload

echo
echo "STAGED ONLY: Instagram publishing is NOT enabled."
echo "1) Add this public deploy key to GitHub repo Settings > Deploy keys"
echo "   (Allow write access). This is a PUBLIC key:"
cat "$KEY.pub"
echo "   https://github.com/bhgat9-web/oddnews73-auto/settings/keys"
echo
echo "2) Store tokens only on the server: sudo nano /etc/oddnews73/secrets.env"
echo "3) Then activate: sudo bash /srv/oddnews73/repo/vps/activate.sh"
echo "   Activation disables GitHub scheduled publishing before enabling VPS timer."
