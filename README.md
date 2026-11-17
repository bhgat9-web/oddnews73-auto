# ODD News 73 — Free-first Instagram automation

This repository hosts the automation for **@oddnews73**. It discovers unusual news from attributed sources, prepares original branded 4:5 JPEG graphics and draft captions, and uses the official Instagram API after the account is configured and explicitly enabled.

**Safety first:** Instagram publication is OFF unless the GitHub Actions variable `LIVE_PUBLISH` is explicitly set to `true`. Never commit access tokens or API keys into this public repository. Use GitHub Actions Secrets.

The pipeline is designed to run around 09:07, 14:07 and 20:07 Asia/Kolkata. Scheduled workflows may be delayed. It may skip a run if no suitable story is available.

## Setup checklist

1. Enable **Settings → Pages → Build and deployment → GitHub Actions**.
2. Set **Settings → Actions → General → Workflow permissions → Read and write permissions**.
3. Leave `LIVE_PUBLISH` unset (or set it to `false`) while testing.
4. Run the workflow manually in **Actions** using `demo_mode=true` to test the graphics without Instagram publishing.
5. Verify the image appears on your GitHub Pages site, and review a real-source draft before enabling any live publication.
6. Later connect a professional Instagram account using the official Meta Instagram Login publishing permissions, and save access credentials only as GitHub Actions Secrets.

The original poster ZIP is available in the ChatGPT conversation. **Do not enable publishing before completing the live integration test and validating the target account @oddnews73.**
