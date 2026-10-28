"""Local preview runner. Live adapters are deliberately unavailable."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['preview','once','watch'])
    parser.add_argument('--config',default='.locals.example.json')
    parser.add_argument('--now',help='Aware ISO timestamp, preview only')
    parser.add_argument('--seed',type=int,help='Repeatable preview selection only')
    args=parser.parse_args()
    try:
        settings=Settings.load(args.config)
        if settings.mode!='preview':raise Blocked('Live execution disabled until approved Maps/Slack adapters are installed and reviewed')
        if args.action!='preview' and (args.now or args.seed is not None):
            raise Blocked('Clock/seed overrides are preview-only')
        clock=lambda:datetime.now(timezone.utc)
        if args.now:
            fixed=datetime.fromisoformat(args.now);clock=lambda:fixed
        with worker_lock(settings.state_path+'.lock'):
            store=Store(settings.state_path)
            try:
                while True:
                    result=run(settings,store,FileLists(),clock(),rng=random.Random(args.seed) if args.seed is not None else None)
                    print(json.dumps(result),flush=True)
                    if args.action!='watch':return 0
                    time.sleep(60)
            finally:store.db.close()
    except (Blocked,ValueError,KeyError,OSError) as error:
        print(json.dumps({'status':'blocked','detail':str(error)}));return 1
    except KeyboardInterrupt:return 0


if __name__=='__main__':raise SystemExit(main())
