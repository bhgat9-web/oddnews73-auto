import base64
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import sys
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import editorial_visuals as visuals
import oddnews73 as app


class VisualTests(unittest.TestCase):
    def brief(self):
        return {"headline": "Doomscrolling before screens",
                "subtitle": "A 16th-century book turned disasters into art.",
                "category": "STRANGE HISTORY", "scene": "An open illuminated manuscript."}

    def test_paid_generation_requires_enablement(self):
        with patch.dict(os.environ, {"AI_VISUALS_ENABLED": "false"}), \
                patch.object(visuals.requests, "post") as post:
            with self.assertRaises(RuntimeError):
                visuals.generate_poster({}, Path("unused.jpg"), None, None)
            post.assert_not_called()

    def test_category_and_overlong_headline_are_rejected(self):
        for field, value in (("category", "SPACE ODDITIES"), ("headline", "word " * 12)):
            brief = self.brief()
            brief[field] = value
            with self.assertRaises(RuntimeError):
                visuals.validate_brief(brief)

    def test_no_images_from_thinking_or_invalid_bytes(self):
        for payload in (
            {"steps": [{"type": "thought", "content": [{"type": "image", "data": "abc"}]}]},
            {"steps": [{"type": "model_output", "content": [{"type": "text", "text": "refused"}]}]},
        ):
            with self.assertRaises(RuntimeError):
                visuals.decode_image(payload)

    def test_accepts_final_image_with_valid_dimensions(self):
        data = io.BytesIO()
        Image.new("RGB", (1024, 1280), "orange").save(data, "JPEG")
        payload = {"steps": [{"type": "model_output", "content": [{
            "type": "image", "data": base64.b64encode(data.getvalue()).decode()
        }]}]}
        self.assertEqual(visuals.decode_image(payload).size, (1024, 1280))

    def test_paid_error_is_not_retried_or_logged(self):
        response = Mock(ok=False, text="secret remote details")
        with patch.object(visuals.requests, "post", return_value=response) as post:
            with self.assertRaisesRegex(RuntimeError, "^AI illustration unavailable$"):
                visuals.make_art(self.brief(), "test-key")
            self.assertEqual(post.call_count, 1)
            body = post.call_args.kwargs["json"]
            self.assertEqual(body["response_format"]["image_size"], "1K")
            self.assertEqual(body["model"], visuals.IMAGE_MODEL)

    def test_layout_fits_and_inserts_exact_logo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "poster.jpg"
            with patch.object(app, "add_official_logo", wraps=app.add_official_logo) as logo:
                visuals.render_poster(
                    {"source": "Smithsonian Smart News",
                     "published_utc": "2026-11-18T00:00:00+00:00"},
                    self.brief(), Image.new("RGB", (1024, 1280), (130, 60, 20)),
                    path, app.font, logo)
                logo.assert_called_once()
            with Image.open(path) as poster:
                self.assertEqual(poster.size, (1080, 1350))
                self.assertEqual(poster.format, "JPEG")

    def test_visual_failure_does_not_mark_story_seen_or_leave_a_run(self):
        story = {"title": "A strange historic manuscript", "link": "https://nasa.gov/test",
                 "source": "NASA", "published_utc": "2026-11-18T00:00:00+00:00"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(app, "STATE", root / "state.json"), \
                    patch.object(app, "RUN", root / "run.json"), \
                    patch.object(app, "SITE", root / "site"), \
                    patch.object(app, "choose", return_value=story), \
                    patch.object(app, "caption", return_value="Factual caption"), \
                    patch.object(app, "graphic", side_effect=RuntimeError("No image")), \
                    patch.dict(os.environ, {"LIVE_PUBLISH": "false", "AI_VISUALS_ENABLED": "true"}):
                app.prepare()
                self.assertFalse(app.RUN.exists())
                self.assertFalse(app.STATE.exists())


if __name__ == "__main__":
    unittest.main()
