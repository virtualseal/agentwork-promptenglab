"""Protected, fixed-target deployment operations. Installed only by a human admin.

Uses the existing broker's bounded HTTP API and private journal primitives.
No credential lookup or generic GraphQL forwarding is exposed to callers.
"""
import io
import os
import json
from pathlib import Path
import re
import stat
import time

PROJECT = '2d6b15bd-cdab-4978-9518-2d44820cfc85'
REPO = 'virtualseal/agentwork-promptenglab'
WORKSPACE = '1fc03572-3e94-4c8b-bb59-42dbc26e0d28'
OPERATIONS = {'deployment.inspect', 'deployment.submit', 'deployment.reconcile'}
ROOT = Path('/Library/Application Support/CredentialProxy')
BINDING = ROOT / 'admin/thursday-deployment.json'
STATE = ROOT / 'state/thursday-deployment.sqlite3'
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
SHA = re.compile(r'[0-9a-f]{40}')
CHECKS = {'unit', 'acceptance', 'slack-runtime', 'deployment', 'independent-review'}
PROJECT_QUERY = '''query ThursdayProject($id: String!) { project(id:$id) {
 id services { edges { node { id name } } pageInfo { hasNextPage } }
 environments { edges { node { id name } } pageInfo { hasNextPage } } } }'''
HISTORY = '''query ThursdayDeployments($input: DeploymentListInput!) {
 deployments(input:$input,first:100) { edges { node { id status meta } }
 pageInfo { hasNextPage } } }'''
DEPLOY = '''mutation ThursdayDeploy($serviceId:String!, $environmentId:String!, $commitSha:String!) {
 serviceInstanceDeployV2(serviceId:$serviceId,environmentId:$environmentId,commitSha:$commitSha) }'''


class Blocked(RuntimeError):
    pass


def validate_payload(policy, operation, value):
    if policy.get('workspace_id') != WORKSPACE or policy.get('owner') != 'virtualseal':
        raise ValueError('deployment workspace mismatch')
    fields = {'project', 'repo'} | ({'sha'} if operation != 'deployment.inspect' else set())
    if operation not in OPERATIONS or not isinstance(value, dict) or set(value) != fields:
        raise ValueError('unsupported deployment operation or fields')
    if value['project'] != PROJECT or value['repo'] != REPO:
        raise ValueError('deployment target mismatch')
    if 'sha' in value and (not isinstance(value['sha'], str) or not SHA.fullmatch(value['sha'])):
        raise ValueError('immutable full commit SHA required')


def protected_json(path):
    # Protected parent prevents UID502 replacing an admin-approved file.
    for parent in path.absolute().parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise Blocked('unsafe admin binding directory')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise Blocked('unsafe admin binding')
        if info.st_size > 65536:
            raise Blocked('oversized admin binding')
        with os.fdopen(fd, 'r') as stream:
            fd = None
            return json.load(stream)
    finally:
        if fd is not None: os.close(fd)


def validate_binding(binding):
    if set(binding) != {'project', 'repo', 'service', 'environment', 'writes_enabled', 'approval'}:
        raise Blocked('invalid binding schema')
    if binding['project'] != PROJECT or binding['repo'] != REPO or type(binding['writes_enabled']) is not bool:
        raise Blocked('invalid binding scope')
    for field in ('service', 'environment'):
        if binding[field] is not None and (not isinstance(binding[field], str) or not UUID.fullmatch(binding[field])):
            raise Blocked('invalid binding identity')


def nodes(connection):
    if not isinstance(connection, dict) or connection.get('pageInfo', {}).get('hasNextPage') is not False:
        raise Blocked('incomplete authoritative readback')
    values = [edge['node'] for edge in connection['edges']]
    if any(not isinstance(v.get('id'), str) or not UUID.fullmatch(v['id']) for v in values):
        raise Blocked('invalid readback identities')
    if len({v['id'] for v in values}) != len(values):
        raise Blocked('duplicate readback identities')
    return values


def inspect(api, binding):
    project = api.call(PROJECT_QUERY, {'id': PROJECT})['project']
    if project['id'] != PROJECT:
        raise Blocked('project identity mismatch')
    services, environments = nodes(project['services']), nodes(project['environments'])
    if binding['service'] is not None and binding['service'] not in {s['id'] for s in services}:
        raise Blocked('bound service missing from project')
    if binding['environment'] is not None and binding['environment'] not in {e['id'] for e in environments}:
        raise Blocked('bound environment missing from project')
    return {'project': PROJECT, 'repo': REPO, 'services': services, 'environments': environments,
            'writes_enabled': binding['writes_enabled'], 'delivery_ready': False}


def history(api, binding):
    return nodes(api.call(HISTORY, {'input': {'projectId': PROJECT, 'serviceId': binding['service'],
                                            'environmentId': binding['environment']}})['deployments'])


