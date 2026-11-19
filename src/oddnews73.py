"""ODD News 73: source-linked Instagram feed autopublisher.
Commands: prepare [--demo], review, approve, check-account, preflight, publish, status.
Never calls Meta's publishing API unless LIVE_PUBLISH=true.
"""
import argparse
import hashlib
import hmac
import html
import io
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state.json"
SITE = ROOT / "site"
RUN = ROOT / "run.json"
LOGO = ROOT / "assets" / "odd-news-73-logo.png"
EXPECTED_USER = "oddnews73"
API_VERSION = os.environ.get("IG_API_VERSION", "v27.0")
API_HOST = os.environ.get("IG_API_HOST", "graph.facebook.com").strip().lower()
ALLOWED_API_HOSTS = ("graph.instagram.com", "graph.facebook.com")
EXPECTED_ID = "17841472407525134"  # Verified from account listing in Meta app screenshot
NOW = lambda: datetime.now(timezone.utc)

FEEDS = [
    ("NASA", "https://www.nasa.gov/feed/"),
    ("Phys.org Earth", "https://phys.org/rss-feed/earth-news/"),
    ("Live Science", "https://www.livescience.com/feeds.xml"),
    ("Smithsonian Smart News", "https://www.smithsonianmag.com/rss/smart-news/"),
    ("Smithsonian Science", "https://www.smithsonianmag.com/rss/science-nature/"),
]
ALLOW = ("nasa.gov", "phys.org", "livescience.com", "smithsonianmag.com")
WEIRD = ("unusual", "bizarre", "strange", "mystery", "mysterious", "rare",
         "fossil", "ancient", "unexplained", "deep sea", "new species",
         "extinct", "prehistoric", "archaeolog", "odd", "unexpected",
         "meteorite", "comet", "hidden", "enigmatic", "unidentified", "unprecedented")
ORDINARY_NEWS = ("spacex", "starship", "rocket", "upper stage", "stock market",
                 "quarterly earnings", "new smartphone", "phone launch",
                 "launches satellite", "company reports", "reusable rocket")
EXCLUDE = ("political party", "election fraud", "miracle cure", "cancer cure",
           "celebrity scandal", "conspiracy theory", "alien spacecraft",
           "terrorist attack", "assault allegation", "ghost caught on camera",
           "murder suspect", "crash victims")
UA = "ODDNews73/1.2 (original graphics, cite source; contact Instagram @oddnews73)"


def clean(value):
    value = html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")))
    return re.sub(r"\s+", " ", value).strip()


def short(value, limit):
    value = clean(value)
    return value if len(value) <= limit else value[:limit-1].rsplit(" ", 1)[0] + "…"


def allowed(url):
    try:
        u = urlparse(url)
        return u.scheme == "https" and bool(u.hostname) and any(
            u.hostname == d or u.hostname.endswith("." + d) for d in ALLOW
        )
    except (ValueError, AttributeError):
        return False


def load():
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    state.setdefault("entries", [])
    state.setdefault("seen_links", [])
    return state


def save(st):
    STATE.write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rss_items(payload):
    root = ET.fromstring(payload)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for item in items[:45]:
        def field(*names):
            for name in names:
                el = item.find(name)
                if el is not None and el.text:
                    return el.text.strip()
            return ""
        link = field("link")
        if not link:
            el = item.find("{http://www.w3.org/2005/Atom}link")
            if el is not None:
                link = el.attrib.get("href", "")
        date = field("pubDate", "{http://purl.org/dc/elements/1.1/}date",
                     "{http://www.w3.org/2005/Atom}published",
                     "{http://www.w3.org/2005/Atom}updated")
        try:
            pub = datetime.fromisoformat(date.replace("Z", "+00:00")) if re.match(
                r"^\d{4}-\d{2}-\d{2}T", date
            ) else parsedate_to_datetime(date)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        yield {
            "title": field("title", "{http://www.w3.org/2005/Atom}title"),
            "excerpt": field("description", "summary", "{http://www.w3.org/2005/Atom}summary",
                             "{http://purl.org/rss/1.0/modules/content/}encoded"),
            "link": link, "published_utc": pub.astimezone(timezone.utc).isoformat()
        }


