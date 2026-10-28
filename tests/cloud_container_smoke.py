"""Offline Docker smoke: real launchers, identities, HTTP, durable restart.

Run as agentwork UID502; pass the dedicated test daemon via DOCKER_HOST.
Only dummy provider credentials enter disposable containers. No host mounts.
"""
import base64
import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid


def main():
    if os.getuid() != 502 or not os.environ.get('DOCKER_HOST'):
        raise SystemExit('Use agentwork UID502 and an explicit isolated DOCKER_HOST.')
    root = Path(__file__).resolve().parents[1]
    name = 'sdr-smoke-' + uuid.uuid4().hex[:10]
    containers = []
    def docker(*args):
        result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=240)
        if result.returncode:
            # All resources are disposable and contain dummy configuration only.
            raise RuntimeError(result.stderr[-2000:])
        return (result.stdout + (result.stderr if args[0]=='logs' else '')).strip()
    def request(container, path, raw=None, headers=None):
        code = ('import json,urllib.request; '
                'r=urllib.request.Request("http://[::1]:8080"+' + repr(path) +
                ',data=' + repr(raw) + ',headers=' + repr(headers or {}) + '); '
                'o=urllib.request.build_opener(urllib.request.ProxyHandler({})); '
                'print(o.open(r,timeout=8).read().decode())')
        output = docker('exec',container,'python','-c',code)
        return json.loads(output) if output else None
    def launch(role, scope, extra):
        container = name+'-'+role
        args = ['run','-d','--name',container,'--network',name,
                '--network-alias', 'nooks-verifier.railway.internal' if role=='verifier' else 'receiver']
        env = {'RAILWAY_PROJECT_ID':'dummy','RAILWAY_ENVIRONMENT_ID':'dummy',
               'SDR_ROLE':role,'CAPTURE_SCOPE':scope,'PORT':'8080',**extra}
        if role == 'receiver': args += ['--mount','type=volume,src='+name+',dst=/data']
        for key,value in env.items(): args += ['-e',key+'='+value]
        containers.append(container)
        docker(*args,name)
        for _ in range(50):
            try:
                request(container,'/healthz')
                break
            except RuntimeError as error:
                last_error = str(error)
                time.sleep(.2)
        else:
            raise RuntimeError('Container did not become healthy: '+last_error+' '+docker('logs',container))
        identity = docker('exec',container,'python','-c',
            'print("\\n".join(x for x in open("/proc/1/status") if x.startswith(("Uid:","Gid:"))))')
        expected = '502' if role=='receiver' else '503'
        for line in filter(str.strip, identity.splitlines()):
            assert line.split()[1:] == [expected]*4, identity
        return container
    try:
        with tempfile.TemporaryDirectory() as folder:
            context = Path(folder)
            shutil.copytree(root/'cloud'/'sdr',context/'cloud'/'sdr',ignore=shutil.ignore_patterns('__pycache__'))
            docker('build','-q','-t',name,'-f',str(context/'cloud'/'sdr'/'Dockerfile'),str(context))
        docker('network','create','--internal',name)
        docker('volume','create',name)
        now = int(time.time())
        scope = json.dumps({'workspace_id':'dummyworkspace','prospect_id':'123',
                            'not_before':now-10,'expires_at':now+600})
        extra = {'RAILWAY_VOLUME_MOUNT_PATH':'/data',
                 'VERIFIER_URL':'http://nooks-verifier.railway.internal:8080'}
        receiver = launch('receiver',scope,extra)
        public = request(receiver,'/identity')['public_key']
        launch('verifier',scope,{'RECEIVER_PUBLIC_KEY':public,'NOOKS_SIGNING_KEY':'dummy-smoke-key'})
        assert request(receiver,'/ready')['verifier_ready'] is True
        iso = lambda n: datetime.datetime.fromtimestamp(n,datetime.timezone.utc).isoformat()
        event = {'event':'call.logged','occurredAt':iso(now),'callData':{
            'workspaceId':'dummyworkspace','callId':'dummy-call','status':'completed','callDirection':'outbound',
            'prospectData':{'prospectId':'123'},'userData':{'userId':'dummy-rep'},
            'disposition':{'id':'dummy-disposition','name':'No Answer'},'startedAt':iso(now)}}
        raw = json.dumps(event).encode()
        stamp = str(int(time.time()*1000))
        signature = base64.b64encode(hmac.new(b'dummy-smoke-key',stamp.encode()+b'.'+raw,hashlib.sha256).digest()).decode()
        headers = {'x-webhook-signature':'t='+stamp+',s='+signature}
        assert request(receiver,'/api/sdr/webhooks/nooks',raw,headers) == {'status':'captured'}
        docker('rm','-f',receiver)
        containers.remove(receiver)
        receiver = launch('receiver',scope,extra)
        assert request(receiver,'/identity')['public_key'] == public
        assert request(receiver,'/ready')['event_count'] == 1
        assert request(receiver,'/api/sdr/webhooks/nooks',raw,headers) == {'status':'duplicate'}
        print('PASS: both Linux roles dropped privileges; private HTTP verification, volume initialization, signed capture and restart deduplication succeeded.')
    finally:
        for container in containers:
            subprocess.run(['docker','rm','-f',container],capture_output=True)
        for resource in ('volume','network','image'):
            subprocess.run(['docker',resource,'rm',name],capture_output=True)


if __name__ == '__main__': main()
