"""Offline personal credential routing and generated proxy integration."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from admin import personal_railway as personal
from admin.prepare_personal_railway import prepare,APP,ROOT,render_proxy
from tools import railway_deploy as cli
E='22222222-2222-2222-2222-222222222222'
POLICY={'railway_project':personal.PROJECT,'environment_id':E,'repo':personal.REPO}
VALUE={'project':personal.PROJECT,'environment':E,'repo':personal.REPO}

class API:
    def __init__(self,value):self.value=value;self.calls=0;self.inventory={'environment':{'id':E,'serviceInstances':{'edges':[],'pageInfo':{'hasNextPage':False}}}}
    def call(self,query,*args,**kwargs):
        self.calls+=1
        return self.inventory if query==personal.SERVICES_QUERY else self.value

class PersonalRailwayTests(unittest.TestCase):
    def test_correct_token_matches_and_wrong_or_missing_identity_fails_closed(self):
        api=API({'projectToken':{'projectId':personal.PROJECT,'environmentId':E}})
        result=personal.run(api,POLICY,'connection.inspect',VALUE)
        self.assertTrue(result['connected']);self.assertFalse(result['writes_enabled'])
        for data in [None,{}, {'projectToken':None},{'projectToken':{'projectId':E,'environmentId':E}},
                     {'projectToken':{'projectId':personal.PROJECT,'environmentId':personal.PROJECT}}]:
            with self.assertRaises(ValueError):personal.run(API(data),POLICY,'connection.inspect',VALUE)

    def test_scope_and_every_mutation_rejected_before_provider_call(self):
        api=API({})
        for operation,value in [('deployment.submit',VALUE),('project.ensure',VALUE),
                                ('connection.inspect',dict(VALUE,project=E)),
                                ('connection.inspect',dict(VALUE,environment=personal.PROJECT)),
                                ('connection.inspect',dict(VALUE,query='query {me {email}}'))]:
            with self.assertRaises(ValueError):personal.run(api,POLICY,operation,value)
        self.assertEqual(api.calls,0)

    def test_local_routing_cannot_choose_shared_integration_or_missing_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'connection.json'
            base={'schema':1,'integration':personal.INTEGRATION,**VALUE,'writes_enabled':False}
            with patch.object(cli,'CONNECTION',path):
                path.write_text(json.dumps(base));self.assertEqual(cli.load_connection()['environment'],E)
                for change in [{'integration':'workspace-railway'},{'environment':None},{'project':E},{'writes_enabled':True}]:
                    path.write_text(json.dumps(dict(base,**change)))
                    with self.assertRaises(ValueError):cli.load_connection()

    def test_generated_proxy_validates_policy_without_loading_credentials_and_preserves_other_integrations(self):
        from admin import prepare_personal_railway as preparer
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);baseline=base/'synthetic-baseline';baseline.mkdir()
            app=base/'synthetic-package';(app/'admin').mkdir(parents=True)
            # A minimal synthetic source exercises every patch anchor. Never copy
            # installed admin configuration or credentials into test fixtures.
            source="""import github_publish
class Provider:
    def call(self,operation,value,limits,control):
        if self.service == 'railway-projects':
            return

def validate_config(config):
    for policy in config['integrations'].values():
        service=policy['service']
        extras = {'provider'} if service == 'web-research' else {'repository'}
        if service not in ('anthropic','web-research','railway-projects'):
            raise ValueError('service')
        supported = web_research.OPERATIONS if service == 'web-research' else set()
        if service == 'web-research':
            web_research.validate_policy(policy)

def request(policy,operation,payload):
    if True:
        if policy['service']=='web-research':
            return
        elif policy['service']=='railway-projects':
            return
