"""Personal project-token readback. Protected admin-installed service only."""
import http.client
import io
import json
import re
import ssl

INTEGRATION='personal-thursday-railway'
PROJECT='2d6b15bd-cdab-4978-9518-2d44820cfc85'
REPO='virtualseal/agentwork-promptenglab'
OPERATIONS={'connection.inspect'}
TOKEN_QUERY='query PersonalRailwayIdentity { projectToken { projectId environmentId } }'
SERVICES_QUERY='query PersonalRailwayServices($id: String!) { environment(id:$id) { id serviceInstances { edges { node { serviceId serviceName latestDeployment { id status } } } pageInfo { hasNextPage } } } }'
UUID=re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def validate_policy(policy):
    if policy.get('railway_project')!=PROJECT or policy.get('repo')!=REPO:
        raise ValueError('Personal Railway project/repository mismatch')
    if not isinstance(policy.get('environment_id'),str) or not UUID.fullmatch(policy['environment_id']):
        raise ValueError('Personal Railway environment must be explicitly bound')


def validate_payload(policy,operation,value):
    validate_policy(policy)
    if operation!='connection.inspect' or not isinstance(value,dict) or value!={'project':PROJECT,'environment':policy['environment_id'],'repo':REPO}:
        raise ValueError('Only bound read-only personal connection inspection is allowed')


def run(api,policy,operation,value):
    validate_payload(policy,operation,value)
    data=api.call(TOKEN_QUERY,{})
    identity=data.get('projectToken') if isinstance(data,dict) else None
    if not isinstance(identity,dict) or identity.get('projectId')!=PROJECT or identity.get('environmentId')!=policy['environment_id']:
        raise ValueError('Personal Railway credential target mismatch')
    environment=api.call(SERVICES_QUERY,{'id':policy['environment_id']}).get('environment')
    if not isinstance(environment,dict) or environment.get('id')!=policy['environment_id']:
        raise ValueError('Personal service environment mismatch')
    connection=environment.get('serviceInstances')
    if not isinstance(connection,dict) or connection.get('pageInfo',{}).get('hasNextPage') is not False:
        raise ValueError('Incomplete personal service inventory')
    edges=connection.get('edges')
    if not isinstance(edges,list) or len(edges)>100:raise ValueError('Invalid service inventory bounds')
    services=[];seen=set()
    for edge in edges:
        node=edge.get('node') if isinstance(edge,dict) else None
        if not isinstance(node,dict):raise ValueError('Invalid service record')
        identifier,name=node.get('serviceId'),node.get('serviceName')
        if not isinstance(identifier,str) or not UUID.fullmatch(identifier) or identifier in seen:
            raise ValueError('Invalid or duplicate service identity')
        if not isinstance(name,str) or not 1<=len(name)<=150 or any(ord(c)<32 for c in name):
            raise ValueError('Invalid service name')
        if 'latestDeployment' not in node:raise ValueError('Missing deployment metadata')
        seen.add(identifier);deployment=node['latestDeployment']
        if deployment is not None and (not isinstance(deployment,dict)
                or not isinstance(deployment.get('id'),str) or not UUID.fullmatch(deployment['id'])
                or not isinstance(deployment.get('status'),str) or not 1<=len(deployment['status'])<=64):
            raise ValueError('Invalid deployment status metadata')
        services.append({'id':identifier,'name':name,'latest_deployment':None if deployment is None else {'id':deployment['id'],'status':deployment['status']}})
    return {'integration':INTEGRATION,'project':PROJECT,'environment':policy['environment_id'],
            'repo':REPO,'connected':True,'writes_enabled':False,'services':services}


class API:
    def __init__(self, key, limits, control, environment=None):
        self.environment=environment
        self.key, self.limits, self.control = key, limits, control
        self.remaining = limits['max_response_bytes']

    def call(self, query, variables, write=False):
        from transfer import TransferError
        identity=query==TOKEN_QUERY and variables=={}
        services=(query==SERVICES_QUERY and isinstance(self.environment,str) and UUID.fullmatch(self.environment)
                  and variables=={'id':self.environment})
        if write or not (identity or services):
            raise ValueError('Only fixed bound read-only queries are allowed')
        conn = http.client.HTTPSConnection('backboard.railway.com', timeout=self.limits['idle_timeout_seconds'], context=ssl.create_default_context())
        sent = False
        try:
            self.control.check()
            conn.connect()
            self.control.attach(conn.sock)
            sent = True
            conn.request('POST', '/graphql/v2', json.dumps({'query': query, 'variables': variables}).encode(),
                         {'Project-Access-Token': self.key, 'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'AgentworkCredentialProxy'})
            response = conn.getresponse()
            self.control.check()
            if response.status != 200:
                raise TransferError('railway_write_reconcile_required' if write else 'railway_read_rejected')
            if response.getheader('Content-Encoding') not in (None, 'identity') or (response.getheader('Content-Type') or '').split(';')[0] != 'application/json':
                raise TransferError('invalid_response_type')
            raw = response.getheader('Content-Length')
            length = None if raw is None else int(raw)
            if length is not None and (length < 0 or length > self.remaining): raise TransferError('response_too_large')
            chunks, received = [], 0
            while True:
                self.control.check()
                chunk = response.read1(min(65536, self.remaining+1))
                if not chunk: break
                received += len(chunk)
                self.remaining -= len(chunk)
                if self.remaining < 0: raise TransferError('response_too_large')
                chunks.append(chunk)
            self.control.check()
            if length is not None and received != length: raise TransferError('incomplete_transfer')
            result = json.loads(b''.join(chunks))
            if not isinstance(result, dict) or result.get('errors') or not isinstance(result.get('data'), dict):
                raise TransferError('railway_write_reconcile_required' if write else 'railway_query_rejected')
            return result['data']
        except TransferError:
            raise
        except Exception as error:
            raise TransferError('railway_write_outcome_unknown' if write and sent else 'railway_read_failed') from error
        finally:
            conn.close()


def dispatch(policy,key,operation,value,limits,control):
    from transfer import frames,TransferError
    try:result=run(API(key,limits,control,policy['environment_id']),policy,operation,value)
    except Exception:raise TransferError('personal_railway_inspection_failed') from None
    body=json.dumps(result).encode()
    class Response(io.BytesIO):
        status=200
        def getheader(self,name):return {'Content-Type':'application/json','Content-Length':str(len(body))}.get(name)
    yield from frames(Response(body),limits,control)
