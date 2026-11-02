"""Current user objective: Want to go only,10 miles,Thursday17 Pacific."""
from dataclasses import replace
from datetime import datetime
import json,math,tempfile,unittest
from pathlib import Path
from app.domain import Settings,Place,eligible
from app.service import due,run
from app.store import Store
from app.sources import Snapshot,Lookup
ROOT=Path(__file__).resolve().parents[1]

class ScheduleTests(unittest.TestCase):
    def setUp(self):self.settings=Settings.load(ROOT/'restaurant.config.json')
    def test_actual_default_scope(self):
        s=self.settings
        self.assertEqual(s.send_time,'17:00');self.assertEqual(s.timezone,'America/Los_Angeles')
        self.assertEqual(s.radius_miles,10);self.assertEqual(s.channel,'C0CCRQUR6G1')
        self.assertEqual([n for n,r in s.lists],['Want to go'])
        self.assertFalse(s.live_reviewed)
    def test_thursday_5pm_boundaries_across_daylight_saving(self):
        for before,at in [('2026-10-29T23:59:00+00:00','2026-10-30T00:00:00+00:00'),
                          ('2026-12-04T00:59:00+00:00','2026-12-04T01:00:00+00:00')]:
            self.assertFalse(due(self.settings,datetime.fromisoformat(before))[1])
            self.assertTrue(due(self.settings,datetime.fromisoformat(at))[1])
        self.assertFalse(due(self.settings,datetime.fromisoformat('2026-10-31T00:00:00+00:00'))[1])
    def test_ten_mile_boundary_and_single_list_send_recovery(self):
        s=self.settings
        def place(i,miles):return Place(i,'Synthetic '+i,'Synthetic address',s.latitude+miles/3958.7613*180/math.pi,s.longitude,'https://www.google.com/maps?q=synthetic',('Want to go',))
        near,edge,far=place('near',2),place('edge',10),place('far',10.01)
        self.assertEqual([p.identifier for p in eligible([near,edge,far],s)],['edge','near'])
        class Source:
            def __init__(self):self.names=[]
            def fetch(self,name,reference):self.names.append(name);return Snapshot((near,edge,far))
        class Slack:
            def __init__(self):self.sent={};self.calls=0
            def lookup(self,ch,key):return Lookup('present','123.456') if key in self.sent else Lookup('absent')
            def post(self,ch,text,key):self.calls+=1;self.sent[key]=text;raise TimeoutError()
        source=Source();slack=Slack()
        with tempfile.TemporaryDirectory() as temporary:
            settings=replace(s,mode='live',state_path=str(Path(temporary)/'state.db'))
            store=Store(settings.state_path)
            now=datetime.fromisoformat('2026-10-30T00:00:00+00:00')
            try:self.assertEqual(run(settings,store,source,now,slack)['status'],'uncertain')
            finally:store.db.close()
            store=Store(settings.state_path)
            try:self.assertTrue(run(settings,store,source,now,slack)['reconciled'])
            finally:store.db.close()
            self.assertEqual(source.names,['Want to go']);self.assertEqual(slack.calls,1)
            self.assertTrue(all('Synthetic far' not in text for text in slack.sent.values()))
