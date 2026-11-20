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
    def test_utc_triggers_cover_three_attempts_in_each_ist_slot(self):
        workflow = (app.ROOT / ".github/workflows/oddnews73.yml").read_text()
        schedule = workflow.split("  schedule:\n", 1)[1].split("  workflow_dispatch:", 1)[0]
        self.assertNotIn("timezone:", schedule)
        crons = re.findall(r"cron: '([^']+)'", schedule)
        self.assertEqual(len(crons), 2)
        for month in (1, 7, 11):
            local_times = []
            slots = {}
            for cron in crons:
                minute, hour, day, month_field, weekday = cron.split()
                self.assertEqual((day, month_field, weekday), ("*", "*", "*"))
                for h in map(int, hour.split(",")):
                    for m in map(int, minute.split(",")):
                        at = datetime(2026, month, 20, h, m, tzinfo=timezone.utc)
                        local = at.astimezone(app.IST)
                        local_times.append((local.hour, local.minute))
                        slot = app.scheduled_slot(at)
                        self.assertIsNotNone(slot)
                        slots[slot] = slots.get(slot, 0) + 1
            self.assertCountEqual(local_times, [(h, m) for h in (9, 14, 21)
                                               for m in (7, 27, 47)])
            self.assertEqual(sorted(slots.values()), [3, 3, 3])

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


if __name__ == "__main__":
    unittest.main()
