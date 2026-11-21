# ODD News 73 — prepared-image publishing

Scheduled publishing uses images and captions prepared in ChatGPT. It makes
**no generative AI API calls**, so it does not require Gemini billing or an
image-generation API subscription.

## How it works
1. Ask ChatGPT to research a batch of unusual stories and make branded illustrations.
2. Review the finished images and source-linked captions; add the bundles to
   queue/posts.json and queue/images/<slug>.jpg through a pull request.
3. Scheduled runs target 09:07, 14:07 and 21:07 Asia/Kolkata, with backup
   checks at 09:27/09:47, 14:27/14:47 and 21:27/21:47. A successful first post blocks the
   backup from posting a duplicate in the same local-time slot. GitHub
   scheduling is best-effort and none of the attempts is guaranteed to start.
4. An empty or invalid queue skips the slot and marks the scheduled workflow
   **failed** with an explanatory reason; it never substitutes generic content.
   A backup checking a slot already published is recorded as a safe success.

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

## Schedule limitations and diagnostics
- The workflow uses explicit UTC cron entries: `37,57 3,8,15 * * *` and
  `17 4,9,16 * * *`. These map to the India times above; India has no DST.
  Changing the cron refreshes the schedule definition without changing posting hours.
- Missing schedule events have no job logs. The 20 November morning attempts
  did not appear in the run history; the exact scheduler-side cause is unknown.
  UTC scheduling and an extra backup are recovery measures, not a delivery guarantee.
- Code Safety Tests checks the publishing workflow's enabled state through a
  read-only GitHub API request. A passing preview proves the pipeline works,
  but only a run labelled `schedule` proves the scheduler triggered it.
- A pending post from an older slot blocks scheduled preparation for review;
  it is never silently moved into a newer slot or retried automatically.
- GitHub Actions cannot guarantee minute-accurate scheduling. Each slot accepts
  starts up to three hours late: 09:07–12:07, 14:07–17:07 and 21:07–midnight IST
  (end times excluded). The current day's slot is used; missed slots are not replayed.
  The window is checked again before preflight and the final Instagram publish call.
  Duplicate protection still permits at most one successful post per slot.
- The 20 November runs started at 22:43 and 23:20 IST. Both failed the previous
  one-hour guard before reaching Instagram. The three-hour allowance admits those
  observed delays, but cannot make GitHub create a missing trigger.
- On 21 November the three unused sources were re-read and remained consistent
  with their captions. Their expiry was extended to 23 November 00:00 UTC, within
  seven days of every source publication. No image, caption or posting history changed.
- If the initial slot already posted successfully, a backup attempt logs
  `already_posted` and exits without consuming another queue item.
- When no eligible prepared post exists, the scheduled workflow is **red**,
  not green, and its logs name `queue_exhausted` or `queue_missing`.
- GitHub will not automatically refill the artwork queue; that requires a
  separate image and editorial production system. Keep enough posts ready.