def normalized(title):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", clean(title).lower())).strip()


def duplicate(title, st):
    title = normalized(title)
    for entry in st["entries"][-120:]:
        old = normalized(entry.get("title"))
        if title and old and (
            title == old or (min(len(title), len(old)) >= 24
                             and SequenceMatcher(None, title, old).ratio() >= .88)
        ):
            return True
    return False


def choose(st):
    candidates = []
    feed_items = 0
    skipped_duplicate = 0
    skipped_topic = 0
    for source, feed in FEEDS:
        try:
            resp = requests.get(feed, timeout=15, headers={"User-Agent": UA})
            resp.raise_for_status()
            if len(resp.content) > 3_000_000:
                continue
            parsed = list(rss_items(resp.content))
            feed_items += len(parsed)
            print(f"Source {source}: {len(parsed)} timestamped feed items.")
            for item in parsed:
                link = item["link"].split("#")[0]
                title, excerpt = clean(item["title"]), clean(item["excerpt"])
                if not allowed(link) or not title or not excerpt:
                    continue
                if link in st["seen_links"] or duplicate(title, st):
                    skipped_duplicate += 1
                    continue
                age = (NOW() - datetime.fromisoformat(item["published_utc"])).total_seconds() / 3600
                if age < -2 or age > 168:
                    continue
                txt = (title + " " + excerpt).lower()
                title_lower = title.lower()
                if any(term in txt for term in EXCLUDE):
                    continue
                if any(term in title_lower for term in ORDINARY_NEWS):
                    continue
                # A general science/business item isn't inherently weird.
                # The unusual aspect must appear in the source headline itself.
                headline_matches = sum(term in title_lower for term in WEIRD)
                if headline_matches < 1:
                    skipped_topic += 1
                    continue
                matches = headline_matches * 2 + sum(term in excerpt.lower() for term in WEIRD)
                item.update(link=link, title=title, excerpt=short(excerpt, 500), source=source)
                item["score"] = matches * 5 + (30 if age <= 48 else 0) - age / 24
                candidates.append(item)
        except (requests.RequestException, ET.ParseError, ValueError) as exc:
            print(f"Feed unavailable: {source} ({type(exc).__name__})", file=sys.stderr)
    print(f"Eligible news candidates: {len(candidates)}; parsed {feed_items} feed items, "
          f"duplicates: {skipped_duplicate}, non-matching headlines: {skipped_topic}.")
    if not candidates:
        print("EDITORIAL SKIP: No recent non-duplicate, unusual source-linked story qualified.")
        return None
    fresh = [x for x in candidates if (NOW() - datetime.fromisoformat(x["published_utc"])).total_seconds() <= 172800]
    selected = max(fresh or candidates, key=lambda x: x["score"])
    print(f"Selected candidate: {selected['source']} — {short(selected['title'], 110)}")
    return selected


