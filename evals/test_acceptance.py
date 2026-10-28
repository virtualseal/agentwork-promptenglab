"""Product scenarios kept separate from unit tests; no provider calls."""
from datetime import datetime
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from app.domain import Settings
from app.service import run
from app.sources import FileLists
from app.store import Store

class Acceptance(unittest.TestCase):
    def test_thursday_message_from_both_fixture_lists_and_friday_silence(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            settings=replace(Settings.load(root/'.locals.example.json'),state_path=str(Path(temp)/'state.db'))
            store=Store(settings.state_path)
            try:
                before=run(settings,store,FileLists(),datetime.fromisoformat('2026-12-03T17:59:00+00:00'))
                self.assertEqual(before['status'],'idle')
                result=run(settings,store,FileLists(),datetime.fromisoformat('2026-12-03T18:00:00+00:00'))
                self.assertEqual(result['status'],'previewed')
                self.assertIn("Today we're going to eat here: Sample",result['message'])
                self.assertIn('Google Maps',result['message'])
                friday=run(settings,store,FileLists(),datetime.fromisoformat('2026-12-04T18:00:00+00:00'))
                self.assertEqual(friday['status'],'idle')
            finally:store.db.close()
