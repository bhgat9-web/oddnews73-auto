# ODD News 73 — Hostinger VPS installation

The publisher uses a separate unprivileged Linux account named oddnews73 on the
existing Scalper-B73 server. No trading files, broker credentials or firewall
rules are changed. The server timezone remains Asia/Kolkata.

## Architecture

The systemd timer triggers at 09:07, 14:07, and 21:07 IST, with five
backup checks at +10, +20, +40, +60, and +80 minutes. The runner
prevents duplicates within each slot and records unsuccessful attempts
in GitHub state.json so an independent monitor can report problems.

The editorial system publishes only prepared, attributed, story-specific
1080x1350 artwork from the reviewed queue. If the queue runs out, the slot is
skipped and reported. The publisher never substitutes a plain or generic
graphic for the approved visual style.

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

## Step 4 — Store the Instagram token locally

On the VPS terminal:

~~~bash
sudo nano /etc/oddnews73/secrets.env
~~~

Enter your existing INSTAGRAM_ACCESS_TOKEN value. Do not paste this secret in
ChatGPT or commit it to GitHub. The VPS secrets file is root-owned, permission
0640. Image preparation uses the owner's Work automation and does not require a
generative-AI API key on the VPS.

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
- Prepared artwork depends on the owner's Work automation and available plan usage.
- GitHub Pages deployment or Instagram API errors may delay or prevent a post.
- An ambiguous Meta publication is never retried blindly.
- No new inbound public server port is opened.
- Initial deployment needs one-time authenticated SSH access and local secret entry.



## Apply a newer timer schedule to an already running VPS

Git pulls update `vps/runner.py` but **do not update installed systemd timer
units**. From Hostinger's root console, run:

~~~bash
sudo -u oddnews73 git -C /srv/oddnews73/repo pull --ff-only origin main
sudo install -m 0644 /srv/oddnews73/repo/vps/oddnews73-publisher.timer /etc/systemd/system/oddnews73-publisher.timer
sudo systemctl daemon-reload
sudo systemctl restart oddnews73-publisher.timer
sudo systemctl list-timers oddnews73-publisher.timer --no-pager
~~~

Only the ODD News 73 timer unit is refreshed. This does not restart the
trading project or trigger a manual Instagram post. If any command fails,
inspect its output before continuing.
