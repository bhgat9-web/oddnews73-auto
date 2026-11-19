import json
import tempfile
import unittest
from io import StringIO
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

    def test_missing_ai_key_prevents_generic_caption(self):
        story = {"title": "Rare bird mystery", "source": "NASA",
                 "link": "https://nasa.gov/test", "excerpt": "Something unusual",
                 "published_utc": "2026-11-17T00:00:00+00:00"}
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            self.assertIsNone(app.caption(story))

    def test_failed_ai_request_prevents_caption(self):
        import requests
        story = {"title": "Rare bird mystery", "source": "NASA",
                 "link": "https://nasa.gov/test", "excerpt": "Something unusual",
                 "published_utc": "2026-11-17T00:00:00+00:00"}
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-test-key"}), \
                patch.object(app.requests, "post", side_effect=requests.Timeout):
            self.assertIsNone(app.caption(story))

    def test_unavailable_current_model_falls_back_to_approved_free_model(self):
        from unittest.mock import Mock
        story = {"title": "Rare mysterious fossil", "source": "NASA",
                 "link": "https://nasa.gov/test", "excerpt": "An unusual discovery",
                 "published_utc": "2026-11-17T00:00:00+00:00"}
        prose = (
            "A remarkable fossil found beneath an ancient landscape has raised questions "
            "about the wildlife that lived there thousands of years ago. The source describes "
            "the remains as unusually preserved, and researchers are still investigating "
            "what they represent. The real story is worth examining carefully, because "
            "extraordinary claims require traceable evidence and responsible reporting. "
        )
        long_caption = prose + story["link"] + " #ODDNews73"
        not_found = Mock(status_code=404)
        success = Mock(status_code=200)
        success.json.return_value = {"candidates": [{"content": {"parts": [{"text": long_caption}]}}]}
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-test-key",
                                        "GEMINI_MODEL": "gemini-3.5-flash-lite"}), \
                patch.object(app.requests, "post", side_effect=[not_found, success]) as post:
            generated = app.caption(story)
            expected = (
                prose.strip() + "\n\nSource: NASA · 17 Nov 2026\n"
                + story["link"]
                + "\n\n#ODDNews73 #WeirdNews #StrangeWorld #Discoveries"
            )
            self.assertEqual(generated, expected)
            self.assertEqual(generated.count(story["link"]), 1)
            self.assertEqual(generated.count("#ODDNews73"), 1)
        self.assertEqual(post.call_count, 2)
        self.assertIn("gemini-3.5-flash-lite", post.call_args_list[0].args[0])
        self.assertIn("gemini-3.1-flash-lite", post.call_args_list[1].args[0])

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

    def test_official_logo_asset_is_square(self):
        from PIL import Image
        self.assertTrue(app.LOGO.is_file())
        with Image.open(app.LOGO) as logo:
            self.assertEqual(logo.width, logo.height)
            self.assertGreaterEqual(logo.width, 256)
            self.assertEqual(logo.format, "PNG")


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

    def test_meta_api_host_is_allowlisted(self):
        with patch.object(app, "API_HOST", "attacker.example"):
            with self.assertRaisesRegex(RuntimeError, "unsupported Meta API host"):
                app.ig("GET", "me", "secret")

    def test_approval_binds_exact_caption_and_jpeg(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            run = root / "run.json"
            site = root / "site"
            (site / "posts").mkdir(parents=True)
            rec = {"slug": "0123456789abcdef", "title": "Rare bird mystery",
                   "status": "draft", "source": "NASA",
                   "source_url": "https://nasa.gov/story", "caption": "Exact caption",
                   "demo": False}
            state.write_text(json.dumps({"entries": [rec], "seen_links": []}))
            Image.new("RGB", (1080, 1350)).save(site / "posts" / "0123456789abcdef.jpg", "JPEG")
            with patch.object(app, "STATE", state), patch.object(app, "RUN", run), \
                    patch.object(app, "SITE", site), \
                    patch.dict("os.environ", {"LIVE_PUBLISH": "true"}):
                digest = app.approval_digest(rec)
                with self.assertRaisesRegex(RuntimeError, "approval does not match"):
                    app.approve(rec["slug"], "0" * 64)
                self.assertEqual(json.loads(state.read_text())["entries"][0]["status"], "draft")
                app.approve(rec["slug"], digest)
                saved = json.loads(state.read_text())["entries"][0]
                self.assertEqual(saved["status"], "pending")
                self.assertEqual(saved["approved_digest"], digest)
                self.assertEqual(json.loads(run.read_text())["slug"], rec["slug"])

    def test_publish_failure_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            run = root / "run.json"
            rec = {"slug": "0123456789abcdef", "title": "Rare bird mystery",
                   "status": "in_flight", "source": "NASA",
                   "source_url": "https://nasa.gov/story", "caption": "Exact caption",
                   "image_url": "https://bhgat9-web.github.io/oddnews73-auto/posts/x.jpg",
                   "demo": False}
            state.write_text(json.dumps({"entries": [rec], "seen_links": [],
                                         "verified_instagram_id": app.EXPECTED_ID}))
            run.write_text(json.dumps({"slug": rec["slug"]}))
            with patch.object(app, "STATE", state), patch.object(app, "RUN", run), \
                    patch.dict("os.environ", {"LIVE_PUBLISH": "true"}), \
                    patch.object(app, "verify_account", return_value="secret"), \
                    patch.object(app, "ig", side_effect=RuntimeError("simulated failure")):
                with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                    app.publish()
            self.assertEqual(json.loads(state.read_text())["entries"][0]["status"],
                             "not_published")

    def test_review_bundle_contains_digest(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            site = root / "site"
            (site / "posts").mkdir(parents=True)
            rec = {"slug": "0123456789abcdef", "title": "Rare bird mystery",
                   "status": "draft", "source": "NASA",
                   "source_url": "https://nasa.gov/story", "caption": "Exact caption",
                   "demo": False}
            state.write_text(json.dumps({"entries": [rec], "seen_links": []}))
            Image.new("RGB", (1080, 1350)).save(site / "posts" / "0123456789abcdef.jpg", "JPEG")
            with patch.object(app, "STATE", state), patch.object(app, "SITE", site), \
                    patch("sys.stdout", new_callable=StringIO) as output:
                app.review(rec["slug"])
            bundle = json.loads(output.getvalue())
            self.assertEqual(bundle["slug"], rec["slug"])
            self.assertEqual(len(bundle["approval_digest"]), 64)


class ScheduledBackupTests(unittest.TestCase):
    def test_ist_slots_and_late_window(self):
        ist = app.IST
        for h in (9, 14, 21):
            self.assertIsNone(
                app.scheduled_slot(app.datetime(2026, 11, 20, h, 6, tzinfo=ist))
            )
            expected = f"2026-11-20T{h:02d}:07+0530"
            self.assertEqual(
                app.scheduled_slot(app.datetime(2026, 11, 20, h, 7, tzinfo=ist)),
                expected
            )
            self.assertEqual(
                app.scheduled_slot(app.datetime(2026, 11, 20, h, 27, tzinfo=ist)),
                expected
            )
        self.assertIsNone(
            app.scheduled_slot(app.datetime(2026, 11, 20, 17, 35, tzinfo=ist))
        )

    def test_backup_never_duplicates_successful_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            slot = "2026-11-20T21:07+0530"
            state.write_text(json.dumps({
                "entries": [{"status": "posted", "scheduled_slot": slot,
                             "slug": "already-published"}],
                "seen_links": []
            }))
            run = root / "run.json"
            report = root / "schedule_result.json"
            at_backup = app.datetime(2026, 11, 20, 21, 27, tzinfo=app.IST)
            with patch.object(app, "STATE", state), \
                    patch.object(app, "RUN", run), \
                    patch.object(app, "SLOT_RESULT", report), \
                    patch.object(app, "NOW", return_value=at_backup), \
                    patch.dict("os.environ", {"LIVE_PUBLISH": "true", "AUTO_PUBLISH": "true"}):
                app.prepare_queued()
            self.assertFalse(run.exists())
            self.assertEqual(json.loads(report.read_text())["status"], "already_posted")
            self.assertEqual(len(json.loads(state.read_text())["entries"]), 1)

    def test_outside_window_rejected_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            state.write_text(json.dumps({"entries": [], "seen_links": []}))
            run = root / "run.json"
            report = root / "schedule_result.json"
            late = app.datetime(2026, 11, 20, 18, 0, tzinfo=app.IST)
            with patch.object(app, "STATE", state), \
                    patch.object(app, "RUN", run), \
                    patch.object(app, "SLOT_RESULT", report), \
                    patch.object(app, "NOW", return_value=late), \
                    patch.dict("os.environ", {"LIVE_PUBLISH": "true", "AUTO_PUBLISH": "true"}):
                with self.assertRaisesRegex(RuntimeError, "outside"):
                    app.prepare_queued()
            self.assertFalse(run.exists())
            self.assertEqual(json.loads(report.read_text())["status"], "outside_window")


class AutomaticPublishingTests(unittest.TestCase):
    def test_auto_binding_requires_explicit_mode_and_unchanged_content(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "posts").mkdir()
            rec = {"slug": "0123456789abcdef", "title": "Rare fossil",
                   "source": "NASA", "source_url": "https://nasa.gov/story",
                   "caption": "Source-linked report", "demo": False}
            Image.new("RGB", (1080, 1350)).save(site / "posts" / (rec["slug"] + ".jpg"))
            with patch.object(app, "SITE", site):
                rec["automatic_digest"] = app.approval_digest(rec)
                with patch.dict("os.environ", {"AUTO_PUBLISH": "false"}):
                    with self.assertRaises(RuntimeError):
                        app.validate_publication_authorization(rec)
                with patch.dict("os.environ", {"AUTO_PUBLISH": "true"}):
                    app.validate_publication_authorization(rec)
                    rec["caption"] = "Changed after preparation"
                    with self.assertRaises(RuntimeError):
                        app.validate_publication_authorization(rec)

    def test_automatic_prepare_binds_new_post_and_skips_duplicates(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "site"
            (site / "posts").mkdir(parents=True)
            story = {"title": "Rare fossil found", "source": "NASA",
                     "link": "https://nasa.gov/story",
                     "published_utc": "2026-11-18T00:00:00+00:00"}
            def render(story, path, demo):
                Image.new("RGB", (1080, 1350)).save(path)
            with patch.object(app, "STATE", root / "state.json"), \
                    patch.object(app, "RUN", root / "run.json"), \
                    patch.object(app, "SITE", site), \
                    patch.object(app, "choose", return_value=story) as choose, \
                    patch.object(app, "caption", return_value="Source-linked report"), \
                    patch.object(app, "graphic", side_effect=render), \
                    patch.dict("os.environ", {"LIVE_PUBLISH": "true", "AUTO_PUBLISH": "true"}):
                app.prepare()
                rec = app.load()["entries"][0]
                self.assertEqual(rec["status"], "pending")
                app.validate_publication_authorization(rec)
                app.prepare()
                self.assertEqual(choose.call_count, 1)
                self.assertEqual(len(app.load()["entries"]), 1)
                st = app.load()
                st["entries"][0]["status"] = "needs_review"
                app.save(st)
                app.prepare()
                self.assertFalse(app.RUN.exists())
                self.assertEqual(choose.call_count, 1)


    def test_rejected_candidates_are_bounded_and_do_not_pollute_history(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "site"
            (site / "posts").mkdir(parents=True)
            stories = [
                {"title": "Rare fossil " + str(i), "source": "NASA",
                 "link": "https://nasa.gov/story" + str(i),
                 "published_utc": "2026-11-19T00:00:00+00:00"}
                for i in range(3)
            ]
            def select(st):
                return next((s for s in stories if s["link"] not in st["seen_links"]), None)
            def render(story, path, demo):
                Image.new("RGB", (1080, 1350)).save(path)
            with patch.object(app, "STATE", root / "state.json"), \
                    patch.object(app, "RUN", root / "run.json"), \
                    patch.object(app, "SITE", site), \
                    patch.object(app, "choose", side_effect=select) as choose, \
                    patch.object(app, "caption", side_effect=[None, "Valid source caption"]) as caption, \
                    patch.object(app, "graphic", side_effect=render), \
                    patch.dict("os.environ", {"LIVE_PUBLISH": "false", "AUTO_PUBLISH": "false"}):
                app.prepare()
                self.assertEqual(choose.call_count, 2)
                self.assertEqual(app.load()["seen_links"], [stories[1]["link"]])
                self.assertEqual(len(app.load()["entries"]), 1)
                self.assertEqual(app.load()["entries"][0]["status"], "draft")
                before = app.STATE.read_bytes()
                caption.side_effect = None
                caption.return_value = None
                choose.side_effect = None
                choose.return_value = stories[0]
                choose.reset_mock()
                app.prepare()
                self.assertEqual(choose.call_count, 3)
                self.assertFalse(app.RUN.exists())
                self.assertEqual(app.STATE.read_bytes(), before)

if __name__ == "__main__":
    unittest.main()

