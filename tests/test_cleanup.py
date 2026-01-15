import unittest
import tempfile
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, date


class CleanupTests(unittest.TestCase):
    def setUp(self):
        # prevent background threads from starting when importing app
        import os
        os.environ['DISABLE_BACKGROUND_TASKS'] = '1'
        # create isolated temp dir and point app DB and capture dir there
        import app as app_module
        self.app = app_module
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        # override DB path and ensure data dir exists
        self.app.DB_PATH = self.root / 'app.db'
        # ensure playwright_captures folder inside tempdir
        (self.root / 'playwright_captures').mkdir(parents=True, exist_ok=True)
        # initialize DB schema
        self.app.init_db()

    def tearDown(self):
        try:
            self.tmpdir.cleanup()
        except Exception:
            pass
        try:
            os.environ.pop('DISABLE_BACKGROUND_TASKS', None)
        except Exception:
            pass

    def test_cleanup_old_events_deletes_old_rows_and_prunes_file(self):
        # Insert manual events: one old (>60 days) and one recent
        old_dt = (date.today() - timedelta(days=90)).isoformat() + 'T09:00:00'
        recent_dt = (date.today() - timedelta(days=10)).isoformat() + 'T09:00:00'

        old_ev = {'start': old_dt, 'end': None, 'title': 'Old', 'location': '', 'raw': {}, 'created_at': datetime.now().isoformat()}
        recent_ev = {'start': recent_dt, 'end': None, 'title': 'Recent', 'location': '', 'raw': {}, 'created_at': datetime.now().isoformat()}

        old_id = self.app.add_manual_event_db(old_ev)
        rec_id = self.app.add_manual_event_db(recent_ev)

        # Insert extracurricular events: one old and one recent
        old_extra = {'title': 'OldX', 'organizer': 'Org', 'date': (date.today() - timedelta(days=95)).isoformat(), 'time': '10:00', 'location': '', 'category': '', 'description': '', 'created_at': datetime.now().isoformat()}
        rec_extra = {'title': 'RecX', 'organizer': 'Org', 'date': (date.today() + timedelta(days=2)).isoformat(), 'time': '11:00', 'location': '', 'category': '', 'description': '', 'created_at': datetime.now().isoformat()}
        old_eid = self.app.add_extracurricular_db(old_extra)
        rec_eid = self.app.add_extracurricular_db(rec_extra)

        # Create playwright_captures/events.json with an old and recent event
        events_file = self.root / 'playwright_captures' / 'events.json'
        events = [
            {'start': (date.today() - timedelta(days=80)).isoformat() + 'T08:00:00', 'title': 'file-old'},
            {'start': (date.today() + timedelta(days=1)).isoformat() + 'T08:00:00', 'title': 'file-recent'},
        ]
        with open(events_file, 'w', encoding='utf-8') as f:
            json.dump(events, f)

        # Create a per-calendar events_<hash>.json file and set its mtime to old
        cal_file = self.root / 'playwright_captures' / 'events_abcdef12.json'
        with open(cal_file, 'w', encoding='utf-8') as f:
            json.dump([{'start': (date.today() - timedelta(days=90)).isoformat() + 'T07:00:00', 'title': 'cal-old'}], f)
        # set mtime to 90 days ago
        old_time = (datetime.now() - timedelta(days=90)).timestamp()
        os.utime(cal_file, times=(old_time, old_time))

        # Run cleanup with 60-day cutoff, pass base_dir so function doesn't depend on CWD
        result = self.app.cleanup_old_events(cutoff_days=60, base_dir=self.root)

        # Expect old manual and old extracurricular removed, one events.json entry removed
        # and one per-calendar file removed
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get('manual_deleted'), 1)
        self.assertEqual(result.get('extracurricular_deleted'), 1)
        self.assertEqual(result.get('file_removed'), 1)
        self.assertEqual(result.get('calendar_files_removed'), 1)

        # Verify DB rows
        manual_rows = self.app.list_manual_events_db()
        self.assertEqual(len(manual_rows), 1)
        self.assertEqual(manual_rows[0]['title'], 'Recent')

        extra_rows = self.app.list_extracurricular_db()
        titles = [r['title'] for r in extra_rows]
        self.assertIn('RecX', titles)
        self.assertNotIn('OldX', titles)

        # Verify file pruned
        with open(events_file, 'r', encoding='utf-8') as f:
            remaining = json.load(f)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]['title'], 'file-recent')
        # per-calendar file should be removed
        self.assertFalse(cal_file.exists())


if __name__ == '__main__':
    unittest.main()