def caption(story, demo=False):
    if demo:
        return "DEMO ONLY — NOT A REAL NEWS REPORT."
    date = datetime.fromisoformat(story["published_utc"]).strftime("%d %b %Y")
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        print("EDITORIAL SKIP: GEMINI_API_KEY not configured; refusing generic automatic post.")
        return None

    instructions = (
        "You are the careful, vivid news editor of Instagram @oddnews73. "
        "Only use the provided publication headline, source, publication date and excerpt. "
        "Write 90-130 words of specific, interesting, accurate prose with a compelling "
        "first sentence, two concrete details supported by the provided source text, and "
        "a genuinely relevant closing question. Clearly attribute reports and uncertainty; "
        "never present unconfirmed claims as verified. If the excerpt lacks two substantive "
        "facts, return INSUFFICIENT_SOURCE_DETAILS instead of inventing any. "
        "Avoid hype, generic filler, sensationalized unsupported claims, broad claims or "
        "repetition of the entire source title. Do not add hashtags, URLs or a separate "
        "source line: the publishing software attaches those accurately. "
        "Output just the caption text.\n"
        f"Source: {story['source']}\nTitle: {story['title']}\n"
        f"Publication date: {date}\nExcerpt: {story['excerpt']}"
    )

    preferred = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    free_candidates = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
    models = [preferred] if preferred in free_candidates else []
    models.extend(m for m in free_candidates if m not in models)
    for model in models:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": instructions}]}],
                      "generationConfig": {"temperature": .30, "maxOutputTokens": 1400}},
                timeout=30
            )
            if r.status_code == 404:
                print(f"EDITORIAL: {model} not available; trying alternative model.", file=sys.stderr)
                continue
            r.raise_for_status()
            result = "".join(
                p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"]
            ).strip()
            if result.upper().startswith("INSUFFICIENT_SOURCE_DETAILS"):
                print("EDITORIAL SKIP: News excerpt lacked enough concrete, verifiable facts.")
                return None
            if story["link"] in result:
                result = result.replace(story["link"], "").strip()
            # Keep model prose but attach source metadata and stable hashtags in code,
            # rather than requiring the language model to reproduce the exact URL.
            result = re.sub(r"#(?:ODDNews73|WeirdNews|StrangeWorld|Discoveries)\b",
                            "", result, flags=re.I).strip()
            if (240 <= len(result) <= 1750
                    and len(result.split()) >= 50
                    and "an unusual report from" not in result.lower()
                    and "has caught our attention" not in result.lower()):
                print(f"Gemini editorial caption accepted using {model}.")
                return (result + f"\n\nSource: {story['source']} · {date}\n"
                        + story["link"]
                        + "\n\n#ODDNews73 #WeirdNews #StrangeWorld #Discoveries")
            print(f"EDITORIAL SKIP: AI result failed prose checks "
                  f"(characters={len(result)}, words={len(result.split())}).",
                  file=sys.stderr)
            return None
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            print(f"EDITORIAL SKIP: Gemini {model} returned HTTP {status}.", file=sys.stderr)
            return None
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            print(f"EDITORIAL SKIP: Gemini {model} failed to provide usable text.", file=sys.stderr)
            return None
    print("EDITORIAL SKIP: Neither free-tier model was available.", file=sys.stderr)
    return None


def font(size, bold=False):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ):
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap(draw, title, max_width=940, max_lines=4):
    for size in range(70, 35, -4):
        f = font(size, True)
        lines, current = [], ""
        for word in short(title.upper(), 140).split():
            candidate = (current + " " + word).strip()
            if draw.textbbox((0, 0), candidate, font=f)[2] < max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if len(lines) <= max_lines:
            return lines, f
    return lines[:max_lines], f


def add_official_logo(img, xy=(45, 35), size=190):
    """Place the owner-supplied ODD News 73 logo without generative alteration."""
    if not LOGO.is_file():
        raise RuntimeError("Missing official ODD News 73 logo asset")
    with Image.open(LOGO) as source:
        logo = ImageOps.fit(source.convert("RGB"), (size, size),
                            method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, size - 2, size - 2), fill=255)
    img.paste(logo, xy, mask)


