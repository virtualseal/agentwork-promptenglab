from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
import random
import tempfile
import unittest
from app.domain import Settings, Blocked, eligible, distance_miles, slack_text, Place
from app.sources import FileLists, Snapshot, Lookup, TemporaryFailure
from app.service import run, due
from app.store import Store
from app.cli import worker_lock

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime.fromisoformat('2026-10-29T10:00:00-07:00')

class Slack:
    def __init__(self):self.messages={};self.calls=0;self.failure=None
    def lookup(self,channel,key):
        return Lookup('present',self.messages[key]) if key in self.messages else Lookup('absent')
    def post(self,channel,text,key):
        self.calls+=1
        if self.failure=='temporary':raise TemporaryFailure()
        self.messages[key]='message-1'
        if self.failure=='lost':raise TimeoutError()
        return 'message-1'

class PickerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.settings=replace(Settings.load(ROOT/'.locals.example.json'),state_path=str(Path(self.temp.name)/'state.db'))
        self.store=Store(self.settings.state_path);self.addCleanup(self.store.db.close)
        self.source=FileLists()
    def live(self):return replace(self.settings,mode='live',channel='C_TEST')
    def test_two_lists_union_dedup_and_radius(self):
        all_places=[p for name,path in self.settings.lists for p in self.source.fetch(name,path).places]
        actual=eligible(all_places,self.settings)
        self.assertEqual(len(actual),2)
        self.assertEqual(set(next(p for p in actual if p.identifier=='demo-near').sources),{'Want to Go','SF Bay Area'})
        self.assertTrue(all(distance_miles(self.settings.latitude,self.settings.longitude,p.latitude,p.longitude)<=15 for p in actual))
    def test_identity_bridge_deduplicates_every_input_order(self):
        from itertools import permutations
        original=self.source.fetch(*self.settings.lists[0]).places[0]
        a=replace(original,identifier='A',name='Old Name')
        b=replace(original,identifier='B',name='New Name')
        bridge=replace(a,name='New Name',sources=('SF Bay Area',))
        outcomes=[]
        for order in permutations((a,b,bridge)):
            result=eligible(order,self.settings)
            self.assertEqual(len(result),1)
            self.assertEqual(set(result[0].sources),{'Want to Go','SF Bay Area'})
            outcomes.append(result)
        self.assertTrue(all(result==outcomes[0] for result in outcomes))

    def test_radius_boundary(self):
        p=Place('id','N','A',self.settings.latitude+15/3958.7613*180/3.141592653589793,self.settings.longitude,'https://www.google.com/maps?q=test',('one',))
        self.assertEqual(eligible([p],self.settings),[p])
        self.assertEqual(eligible([replace(p,latitude=p.latitude+0.001)],self.settings),[])
    def test_schedule_thursday_pacific_summer_and_winter(self):
        for text,expected in [('2026-10-29T16:59:00+00:00',False),('2026-10-29T17:00:00+00:00',True),('2026-12-03T17:59:00+00:00',False),('2026-12-03T18:00:00+00:00',True),('2026-10-30T10:00:00-07:00',False)]:
            with self.subTest(text=text):self.assertEqual(due(self.settings,datetime.fromisoformat(text))[1],expected)
    def test_preview_restart_preserves_choice_and_never_sends(self):
        slack=Slack();first=run(self.settings,self.store,self.source,NOW,slack,rng=random.Random(1))
        self.assertEqual(first['status'],'previewed');self.assertIn("Today we're going to eat here",first['message'])
        second_store=Store(self.settings.state_path)
        try:second=run(self.settings,second_store,self.source,NOW,slack)
        finally:second_store.db.close()
        self.assertTrue(second['duplicate']);self.assertEqual(slack.calls,0)
    def test_incomplete_list_blocks_selection(self):
        class Partial:
            def fetch(self,name,ref):return Snapshot((),False)
        with self.assertRaises(Blocked):run(self.settings,self.store,Partial(),NOW)
        self.assertIsNone(self.store.get('preview','2026-10-29'))
    def test_missing_second_source_no_fallback(self):
        settings=replace(self.settings,lists=(self.settings.lists[0],('SF Bay Area',None)))
        with self.assertRaises(Blocked):run(settings,self.store,self.source,NOW)
        self.assertIsNone(self.store.get('preview','2026-10-29'))
    def test_missing_coordinates_blocks_import(self):
        path=Path(self.temp.name)/'bad.json';path.write_text(json.dumps([{'name':'A','category':'restaurant','address':'B','maps_url':'https://www.google.com/maps?q=x'}]))
        with self.assertRaises(Blocked):self.source.fetch('bad',path)
    def test_confirmed_send_is_idempotent_after_restart(self):
        slack=Slack();settings=self.live()
        self.assertEqual(run(settings,self.store,self.source,NOW,slack)['status'],'sent')
        another=Store(settings.state_path)
        try:self.assertTrue(run(settings,another,self.source,NOW,slack)['duplicate'])
        finally:another.db.close()
        self.assertEqual(slack.calls,1)
    def test_lost_ack_reconciles_without_second_post(self):
        slack=Slack();slack.failure='lost';settings=self.live()
        self.assertEqual(run(settings,self.store,self.source,NOW,slack)['status'],'uncertain')
        result=run(settings,self.store,self.source,NOW+timedelta(minutes=11),slack)
        self.assertTrue(result['reconciled']);self.assertEqual(slack.calls,1)
    def test_unknown_lookup_never_posts(self):
        slack=Slack();slack.lookup=lambda *args:Lookup('unknown')
        with self.assertRaises(Blocked):run(self.live(),self.store,self.source,NOW,slack)
        self.assertEqual(slack.calls,0)
    def test_retry_budget_and_backoff_survive_restart(self):
        slack=Slack();slack.failure='temporary';settings=self.live()
        self.assertEqual(run(settings,self.store,self.source,NOW,slack)['status'],'retry_wait')
        run(settings,self.store,self.source,NOW+timedelta(seconds=1),slack);self.assertEqual(slack.calls,1)
        for minute in (11,22):run(settings,self.store,self.source,NOW+timedelta(minutes=minute),slack)
        another=Store(settings.state_path)
        try:
            with self.assertRaises(Blocked):run(settings,another,self.source,NOW+timedelta(minutes=33),slack)
        finally:another.db.close()
        self.assertEqual(slack.calls,3)
    def test_pending_config_change_blocks_reroll(self):
        slack=Slack();slack.failure='temporary';settings=self.live();run(settings,self.store,self.source,NOW,slack)
        with self.assertRaises(Blocked):run(replace(settings,radius_miles=14),self.store,self.source,NOW+timedelta(minutes=11),slack)
        self.assertEqual(slack.calls,1)
    def test_disabled_live_adapter_blocks(self):
        with self.assertRaises(Blocked):run(self.live(),self.store,self.source,NOW)
        self.assertEqual(self.store.get('live','2026-10-29')['attempts'],0)
    def test_worker_exclusion(self):
        path=Path(self.temp.name)/'worker.lock'
        with worker_lock(path):
            with self.assertRaises(Blocked):
                with worker_lock(path):pass
    def test_slack_mentions_escaped(self):
        place=self.source.fetch(*self.settings.lists[0]).places[0]
        text=slack_text(replace(place,name='<!channel> & dinner'))
        self.assertNotIn('<!channel>',text);self.assertIn('&lt;!channel&gt;',text)
    def test_empty_eligible_set_blocks(self):
        class Empty:
            def fetch(self,*args):return Snapshot(())
        with self.assertRaises(Blocked):run(self.settings,self.store,Empty(),NOW)

if __name__=='__main__':unittest.main()
