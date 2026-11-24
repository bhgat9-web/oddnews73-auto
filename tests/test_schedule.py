"""Check UTC triggers against the real IST posting windows and retry guards."""
import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import oddnews73 as app


class ScheduleConfigurationTests(unittest.TestCase):
    def test_vps_timer_covers_three_attempts_in_each_ist_slot(self):
        timer = (app.ROOT / "vps/oddnews73-publisher.timer").read_text()
        configured = re.findall(r"OnCalendar=\*-\*-\* (\d\d):(\d\d):00", timer)
        expected = [(f"{hour:02d}", f"{minute:02d}")
                    for hour in (9, 14, 21) for minute in (7, 17, 27)]
        self.assertCountEqual(configured, expected)
        for hour, minute in configured:
            local = datetime(2026, 11, 20, int(hour), int(minute), tzinfo=app.IST)
            self.assertIsNotNone(app.scheduled_slot(local))

        workflow = (app.ROOT / ".github/workflows/oddnews73.yml").read_text()
        self.assertNotIn("  schedule:", workflow)

    def test_final_backup_skips_a_successful_slot_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slot = "2026-11-20T09:07+0530"
            state = root / "state.json"
            state.write_text(json.dumps({"entries": [
                {"status": "posted", "scheduled_slot": slot, "slug": "posted"}
            ], "seen_links": []}))
            before = state.read_bytes()
            with patch.object(app, "STATE", state), \
                    patch.object(app, "RUN", root / "run.json"), \
                    patch.object(app, "SLOT_RESULT", root / "result.json"), \
                    patch.object(app, "NOW", return_value=datetime(2026, 11, 20, 9, 47, tzinfo=app.IST)), \
                    patch.dict("os.environ", {"LIVE_PUBLISH": "true", "AUTO_PUBLISH": "true",
                                             "STRICT_SCHEDULE": "true"}), \
                    patch.object(app.requests, "get") as get, \
                    patch.object(app.requests, "post") as post:
                app.prepare_queued()
                self.assertFalse(app.RUN.exists())
                self.assertEqual(json.loads(app.SLOT_RESULT.read_text())["status"], "already_posted")
                get.assert_not_called()
                post.assert_not_called()
            self.assertEqual(state.read_bytes(), before)

    def test_old_pending_cannot_be_reused_in_a_new_slot(self):
        for old_slot in ("2026-11-19T09:07+0530", None):
            with self.subTest(old_slot=old_slot), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = root / "state.json"
                state.write_text(json.dumps({"entries": [
                    {"status": "pending", "scheduled_slot": old_slot, "slug": "old"}
                ], "seen_links": []}))
                before = state.read_bytes()
                with patch.object(app, "STATE", state), \
                        patch.object(app, "RUN", root / "run.json"), \
                        patch.object(app, "SLOT_RESULT", root / "result.json"), \
                        patch.object(app, "NOW", return_value=datetime(2026, 11, 20, 9, 47, tzinfo=app.IST)), \
                        patch.dict("os.environ", {"LIVE_PUBLISH": "true", "AUTO_PUBLISH": "true",
                                                 "STRICT_SCHEDULE": "true"}), \
                        patch.object(app, "validate_publication_authorization") as authorize:
                    with self.assertRaisesRegex(RuntimeError, "another slot"):
                        app.prepare_queued()
                    self.assertFalse(app.RUN.exists())
                    self.assertEqual(json.loads(app.SLOT_RESULT.read_text())["status"],
                                     "blocked_stale_pending")
                    authorize.assert_not_called()
                self.assertEqual(state.read_bytes(), before)