def graphic(story, path, demo=False):
    w, h = 1080, 1350
    title = story["title"]
    kind = "ODD DISCOVERIES"
    accent = (84, 220, 255)
    txt = title.lower()
    if any(t in txt for t in ("space", "meteor", "moon", "planet", "galaxy", "comet")):
        kind, accent = "SPACE ODDITIES", (106, 218, 255)
    elif any(t in txt for t in ("ancient", "archaeolog", "fossil", "tomb", "prehistoric")):
        kind, accent = "LOST HISTORY", (255, 185, 75)
    elif any(t in txt for t in ("animal", "bird", "whale", "fish", "species")):
        kind, accent = "STRANGE NATURE", (84, 235, 165)
    img = Image.new("RGB", (w, h), (6, 17, 32))
    d = ImageDraw.Draw(img)
    for y in range(h):
        q = y / h
        d.line((0, y, w, y), fill=(int(5+7*q), int(16+12*q), int(32+14*q)))
    random.seed(int(hashlib.sha256(title.encode()).hexdigest()[:8], 16))
    for _ in range(115):
        x, y = random.randrange(60, 1015), random.randrange(155, 770)
        d.ellipse((x, y, x+3, y+3), fill=(30, 70, 98))
    # Original abstract orbital/eye symbol, not purported photographic evidence
    d.ellipse((610, 185, 1190, 765), outline=accent, width=7)
    d.ellipse((705, 275, 1095, 665), outline=(45, 112, 151), width=4)
    d.arc((730, 320, 1070, 610), 15, 180, fill=accent, width=7)
    d.ellipse((790, 405, 987, 538), outline=accent, width=8)
    d.ellipse((870, 433, 917, 480), fill=accent)
    brand = (255, 132, 0)
    d.rounded_rectangle((255, 52, 1015, 145), 18, fill=(8, 21, 36), outline=brand, width=3)
    d.text((285, 59), "ODD NEWS 73", font=font(37, True), fill=(250, 252, 255))
    d.text((780, 102), "@oddnews73", font=font(22, True), fill=brand)
    add_official_logo(img)
    d.rounded_rectangle((66, 732, 550, 795), 14, fill=accent)
    d.text((92, 742), kind, font=font(28, True), fill=(5, 17, 30))
    lines, f = wrap(d, title)
    y = 832
    for line in lines:
        d.text((68, y), line, font=f, fill="white")
        y += f.size + 12
    bar = max(1140, y + 12)
    d.line((66, bar, 1013, bar), fill=accent, width=3)
    d.text((68, bar+22), short(story["source"], 37).upper(), font=font(25, True), fill=accent)
    date = datetime.fromisoformat(story["published_utc"]).strftime("%d %b %Y")
    d.text((68, bar+68), date.upper(), font=font(23), fill=(196, 215, 231))
    d.text((68, 1290), "SOURCE-LINKED REPORT • ORIGINAL GRAPHIC",
           font=font(19), fill=(169, 189, 207))
    if demo:
        d.rounded_rectangle((170, 648, 920, 714), 10, fill=(255, 212, 67))
        d.text((197, 662), "DEMO ONLY — NOT A NEWS REPORT",
               font=font(27, True), fill=(15, 15, 15))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=90, optimize=True)


def sources_index(st):
    lines = []
    for rec in reversed(st["entries"][-60:]):
        if rec.get("demo") or not allowed(rec.get("source_url", "")):
            continue
        href = html.escape(rec["source_url"], quote=True)
        title = html.escape(rec["title"])
        source = html.escape(rec["source"])
        lines.append(f'<li><a href="{href}" rel="noopener noreferrer" target="_blank">{title}</a> — {source}</li>')
    markup = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>ODD News 73 — Original Sources</title>'
        '<style>body{background:#081725;color:#f9fbff;max-width:760px;'
        'margin:3rem auto;padding:1rem;font:18px/1.6 system-ui}a{color:#ffd25b}'
        'h1{color:#62e5f8}li{margin:1rem 0}</style>'
        '<h1>ODD NEWS 73</h1><p>Original sources behind our unusual news graphics. '
        'Headlines are source-linked, not proof of extraordinary claims.</p><ul>'
    )
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(markup + "\n".join(lines) + "</ul></html>", encoding="utf-8")


