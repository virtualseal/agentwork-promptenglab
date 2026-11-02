"""Offline real-container verification; no provider credentials or requests."""
import os
if __package__:
    from .verification_identity import require_verification_identity,verification_hosted
else:
    from verification_identity import require_verification_identity,verification_hosted
require_verification_identity()

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True,help='Explicit dedicated Docker endpoint')
    parser.add_argument('--image',default='thursday-worker:local')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent.parent
    config=root/'.review/build-runtime/docker-client';config.mkdir(parents=True,exist_ok=True)
    command=['docker','--config',str(config),'--host',args.host]
    def invoke(extra,**kwargs):
        return subprocess.run(command+extra,check=True,text=True,timeout=90,**kwargs)
    image=json.loads(invoke(['image','inspect',args.image],capture_output=True).stdout)[0]
    assert image['Os']=='linux' and image['Architecture']=='amd64'
    assert image['Config']['User']=='502:502'
    # Pin container execution to the inspected image ID, not a mutable tag.
    image_id=image['Id']
    files=[*root.glob('app/*.py'),root/'run',root/'deployment/worker.py',root/'deployment/worker.config.json',root/'deployment/worker.Dockerfile']
    expected={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    payload='''import os,json,hashlib,sqlite3
from pathlib import Path
assert os.getuid()==502
assert not any(name in os.environ for name in ['SLACK_BOT_TOKEN','RAILWAY_TOKEN','ANTHROPIC_API_KEY'])
assert not Path('/app/admin').exists()
expected=EXPECTED
assert all(hashlib.sha256(Path('/app',name).read_bytes()).hexdigest()==digest for name,digest in expected.items())
from app.domain import Settings
settings=Settings.load('/app/deployment/worker.config.json')
assert settings.mode=='preview' and not settings.live_reviewed
assert settings.send_time=='17:00' and settings.timezone=='America/Los_Angeles'
assert settings.radius_miles==10 and len(settings.lists)==1 and settings.lists[0][0]=='Want to go'
assert settings.channel=='C0CCRQUR6G1'
assert settings.state_path.startswith('/data/worker/') and settings.maps_snapshot.startswith('/data/worker/')
assert Path(settings.category_python).is_file()
from importlib.metadata import version
for package,expected_version in [('playwright','1.60.0'),('pyee','13.0.1'),('greenlet','3.5.6'),('typing-extensions','4.16.0')]:
    assert version(package)==expected_version
from app.maps_categories import primary_metadata
from playwright.sync_api import sync_playwright
with sync_playwright() as runtime:
    browser=runtime.chromium.launch(headless=True)
    context=browser.new_context(service_workers='block')
    context.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html',body='<h1>Synthetic Restaurant</h1><button class="DkEaL">Restaurant</button><button data-item-id="address" aria-label="Address: Synthetic Street"></button>'))
    page=context.new_page();page.goto('https://www.google.com/maps?cid=12345')
    evidence=primary_metadata(page,'12345')
    assert evidence['place_name']=='Synthetic Restaurant' and evidence['category']=='Restaurant'
    assert evidence['address']=='Synthetic Street'
    context.close();browser.close()
from app.store import Store
store=Store(settings.state_path)
with store.db:store.db.execute("INSERT INTO weekly VALUES ('preview','synthetic','context','{}','key','pending',1,0,NULL,NULL)")
store.db.close()
print('Linux/amd64 UID502, current image source bytes, browser DOM evidence and persistent SQLite write verified')
'''.replace('EXPECTED',repr(expected))
    invocation=os.environ.get('THURSDAY_VERIFY_RUN',uuid.uuid4().hex)
    if len(invocation)!=32 or any(c not in '0123456789abcdef' for c in invocation):raise ValueError('Invalid verification invocation')
    volume='thursday-verify-'+invocation
    invoke(['volume','create',volume],capture_output=True)
    container='thursday-check-'+invocation
    try:
        options=['run','--rm','--name',container,'--platform','linux/amd64','--user','502:502','--read-only','--network','none','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,nosuid,size=256m','--mount','type=volume,source='+volume+',target=/data/worker']
        invoke(options+['-i',image_id,'/home/agentwork/venv/bin/python','-B','-'],input=payload)
        recovery="from app.store import Store;s=Store('/data/worker/weekly-1700-10mi.sqlite3');r=s.get('preview','synthetic');assert r['delivery_key']=='key' and r['attempts']==1;s.db.close();print('Second-container restart recovery verified')"
        invoke(options+[image_id,'/usr/bin/python3','-B','-c',recovery])
        print(json.dumps({'status':'passed','image_id':image_id,'platform':'linux/amd64','provider_calls':0,'real_cloud_storage_verified':False}))
    finally:
        # A client timeout does not stop the remote process. Remove this exact
        # uniquely named test container before removing its synthetic volume.
        cleaned=subprocess.run(command+['container','rm','--force',container],text=True,capture_output=True,timeout=20)
        if cleaned.returncode and 'No such container' not in cleaned.stderr:
            raise RuntimeError('Test container cleanup failed; preserve volume '+volume)
        invoke(['volume','rm',volume],capture_output=True)


if __name__=='__main__':main()
