# ODD News 73 — hands-free verified-news and image producer

**Status: GitHub code built and offline-tested. Not yet activated on the Hostinger VPS.**
The existing Instagram publishing service continues independently. The producer
is strictly opt-in and never calls Instagram or modifies the trading system.

## Workflow

Scheduled checks at **05:30, 12:00 and 18:00 IST** find recent unusual stories
from the publisher's existing allowlisted RSS feeds (NASA, Smithsonian, Phys.org
and Live Science). Each article must be retrieved; RSS headlines alone are not
used to write posts.

Gemini's existing free-tier **text** API drafts captions using two
verbatim evidence excerpts from the retrieved article. Unsourced material
is rejected.

The default `PRODUCER_IMAGE_MODE=free_original` draws original, thematic
illustrations locally using Pillow on your Hostinger VPS. It uses **no**
paid image provider, GPU, external image key, borrowed copyrighted photo
or image API. Artwork includes explicit subjects (submarine, fish, snake,
fossil flower, burial, fossils, planets, forest) rather than unrelated
eye/orbit motifs. Stories outside the supported illustrated subjects are
skipped. This is programmed vector-style art, not photorealistic AI imagery;
visual quality must be assessed with examples before going unattended.

The original ODD NEWS 73 logo and concise source-specific headline are
applied to each **1080 × 1350 JPEG**. The file and attributed caption
are validated with the publisher's exact content and image digests.

The producer holds the existing repository write lock and adds up to
three bundles per production run, aiming for nine unused, recent posts.
The operational publisher retains duplicate protection and exact JPEG
verification; **this new producer does not call Instagram**.

## No new image provider or image fees

No Cloudflare account is needed, and the original free artwork path
**never calls the paid Gemini image API**. It still requires a usable
`GEMINI_API_KEY` on the VPS for the **text** editor. Some Gemini text
models allow free API usage subject to current Google quotas. The presence
of a token and free-tier eligibility must be checked privately on the VPS.

Paid image generation is a separate, **disabled** option requiring both
`PRODUCER_IMAGE_MODE=paid_gemini` and `GEMINI_IMAGE_PAID_OK=yes`.
It is never switched on by the free-mode setup.

**Status:** Free artwork and producer code are present in GitHub and subject
to automated offline tests. The new producer systemd timer is not yet
activated or live-tested on Hostinger. The existing publisher continues.

## Safe deployment on Hostinger (only once account access is confirmed)

From your Hostinger root browser console, first confirm that your
existing private file `/etc/oddnews73/secrets.env` contains a Gemini
API key. Do not display or share the actual value. Preserve the Instagram
token and other settings. Add these two lines if absent:

~~~dotenv
PRODUCER_ENABLED=true
PRODUCER_IMAGE_MODE=free_original
~~~

`GEMINI_IMAGE_PAID_OK=yes` is **not needed** for the no-fee setting
and should not be added.

Then run the guarded one-command installer:

~~~bash
sudo -u oddnews73 git -C /srv/oddnews73/repo pull --ff-only origin main
sudo bash /srv/oddnews73/repo/vps/install-producer.sh
~~~

The installer verifies the private Gemini key exists without displaying
it, runs unit tests and installs only the separate producer timer.
It will stop safely if prerequisites fail. No paid image generation
and no manual Instagram posting are performed.

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