def prepare(demo=False):
    RUN.unlink(missing_ok=True)
    st = load()
    if not demo and os.getenv("LIVE_PUBLISH", "false").lower() == "true":
        if any(x["status"] in ("in_flight", "needs_review") for x in st["entries"]):
            print("SAFE STOP: unresolved publication; check state.json.")
            return
        pending = next((x for x in st["entries"] if x["status"] == "pending"), None)
        if pending:
            RUN.write_text(json.dumps({"slug": pending["slug"]}), encoding="utf-8")
            print("Existing unattempted draft selected.")
            return
    selection_state = {**st, "seen_links": list(st["seen_links"])}
    generated_caption = None
    for attempt in range(1 if demo else 3):
        story = (
            {"title": "This is a design demonstration, not a real news event",
             "excerpt": "Fictional graphic", "source": "DEMO",
             "link": "https://example.org/demo", "published_utc": NOW().isoformat()}
            if demo else choose(selection_state)
        )
        if not story:
            print("No suitable recent attributed report; skipping slot.")
            return
        generated_caption = caption(story, demo)
        if generated_caption:
            break
        selection_state["seen_links"].append(story["link"])
        print(f"Candidate {attempt + 1} rejected by editorial checks; trying another within the three-story limit.")
    if not generated_caption:
        print("Skipping this scheduled slot: no valid source-linked AI caption.")
        return
    slug = hashlib.sha256(story["link"].encode()).hexdigest()[:16]
    status = "pending" if os.getenv("LIVE_PUBLISH", "false").lower() == "true" and not demo else "draft"
    rec = {"slug": slug, "title": story["title"], "status": status,
           "source": story["source"], "source_url": story["link"],
           "published_utc": story["published_utc"], "created_utc": NOW().isoformat(),
           "caption": generated_caption, "demo": bool(demo)}
    graphic(story, SITE / "posts" / (slug + ".jpg"), demo)
    if status == "pending" and os.getenv("AUTO_PUBLISH", "").lower() == "true":
        rec["automatic_digest"] = approval_digest(rec)
        rec["authorization"] = "owner-enabled recurring publishing"
    (SITE / "posts" / (slug + ".json")).write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    st["entries"] = (st["entries"] + [rec])[-300:]
    if not demo:
        st["seen_links"] = (st["seen_links"] + [story["link"]])[-1200:]
    save(st)
    sources_index(st)
    RUN.write_text(json.dumps({"slug": slug}), encoding="utf-8")
    print("Prepared:", rec["title"], status)


def current(st):
    if not RUN.is_file():
        raise RuntimeError("Missing run.json")
    slug = json.loads(RUN.read_text(encoding="utf-8"))["slug"]
    rec = next((x for x in reversed(st["entries"]) if x["slug"] == slug), None)
    if not rec:
        raise RuntimeError("Current record not found")
    return rec


