# ODD News 73 — Free-first Instagram automation

> **Meta Instagram Login:** This app uses Meta's Instagram API host (`graph.instagram.com`) and an Instagram user access token stored only in GitHub Actions Secrets. No token or app secret should ever be shared in chat or committed to this public repository. Recurring publication is intentionally absent until the first real publishing test is supervised and verified.

This repository hosts the automation for **@oddnews73**. It discovers unusual news from attributed sources, prepares original branded 4:5 JPEG graphics and draft captions, and uses the official Instagram API after the account is configured and explicitly enabled.

**Safety first:** The scheduled workflow can only prepare drafts and deploy their review images; it contains no publish job. The separate first-post workflow is manual-only and requires the exact draft slug, a digest bound to the caption/source/JPEG, and the literal confirmation `PUBLISH @oddnews73`. Never commit access tokens or API keys into this public repository. Use GitHub Actions Secrets.

The pipeline is designed to run around 09:07, 14:07 and 20:07 Asia/Kolkata. Scheduled workflows may be delayed. It may skip a run if no suitable story is available.

## Setup checklist

1. Enable **Settings → Pages → Build and deployment → GitHub Actions**.
2. Set **Settings → Actions → General → Workflow permissions → Read and write permissions**.
3. Do not add or enable any recurring publishing workflow while testing.
4. Run the draft workflow manually using `demo_mode=true` to test graphics without Instagram publishing.
5. Run it once with `demo_mode=false` to prepare a real-source draft. Review its exact JPEG, caption, source link, slug, and approval digest before any publish action.
6. In Meta's Instagram API with Instagram Login, add @oddnews73 as an Instagram Tester and generate an access token. In GitHub, open Settings → Secrets and variables → Actions → New repository secret, name it `INSTAGRAM_ACCESS_TOKEN`, and paste the token **only there**. Then run **ODD News 73 - Verify Instagram Connection** from Actions. Its identity and publishing-capability queries are read-only; it cannot create a media container.
7. Only after the owner approves the exact first post, manually run **ODD News 73 - Supervised One-Time First Post** with the approved slug, approval digest, and confirmation phrase. That workflow publishes at most that one approved draft.

The original poster ZIP is available in the ChatGPT conversation. **Do not enable publishing before completing the live integration test and validating the target account @oddnews73.**


## Current account-check stage

- Professional Instagram account: `@oddnews73` (confirmed in the Meta app screenshot).
- Expected Instagram account ID: `17841472407525134` (public identifier, not a credential).
- The read-only GitHub Actions workflow **ODD News 73 - Verify Instagram Connection** checks account ID, username, and publishing-capability access through Meta's documented Instagram Login host. It cannot create a media container or publish.
- Never add access tokens to the repository or send them in screenshots or chat.
- Recurring live posting remains structurally disabled until the supervised first-post result has been independently verified.

