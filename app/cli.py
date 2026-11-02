"""Public import, safe preview and explicitly reviewed scoped worker."""
import argparse
from dataclasses import replace
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import random
import time
from .domain import Settings, Blocked
from .service import run
from .sources import FileLists
from .store import Store


@contextmanager
def worker_lock(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Blocked('Another worker owns this state file')
        try:yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


class RefreshingLists:
    """Service collects once per new week; retries use its durable saved choice."""
    def __init__(self,settings,classify=None,fetch=None):
        from .maps_import import BrowserCategories
        self.settings=settings
        self.classify=classify if classify is not None else BrowserCategories(settings.category_python)
        self.fetch_public=fetch

    def fetch(self,name,reference):
        from .maps_import import import_lists,ImportedLists
        options={} if self.fetch_public is None else {'fetch':self.fetch_public}
        with worker_lock(self.settings.maps_snapshot+'.lock'):
            import_lists(self.settings,self.classify,self.settings.maps_snapshot,**options)
            return ImportedLists(self.settings.maps_snapshot,self.settings).fetch(name,reference)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['preview','once','watch','import-maps'])
    parser.add_argument('--config',default='restaurant.config.json')
    parser.add_argument('--now',help='Aware ISO timestamp, preview only')
    parser.add_argument('--seed',type=int,help='Repeatable preview selection only')
    args=parser.parse_args()
    try:
        settings=Settings.load(args.config)
        if args.action == 'import-maps':
            from .maps_import import import_lists, BrowserCategories
            if not settings.maps_snapshot or not settings.category_python:
                raise Blocked('Configure maps_snapshot and category_python for public import')
            if args.now or args.seed is not None:
                raise Blocked('Clock/seed overrides are preview-only')
            with worker_lock(settings.maps_snapshot+'.lock'):
                payload = import_lists(settings, BrowserCategories(settings.category_python), settings.maps_snapshot)
            print(json.dumps({'status':'imported','evidence':payload['evidence'],
                              'unique_restaurants':payload['unique_restaurants']}))
            return 0
        if args.action == 'preview':
            settings = replace(settings, mode='preview', state_path=settings.state_path+'.preview')
        source = FileLists()
        if settings.maps_snapshot and settings.mode != 'live':
            from .maps_import import ImportedLists
            source = ImportedLists(settings.maps_snapshot, settings)
        slack = None
        if settings.mode == 'live':
            if (not settings.live_reviewed or not settings.maps_snapshot or not settings.category_python
                    or settings.channel != 'C0CCRQUR6G1'
                    or settings.timezone != 'America/Los_Angeles' or settings.send_time != '17:00'
                    or settings.radius_miles != 10
                    or len(settings.lists)!=1 or settings.lists[0][0]!='Want to go'
                    or settings.latitude != 37.54836 or settings.longitude != -122.31115):
                raise Blocked('Live execution requires reviewed configuration and complete Maps import')
            source=RefreshingLists(settings)
            from .broker_slack import BrokerSlack
            slack = BrokerSlack(os.environ['SLACK_BROKER_URL'],
                                os.environ['SLACK_BROKER_CAPABILITY'],os.environ['SLACK_WORKSPACE_ID'])
        if args.action!='preview' and (args.now or args.seed is not None):
            raise Blocked('Clock/seed overrides are preview-only')
        clock=lambda:datetime.now(timezone.utc)
        if args.now:
            fixed=datetime.fromisoformat(args.now);clock=lambda:fixed
        with worker_lock(settings.state_path+'.lock'):
            store=Store(settings.state_path)
            try:
                failures = 0
                while True:
                    try:
                        result=run(settings,store,source,clock(),slack=slack,
                                   rng=random.Random(args.seed) if args.seed is not None else None)
                        failures = 0
                        print(json.dumps(result),flush=True)
                    except (Blocked, ValueError, OSError):
                        failures += 1
                        print(json.dumps({'status':'blocked','detail':'Worker prerequisite unavailable',
                                          'consecutive_failures':failures}),flush=True)
                        if args.action != 'watch' or failures >= 3:
                            return 1
                    if args.action!='watch':return 0
                    time.sleep(min(600, 60 * (2 ** failures)))
            finally:store.db.close()
    except (Blocked,ValueError,KeyError,OSError) as error:
        print(json.dumps({'status':'blocked','detail':str(error)}));return 1
    except KeyboardInterrupt:return 0


if __name__=='__main__':raise SystemExit(main())
