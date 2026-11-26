"""Offline tests for the opt-in autonomous news/artwork producer."""
import base64
import hashlib
import io
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vps"))
import producer


class ProducerTests(unittest.TestCase):
    def test_disabled_producer_never_calls_cloud_ai_or_git(self):
        with patch.dict(os.environ, {"PRODUCER_ENABLED": "false"}), \
             patch.object(producer, "gemini") as ai, \
             patch.object(producer, "git") as git:
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                producer.run()
        ai.assert_not_called()
        git.assert_not_called()

    def test_paid_images_require_separate_explicit_opt_in(self):
        with patch.dict(os.environ, {
            "PRODUCER_ENABLED": "true",
            "GEMINI_API_KEY": "dummy-secret-for-test",
            "ODDNEWS73_VISUAL_QA_APPROVED": "yes",
            "GEMINI_IMAGE_PAID_OK": "",
        }), patch.object(producer, "IMAGE_MODE", "paid_gemini"), \
             patch.object(producer, "git") as git, \
             patch.object(producer, "gemini") as api:
            with self.assertRaisesRegex(RuntimeError, "explicitly authorized"):
                producer.run()
        git.assert_not_called()
        api.assert_not_called()

    def test_no_approval_no_artwork_generation(self):
        with patch.dict(os.environ, {
            "PRODUCER_ENABLED": "true",
            "ODDNEWS73_VISUAL_QA_APPROVED": "",
        }), patch.object(producer, "gemini") as ai, \
             patch.object(producer, "git") as git:
            with self.assertRaisesRegex(RuntimeError, "visual quality approval"):
                producer.run()
        ai.assert_not_called()
        git.assert_not_called()

    def test_unreadable_paid_budget_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            budget = Path(temp) / "budget.json"
            budget.write_text("not valid json")
            with patch.object(producer, "BUDGET_FILE", budget):
                with self.assertRaisesRegex(RuntimeError, "unreadable"):
                    producer.reserve_image_budget()
            self.assertEqual(budget.read_text(), "not valid json")

    def test_evidence_quotes_must_appear_in_article(self):
        body = (
            "Scientists discovered a bright yellow burbot in the bay. "
            "The unusual coloration is attributed to xanthochromism. "
            "This animal will be examined by local specialists."
        )
        yes = {"evidence_quotes": [
            "Scientists discovered a bright yellow burbot in the bay.",
            "The unusual coloration is attributed to xanthochromism."
        ]}
        self.assertTrue(producer.evidence_supported(yes, body))
        bad = {**yes, "evidence_quotes": [
            "Scientists discovered a bright yellow burbot in the bay.",
            "The unusual coloration is caused by alien intervention."
        ]}
        self.assertFalse(producer.evidence_supported(bad, body))

    def test_poster_is_story_specific_4_by_5_jpeg(self):
        image = Image.new("RGB", (1024, 1024), (70, 96, 126))
        raw = io.BytesIO()
        image.save(raw, "PNG")
        jpg = producer.poster(raw.getvalue(), "Rare golden fish surprises researchers")
        with Image.open(io.BytesIO(jpg)) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertEqual(im.size, (1080, 1350))
        self.assertLess(len(jpg), 8_000_000)

    def test_bundle_is_compatible_with_exact_publisher_contract(self):
        source = (
            "https://phys.org/news/2026-11-hidden-million-years-rays-reveal.html"
        )
        story = {
            "source_url": source,
            "title": "A tiny flower hidden for 100 million years",
            "source": "Phys.org",
            "published_utc": "2026-11-23T00:00:00+00:00"
        }
        image = Image.new("RGB", (768, 768), (16, 55, 84))
        raw = io.BytesIO()
        image.save(raw, "JPEG")
        edited = {
            "headline": "A tiny flower survives in stone",
            "caption": " ".join(["Scientists describe a tiny flower revealed inside a sandstone specimen."] * 12),
            "image_prompt": " ".join(["A macro view of a fossil flower embedded in textured sandstone with gentle golden light."] * 4),
            "evidence_quotes": ["The sandstone contains a fossil",
                                "The specimen was taken to the laboratory"]
        }
        with patch.object(producer, "article_text", return_value="Verified article body"), \
             patch.object(producer, "write_story", return_value=edited), \
             patch.object(producer, "IMAGE_MODE", "free_original"), \
             patch.object(producer, "gemini_image") as paid_image:
            item, jpg = producer.make_bundle(story)
            paid_image.assert_not_called()
        self.assertTrue(item["ready"])
        self.assertEqual(item["image_sha256"], hashlib.sha256(jpg).hexdigest())
        self.assertEqual(item["bundle_digest"], producer.pub.queue_digest(item))
        self.assertIn("original digitally drawn editorial illustration", item["caption"])
        self.assertIn(source, item["caption"])
        self.assertEqual(datetime.fromisoformat(item["expires_utc"]) -
                         datetime.fromisoformat(item["published_utc"]),
                         producer.timedelta(days=7))


    def test_daily_paid_image_budget_is_bounded_and_persists(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            budget = Path(temp) / "budget.json"
            with patch.object(producer, "BUDGET_FILE", budget), \
                 patch.dict(os.environ, {"PRODUCER_DAILY_IMAGE_LIMIT": "2"}):
                producer.reserve_image_budget()
                producer.reserve_image_budget()
                self.assertEqual(json.loads(budget.read_text())["image_calls"], 2)
                with self.assertRaisesRegex(RuntimeError, "cap"):
                    producer.reserve_image_budget()

    def test_gemini_image_request_extracts_only_real_base64_image(self):
        image = Image.new("RGB", (512, 512), (12, 45, 78))
        b = io.BytesIO()
        image.save(b, "PNG")
        data = base64.b64encode(b.getvalue()).decode()
        response = {"candidates": [{"content": {"parts": [
            {"text": "Here is the image."},
            {"inlineData": {"mimeType": "image/png", "data": data}}
        ]}}]}
        with patch.object(producer, "reserve_image_budget") as cap, \
             patch.object(producer, "gemini", return_value=response) as call:
            raw = producer.gemini_image("a rare fish underwater")
        self.assertEqual(raw, b.getvalue())
        cap.assert_called_once()
        args, kw = call.call_args
        self.assertEqual(args[0], producer.MODEL_IMAGE)
        self.assertIn("IMAGE", args[1]["generationConfig"]["responseModalities"])


    def test_free_art_is_subject_specific_and_no_provider_network(self):
        from unittest.mock import patch
        from PIL import Image
        import free_art
        self.assertEqual(free_art.category("Deep sea submarine explores trench"), "deep_sea")
        self.assertEqual(free_art.category("A golden burbot fish was discovered"), "fish")
        self.assertEqual(free_art.category("Flowers hidden in 100 million year fossil"), "flower")
        self.assertEqual(free_art.category("Archaeologists reveal an ancient tomb"), "archaeology")
        self.assertIsNone(free_art.category("Researchers discover an unusual mystery"))
        with patch.object(producer, "gemini") as api:
            for title in ("Deep sea submarine explores trench",
                          "A golden burbot fish was discovered",
                          "Flowers hidden in 100 million year fossil",
                          "Archaeologists reveal an ancient tomb"):
                with self.subTest(title=title):
                    raw = free_art.render(title)
                    with Image.open(io.BytesIO(raw)) as im:
                        self.assertEqual(im.size, (1080, 1350))
                        self.assertEqual(im.format, "PNG")
            api.assert_not_called()
        with self.assertRaisesRegex(ValueError, "No source-specific"):
            free_art.render("Researchers discover an unusual mystery")

    def test_text_editor_uses_supported_existing_gemini_model(self):
        payload = {"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}]}
        with patch.object(producer, "gemini", return_value=payload) as api:
            response = producer.gemini_text("Test instruction", "Article")
        self.assertEqual(json.loads(response), {"ok": True})
        self.assertEqual(api.call_args.args[0], producer.MODEL_TEXT)


if __name__ == "__main__":
    unittest.main()
