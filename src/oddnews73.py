"""ODD News 73: source-linked Instagram feed autopublisher.
Commands: prepare [--demo], preflight --site-url URL, publish, status.
Never calls Meta's publishing API unless LIVE_PUBLISH=true.
"""
import argparse
import hashlib
import html
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
from cryptography.fernet import Fernet
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state.json"
SITE = ROOT / "site"
RUN = ROOT / "run.json"
TOKEN_FILE = ROOT / ".secure" / "instagram_token.enc"
EXPECTED_USER = "oddnews73"
API_VERSION = os.environ.get("IG_API_VERSION", "v26.0")
NOW = lambda: datetime.now(timezone.utc)

FEEDS = [
    ("NASA", "https://www.nasa.gov/feed/"),
    ("Phys.org Earth", "https://phys.org/rss-feed/earth-news/"),
    ("Live Science", "https://www.livescience.com/feeds.xml"),
    ("Smithsonian Smart News", "https://www.smithsonianmag.com/rss/smart-news/"),
    ("Smithsonian Science", "https://www.smithsonianmag.com/rss/science-nature/"),
]
ALLOW = ("nasa.gov", "phys.org", "livescience.com", "smithsonianmag.com")
WEIRD = ("unusual", "strange", "mystery", "mysterious", "rare", "fossil",
         "ancient", "unexplained", "deep sea", "new species", "discovery",
         "discover", "extinct", "prehistoric", "archaeolog", "odd", "unexpected",
         "meteor", "comet", "planet", "giant", "animal", "secret", "hidden")
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
    for source, feed in FEEDS:
        try:
            resp = requests.get(feed, timeout=15, headers={"User-Agent": UA})
            resp.raise_for_status()
            if len(resp.content) > 3_000_000:
                continue
            for item in rss_items(resp.content):
                link = item["link"].split("#")[0]
                title, excerpt = clean(item["title"]), clean(item["excerpt"])
                if not allowed(link) or not title or not excerpt:
                    continue
                if link in st["seen_links"] or duplicate(title, st):
                    continue
                age = (NOW() - datetime.fromisoformat(item["published_utc"])).total_seconds() / 3600
                if age < -2 or age > 168:
                    continue
                txt = (title + " " + excerpt).lower()
                if any(term in txt for term in EXCLUDE):
                    continue
                matches = sum(term in txt for term in WEIRD)
                if matches < 1:
                    continue
                item.update(link=link, title=title, excerpt=short(excerpt, 500), source=source)
                item["score"] = matches * 5 + (30 if age <= 48 else 0) - age / 24
                candidates.append(item)
        except (requests.RequestException, ET.ParseError, ValueError) as exc:
            print(f"Feed unavailable: {source} ({type(exc).__name__})", file=sys.stderr)
    if not candidates:
        return None
    fresh = [x for x in candidates if (NOW() - datetime.fromisoformat(x["published_utc"])).total_seconds() <= 172800]
    return max(fresh or candidates, key=lambda x: x["score"])


def caption(story, demo=False):
    if demo:
        return "DEMO ONLY — NOT A REAL NEWS REPORT."
    date = datetime.fromisoformat(story["published_utc"]).strftime("%d %b %Y")
    fallback = (
        f"🌍 {short(story['title'], 120)}\n\n"
        f"An unusual report from {story['source']} has caught our attention. "
        "This post links to the original publication, not independently verified firsthand evidence. "
        "Read the full report before drawing conclusions.\n\n"
        f"🗓️ {date} · 🔎 {story['source']}\nOriginal source: {story['link']}\n\n"
        "What do you make of this?\n\n#ODDNews73 #WeirdNews #StrangeWorld #Discoveries"
    )
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return fallback
    instructions = (
        "You are a cautious editor for @oddnews73. Based exclusively on the title, source, "
        "date and excerpt below, write a 90-135 word Instagram caption with an engaging headline, "
        "accurate paraphrase, a question and 4 hashtags. Do not add facts, quotes, implications "
        "or measurements. Explicitly attribute claims to the source; do not call speculation "
        "confirmed. Output plain text; use entirely original language and include the precise "
        f"URL {story['link']} at the end.\n"
        f"Source: {story['source']}\nTitle: {story['title']}\nDate: {date}\n"
        f"Excerpt: {story['excerpt']}"
    )
    try:
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": instructions}]}],
                  "generationConfig": {"temperature": .2, "maxOutputTokens": 500}},
            timeout=30
        )
        r.raise_for_status()
        result = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"]).strip()
        if story["link"] in result and 100 < len(result) < 1600:
            return result
    except (requests.RequestException, ValueError, KeyError, IndexError):
        print("Gemini unavailable; using factual attribution template.", file=sys.stderr)
    return fallback


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
    d.rounded_rectangle((65, 53, 1015, 123), 18, fill=(11, 35, 58), outline=accent, width=3)
    d.text((90, 63), "ODD NEWS 73", font=font(38, True), fill=(250, 252, 255))
    d.text((756, 78), "@oddnews73", font=font(23, True), fill=(180, 219, 236))
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
    story = (
        {"title": "This is a design demonstration, not a real news event",
         "excerpt": "Fictional graphic", "source": "DEMO",
         "link": "https://example.org/demo", "published_utc": NOW().isoformat()}
        if demo else choose(st)
    )
    if not story:
        print("No suitable recent attributed report; skipping slot.")
        return
    slug = hashlib.sha256(story["link"].encode()).hexdigest()[:16]
    status = "pending" if os.getenv("LIVE_PUBLISH", "false").lower() == "true" and not demo else "draft"
    rec = {"slug": slug, "title": story["title"], "status": status,
           "source": story["source"], "source_url": story["link"],
           "published_utc": story["published_utc"], "created_utc": NOW().isoformat(),
           "caption": caption(story, demo), "demo": bool(demo)}
    graphic(story, SITE / "posts" / (slug + ".jpg"), demo)
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
    rec = next((x for x in st["entries"] if x["slug"] == slug), None)
    if not rec:
        raise RuntimeError("Current record not found")
    return rec


