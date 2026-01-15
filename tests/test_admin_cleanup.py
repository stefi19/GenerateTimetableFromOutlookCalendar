import unittest
import tempfile
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, date


class AdminCleanupTests(unittest.TestCase):
    def setUp(self):
        # prevent background threads from starting when importing app
        os.environ['DISABLE_BACKGROUND_TASKS'] = '1'
        import app as app_module
        self.app = app_module
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.app.DB_PATH = self.root / 'app.db'
        (self.root / 'playwright_captures').mkdir(parents=True, exist_ok=True)
        self.app.init_db()

    def tearDown(self):
        try:
            self.tmpdir.cleanup()
        finally:
            os.environ.pop('DISABLE_BACKGROUND_TASKS', None)

    def test_admin_endpoint_triggers_cleanup(self):
        # Add an old manual event
        old_dt = (date.today() - timedelta(days=90)).isoformat() + 'T09:00:00'
        old_ev = {'start': old_dt, 'end': None, 'title': 'Old', 'location': '', 'raw': {}, 'created_at': datetime.now().isoformat()}
        self.app.add_manual_event_db(old_ev)

        # Create events.json with an old event
        events_file = self.root / 'playwright_captures' / 'events.json'
        events = [
            {'start': (date.today() - timedelta(days=80)).isoformat() + 'T08:00:00', 'title': 'file-old'},
        ]
        with open(events_file, 'w', encoding='utf-8') as f:
            json.dump(events, f)

        client = self.app.app.test_client()
        # use default password ADMIN_PASSWORD ('admin123') -> Basic auth header
        import base64
        token = base64.b64encode(b'admin:admin123').decode('ascii')
        headers = {'Authorization': f'Basic {token}'}

        resp = client.post('/admin/cleanup_old_events', headers=headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, dict)
        self.assertGreaterEqual(data.get('manual_deleted', 0), 1)
        # verify file pruned
        with open(events_file, 'r', encoding='utf-8') as f:
            remaining = json.load(f)
        self.assertEqual(len(remaining), 0)


if __name__ == '__main__':
    unittest.main()