"""
            config={'socket':'/synthetic/socket','state_dir':'/synthetic/state','private_dir':'/synthetic/private',
                    'integrations':{'work-fixture':{'project':'linkedin','service':'github','repository':'virtualseal/fixture','allowed_uids':[502],
                    'operations':{'repository.get':{'max_request_bytes':2048,'max_response_bytes':65536,'idle_timeout_seconds':5,'total_timeout_seconds':30}},
                    'mock':True,'per_minute':1,'per_day':1}}}
            (baseline/'proxy.py').write_text(source);(baseline/'config.json').write_text(json.dumps(config))
            (app/'admin/personal_railway.py').write_text((APP/'admin/personal_railway.py').read_text())
            manifest={'baseline_sha256':{n:hashlib.sha256((baseline/n).read_bytes()).hexdigest() for n in ['proxy.py','config.json']},'sha256':{}}
            (app/'admin/personal-railway-package.json').write_text(json.dumps(manifest))
            out=base/'stage'
            with patch.object(preparer,'APP',app):prepare(out,E,baseline)
            addition=json.loads((out/'policy-addition.json').read_text())
            self.assertEqual(set(addition),{personal.INTEGRATION})
            self.assertEqual(addition[personal.INTEGRATION]['operations'].keys(),{'connection.inspect'})
            self.assertFalse((out/'config.json').exists());self.assertFalse((out/'proxy.py').exists())
            compile(render_proxy(source),'synthetic-patched-proxy','exec')
            # Validate generated policy using the currently installed validator,
            # not the synthetic patch-anchor source or any Provider constructor.
            code='import sys,json;sys.path.insert(0,"/Library/Application Support/CredentialProxy");import proxy;c=json.loads(sys.stdin.readline());a=json.loads(sys.stdin.readline());before=dict(c["integrations"]);c["integrations"].update(a);proxy.validate_config(c);assert all(c["integrations"][k]==v for k,v in before.items());print("no providers constructed")'
            result=subprocess.run([sys.executable,'-B','-c',code],input=json.dumps(config)+'\n'+json.dumps(addition)+'\n',capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('no providers constructed',result.stdout)
            # A real baseline change must still fail closed rather than being skipped.
            (baseline/'proxy.py').write_text(source+'# drift\n')
            with patch.object(preparer,'APP',app),self.assertRaisesRegex(ValueError,'baseline drift'):
                prepare(base/'must-not-exist',E,baseline)
            self.assertFalse((base/'must-not-exist').exists())

    def test_http_uses_project_token_header_and_rejects_partial_body(self):
        import io
        class Response:
            status=200
            def __init__(self,partial):
                self.body=json.dumps({'data':{'projectToken':{'projectId':personal.PROJECT,'environmentId':E},'environment':{'id':E,'serviceInstances':{'edges':[],'pageInfo':{'hasNextPage':False}}}}}).encode()
                self.stream=io.BytesIO(self.body);self.partial=partial
            def getheader(self,name):return {'Content-Type':'application/json','Content-Length':str(len(self.body)+(1 if self.partial else 0))}.get(name)
            def read1(self,n):return self.stream.read(n)
        class Control:
            def check(self):pass
            def attach(self,sock):pass
        for partial in [False,True]:
            connection=unittest.mock.Mock();connection.getresponse.side_effect=[Response(partial),Response(False)]
            with patch.object(personal.http.client,'HTTPSConnection',return_value=connection):
                api=personal.API('synthetic-project-token',{'idle_timeout_seconds':5,'max_response_bytes':4096},Control(),E)
                if partial:
                    with self.assertRaises(Exception):personal.run(api,POLICY,'connection.inspect',VALUE)
                else:self.assertTrue(personal.run(api,POLICY,'connection.inspect',VALUE)['connected'])
                headers=connection.request.call_args[0][3]
                self.assertEqual(headers['Project-Access-Token'],'synthetic-project-token');self.assertNotIn('Authorization',headers)
                self.assertEqual(connection.close.call_count,1 if partial else 2)

    def test_service_inventory_scope_pagination_and_duplicates_fail_closed(self):
        identity={'projectToken':{'projectId':personal.PROJECT,'environmentId':E}}
        node={'serviceId':'33333333-3333-3333-3333-333333333333','serviceName':'Personal Slack','latestDeployment':None}
        api=API(identity);api.inventory['environment']['serviceInstances']['edges']=[{'node':node}]
        result=personal.run(api,POLICY,'connection.inspect',VALUE)
        self.assertEqual(result['services'],[{'id':node['serviceId'],'name':'Personal Slack','latest_deployment':None}])
        for change in ['foreign-env','partial','duplicate','bad-id','missing-edges','missing-deployment']:
            value=json.loads(json.dumps(api.inventory))
            if change=='foreign-env':value['environment']['id']=personal.PROJECT
            elif change=='partial':value['environment']['serviceInstances']['pageInfo']['hasNextPage']=True
            elif change=='duplicate':value['environment']['serviceInstances']['edges'].append({'node':node})
            elif change=='bad-id':value['environment']['serviceInstances']['edges'][0]['node']['serviceId']='foreign'
            elif change=='missing-deployment':del value['environment']['serviceInstances']['edges'][0]['node']['latestDeployment']
            else:del value['environment']['serviceInstances']['edges']
            api.inventory=value
            with self.assertRaises(ValueError):personal.run(api,POLICY,'connection.inspect',VALUE)
            api.inventory={'environment':{'id':E,'serviceInstances':{'edges':[{'node':node}],'pageInfo':{'hasNextPage':False}}}}

    def test_transport_rejects_account_queries_mutations_or_foreign_environment(self):
        with patch.object(personal.http.client,'HTTPSConnection') as connection:
            api=personal.API('synthetic',{'idle_timeout_seconds':5,'max_response_bytes':4096},object(),E)
            for query,variables,write in [('query {projects {edges {node {id}}}}',{},False),
                                         (personal.SERVICES_QUERY,{'id':personal.PROJECT},False),
                                         (personal.TOKEN_QUERY,{},True)]:
                with self.assertRaises(ValueError):api.call(query,variables,write)
            connection.assert_not_called()

    def test_nonadmin_installer_fails_before_prompt_or_any_mutation(self):
        from admin import install_personal_railway as install
        with patch.object(install.os,'getuid',return_value=502),patch.object(install.getpass,'getpass') as prompt:
            with self.assertRaises(ValueError):install.install(Path('unused'),Path('unused'),E)
            prompt.assert_not_called()


class AdminInstallFailureTests(unittest.TestCase):
    def setUp(self):
        from admin import install_personal_railway as install
        self.install=install
        self.real_require_directory=install.require_directory
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'protected';self.root.mkdir()
        self.private=self.base/'synthetic-private';self.private.mkdir(mode=0o700)
        self.old={'private_dir':str(self.private),'integrations':{'work-fixture':{'unchanged':True}}}
        (self.root/'config.json').write_text(json.dumps(self.old));(self.root/'proxy.py').write_text('old proxy')
        self.original=(self.root/'config.json').read_bytes()
        self.existing=self.private/'work-fixture.key';self.existing.write_text('synthetic existing credential sentinel')
        self.backup=self.base/'backup';self.stage=self.base/'stage'
        self.package=self.base/'package';(self.package/'admin').mkdir(parents=True)
        (self.package/'admin/personal-railway-package.json').write_text(json.dumps({'sha256':{}}))
        self.files={'proxy.patch':'reviewed additive patch','policy-addition.json':json.dumps({personal.INTEGRATION:{'service':'railway-personal','operations':{'connection.inspect':{}}}}),
                    'personal_railway.py':'new reviewed adapter','railway.connection.json':json.dumps(VALUE)}
        self.make_stage(self.stage)
        self.socket=unittest.mock.Mock();self.socket.connect.side_effect=ConnectionRefusedError()
        patches=[patch.object(install,'ROOT',self.root),patch.object(install,'APP',self.package),patch.object(install,'require_file'),patch.object(install.os,'getuid',return_value=0),
                 patch.object(install,'require_directory'),patch.object(install.os,'fchown'),
                 patch.object(install.socket,'socket',return_value=self.socket),
                 patch.object(install,'prepare',side_effect=self.make_stage),
                 patch.object(install,'render_proxy',side_effect=lambda source: 'new proxy' if source=='old proxy' else (_ for _ in ()).throw(ValueError('drift'))),
                 patch.object(install.getpass,'getpass',return_value='synthetic-new-project-token')]
        for item in patches:item.start();self.addCleanup(item.stop)

    def make_stage(self,path,*args):
        path.mkdir()
        for name,body in self.files.items():(path/name).write_text(body)

    def run_install(self):self.install.install(self.stage,self.backup,E)

    def assert_work_untouched(self):
        self.assertEqual(self.existing.read_text(),'synthetic existing credential sentinel')
        self.assertEqual(json.loads((self.root/'config.json').read_text())['integrations']['work-fixture'],self.old['integrations']['work-fixture'])

    def test_additive_install_preserves_existing_credential_and_original_backup(self):
        self.run_install();self.assert_work_untouched()
        self.assertEqual((self.backup/'config.json').read_bytes(),self.original)
        self.assertEqual((self.backup/'proxy.py').read_text(),'old proxy')
        self.assertEqual((self.root/'proxy.py').read_text(),'new proxy')
        self.assertEqual(set(json.loads((self.root/'config.json').read_text())['integrations']),{'work-fixture',personal.INTEGRATION})
        key=self.private/(personal.INTEGRATION+'.key');self.assertEqual(key.stat().st_mode&0o777,0o600)
        self.assertEqual(key.read_text(),'synthetic-new-project-token')
        self.install.os.fchown.assert_called_once()
        self.socket.close.assert_called_once()

    def test_running_or_unknown_proxy_never_prompts_or_installs(self):
        for failure in [None,TimeoutError('unknown connection')]:
            self.socket.connect.side_effect=failure
            with self.assertRaises((ValueError,TimeoutError)):self.run_install()
            self.assertFalse(self.backup.exists());self.assertEqual((self.root/'config.json').read_bytes(),self.original)
            self.install.getpass.getpass.assert_not_called()

    def test_stage_and_baseline_drift_stop_before_backup_or_token(self):
        (self.stage/'proxy.patch').write_text('wrong bytes')
        with self.assertRaisesRegex(ValueError,'Stage differs'):self.run_install()
        self.assertFalse(self.backup.exists());self.install.getpass.getpass.assert_not_called()
        self.install.prepare.side_effect=ValueError('Baseline drift')
        with self.assertRaisesRegex(ValueError,'Baseline drift'):self.run_install()
        self.assertFalse(self.backup.exists())

    def test_insecure_prompt_aborts_before_any_token_or_live_file_write(self):
        import warnings
        def insecure(*args):warnings.warn('secure input unavailable',self.install.getpass.GetPassWarning)
        self.install.getpass.getpass.side_effect=insecure
        with self.assertRaises(self.install.getpass.GetPassWarning):self.run_install()
        self.assertFalse((self.private/(personal.INTEGRATION+'.key')).exists())
        self.assertEqual((self.root/'config.json').read_bytes(),self.original)
        self.assertEqual((self.backup/'config.json').read_bytes(),self.original)
        self.assert_work_untouched()

    def test_backup_failure_precedes_key_and_installed_mutations(self):
        original=self.install.atomic
        def fail_backup(path,body):
            if path.parent==self.backup:raise OSError('backup unavailable')
            original(path,body)
        with patch.object(self.install,'atomic',side_effect=fail_backup):
            with self.assertRaises(OSError):self.run_install()
        self.install.getpass.getpass.assert_not_called()
        self.assertEqual((self.root/'proxy.py').read_text(),'old proxy')
        self.assertFalse((self.private/(personal.INTEGRATION+'.key')).exists())

    def test_interrupted_key_and_config_writes_preserve_backup_and_refuse_blind_rerun(self):
        with patch.object(self.install.os,'fchown',side_effect=OSError('key interrupted')):
            with self.assertRaises(OSError):self.run_install()
        self.assertEqual((self.root/'config.json').read_bytes(),self.original)
        self.assertEqual((self.backup/'config.json').read_bytes(),self.original)
        self.assert_work_untouched()
        with self.assertRaisesRegex(ValueError,'already exists'):self.run_install()

    def test_config_failure_leaves_original_grants_and_no_success(self):
        from contextlib import redirect_stdout
        import io
        original=self.install.atomic
        def fail_config(path,body):
            if path==self.root/'config.json':raise OSError('config interrupted')
            original(path,body)
        output=io.StringIO()
        with patch.object(self.install,'atomic',side_effect=fail_config),redirect_stdout(output):
            with self.assertRaises(OSError):self.run_install()
        self.assertEqual(output.getvalue(),'')
        self.assertEqual((self.root/'config.json').read_bytes(),self.original)
        self.assertEqual((self.backup/'config.json').read_bytes(),self.original)
        self.assert_work_untouched()
        with self.assertRaisesRegex(ValueError,'already exists'):self.run_install()

    def test_directory_guard_rejects_unprotected_paths(self):
        # Production guard separately exercised without root; synthetic install tests
        # patch only ownership checks to avoid privileged operations in tests.
        with patch.object(Path,'lstat',return_value=type('Info',(),{'st_mode':0o40777,'st_uid':503})()):
            with self.assertRaises(ValueError):self.real_require_directory(self.private,503,True)


class PackageIntegrityTests(unittest.TestCase):
    def test_privileged_entry_refuses_actual_agent_owned_checkout_before_prompt(self):
        from admin import install_personal_railway as installer
        with patch.object(installer.os,'getuid',return_value=0),patch.object(installer.getpass,'getpass') as prompt,patch.object(installer.socket,'socket') as sock:
            with self.assertRaises(ValueError):installer.install(Path('unused'),Path('unused'),E)
            prompt.assert_not_called();sock.assert_not_called()

    def test_root_package_rejects_mutable_manifest_or_source_file(self):
        from admin import install_personal_railway as installer
        info=type('Info',(),{'st_mode':0o100666,'st_uid':0})()
        with patch.object(Path,'lstat',return_value=info):
            with self.assertRaises(ValueError):installer.require_file(Path('synthetic-file'))
        info=type('Info',(),{'st_mode':0o100644,'st_uid':502})()
        with patch.object(Path,'lstat',return_value=info):
            with self.assertRaises(ValueError):installer.require_file(Path('synthetic-file'))

    def test_all_package_manifests_pin_current_bytes(self):
        for name in ['personal-railway','slack','railway','maps']:
            record=json.loads((APP/('admin/'+name+'-package.json')).read_text())
            for filename,expected in record['sha256'].items():
                with self.subTest(package=name,file=filename):
                    self.assertEqual(hashlib.sha256((APP/filename).read_bytes()).hexdigest(),expected)
