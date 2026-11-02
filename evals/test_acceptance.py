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
            settings=replace(Settings.load(root/'tests/fixtures/two-list-settings.json'),state_path=str(Path(temp)/'state.db'))
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

    def test_complete_public_import_to_preview_uses_both_sources_without_provider_calls(self):
        from unittest.mock import patch
        from app.maps_import import LISTS, import_lists, ImportedLists
        import json
        root = Path(__file__).resolve().parents[1]
        settings = Settings.load(root / 'tests/fixtures/two-list-settings.json')
        specs = tuple((name, url, identity, 1) for name, url, identity, count in LISTS)
        responses = {}
        for name, url, identity, count in specs:
            endpoint = 'https://www.google.com/maps/preview/entitylist/getlist?pb=!1s'+identity+'!4i10000!6b1'
            responses[url] = '<link href="'+endpoint.replace('10000', '500')+'">'
            data = [None] * 21
            data[0] = [identity]; data[4] = name; data[12] = 1
            data[8] = [[None, [None, None, None, None, '1 Synthetic Avenue',
                              [None, None, 37.55, -122.31], ['1', '42']], 'Synthetic Restaurant']]
            responses[endpoint] = json.dumps([data, '', None, None, None, None, None])
        def classify(row):
            return dict(cid=row['id'], name=row['name'], category='Restaurant',
                        status='verified_public_category', final_url=row['maps_url'])
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / 'maps.json'
            import_lists(settings, classify, snapshot, responses.__getitem__, specs)
            settings = replace(settings, lists=tuple((s[0], None) for s in specs),
                               maps_snapshot=str(snapshot), state_path=str(Path(temp) / 'state.db'))
            with patch('app.maps_import.LISTS', specs):
                source = ImportedLists(snapshot, settings)
            store = Store(settings.state_path)
            try:
                result = run(settings, store, source, datetime.fromisoformat('2026-12-03T18:00:00+00:00'))
                self.assertEqual(result['status'], 'previewed')
                self.assertEqual(set(result['sources']), {s[0] for s in specs})
                self.assertIn('Synthetic Restaurant', result['message'])
                self.assertIn('1 Synthetic Avenue', result['message'])
            finally:
                store.db.close()

    def test_current_goal_imports_only_want_to_go_and_excludes_over_ten_miles(self):
        import json,math
        from app.maps_import import LISTS,import_lists,ImportedLists
        root=Path(__file__).resolve().parents[1]
        settings=Settings.load(root/'restaurant.config.json')
        want=LISTS[0];calls=[]
        endpoint='https://www.google.com/maps/preview/entitylist/getlist?pb=!1s'+want[2]+'!4i10000!6b1'
        entries=[]
        for cid,miles in [('1',5),('2',10.1)]:
            lat=settings.latitude+miles/3958.7613*180/math.pi
            entries.append([None,[None,None,None,None,'Synthetic address',[None,None,lat,settings.longitude],['1',cid]],'Synthetic '+cid])
        raw=[None]*21;raw[0]=[want[2]];raw[4]=want[0];raw[12]=2;raw[8]=entries
        responses={want[1]:'<link href="'+endpoint+'">',endpoint:json.dumps([raw,'',None,None,None,None,None])}
        def fetch(url):calls.append(url);return responses[url]
        def classify(row):return dict(cid=row['id'],name=row['name'],category='Restaurant',status='verified_public_category',final_url=row['maps_url'])
        with tempfile.TemporaryDirectory() as temporary:
            snapshot=Path(temporary)/'maps.json'
            payload=import_lists(settings,classify,snapshot,fetch)
            self.assertEqual(set(payload['lists']),{'Want to go'})
            self.assertEqual([p['id'] for p in payload['lists']['Want to go']],['1'])
            settings=replace(settings,maps_snapshot=str(snapshot),state_path=str(Path(temporary)/'state.db'))
            source=ImportedLists(snapshot,settings);store=Store(settings.state_path)
            try:
                result=run(settings,store,source,datetime.fromisoformat('2026-10-30T00:00:00+00:00'))
                self.assertEqual(result['status'],'previewed')
                self.assertIn('Synthetic 1',result['message']);self.assertNotIn('Synthetic 2',result['message'])
                self.assertEqual(list(result['sources']),['Want to go'])
            finally:store.db.close()
        self.assertEqual(calls,[want[1],endpoint])

    def test_live_weekly_selection_refreshes_list_but_restarts_reuse_saved_choice(self):
        import json
        from app.cli import RefreshingLists
        from app.maps_import import LISTS
        from app.sources import Lookup
        root=Path(__file__).resolve().parents[1];settings=Settings.load(root/'restaurant.config.json')
        want=LISTS[0];cid=['101'];calls=[]
        endpoint='https://www.google.com/maps/preview/entitylist/getlist?pb=!1s'+want[2]+'!4i10000!6b1'
        def fetch(url):
            calls.append(url)
            if url==want[1]:return '<link href="'+endpoint+'">'
            self.assertEqual(url,endpoint)
            data=[None]*21;data[0]=[want[2]];data[4]=want[0];data[12]=1
            data[8]=[[None,[None,None,None,None,'Synthetic address',[None,None,settings.latitude,settings.longitude],['1',cid[0]]],'Synthetic '+cid[0]]]
            return json.dumps([data,'',None,None,None,None,None])
        def classify(row):return dict(cid=row['id'],name=row['name'],category='Restaurant',status='verified_public_category',final_url=row['maps_url'])
        class Slack:
            def __init__(self):self.messages={}
            def lookup(self,ch,key):return Lookup('present',self.messages[key][0]) if key in self.messages else Lookup('absent')
            def post(self,ch,text,key):self.messages[key]=('123.456',text);return '123.456'
        slack=Slack()
        with tempfile.TemporaryDirectory() as temporary:
            settings=replace(settings,mode='live',maps_snapshot=str(Path(temporary)/'maps.json'),state_path=str(Path(temporary)/'state.db'))
            source=RefreshingLists(settings,classify,fetch)
            now=datetime.fromisoformat('2026-10-30T00:00:00+00:00')
            store=Store(settings.state_path)
            try:self.assertEqual(run(settings,store,source,now,slack)['status'],'sent')
            finally:store.db.close()
            self.assertEqual(len(calls),2)
            cid[0]='202' # Changed Google list must not affect this week's saved delivery.
            store=Store(settings.state_path)
            try:self.assertTrue(run(settings,store,RefreshingLists(settings,classify,fetch),now,slack)['duplicate'])
            finally:store.db.close()
            self.assertEqual(len(calls),2)
            store=Store(settings.state_path)
            try:self.assertEqual(run(settings,store,source,datetime.fromisoformat('2026-11-06T01:00:00+00:00'),slack)['status'],'sent')
            finally:store.db.close()
            self.assertEqual(len(calls),4);self.assertEqual(len(slack.messages),2)
            texts=[v[1] for v in slack.messages.values()]
            self.assertIn('Synthetic 101',texts[0]);self.assertIn('Synthetic 202',texts[1])
