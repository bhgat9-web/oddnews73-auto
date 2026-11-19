# Story-specific AI visual upgrade (pending activation)

The owner selected AI illustrations instead of abstract template backgrounds.

## Design
- 1080 × 1350 Instagram JPEG.
- A large illustration based on the selected story, with a dark text zone.
- Short factual headline (up to nine words), one supporting sentence.
- Official logo composited from the existing asset; never redrawn by the model.
- Visible AI ILLUSTRATION label and source/date.
- Classification comes from the story's main subject. A manuscript mentioning comets belongs to history.

The current manuscript concept was generated separately with ChatGPT's image tool.
It is an art-direction reference, not a verified output from the Gemini integration.
The Gemini render uses the same hierarchy with deterministic typography and exact logo.
The published Instagram post remains unchanged.

## Activation and cost
The code is opt-in through repository variable ODDNEWS_AI_VISUALS=true.
Keep it unset until the owner approves image spending, Gemini billing is ready,
and one draft-only production preview has been inspected.

Uses the existing GEMINI_API_KEY secret. It is sent only in the API header.
Text briefing uses the existing GEMINI_MODEL. Image generation uses
gemini-3.1-flash-lite-image at 1K with one image request per run, no retries,
no paid model fallback and no external search tools.
Google lists $0.0336 per 1K output image, plus input/text tokens:
https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite-image

At three successful image generations daily, 90 images/30 days cost about $3.03
in image output fees, plus input/text fees. This is an estimate, NOT a hard dollar
cap. Manual runs and reruns also cost money. Check current rates before activation.

If generation fails after opt-in, preparation stops without creating a publishable
record or marking the story as seen. It does not silently use generic art.
Publishing and exact-image approval safeguards are unchanged.
No live image API call is included in offline tests.

## Validation before activating
1. Pass code safety tests.
2. Enable image mode only for a manually run draft preview with billing approved.
3. Inspect the generated JPEG, factual short headline, source and illustration label.
4. Activate the main workflow variable only after the preview is accepted.
