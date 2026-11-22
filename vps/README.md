# ODD News 73 — Hostinger VPS installation

The publisher uses a separate unprivileged Linux account named oddnews73 on the
existing Scalper-B73 server. No trading files, broker credentials or firewall
rules are changed. The server timezone remains Asia/Kolkata.

## Architecture

The systemd timer triggers at 09:07, 14:07, and 21:07 IST, with backup checks
10 and 20 minutes later. The runner prevents duplicates within each slot.

The existing editorial system uses prepared, attributed items first. When these
run out, it tries fresh RSS stories from established sources, Gemini captions,
and branded Pillow-generated 1080x1350 graphics. Weakly supported stories are
skipped rather than invented. Fallback graphics are abstract illustrations
and typography, not AI-generated photographic scenes.

The exact JPEG is committed to GitHub Pages and checked byte-for-byte before
Instagram publishing. An in-flight marker is stored before the Meta API POST.
GitHub Actions only hosts images; systemd on the VPS owns scheduling.

## Step 1 — SSH login in Windows PowerShell

Use the existing account and your existing SSH key. Never share private keys.

~~~powershell
ssh -i "PATH_TO_YOUR_EXISTING_PRIVATE_KEY" YOUR_SSH_USER@YOUR_VPS_HOST
~~~

## Step 2 — Install safely in VPS terminal

~~~bash
git clone https://github.com/bhgat9-web/oddnews73-auto.git /tmp/oddnews73-install
sudo bash /tmp/oddnews73-install/vps/install.sh
~~~

The installer creates the dedicated account, virtual environment, repository
deployment key, service unit and timer. Publishing remains DISABLED.

## Step 3 — GitHub Deploy Key

The installer prints a PUBLIC SSH key starting with ssh-ed25519.
Add ONLY this public key to the repository settings:

https://github.com/bhgat9-web/oddnews73-auto/settings/keys

Choose Add deploy key, title ODD News 73 VPS and Allow write access.
Never share or upload the private key. This key is scoped to this repository.

## Step 4 — Store two API secrets locally

On the VPS terminal:

~~~bash
sudo nano /etc/oddnews73/secrets.env
~~~

Enter your existing GEMINI_API_KEY and INSTAGRAM_ACCESS_TOKEN values. Do not
paste these secrets in ChatGPT or commit them to GitHub. Actions Secrets cannot
be read back in plaintext. The VPS secrets file is root-owned, permission 0640.

## Step 5 — Activate after the key and tokens are ready

~~~bash
sudo bash /srv/oddnews73/repo/vps/activate.sh
~~~

This verifies deploy-key permissions, checks configuration without revealing
secrets, runs unit tests, removes the OLD GitHub Actions scheduled trigger,
pushes the change, then enables the VPS timer. If prerequisites fail,
publishing remains off.

## View health

~~~bash
sudo systemctl status oddnews73-publisher.timer --no-pager
sudo systemctl list-timers oddnews73-publisher.timer --no-pager
sudo journalctl -u oddnews73-publisher.service -n 80 --no-pager
~~~

## Pause service

~~~bash
sudo systemctl disable --now oddnews73-publisher.timer
~~~

### Limitations

- The daily target is three posts when three credible stories are available.
- Gemini free tier can run out of quota; no unlimited free output promised.
- GitHub Pages deployment or Instagram API errors may delay or prevent a post.
- An ambiguous Meta publication is never retried blindly.
- No new inbound public server port is opened.
- Initial deployment needs one-time authenticated SSH access and local secret entry.
