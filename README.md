# ODD News 73 — prepared-image publishing

Scheduled publishing uses images and captions prepared in ChatGPT. It makes
**no generative AI API calls**, so it does not require Gemini billing or an
image-generation API subscription.

## How it works
1. Ask ChatGPT to research a batch of unusual stories and make branded illustrations.
2. Review the finished images and source-linked captions; add the bundles to
   queue/posts.json and queue/images/<slug>.jpg through a pull request.
3. Scheduled runs at 09:07, 14:07 and 21:07 Asia/Kolkata take one ready, unexpired
   item. GitHub scheduling can be delayed.
4. An empty queue skips the slot. It never falls back to generic graphics or a paid API.

The initial batch contains three original AI-illustrated stories: Chihuahua/coyote
ancestry, missing geological layers, and the Rødhals Man's changing diet.
The already-published manuscript story is deliberately excluded.
These illustrations were generated with ChatGPT's built-in image tool, not Gemini.

## What “free” means here
- This public repository uses standard GitHub-hosted Linux runners, whose compute
  is free: https://docs.github.com/en/actions/concepts/billing-and-usage
- No external AI generation service is called by the scheduled or preview workflows.
- Creating/refilling batches here uses your existing ChatGPT plan and image limits;
  unlimited free image generation is not promised.
- Artifact storage and other GitHub quotas still apply. Preview artifacts are retained
  for one day; keep usage within the account's included allowances.
- This is automatic *publishing*, not unattended creation of unlimited fresh images.
  Refill the queue here when it runs out; at three posts per day this batch covers
  three posting slots.

## Queue contract
Each ready entry includes title, caption, source, source_url, published_utc,
expires_utc, the source-derived 16-character slug, image_sha256 and bundle_digest.
The bundle digest covers the content fields and image hash; it detects accidental
edits and is not a cryptographic signature from an independent reviewer.
The fixed image path is queue/images/<slug>.jpg: JPEG, RGB, 1080×1350, under 8 MB.
Use the official logo, label AI illustrations and link the source in the caption.
Keep expiry no later than seven days after source publication. Recheck facts before refill.
Prepared bundles expire; stale news is not silently posted.

## Safety and testing
A preview neither publishes nor consumes the item. Scheduled preparation stores
the exact-byte publication authorization and a pending record. Existing duplicate,
account, image checksum and committed in-flight safeguards remain active.
An ambiguous publication stops subsequent posting for review.
The queue never automatically retries a posted or failed item.

Run: python -m unittest discover -s tests -v
Preview: python src/oddnews73.py prepare-queued
The Preview Real Story workflow has no Instagram or Gemini token and cannot publish.
The old manual Gemini diagnostics remain separate and are not part of this free pipeline.
