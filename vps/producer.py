#!/usr/bin/env python3
"""ODD News 73: isolated, opt-in, source-linked artwork queue replenisher.

No Instagram API calls. No publishing, no generic filler graphics.
Reuses the existing GEMINI_API_KEY (separate image generation API billing may apply).
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "src"))
import oddnews73 as pub

LOCK = BASE.parent / "publisher.lock"
MODEL_TEXT = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.1-flash-lite")
MODEL_IMAGE = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-lite-image")
TEXT_MODELS = {"gemini-3.1-flash-lite", "gemini-3.5-flash-lite"}
IMAGE_MODELS = {"gemini-3.1-flash-lite-image", "gemini-3.1-flash-image"}
QUEUE = BASE / "queue" / "posts.json"
IMAGES = BASE / "queue" / "images"
MAX_QUEUE = 9
MAX_NEW = 3
MAX_CANDIDATES = 8
UA = pub.UA
BUDGET_FILE = BASE.parent / "producer_budget.json"


def gemini(model: str, payload: dict, timeout: int = 90) -> dict:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing from the dedicated service environment")
    if model not in TEXT_MODELS | IMAGE_MODELS:
        raise ValueError("Unsupported Gemini model; no API call attempted")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(
        url,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if r.status_code in (401, 403):
        raise RuntimeError("Gemini API credential or model access denied")
    if r.status_code == 429:
        raise RuntimeError("Gemini model quota exhausted; no fallback paid provider")
    if r.status_code == 404:
        raise RuntimeError(f"Gemini model unavailable: {model}")
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or not data.get("candidates"):
        raise ValueError("Gemini returned no approved candidate (possible safety refusal)")
    return data


def gemini_text(instruction: str, user: str) -> str:
    data = gemini(MODEL_TEXT, {
        "contents": [{"role": "user", "parts": [
            {"text": instruction + "\n\n" + user}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1400,
            "responseMimeType": "application/json",
        },
    }, timeout=90)
    return "".join(
        part.get("text", "") for part in
        data["candidates"][0].get("content", {}).get("parts", [])
    ).strip()


def reserve_image_budget():
    """Conservative global daily cap, persisted on VPS *before* paid image calls."""
    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    # Only project-specific spend tracking. No secrets are recorded.
    try:
        budget = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        budget = {}
    if budget.get("utc_date") != date:
        budget = {"utc_date": date, "image_calls": 0}
    maximum = max(0, min(3, int(os.getenv("PRODUCER_DAILY_IMAGE_LIMIT", "3"))))
    if budget["image_calls"] >= maximum:
        raise RuntimeError("Daily Gemini image-generation cap reached")
    budget["image_calls"] += 1
    BUDGET_FILE.write_text(json.dumps(budget) + "\n", encoding="utf-8")


def gemini_image(visual: str) -> bytes:
    reserve_image_budget()
    data = gemini(MODEL_IMAGE, {
        "contents": [{"role": "user", "parts": [{"text": visual}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "4:5", "imageSize": "1K"},
        },
    }, timeout=120)
    for part in data["candidates"][0].get("content", {}).get("parts", []):
        image = part.get("inlineData") or part.get("inline_data") or {}
        encoded = image.get("data")
        if isinstance(encoded, str) and image.get("mimeType", image.get("mime_type", "")).startswith("image/"):
            raw = base64.b64decode(encoded, validate=True)
            if 0 < len(raw) < 8_000_000:
                return raw
            raise ValueError("Image generated but exceeds approved size")
    raise ValueError("Gemini produced no image; artwork was not queued")


def canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def evidence_supported(evidence: dict, source: str) -> bool:
    quotes = evidence.get("evidence_quotes")
    if not isinstance(quotes, list) or len(quotes) < 2:
        return False
    body = canonical(source)
    return all(isinstance(q, str) and 24 <= len(q) <= 250
               and canonical(q) in body for q in quotes[:2])


def article_text(url: str) -> str:
    if not pub.allowed(url):
        raise ValueError("Untrusted article URL")
    r = requests.get(url, timeout=24, headers={"User-Agent": UA})
    r.raise_for_status()
    if len(r.content) > 2_500_000:
        raise ValueError("Article too large")
    soup = BeautifulSoup(r.content, "html.parser")
    for node in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        node.decompose()
    el = soup.find("article") or soup.find("main")
    if el is None:
        raise ValueError("No article body: reject rather than fabricate")
    text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
    if not 450 <= len(text) <= 110_000:
        raise ValueError("Insufficient or excessive article text")
    return text[:12000]


def candidate_stories(state: dict, queued: list) -> list:
    seen = set(state.get("seen_links", []))
    seen.update(x.get("source_url", "") for x in state.get("entries", []))
    seen.update(x.get("source_url", "") for x in queued)
    now = datetime.now(timezone.utc)
    candidates = []
    for source_name, feed in pub.FEEDS:
        try:
            r = requests.get(feed, timeout=18, headers={"User-Agent": UA})
            r.raise_for_status()
            if len(r.content) > 3_000_000:
                continue
            for item in pub.rss_items(r.content):
                url = item["link"].split("#")[0]
                if not pub.allowed(url) or url in seen:
                    continue
                title = pub.clean(item["title"])
                descr = pub.clean(item["excerpt"])
                if not title or not descr:
                    continue
                age = now - datetime.fromisoformat(item["published_utc"])
                if not timedelta(0) <= age <= timedelta(days=3):
                    continue
                lower = (title + " " + descr).lower()
                if any(word in lower for word in pub.EXCLUDE + pub.ORDINARY_NEWS):
                    continue
                if not any(word in title.lower() for word in pub.WEIRD):
                    continue
                candidates.append({"source": source_name, "title": title,
                                   "source_url": url, "excerpt": descr,
                                   "published_utc": item["published_utc"],
                                   "age_seconds": age.total_seconds()})
                seen.add(url)
        except (requests.RequestException, ValueError, pub.ET.ParseError):
            continue
    candidates.sort(key=lambda x: x["age_seconds"])
    return candidates[:MAX_CANDIDATES]


def write_story(story: dict, evidence_text: str) -> dict:
    instruction = (
        "You are a cautious editor for an Instagram odd-news account. "
        "Using ONLY the provided article text, produce a JSON object with keys: "
        "headline (max 52 chars), caption (90-125 English words), "
        "image_prompt (40-95 words describing an ORIGINAL story-specific illustration, "
        "no typography, no logos, no watermark), evidence_quotes (two DISTINCT, "
        "verbatim, contiguous 24-250 character excerpts copied exactly from article). "
        "Do not insert statements that the article does not support. Clearly state "
        "uncertainties, especially species identification, dates, and scientific hypotheses. "
        "No politics, crime, accusations, medical claims, paranormal claims, or invented events. "
        "No promotional hype. If article lacks two substantive facts, return {}. "
        "Return JSON only, without markdown."
    )
    user = "Headline: " + story["title"] + "\nArticle text: " + evidence_text[:9000]
    response = gemini_text(instruction, user)
    if response.startswith("```"):
        response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        obj = json.loads(response)
    except (ValueError, TypeError) as exc:
        raise ValueError("AI editor did not return valid JSON") from exc
    if not isinstance(obj, dict) or not evidence_supported(obj, evidence_text):
        raise ValueError("AI-generated claims lack two verbatim source citations")
    headline = str(obj.get("headline", "")).strip()
    caption = str(obj.get("caption", "")).strip()
    prompt = str(obj.get("image_prompt", "")).strip()
    if not 10 <= len(headline) <= 52 or not 85 <= len(caption.split()) <= 140:
        raise ValueError("Caption/headline outside editorial length limits")
    if not 30 <= len(prompt.split()) <= 120:
        raise ValueError("Missing story-specific visual description")
    if re.search(r"https?://|#\w+", caption):
        raise ValueError("AI editor included a link or hash tag")
    return {"headline": headline, "caption": caption, "image_prompt": prompt,
            "evidence_quotes": obj["evidence_quotes"][:2]}


def font(size: int, bold: bool = True):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ]
    for name in candidates:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def wrap_title(draw, title, typeface, max_width):
    words = title.split()
    rows = []
    line = ""
    for word in words:
        trial = (line + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=typeface)[2] > max_width and line:
            rows.append(line)
            line = word
        else:
            line = trial
    if line:
        rows.append(line)
    return rows[:3]


def poster(raw: bytes, headline: str) -> bytes:
    if len(raw) > 8_000_000:
        raise ValueError("Provider image too large")
    with Image.open(io.BytesIO(raw)) as im:
        if im.width < 400 or im.height < 400:
            raise ValueError("Provider image too small")
        art = ImageOps.fit(im.convert("RGB"), (1080, 1350),
                           method=Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", art.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for y in range(380):
        alpha = int(220 * (1 - y / 380))
        d.line((0, y, 1080, y), fill=(14, 16, 26, alpha))
    d.rectangle((0, 1276, 1080, 1350), fill=(14, 16, 26, 210))
    label = font(58)
    rows = wrap_title(d, headline, label, 950)
    for i, line in enumerate(rows):
        d.text((52, 140 + i * 70), line, font=label, fill=(255, 242, 205),
               stroke_width=2, stroke_fill=(4, 5, 10))
    d.text((52, 1303), "ODD NEWS 73  /  AI ILLUSTRATION",
           font=font(29), fill=(255, 236, 185))
    logo_path = BASE / "assets" / "odd-news-73-logo.png"
    with Image.open(logo_path) as logo:
        logo = logo.convert("RGBA")
        logo.thumbnail((105, 105), Image.Resampling.LANCZOS)
        overlay.paste(logo, (923, 24), logo)
    final = Image.alpha_composite(art.convert("RGBA"), overlay).convert("RGB")
    out = io.BytesIO()
    final.save(out, format="JPEG", quality=90, optimize=True)
    if len(out.getvalue()) >= 8_000_000:
        raise ValueError("Branded image too large")
    return out.getvalue()


def make_bundle(story: dict) -> tuple[dict, bytes]:
    body = article_text(story["source_url"])
    edit = write_story(story, body)
    visual = (
        "Vertical editorial illustration, richly colored but clean composition, "
        "photographic lighting, crisp metallic accents where appropriate, "
        "visually truthful to the article, no written characters, no label, "
        "no printed headline. " + edit["image_prompt"]
    )[:2048]
    raw = gemini_image(visual)
    jpeg = poster(raw, edit["headline"])
    url = story["source_url"]
    slug = hashlib.sha256(url.encode()).hexdigest()[:16]
    publication = datetime.fromisoformat(story["published_utc"])
    expires = publication + timedelta(days=7)
    caption = (
        edit["caption"] + "\n\nSource: " + story["source"] + " · " +
        publication.strftime("%d %b %Y") + "\n" + url +
        "\n\nVisual: AI-generated illustration, not a documentary photograph." +
        "\n\n#ODDNews73 #OddNews #Discoveries"
    )
    item = {"title": edit["headline"], "source_url": url,
            "source": story["source"], "published_utc": publication.isoformat(),
            "expires_utc": expires.isoformat(), "caption": caption, "slug": slug,
            "image_sha256": hashlib.sha256(jpeg).hexdigest(), "ready": True}
    item["bundle_digest"] = pub.queue_digest(item)
    return item, jpeg


def git(*args):
    subprocess.run(["git", "-C", str(BASE), *args], check=True, timeout=90)


def run():
    if os.getenv("PRODUCER_ENABLED", "").lower() != "true":
        raise RuntimeError("Producer disabled; no external AI calls made")
    if not os.getenv("GEMINI_API_KEY", "").strip():
        raise RuntimeError("Existing Gemini API key not configured on the VPS")
    LOCK.touch(exist_ok=True)
    with LOCK.open("r+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Publisher or another producer currently holds write lock. Skip.")
            return
        git("pull", "--ff-only", "origin", "main")
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
        state = pub.load()
        now = datetime.now(timezone.utc)
        valid_queue = [
            x for x in data.get("posts", [])
            if x.get("ready") and datetime.fromisoformat(x["expires_utc"]) > now
            and x.get("source_url") not in state.get("seen_links", [])
            and not any(e.get("slug") == x.get("slug") and e.get("status") != "draft"
                        for e in state["entries"])
        ]
        need = min(MAX_NEW, max(0, MAX_QUEUE - len(valid_queue)))
        if need == 0:
            print("Queue already stocked.")
            return
        staged = []
        for story in candidate_stories(state, data.get("posts", [])):
            if len(staged) >= need:
                break
            try:
                item, jpg = make_bundle(story)
                if len(item["caption"]) > 2200:
                    raise ValueError("Instagram caption too long")
                staged.append((item, jpg))
                print("Prepared original, source-linked artwork:", item["slug"],
                      item["title"])
            except (requests.RequestException, ValueError, KeyError, TypeError,
                    OSError) as exc:
                print("Editorial reject:", story["source_url"], str(exc)[:140])
                continue
            except RuntimeError as exc:
                # An account, quota or provider problem should not destroy
                # already prepared successful stories.
                print("AI service stopped:", str(exc)[:140])
                break
        if not staged:
            print("No verified sources passed today; queue unchanged.")
            return
        # Leave the repository unchanged until all expensive AI work finishes.
        IMAGES.mkdir(parents=True, exist_ok=True)
        for item, jpg in staged:
            (IMAGES / (item["slug"] + ".jpg")).write_bytes(jpg)
            data["posts"].append(item)
        QUEUE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
        # This queue is separately validated by the existing publication and CI
        # safeguards. Never touch Instagram tokens or publishing markers here.
        git("add", "--", "queue/posts.json", "queue/images")
        git("commit", "-m", f"ODD News 73: automatically replenish {len(staged)} stories")
        git("push", "origin", "HEAD:main")
        print("Queue replenished:", len(staged))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "run"))
    args = parser.parse_args()
    if args.command == "check":
        print("Producer installed. Enabled:", os.getenv("PRODUCER_ENABLED") == "true")
        print("Gemini API key present:", bool(os.getenv("GEMINI_API_KEY")))
        print("No AI generation, Instagram post, or Git update made.")
        return
    run()


if __name__ == "__main__":
    main()