def live():
    if os.getenv("LIVE_PUBLISH", "").lower() != "true":
        raise RuntimeError("Publishing OFF: LIVE_PUBLISH is not true")


def token():
    k = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()
    if not k:
        raise RuntimeError("Missing TOKEN_ENCRYPTION_KEY GitHub Secret")
    cipher = Fernet(k.encode())
    if TOKEN_FILE.is_file():
        return cipher.decrypt(TOKEN_FILE.read_bytes()).decode(), cipher
    value = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not value:
        raise RuntimeError("Missing INSTAGRAM_ACCESS_TOKEN GitHub Secret")
    return value, cipher


def refresh(tok, cipher, st):
    last = st.get("token_last_refresh")
    if last and (NOW() - datetime.fromisoformat(last)).days < 14:
        return tok
    try:
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": tok},
                         timeout=30)
        r.raise_for_status()
        tok = r.json()["access_token"]
        st["token_last_refresh"] = NOW().isoformat()
        print("Instagram access token refreshed.")
    except (requests.RequestException, ValueError, KeyError):
        print("Refresh unsuccessful; trying existing token.", file=sys.stderr)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_bytes(cipher.encrypt(tok.encode()))
    return tok


def ig(method, endpoint, tok, params=None):
    uri = f"https://graph.instagram.com/{API_VERSION}/{endpoint}"
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


def preflight(site_url):
    live()
    st = load()
    rec = current(st)
    if rec.get("demo") or rec["status"] != "pending":
        raise RuntimeError("Only a pending, non-demo post may be published")
    if not site_url.startswith("https://"):
        raise RuntimeError("Site URL must be HTTPS")
    image_url = site_url.rstrip("/") + "/posts/" + rec["slug"] + ".jpg"
    r = requests.get(image_url, timeout=20, stream=True)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "").lower()
    r.close()
    if "image/jpeg" not in ctype:
        raise RuntimeError("Public Instagram image is not a JPEG")
    tok, cipher = token()
    tok = refresh(tok, cipher, st)
    profile = ig("GET", "me", tok, {"fields": "user_id,username"})
    if profile.get("username", "").lower() != EXPECTED_USER:
        raise RuntimeError("SAFE STOP: Instagram identity does not match @oddnews73")
    ig_id = str(profile.get("user_id") or profile.get("id") or "")
    if not ig_id:
        raise RuntimeError("Meta did not supply Instagram user ID")
    st["verified_instagram_id"] = ig_id
    rec["image_url"] = image_url
    rec["status"] = "in_flight"
    save(st)
    print("Preflight successful: correct account and public JPEG, marked in-flight")


def publish():
    live()
    st = load()
    rec = current(st)
    if rec.get("demo") or rec["status"] != "in_flight":
        raise RuntimeError("SAFE STOP: missing committed preflight marker")
    tok, _ = token()
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
        rec["status"] = "posted"
        rec["posted_utc"] = NOW().isoformat()
        print("Instagram published media:", rec["instagram_media_id"])
    except Exception as exc:
        rec["status"] = "needs_review" if did_call_publish else "not_published"
        rec["error"] = str(exc)[:240]
        print("SAFE STOP: " + rec["error"], file=sys.stderr)
    finally:
        save(st)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("prepare", "preflight", "publish", "status"))
    p.add_argument("--demo", action="store_true")
    p.add_argument("--site-url", default="")
    a = p.parse_args()
    if a.command == "prepare":
        prepare(a.demo)
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
