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
             patch.object(producer, "cf") as ai, \
             patch.object(producer, "git") as git:
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                producer.run()
        ai.assert_not_called()
        git.assert_not_called()

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
        def fake_ai(model, payload, timeout=90):
            if model == producer.MODEL_TEXT:
                return {"response": json.dumps(edited)}
            return {"image": base64.b64encode(raw.getvalue()).decode("ascii")}
        with patch.object(producer, "article_text", return_value="Verified article body"), \
             patch.object(producer, "write_story", return_value=edited), \
             patch.object(producer, "cf", side_effect=fake_ai):
            item, jpg = producer.make_bundle(story)
        self.assertTrue(item["ready"])
        self.assertEqual(item["image_sha256"], hashlib.sha256(jpg).hexdigest())
        self.assertEqual(item["bundle_digest"], producer.pub.queue_digest(item))
        self.assertIn("AI-generated illustration", item["caption"])
        self.assertIn(source, item["caption"])
        self.assertEqual(datetime.fromisoformat(item["expires_utc"]) -
                         datetime.fromisoformat(item["published_utc"]),
                         producer.timedelta(days=7))


if __name__ == "__main__":
    unittest.main()