def approval_digest(rec):
    """Bind a human approval to the exact caption, source, and JPEG bytes."""
    image = SITE / "posts" / (rec["slug"] + ".jpg")
    if not image.is_file():
        raise RuntimeError("Draft JPEG is missing")
    approved = {
        "slug": rec["slug"],
        "title": rec["title"],
        "caption": rec["caption"],
        "source": rec["source"],
        "source_url": rec["source_url"],
        "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
    }
    payload = json.dumps(approved, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def approve(slug, supplied_digest):
    """Stage one exact, previously reviewed draft for the supervised test."""
    live()
    if not re.fullmatch(r"[0-9a-f]{16}", slug or ""):
        raise RuntimeError("Invalid approved slug")
    st = load()
    rec = next((x for x in reversed(st["entries"]) if x.get("slug") == slug), None)
    if not rec or rec.get("demo") or rec.get("status") != "draft":
        raise RuntimeError("Only a non-demo draft may be approved")
    if not allowed(rec.get("source_url", "")):
        raise RuntimeError("Approved draft source is not allowlisted")
    expected = approval_digest(rec)
    if not hmac.compare_digest(expected, (supplied_digest or "").lower()):
        raise RuntimeError("SAFE STOP: approval does not match the exact caption and JPEG")
    rec["approved_digest"] = expected
    rec["approved_utc"] = NOW().isoformat()
    rec["status"] = "pending"
    save(st)
    RUN.write_text(json.dumps({"slug": slug}), encoding="utf-8")
    print("Exact reviewed draft approved for one supervised publish:", slug)


def review(slug=""):
    """Print the exact non-secret bundle that a human must review and approve."""
    st = load()
    rec = next((x for x in reversed(st["entries"])
                if not x.get("demo") and x.get("status") == "draft"
                and (not slug or x.get("slug") == slug)), None)
    if not rec:
        raise RuntimeError("No matching non-demo draft is ready for review")
    print(json.dumps({
        "slug": rec["slug"],
        "title": rec["title"],
        "caption": rec["caption"],
        "source": rec["source"],
        "source_url": rec["source_url"],
        "image_path": "site/posts/" + rec["slug"] + ".jpg",
        "approval_digest": approval_digest(rec),
    }, indent=2, ensure_ascii=False))


def live():
    if os.getenv("LIVE_PUBLISH", "").lower() != "true":
        raise RuntimeError("Publishing OFF: LIVE_PUBLISH is not true")


def token():
    """Token exists ONLY in GitHub Actions Secrets; never saved or echoed."""
    tok = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("Missing INSTAGRAM_ACCESS_TOKEN GitHub Actions secret")
    return tok


def ig(method, endpoint, tok, params=None):
    if API_HOST not in ALLOWED_API_HOSTS:
        raise RuntimeError("SAFE STOP: unsupported Meta API host")
    uri = f"https://{API_HOST}/{API_VERSION}/{endpoint}"
    args = {"access_token": tok, **(params or {})}
    r = (requests.get(uri, params=args, timeout=35) if method == "GET"
         else requests.post(uri, data=args, timeout=35))
    try:
        obj = r.json()
    except ValueError:
        obj = {}
    if not r.ok or "error" in obj:
        message = obj.get("error", {}).get("message", "Meta API request unsuccessful")
        raise RuntimeError("Meta API: " + str(message)[:180])
    return obj


def verify_account():
    """Read-only account check; never creates or publishes a media container."""
    tok = token()
    profile = ig("GET", EXPECTED_ID, tok, {"fields": "id,username"})
    if str(profile.get("id", "")) != EXPECTED_ID or str(profile.get("username", "")).lower() != EXPECTED_USER:
        raise RuntimeError("SAFE STOP: token is not authorised for @oddnews73")
    capacity = ig("GET", EXPECTED_ID + "/content_publishing_limit", tok)
    if not isinstance(capacity.get("data"), list):
        raise RuntimeError("SAFE STOP: publishing-capability check returned an unexpected response")
    print(f"Read-only Instagram identity check passed: @oddnews73 via {API_HOST}")
    print("Read-only publishing-capability check passed; no media container was created")
    return tok


def validate_publication_authorization(rec):
    """Keep manual approval and owner-enabled automation distinct."""
    automatic = os.getenv("AUTO_PUBLISH", "").lower() == "true"
    digest = rec.get("automatic_digest") if automatic else rec.get("approved_digest")
    if rec.get("demo") or not allowed(rec.get("source_url", "")):
        raise RuntimeError("SAFE STOP: invalid automatic/manual publication source")
    if not digest or not hmac.compare_digest(digest, approval_digest(rec)):
        raise RuntimeError("SAFE STOP: content differs from its publication authorization")


def preflight(site_url):
    live()
    st = load()
    rec = current(st)
    if rec.get("demo") or rec["status"] != "pending":
        raise RuntimeError("Only a pending, non-demo post may be published")
    validate_publication_authorization(rec)
    if not site_url.startswith("https://"):
        raise RuntimeError("Site URL must be HTTPS")
    # Ensure the image URL is on the intended GitHub Pages host.
    host = urlparse(site_url).hostname or ""
    if host != "bhgat9-web.github.io" or not urlparse(site_url).path.startswith("/oddnews73-auto/"):
        raise RuntimeError("SAFE STOP: unexpected image-host domain or path")
    image_url = site_url.rstrip("/") + "/posts/" + rec["slug"] + ".jpg"
    r = requests.get(image_url, timeout=20)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "").lower()
    if "image/jpeg" not in ctype:
        raise RuntimeError("Public Instagram image is not a JPEG")
    if len(r.content) > 8_000_000:
        raise RuntimeError("Public Instagram image is unexpectedly large")
    try:
        with Image.open(io.BytesIO(r.content)) as img:
            img.verify()
        with Image.open(io.BytesIO(r.content)) as img:
            if img.format != "JPEG" or img.size != (1080, 1350):
                raise RuntimeError("Public image must be the approved 1080x1350 JPEG")
    except (OSError, ValueError) as exc:
        raise RuntimeError("Public Instagram image is invalid") from exc
    local_bytes = (SITE / "posts" / (rec["slug"] + ".jpg")).read_bytes()
    if not hmac.compare_digest(hashlib.sha256(r.content).hexdigest(),
                               hashlib.sha256(local_bytes).hexdigest()):
        raise RuntimeError("SAFE STOP: public JPEG differs from the approved file")
    verify_account()
    st["verified_instagram_id"] = EXPECTED_ID
    rec["image_url"] = image_url
    rec["status"] = "in_flight"
    save(st)
    print("Preflight successful: correct @oddnews73 account and public JPEG")


