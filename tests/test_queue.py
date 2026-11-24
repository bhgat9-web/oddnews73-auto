import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import sys
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import oddnews73 as app


class PreparedQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 11, 19, 13, tzinfo=timezone.utc)
        self.queue = self.root / "queue"
        (self.queue / "images").mkdir(parents=True)
        self.url = "https://www.nasa.gov/test-new-story"
        self.slug = hashlib.sha256(self.url.encode()).hexdigest()[:16]
        self.image = self.queue / "images" / (self.slug + ".jpg")
        Image.new("RGB", (1080, 1350), "orange").save(self.image, "JPEG")
        self.item = {"slug": self.slug, "title": "A new discovery", "source": "NASA",
                     "source_url": self.url, "published_utc": (self.now - timedelta(days=1)).isoformat(),
                     "expires_utc": (self.now + timedelta(days=1)).isoformat(),
                     "caption": "A prepared source-linked news caption. " + self.url
                                + "\nVisual: AI-generated illustration, not a photograph.",
                     "image_sha256": hashlib.sha256(self.image.read_bytes()).hexdigest(),
                     "ready": True}
        self.item["bundle_digest"] = app.queue_digest(self.item)
        self.write()
        for target, value in (("ROOT", self.root), ("STATE", self.root / "state.json"),
                              ("SITE", self.root / "site"), ("RUN", self.root / "run.json"),
                              ("NOW", lambda: self.now)):
            p = patch.object(app, target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.dict("os.environ", {"LIVE_PUBLISH": "false", "AUTO_PUBLISH": "false"})
        p.start()
        self.addCleanup(p.stop)

    def write(self):
        (self.queue / "posts.json").write_text(json.dumps({"posts": [self.item]}))

    def test_preview_uses_no_network_and_does_not_consume_story(self):
        with patch.object(app.requests, "get", side_effect=AssertionError("Network forbidden")), \
                patch.object(app.requests, "post", side_effect=AssertionError("Network forbidden")):
            app.prepare_queued()
        st = app.load()
        self.assertEqual(st["seen_links"], [])
        self.assertEqual(st["entries"][0]["status"], "draft")
        self.assertEqual((app.SITE / "posts" / (self.slug + ".jpg")).read_bytes(),
                         self.image.read_bytes())

    def test_live_stages_exact_image_once_and_reuses_pending(self):
        with patch.dict("os.environ", {"LIVE_PUBLISH": "true", "AUTO_PUBLISH": "true"}):
            app.prepare_queued()
            app.prepare_queued()
            st = app.load()
            self.assertEqual(len(st["entries"]), 1)
            self.assertEqual(st["seen_links"], [self.url])
            app.validate_publication_authorization(st["entries"][0])
            st["entries"][0]["status"] = "posted"
            app.save(st)
            app.prepare_queued()
            self.assertFalse(app.RUN.exists())

    def test_preview_can_later_be_staged_without_duplicate_records(self):
        app.prepare_queued()
        with patch.dict("os.environ", {"LIVE_PUBLISH": "true", "AUTO_PUBLISH": "true"}):
            app.prepare_queued()
        self.assertEqual(len(app.load()["entries"]), 1)
        self.assertEqual(app.load()["entries"][0]["status"], "pending")

    def test_empty_queue_removes_stale_run_and_does_not_generate(self):
        (self.queue / "posts.json").write_text('{"posts":[]}')
        app.RUN.write_text('{"slug":"stale"}')
        with patch.object(app, "caption") as cap, patch.object(app, "graphic") as graphic:
            app.prepare_queued()
            cap.assert_not_called()
            graphic.assert_not_called()
        self.assertFalse(app.RUN.exists())

    def test_changed_caption_and_image_are_rejected(self):
        original = self.item["caption"]
        self.item["caption"] += " altered"
        self.write()
        app.prepare_queued()
        self.assertFalse(app.RUN.exists())
        self.item["caption"] = original
        self.write()
        self.image.write_bytes(b"altered")
        app.prepare_queued()
        self.assertFalse(app.RUN.exists())

    def test_expired_unready_and_untrusted_source_are_skipped(self):
        for key, value in (("expires_utc", (self.now-timedelta(hours=1)).isoformat()),
                           ("ready", False), ("source_url", "https://example.org/news")):
            old = self.item[key]
            self.item[key] = value
            self.item["bundle_digest"] = app.queue_digest(self.item)
            self.write()
            app.prepare_queued()
            self.assertFalse(app.RUN.exists())
            self.item[key] = old

    def test_ambiguous_publication_stops_even_with_new_queue_items(self):
        app.save({"entries": [{"status": "needs_review", "slug": "old"}], "seen_links": []})
        app.prepare_queued()
        self.assertFalse(app.RUN.exists())

    def test_expired_pending_authorization_is_rejected(self):
        with patch.dict("os.environ", {"LIVE_PUBLISH": "true", "AUTO_PUBLISH": "true"}):
            app.prepare_queued()
            with patch.object(app, "NOW", return_value=self.now+timedelta(days=2)):
                with self.assertRaisesRegex(RuntimeError, "expired"):
                    app.prepare_queued()


class ShippedQueueTests(unittest.TestCase):
    def test_every_ready_bundle_matches_its_exact_jpeg(self):
        queue = json.loads((app.ROOT / "queue" / "posts.json").read_text(encoding="utf-8"))
        slugs = set()
        for item in queue["posts"]:
            self.assertNotIn(item["slug"], slugs)
            slugs.add(item["slug"])
            self.assertEqual(app.queue_digest(item), item["bundle_digest"])
            path = app.ROOT / "queue" / "images" / (item["slug"] + ".jpg")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["image_sha256"])
            with Image.open(path) as image:
                self.assertEqual(image.size, (1080, 1350))
                self.assertEqual(image.format, "JPEG")
                image.verify()
            self.assertTrue(app.allowed(item["source_url"]))

    def test_vps_never_uses_generic_fallback_artwork(self):
        runner = (app.ROOT / "vps/runner.py").read_text(encoding="utf-8")
        self.assertIn('report("queue_exhausted"', runner)
        self.assertNotIn("app.prepare()", runner)
        self.assertNotIn("RSS_Gemini", runner)


if __name__ == "__main__":
    unittest.main()

