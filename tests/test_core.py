import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import oddnews73 as app


class EditorialSafetyTests(unittest.TestCase):
    def test_allowlisted_https_only(self):
        self.assertTrue(app.allowed("https://www.nasa.gov/story"))
        self.assertFalse(app.allowed("http://nasa.gov/story"))
        self.assertFalse(app.allowed("https://nasa.gov.attacker.example/story"))
        self.assertFalse(app.allowed("https://example.com/story"))

    def test_rss_parser_has_a_valid_timestamp(self):
        xml = b"<rss><channel><item><title>Rare fossil found</title><link>https://www.nasa.gov/x</link><description>Unusual discovery</description><pubDate>Tue, 17 Nov 2026 07:00:00 GMT</pubDate></item></channel></rss>"
        entries = list(app.rss_items(xml))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Rare fossil found")

    def test_near_duplicate_headline(self):
        st = {"entries": [{"title": "New rare fossil discovered inside an ancient cave"}], "seen_links": []}
        self.assertTrue(app.duplicate("New rare fossil discovered inside an ancient cave!", st))

    def test_public_source_index_escapes_markup(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, "SITE", Path(tmp)):
            st = {"entries": [{"title": "<script>alert(1)</script>",
                    "source": "Example", "source_url": "https://nasa.gov/a", "demo": False}]}
            app.sources_index(st)
            content = (Path(tmp) / "index.html").read_text()
            self.assertNotIn("<script>", content)
            self.assertIn("&lt;script&gt;", content)

    def test_source_based_caption_has_source(self):
        story = {"title": "Rare bird mystery", "source": "NASA",
                 "link": "https://nasa.gov/test", "excerpt": "Something unusual",
                 "published_utc": "2026-11-17T00:00:00+00:00"}
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            result = app.caption(story)
        self.assertIn(story["link"], result)
        self.assertIn("not independently verified", result)

    def test_poster_is_correct_4_by_5_size(self):
        from PIL import Image
        story = {"title": "Fictional demo only", "source": "DEMO",
                 "published_utc": "2026-11-17T00:00:00+00:00"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.jpg"
            app.graphic(story, path, True)
            with Image.open(path) as img:
                self.assertEqual(img.size, (1080, 1350))
                self.assertEqual(img.format, "JPEG")


class PublishingSafetyTests(unittest.TestCase):
    def test_publish_requires_live_enabled(self):
        with patch.dict("os.environ", {"LIVE_PUBLISH": "false"}):
            with self.assertRaises(RuntimeError):
                app.live()

    def test_preflight_never_uses_network_when_disabled(self):
        with patch.dict("os.environ", {"LIVE_PUBLISH": "false"}), patch.object(app.requests, "get") as req:
            with self.assertRaises(RuntimeError):
                app.preflight("https://example.com")
            req.assert_not_called()

    def test_no_demo_can_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            run = Path(tmp) / "run.json"
            path.write_text(json.dumps({"entries": [{"slug": "demo", "status": "pending", "demo": True}], "seen_links": []}))
            run.write_text(json.dumps({"slug": "demo"}))
            with patch.object(app, "STATE", path), patch.object(app, "RUN", run), patch.dict("os.environ", {"LIVE_PUBLISH": "true"}):
                with self.assertRaises(RuntimeError):
                    app.preflight("https://example.com")

if __name__ == "__main__":
    unittest.main()