def approval(binding, sha, now):
    value = binding['approval']
    if not isinstance(value, dict) or set(value) != {'sha', 'expires', 'checks', 'gates'}:
        raise Blocked('admin review approval missing')
    if value['sha'] != sha or type(value['expires']) not in (int, float) or not now < value['expires'] <= now + 86400:
        raise Blocked('stale or wrong revision approval')
    if value['checks'] != {name: 'passed' for name in CHECKS}:
        raise Blocked('required checks missing or failed')
    # These admin-attested external gates cannot currently pass. They must be
    # verified independently; a running HTTP endpoint is not delivery readiness.
    required = {'maps_complete', 'slack_installed', 'source_repo_verified', 'autodeploy_disabled',
                'no_staged_changes', 'durable_volume', 'single_worker', 'uid502', 'pacific_schedule'}
    if (not isinstance(value['gates'], dict) or set(value['gates']) != required
            or any(v is not True for v in value['gates'].values())):
        raise Blocked('activation prerequisites incomplete')


def run(api, policy, operation, value, binding, path=STATE, now=None, refresh=None):
    from railway_projects import journal
    validate_payload(policy, operation, value)
    validate_binding(binding)
    observed = inspect(api, binding)
    if operation == 'deployment.inspect':
        return observed
    if not binding['service'] or not binding['environment']:
        raise Blocked('human admin must bind existing service and environment')
    sha = value['sha']
    # The lock spans read/intent/write/readback; all processes share one journal.
    with journal(path) as db:
        if refresh is not None:
            fresh = refresh()
            validate_binding(fresh)
            if (fresh['service'], fresh['environment']) != (binding['service'], binding['environment']):
                raise Blocked('admin binding changed while queued')
            binding = fresh
        db.execute('CREATE TABLE IF NOT EXISTS deployments (service TEXT, environment TEXT, sha TEXT, baseline TEXT NOT NULL, deployment TEXT, PRIMARY KEY(service,environment,sha))')
        key = (binding['service'], binding['environment'], sha)
        row = db.execute('SELECT baseline,deployment FROM deployments WHERE service=? AND environment=? AND sha=?', key).fetchone()
        values = history(api, binding)
        if row is None:
            if operation == 'deployment.reconcile':
                return {'status': 'no-intent', 'sha': sha, 'delivery_ready': False}
            if not binding['writes_enabled']:
                raise Blocked('deployment writes disabled')
            approval(binding, sha, time.time() if now is None else now)
            # Any unresolved earlier intent blocks a different revision too.
            previous = db.execute('SELECT sha,deployment FROM deployments WHERE service=? AND environment=?', key[:2]).fetchall()
            for old_sha, old_id in previous:
                prior = [v for v in values if v['id'] == old_id and isinstance(v.get('meta'), dict)
                         and v['meta'].get('commitHash') == old_sha and v['meta'].get('repo') == REPO]
                if len(prior) != 1 or prior[0].get('status') not in {'SUCCESS', 'FAILED', 'CRASHED', 'REMOVED', 'SKIPPED'}:
                    raise Blocked('previous deployment outcome unknown or still active')
            baseline = json.dumps([v['id'] for v in values])
            db.execute('INSERT INTO deployments VALUES(?,?,?,?,NULL)', key + (baseline,))
            db.commit()  # Durable intent before even attempting the mutation.
            try:
                result = api.call(DEPLOY, {'serviceId': key[0], 'environmentId': key[1], 'commitSha': sha}, write=True)
                identifier = result['serviceInstanceDeployV2']
                if not isinstance(identifier, str) or not UUID.fullmatch(identifier):
                    raise Blocked('invalid mutation acknowledgement')
                db.execute('UPDATE deployments SET deployment=? WHERE service=? AND environment=? AND sha=?', (identifier,) + key)
                db.commit()
            except Exception:
                # Do not leak provider errors; a later reconcile is read-only.
                return {'status': 'unknown', 'sha': sha, 'delivery_ready': False}
            row = (baseline, identifier)
            values = history(api, binding)
        baseline, identifier = set(json.loads(row[0])), row[1]
        matches = [v for v in values if v['id'] not in baseline and isinstance(v.get('meta'), dict)
                   and v['meta'].get('commitHash') == sha and v['meta'].get('repo') == REPO]
        if identifier:
            matches = [v for v in matches if v['id'] == identifier]
        if len(matches) != 1:
            return {'status': 'unknown', 'sha': sha, 'delivery_ready': False}
        match = matches[0]
        db.execute('UPDATE deployments SET deployment=? WHERE service=? AND environment=? AND sha=?', (match['id'],) + key)
        db.commit()
        status = match.get('status')
        if status not in {'SUCCESS', 'FAILED', 'CRASHED', 'REMOVED', 'SKIPPED', 'BUILDING', 'DEPLOYING', 'WAITING', 'QUEUED', 'SLEEPING'}:
            raise Blocked('unrecognized deployment status')
        return {'status': status, 'deployment': match['id'], 'sha': sha, 'delivery_ready': False}


def dispatch(policy, key, operation, value, limits, control):
    from railway_projects import API
    from transfer import frames
    binding = protected_json(BINDING)
    result = run(API(key, limits, control), policy, operation, value, binding,
                 refresh=lambda: protected_json(BINDING))
    body = json.dumps(result).encode()
    class Response(io.BytesIO):
        status = 200
        def getheader(self, name):
            return {'Content-Type': 'application/json', 'Content-Length': str(len(body))}.get(name)
    yield from frames(Response(body), limits, control)
