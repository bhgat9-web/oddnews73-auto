#!/usr/bin/env python3
"""ODD News 73 VPS worker: no secrets in Git; never touches trading apps."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "src"))
import oddnews73 as app

IST = ZoneInfo("Asia/Kolkata")
SITE_URL = "https://bhgat9-web.github.io/oddnews73-auto/"
LOCK_FILE = BASE.parent / "publisher.lock"
SLOT_HOURS = (9, 14, 21)


def git(*args: str, timeout: int = 120):
    subprocess.run(["git", "-C", str(BASE), *args], check=True, timeout=timeout)


def slot_at(now: datetime | None = None) -> str | None:
    local = (now or datetime.now(IST)).astimezone(IST)
    for hour in SLOT_HOURS:
        start = local.replace(hour=hour, minute=7, second=0, microsecond=0)
        if timedelta(0) <= local - start < timedelta(minutes=40):
            return start.strftime("%Y-%m-%dT%H:%M%z")
    return None


def report(label: str, **fields):
    print(json.dumps(
        {"event": label, "at_ist": datetime.now(IST).isoformat(), **fields},
        ensure_ascii=False
    ), flush=True)


def check():
    missing = [name for name in ("INSTAGRAM_ACCESS_TOKEN",)
               if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError("Missing VPS settings: " + ", ".join(missing))
    if not (BASE / "assets" / "odd-news-73-logo.png").is_file():
        raise RuntimeError("Brand logo missing from repository")
    if not (BASE / "src" / "oddnews73.py").is_file():
        raise RuntimeError("Publisher source missing from repository")
    if app.EXPECTED_USER != "oddnews73":
        raise RuntimeError("Unexpected Instagram account")
    print("Configuration and logo are present; secrets not displayed.")
    print("No Instagram post has been made by this check.")


def commit_push(message: str):
    git("add", "--", "state.json", "site/")
    staged = subprocess.run(["git", "-C", str(BASE), "diff", "--cached", "--quiet"])
    if staged.returncode == 1:
        git("commit", "-m", message)
        git("push", "origin", "HEAD:main", timeout=90)
    elif staged.returncode != 0:
        raise RuntimeError("Unable to inspect staged files")


def wait_for_image(slug: str, max_seconds: int = 540):
    url = SITE_URL.rstrip("/") + "/posts/" + slug + ".jpg"
    data = (BASE / "site" / "posts" / (slug + ".jpg")).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        try:
            resp = requests.get(url, params={"verify": digest[:16]}, timeout=20)
            if (resp.status_code == 200
                    and "image/jpeg" in resp.headers.get("content-type", "").lower()
                    and hashlib.sha256(resp.content).hexdigest() == digest):
                return
        except requests.RequestException:
            pass
        time.sleep(15)
    raise RuntimeError("New image not yet available on GitHub Pages")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("run", "check"))
    args = parser.parse_args()
    check()
    if args.action == "check":
        return

    LOCK_FILE.touch(exist_ok=True)
    with LOCK_FILE.open("r+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            report("already_running")
            return

        slot = slot_at()
        if slot is None:
            report("outside_vps_slot", reason="No late or unscheduled posts allowed")
            return
        report("started", slot=slot)
        os.environ["LIVE_PUBLISH"] = "true"
        os.environ["AUTO_PUBLISH"] = "true"
        os.environ["STRICT_SCHEDULE"] = "false"

        git("pull", "--ff-only", "origin", "main")
        state = app.load()
        if any(e.get("scheduled_slot") == slot and e.get("status") == "posted"
               for e in state["entries"]):
            report("already_posted", slot=slot)
            return
        if any(e.get("status") in ("in_flight", "needs_review")
               for e in state["entries"]):
            raise RuntimeError("Previous publication ambiguous; human review required")
        if any(e.get("status") == "pending" and e.get("scheduled_slot") != slot
               for e in state["entries"]):
            raise RuntimeError("Pending post belongs to an earlier slot; review required")

        # Publish only source-vetted artwork prepared in the queue. Never replace
        # approved editorial artwork with a generic generated card.
        app.prepare_queued()
        if not app.RUN.is_file():
            report("queue_exhausted", slot=slot,
                   reason="No unused approved story-specific artwork")
            return

        state = app.load()
        rec = app.current(state)
        if rec["status"] != "pending" or rec.get("demo"):
            raise RuntimeError("No approved non-demo pending draft")
        rec["scheduled_slot"] = slot
        rec["automatic_digest"] = app.approval_digest(rec)
        app.save(state)

        # Publish only after the committed image is publicly available.
        commit_push("ODD News 73: VPS staged source-linked draft")
        wait_for_image(rec["slug"])
        app.preflight(SITE_URL)
        # Persist marker before Meta POST to prevent ambiguous duplicate attempts.
        commit_push("ODD News 73: VPS publishing in flight")
        try:
            app.publish()
        finally:
            commit_push("ODD News 73: VPS publication outcome")
        report("published", slot=slot, title=rec["title"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report("failed", reason=str(exc)[:200])
        sys.exit(1)

