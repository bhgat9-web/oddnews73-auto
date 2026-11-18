# ODD News 73 — Instagram automation

Automatic publishing was enabled by the account owner on 18 November 2026 after the supervised first post succeeded on @oddnews73.

## Schedule and operation

The workflow runs daily at approximately **09:07, 14:07 and 20:07 Asia/Kolkata**. Each scheduled run selects one new source-linked story, generates a branded 1080×1350 JPEG and caption, deploys the image to GitHub Pages, verifies the exact image and Instagram account, and publishes one post. A slot may be skipped if no suitable recent story is available. GitHub may delay scheduled runs.

Push-triggered runs generate a fictional demo only. Manually running this workflow prepares a draft (or a demo if selected); it does not publish. The separate supervised first-post workflow still requires an exact human approval digest.

The official owner-supplied logo at `assets/odd-news-73-logo.png` is composited into every generated post. Automatic artwork currently uses the procedural branded template; the detailed archaeology artwork for the first post was custom-made separately.

## Publication safeguards

- Automatic authorization binds the exact caption, source and image bytes and is accepted only when the scheduled job explicitly sets `AUTO_PUBLISH=true`.
- Manual approval and automatic authorization are stored separately.
- Source allowlisting, link/headline duplicate checks and the posted history remain active.
- Fictional demos cannot publish.
- The public JPEG must match the local file and be 1080×1350.
- Every post verifies Instagram account ID `17841472407525134` and username `oddnews73`.
- An in-flight marker is committed before publication. Ambiguous results stop later automatic runs until reviewed; they are never blindly retried.
- Jobs that update post state share one concurrency group.

## Pause publishing

In GitHub Actions, open **ODD News 73 - Automatic Instagram Publishing**, choose the workflow menu and **Disable workflow**. This stops future scheduled runs. An already running job must be checked separately.

## Credentials and integration

The successful supervised post used the Meta Facebook Graph host `graph.facebook.com` with `instagram_content_publish`. Credentials are read only from GitHub Actions Secrets (`INSTAGRAM_ACCESS_TOKEN`, and optional `GEMINI_API_KEY` for caption generation). Never commit credentials or paste them in chat. The read-only verification workflow checks identity and publishing-capability access without creating media.

Pages must use GitHub Actions deployment, and the publishing workflow needs repository contents write permission to preserve its publication history.
