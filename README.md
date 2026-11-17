# ODD News 73 — Free-first Instagram automation

> **Meta Unified Login:** This app now uses the Facebook Graph API and a system-user access token, stored only in GitHub Actions Secrets. No token or app secret should ever be shared in chat or committed to this public repository. Live publication remains OFF until the read-only account check succeeds and a real publishing test is supervised.

This repository hosts the automation for **@oddnews73**. It discovers unusual news from attributed sources, prepares original branded 4:5 JPEG graphics and draft captions, and uses the official Instagram API after the account is configured and explicitly enabled.

**Safety first:** Instagram publication is OFF unless the GitHub Actions variable `LIVE_PUBLISH` is explicitly set to `true`. Never commit access tokens or API keys into this public repository. Use GitHub Actions Secrets.

The pipeline is designed to run around 09:07, 14:07 and 20:07 Asia/Kolkata. Scheduled workflows may be delayed. It may skip a run if no suitable story is available.

## Setup checklist

1. Enable **Settings → Pages → Build and deployment → GitHub Actions**.
2. Set **Settings → Actions → General → Workflow permissions → Read and write permissions**.
3. Leave `LIVE_PUBLISH` unset (or set it to `false`) while testing.
4. Run the workflow manually in **Actions** using `demo_mode=true` to test the graphics without Instagram publishing.
5. Verify the image appears on your GitHub Pages site, and review a real-source draft before enabling any live publication.
6. In Meta's Instagram API (Unified Login), add @oddnews73 as an Instagram Tester and generate an access token. In GitHub, open Settings → Secrets and variables → Actions → New repository secret, name it `INSTAGRAM_ACCESS_TOKEN`, and paste the token **only there**. Then run **ODD News 73 - Verify Instagram Connection** from Actions. No publishing occurs in this verification workflow.

The original poster ZIP is available in the ChatGPT conversation. **Do not enable publishing before completing the live integration test and validating the target account @oddnews73.**


## Current account-check stage

- Professional Instagram account: `@oddnews73` (confirmed in the Meta app screenshot).
- Expected Instagram account ID: `17841472407525134` (public identifier, not a credential).
- The read-only GitHub Actions workflow **ODD News 73 - Verify Instagram Connection** checks both account ID and username through Meta's Facebook Graph API. It cannot publish.
- Never add access tokens to the repository or send them in screenshots or chat.
- Leave GitHub Actions variable `LIVE_PUBLISH` empty / `false` until the complete live workflow has been independently verified.
