# ODD News 73 — unattended news and original illustration production

**Status: built and safety-tested; NOT ENABLED.** Publishing is managed by
`oddnews73-publisher.timer`; this is a separate optional producer. Installing
it does not place an Instagram post. The Windows PC is not involved.

## Pipeline

- Three production runs per day, **05:30, 12:00 and 18:00 IST**.
- Read recent public RSS items from the existing allowlisted news sources.
- Choose unusual stories with recent source publication time; skip URLs
  already used in history or the artwork queue.
- Retrieve the underlying article (not only an RSS headline). If the article
  is blocked or lacks enough text, skip it.
- Call Cloudflare Workers AI `@cf/qwen/qwen3-30b-a3b-fp8` for new English
  caption, short visual headline, and TWO source quotations. Reject if those
  evidence excerpts do not appear verbatim in the extracted article.
- Call Cloudflare Workers AI `@cf/black-forest-labs/flux-1-schnell`
  for a story-specific original illustration.
- Locally add branding, an actual short headline, and an AI artwork label.
  Convert to the publisher's required **1080×1350 JPEG**.
- Sign each prepared bundle with the same SHA-256 image and editorial-content
  digest contract used by the existing publisher.
- Acquire the existing publish lock, and push at most 3 new posts per run to
  the same GitHub queue. No Meta token is used by this producer.
- Target up to 9 unused, unexpired prepared posts. If stories are uncertain,
  invalid or unavailable, skip instead of fabricating news. The independent
  GitHub health alert reports low inventory.

## Limitations

This is a new integration and must be tried with real provider credentials.
Offline tests validate the safety contract, not actual Cloudflare image quality,
API quota reliability, source completeness, or Instagram publication. One
reputable article plus two exact evidence excerpts is source-grounding, **not**
independent journalistic fact-checking. Good visuals cannot be guaranteed.
Cloudflare free allowances, per-model access, quotas, and prices can change.
If the free limit or source supply fails, the producer stops and the existing
publisher never substitutes generic filler.

## One-time Cloudflare account setup

From your phone, sign in at https://dash.cloudflare.com. Open **Workers AI**
and select **Use REST API** / **Create a Workers AI API Token**. Save the
Cloudflare **Account ID** and narrowly-scoped API token. See:
https://developers.cloudflare.com/workers-ai/get-started/rest-api/

**Never paste the token into ChatGPT, GitHub commits, or a screenshot.** On
your VPS (Hostinger web console), edit the *existing* secrets file:

~~~bash
sudo nano /etc/oddnews73/secrets.env
~~~

Add the following lines using your **actual private values** without quotes:

~~~dotenv
CLOUDFLARE_ACCOUNT_ID=YOUR_ACCOUNT_ID_HERE
CLOUDFLARE_API_TOKEN=YOUR_WORKERS_AI_TOKEN_HERE
PRODUCER_ENABLED=true
~~~

Keep existing Instagram settings intact. Confirm file permissions remain
root-owned and group-readable only by oddnews73.

## Install the producer on the VPS (DO NOT RUN UNTIL TOKEN READY)

From the root console, after adding Cloudflare settings:

~~~bash
sudo -u oddnews73 git -C /srv/oddnews73/repo pull --ff-only origin main
sudo -u oddnews73 /srv/oddnews73/.venv/bin/python -m pip install -r /srv/oddnews73/repo/requirements.txt
sudo install -m 0644 /srv/oddnews73/repo/vps/oddnews73-producer.service /etc/systemd/system/oddnews73-producer.service
sudo install -m 0644 /srv/oddnews73/repo/vps/oddnews73-producer.timer /etc/systemd/system/oddnews73-producer.timer
sudo systemctl daemon-reload
sudo systemctl enable --now oddnews73-producer.timer
sudo systemctl list-timers oddnews73-producer.timer --no-pager
~~~

This does not modify the trading software or existing publisher timer.
The new producer is **not enabled by code changes or by GitHub workflow runs**.

### Check health / pause production

~~~bash
sudo systemctl status oddnews73-producer.timer --no-pager
sudo journalctl -u oddnews73-producer.service -n 80 --no-pager
sudo systemctl disable --now oddnews73-producer.timer
~~~

Because the new provider's artwork quality is unverified, first conduct an
isolated supervised test and inspect one image before enabling recurring
generation. Do not publish synthetic illustrations as real photographs.