def publish():
    live()
    st = load()
    rec = current(st)
    if rec.get("demo") or rec["status"] != "in_flight":
        raise RuntimeError("SAFE STOP: missing committed preflight marker")
    tok = verify_account()
    ig_id = st["verified_instagram_id"]
    did_call_publish = False
    try:
        info = ig("POST", ig_id + "/media", tok, {
            "image_url": rec["image_url"], "caption": rec["caption"],
            "alt_text": short("Original ODD News 73 graphic: " + rec["title"], 900)
        })
        cid = str(info["id"])
        rec["container_id"] = cid
        for _ in range(9):
            status = ig("GET", cid, tok, {"fields": "status_code"}).get("status_code")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise RuntimeError("Media container status " + status)
            if status not in ("IN_PROGRESS", "PUBLISHED"):
                raise RuntimeError("Unexpected media status " + str(status))
            time.sleep(7)
        else:
            raise RuntimeError("Timed out waiting for media")
        did_call_publish = True
        result = ig("POST", ig_id + "/media_publish", tok, {"creation_id": cid})
        rec["instagram_media_id"] = str(result["id"])
        posted = ig("GET", rec["instagram_media_id"], tok,
                    {"fields": "id,username,permalink"})
        if str(posted.get("username", "")).lower() != EXPECTED_USER:
            raise RuntimeError("SAFE STOP: published media owner is not @oddnews73")
        rec["instagram_permalink"] = str(posted.get("permalink", ""))
        rec["status"] = "posted"
        rec["posted_utc"] = NOW().isoformat()
        print("Instagram published media:", rec["instagram_media_id"])
    except Exception as exc:
        rec["status"] = "needs_review" if did_call_publish else "not_published"
        rec["error"] = str(exc)[:240]
        print("SAFE STOP: " + rec["error"], file=sys.stderr)
        raise RuntimeError(rec["error"]) from exc
    finally:
        save(st)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("prepare", "review", "approve", "check-account", "preflight", "publish", "status"))
    p.add_argument("--demo", action="store_true")
    p.add_argument("--site-url", default="")
    p.add_argument("--slug", default="")
    p.add_argument("--approval-digest", default="")
    a = p.parse_args()
    if a.command == "prepare":
        prepare(a.demo)
    elif a.command == "review":
        review(a.slug)
    elif a.command == "approve":
        approve(a.slug, a.approval_digest)
    elif a.command == "check-account":
        verify_account()
    elif a.command == "preflight":
        preflight(a.site_url)
    elif a.command == "publish":
        publish()
    else:
        for entry in load()["entries"][-12:]:
            print(entry["status"], entry["title"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", str(exc), file=sys.stderr)
        sys.exit(1)

