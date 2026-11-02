"""Offline additive staging, never installation, key reads or provider requests."""
import argparse
import hashlib
import difflib
import json
from pathlib import Path
from .personal_railway import PROJECT,REPO,INTEGRATION,UUID
ROOT=Path('/Library/Application Support/CredentialProxy')
APP=Path(__file__).resolve().parents[1]


def render_proxy(source):
    replacements=[
      ('import github_publish\n','import github_publish\nimport personal_railway\n'),
      ("extras = {'provider'} if service", "extras = {'railway_project','environment_id','repo'} if service == 'railway-personal' else {'provider'} if service"),
      ("if service not in ('anthropic',", "if service not in ('railway-personal', 'anthropic',"),
      ("supported = web_research.OPERATIONS", "supported = personal_railway.OPERATIONS if service == 'railway-personal' else web_research.OPERATIONS"),
      ("        if service == 'web-research':\n            web_research.validate_policy(policy)","        if service == 'railway-personal':\n            personal_railway.validate_policy(policy)\n        elif service == 'web-research':\n            web_research.validate_policy(policy)"),
      ("        if self.service == 'railway-projects':", "        if self.service == 'railway-personal':\n            if self.mock: raise TransferError('personal_railway_disabled')\n            yield from personal_railway.dispatch(self.policy,self.key,operation,value,limits,control)\n            return\n        if self.service == 'railway-projects':"),
      ("        elif policy['service']=='railway-projects':", "        elif policy['service']=='railway-personal':\n            personal_railway.validate_payload(policy,operation,payload)\n        elif policy['service']=='railway-projects':")]
    for old,new in replacements:
        if source.count(old)!=1:raise ValueError('Proxy patch anchor missing/ambiguous')
        source=source.replace(old,new,1)
    return source


def prepare(output,environment,baseline=ROOT):
    if not isinstance(environment,str) or not UUID.fullmatch(environment):raise ValueError('Explicit environment UUID required')
    manifest=json.loads((APP/'admin/personal-railway-package.json').read_text())
    for name,digest in manifest['baseline_sha256'].items():
        if hashlib.sha256((baseline/name).read_bytes()).hexdigest()!=digest:raise ValueError('Installed baseline drift; re-review package')
    for name,digest in manifest['sha256'].items():
        if hashlib.sha256((APP/name).read_bytes()).hexdigest()!=digest:raise ValueError('Personal package drift')
    source=(baseline/'proxy.py').read_text()
    changed=render_proxy(source)
    config=json.loads((baseline/'config.json').read_text())
    if INTEGRATION in config['integrations']:raise ValueError('Personal integration already exists; inspect rather than overwrite')
    # Existing broker enforces a shared UID namespace label. This is not an account identity.
    labels={p['project'] for p in config['integrations'].values() if 502 in p['allowed_uids']}
    if len(labels)!=1:raise ValueError('Existing UID502 namespace is ambiguous')
    addition={'project':labels.pop(),'service':'railway-personal',
        'allowed_uids':[502],'mock':False,'per_minute':5,'per_day':50,
        'railway_project':PROJECT,'environment_id':environment,'repo':REPO,
        'operations':{'connection.inspect':{'max_request_bytes':2048,'max_response_bytes':65536,
                                         'idle_timeout_seconds':5,'total_timeout_seconds':30}}}
    routing={'schema':1,'integration':INTEGRATION,'project':PROJECT,'environment':environment,'repo':REPO,'writes_enabled':False}
    output.mkdir(mode=0o700)
    files={'proxy.patch':''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),fromfile='a/proxy.py',tofile='b/proxy.py')),
           'policy-addition.json':json.dumps({INTEGRATION:addition},indent=2)+'\n',
           'personal_railway.py':(APP/'admin/personal_railway.py').read_text(),
           'railway.connection.json':json.dumps(routing,indent=2)+'\n'}
    for name,text in files.items():
        path=output/name;path.write_text(text);path.chmod(0o600)
    (output/'SHA256.json').write_text(json.dumps({name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--environment',required=True)
    a=p.parse_args();prepare(a.output,a.environment)
