# ODD News 73 — hands-free verified-news and image producer

**Status: GitHub code built and offline-tested. Not yet activated on the Hostinger VPS.**
The existing Instagram publishing service continues independently. The producer
is strictly opt-in and never calls Instagram or modifies the trading system.

## Workflow

Scheduled checks at **05:30, 12:00 and 18:00 IST** find recent unusual stories
from the publisher's existing allowlisted RSS feeds (NASA, Smithsonian, Phys.org
and Live Science). Each article must be retrieved; RSS headlines alone are not
used to write posts.

Gemini text API summarizes with two verbatim evidence excerpts from the
retrieved source. Any story lacking those excerpts or other validation is
rejected. Gemini image API creates an *original conceptual illustration*
describing the article's subject. The existing logo and short headline are
applied locally, and the approved **1080 × 1350 JPEG** is packaged with its
source URL, caption, AI-image disclosure and cryptographic content digests.

The producer shares the existing publisher's repository write lock, and adds
at most three new story bundles per run, up to a reserve of nine prepared
articles. Publication remains entirely owned by the working VPS publisher,
which checks the artwork and Meta status and avoids duplicate publication.

## Reuse existing Gemini account instead of Cloudflare

No Cloudflare account/token is needed. The producer uses `GEMINI_API_KEY`,
the same key *name* already used in `src/oddnews73.py` for text generation.
This does **not** mean the key is available on the VPS: presence and permission
must be checked without revealing the value.

Default text model: `gemini-3.1-flash-lite`.
Default image model: `gemini-3.1-flash-lite-image`.
Image model may be switched to `gemini-3.1-flash-image`, but never silently.

**Image-generation API output is paid, even when Gemini text usage is free.**
Google's official current rate for Gemini 3.1 Flash Lite Image is approximately
US$0.0336 for a 1K image, plus input and any text output. Paid tier access and
budget authorization are required. Check latest official rates before
enabling: https://ai.google.dev/gemini-api/docs/pricing

A conservative VPS-side budget tracker in
`/srv/oddnews73/producer_budget.json` limits attempted paid image calls to
**three per UTC day** (not three *per timer run*) by default. It reserves the
attempt *before* calling Gemini, so unexpected errors still count against the
cap. Set `PRODUCER_DAILY_IMAGE_LIMIT=0` to disable paid calls entirely.
It is not a billing cap across other Google applications using the same key;
Google Cloud billing budgets and API quotas should also be configured.

**No automatic production has been enabled or charged through these code
changes.** A paid account and explicit permission to incur usage are required
before the first actual image-generation test.

## Safe deployment on Hostinger (only once account access is confirmed)

From the root browser console, add the Gemini credential *only if it is not
already present* to the existing **private** file
`/etc/oddnews73/secrets.env`. Do not paste it in chat, screenshots, or GitHub.
Retain the existing Instagram setting. Add:

~~~dotenv
GEMINI_API_KEY=YOUR_EXISTING_GEMINI_API_KEY
PRODUCER_ENABLED=true
PRODUCER_DAILY_IMAGE_LIMIT=3
~~~

Once the user has explicitly authorized paid image generation and the first
test image has been checked, deploy the separate timer:

~~~bash
sudo -u oddnews73 git -C /srv/oddnews73/repo pull --ff-only origin main
sudo -u oddnews73 /srv/oddnews73/.venv/bin/python -m pip install -r /srv/oddnews73/repo/requirements.txt
sudo install -m 0644 /srv/oddnews73/repo/vps/oddnews73-producer.service /etc/systemd/system/oddnews73-producer.service
sudo install -m 0644 /srv/oddnews73/repo/vps/oddnews73-producer.timer /etc/systemd/system/oddnews73-producer.timer
sudo systemctl daemon-reload
sudo systemctl enable --now oddnews73-producer.timer
sudo systemctl list-timers oddnews73-producer.timer --no-pager
~~~

This does not touch `oddnews73-publisher.timer` or the trading app. To
pause content production only:

~~~bash
sudo systemctl disable --now oddnews73-producer.timer
~~~

To view its logs without exposing private credentials:

~~~bash
sudo journalctl -u oddnews73-producer.service -n 80 --no-pager
~~~

## Limits and editorial caution

An AI-generated caption can contain inaccuracies even when evidence excerpts
match article text. Source attribution is not an independent scientific or
journalistic verification. If the original article is inaccessible, uncertain,
or inconsistent, the system should reject it, never fabricate details or
substitute an unrelated graphic. The provider may refuse images or exhaust
quotas; such failures do not justify unsafe double-posting.

The first image and exact source-grounding should be reviewed before switching
on unattended publishing. Nothing in this service grants ChatGPT direct SSH
access or reveals any secret in GitHub.