class DelayedScheduleTests(unittest.TestCase):
    def test_observed_late_runs_stay_in_one_evening_slot(self):
        expected = "2026-11-20T21:07+0530"
        for hour, minute in ((21, 7), (22, 43), (23, 20), (23, 59)):
            self.assertEqual(app.scheduled_slot(
                datetime(2026, 11, 20, hour, minute, tzinfo=app.IST)), expected)

    def test_window_boundaries_and_midnight_never_replay_yesterday(self):
        for hour in (9, 14):
            self.assertIsNotNone(app.scheduled_slot(
                datetime(2026, 11, 20, hour + 3, 6, tzinfo=app.IST)))
            self.assertIsNone(app.scheduled_slot(
                datetime(2026, 11, 20, hour + 3, 7, tzinfo=app.IST)))
        for hour, minute in ((0, 0), (0, 6), (8, 59), (9, 6), (18, 0), (21, 6)):
            self.assertIsNone(app.scheduled_slot(
                datetime(2026, 11, 21, hour, minute, tzinfo=app.IST)))

    def test_late_backup_does_not_publish_a_second_story(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            state.write_text(json.dumps({"entries": [
                {"status": "posted", "scheduled_slot": "2026-11-20T21:07+0530",
                 "slug": "already-posted"}
            ], "seen_links": []}))
            with patch.object(app, "STATE", state), \
                    patch.object(app, "RUN", root / "run.json"), \
                    patch.object(app, "SLOT_RESULT", root / "result.json"), \
                    patch.object(app, "NOW", return_value=datetime(2026, 11, 20, 23, 20, tzinfo=app.IST)), \
                    patch.dict("os.environ", {"LIVE_PUBLISH": "true", "AUTO_PUBLISH": "true",
                                             "STRICT_SCHEDULE": "true"}), \
                    patch.object(app.requests, "get") as get, \
                    patch.object(app.requests, "post") as post:
                app.prepare_queued()
                self.assertFalse(app.RUN.exists())
                self.assertEqual(json.loads(app.SLOT_RESULT.read_text())["status"], "already_posted")
                get.assert_not_called()
                post.assert_not_called()

    def test_preflight_rejects_ended_slot_before_any_network(self):
        rec = {"slug": "late", "status": "pending", "demo": False,
               "scheduled_slot": "2026-11-20T21:07+0530"}
        with patch.object(app, "load", return_value={"entries": [rec]}), \
                patch.object(app, "current", return_value=rec), \
                patch.object(app, "validate_publication_authorization"), \
                patch.object(app, "NOW", return_value=datetime(2026, 11, 21, 0, 0, tzinfo=app.IST)), \
                patch.dict("os.environ", {"LIVE_PUBLISH": "true"}), \
                patch.object(app.requests, "get") as get, \
                patch.object(app, "verify_account") as account:
            with self.assertRaisesRegex(RuntimeError, "posting window"):
                app.preflight("https://bhgat9-web.github.io/oddnews73-auto/")
            get.assert_not_called()
            account.assert_not_called()

    def test_media_finishing_after_midnight_is_not_published(self):
        rec = {"slug": "late", "status": "in_flight", "demo": False,
               "scheduled_slot": "2026-11-20T21:07+0530",
               "title": "Test", "caption": "Test", "image_url": "https://example.com/test.jpg"}
        st = {"entries": [rec], "verified_instagram_id": app.EXPECTED_ID}
        with patch.object(app, "load", return_value=st), \
                patch.object(app, "current", return_value=rec), \
                patch.object(app, "save"), \
                patch.object(app, "NOW", side_effect=[
                    datetime(2026, 11, 20, 23, 59, tzinfo=app.IST),
                    datetime(2026, 11, 21, 0, 0, tzinfo=app.IST)]), \
                patch.dict("os.environ", {"LIVE_PUBLISH": "true"}), \
                patch.object(app, "verify_account", return_value="test-token"), \
                patch.object(app, "ig", side_effect=[{"id": "container"}, {"status_code": "FINISHED"}]) as ig:
            with self.assertRaisesRegex(RuntimeError, "posting window"):
                app.publish()
            self.assertEqual(rec["status"], "not_published")
            self.assertEqual(ig.call_count, 2)
            self.assertFalse(any(call.args[1].endswith("/media_publish")
                                 for call in ig.call_args_list))


if __name__ == "__main__":
    unittest.main()

