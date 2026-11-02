"""A passing emulator, wrong user or stale checkout must not satisfy native CI."""
import unittest
from deployment.native_linux_check import validate_runtime


class NativeRunnerTests(unittest.TestCase):
    def test_rejects_emulation_rootful_engine_wrong_identity_and_stale_sha(self):
        base={'root':'/Users/agentwork/apps/thursday-restaurants','engine':{'OSType':'linux','Architecture':'x86_64','SecurityOptions':['name=rootless','name=seccomp,profile=builtin']},'username':'agentwork','system':'Linux','machine':'x86_64','expected':'a'*40,'actual':'a'*40}
        validate_runtime(**base)
        changes=[{'engine':dict(base['engine'],Architecture='aarch64')},{'machine':'arm64'},{'engine':dict(base['engine'],SecurityOptions=['name=seccomp'])},{'actual':'b'*40},{'expected':None},{'username':'runner'},{'root':'/tmp/checkout'},{'system':'Darwin'}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):validate_runtime(**dict(base,**change))

    def test_preflight_failure_replaces_stale_success_and_does_not_reuse_logs(self):
        import json,os,tempfile
        from pathlib import Path
        from deployment.native_linux_check import execute
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();state=root/'.review/native-linux';state.mkdir(parents=True)
            (state/'result.json').write_text('{"state":"native_checks_passed"}')
            (state/'check-3.log').write_text('old success')
            previous=Path.cwd()
            try:
                os.chdir(root)
                def fail(*args):raise OSError('synthetic unavailable engine')
                with self.assertRaises(OSError):execute(root,'a'*40,fail)
            finally:os.chdir(previous)
            report=json.loads((state/'result.json').read_text())
            self.assertEqual(report['state'],'failed');self.assertFalse(report['ready'])
            self.assertTrue(all(c['status']=='not_run' for c in report['checks']))
            self.assertTrue(all(not Path(c['log']).exists() for c in report['checks']))
            self.assertTrue((state/report['invocation']/'result.json').exists())

    def test_stale_commit_failure_is_persisted_before_any_checks(self):
        import json,os,tempfile
        from pathlib import Path
        from deployment.native_linux_check import execute
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();previous=Path.cwd()
            def fake(command,deadline,log,env=None):
                if 'info' in command:return '{"OSType":"linux","Architecture":"amd64","SecurityOptions":["name=rootless"]}'
                return 'b'*40 if command[0]=='git' else 'agentwork'
            try:
                os.chdir(root)
                with self.assertRaises(ValueError):execute(root,'a'*40,fake)
            finally:os.chdir(previous)
            report=json.loads((root/'.review/native-linux/result.json').read_text())
            self.assertEqual(report['state'],'failed');self.assertEqual(report['commit'],'b'*40)
            self.assertTrue(all(c['status']=='not_run' for c in report['checks']))

    def test_timeout_kills_descendant_process_group(self):
        import os,sys,tempfile,time
        from pathlib import Path
        from deployment.native_linux_check import run_process
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);marker=path/'escaped'
            # A surviving grandchild would create the marker after the parent timeout.
            child='import time;from pathlib import Path;time.sleep(0.5);Path('+repr(str(marker))+').write_text("escaped")'
            parent='import subprocess,sys,time;print("before timeout",flush=True);subprocess.Popen([sys.executable,"-c",'+repr(child)+']);time.sleep(5)'
            with self.assertRaises(TimeoutError):run_process([sys.executable,'-c',parent],time.monotonic()+0.2,path/'timeout.log')
            time.sleep(0.7)
            self.assertFalse(marker.exists())
            self.assertIn('before timeout',(path/'timeout.log').read_text())

    def test_failed_build_marks_later_browser_check_not_run(self):
        import json,os,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from deployment import native_linux_check as native
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();previous=Path.cwd()
            def fake(command,deadline,log,env=None):
                if 'info' in command:return '{}'
                if command[0]=='git':return '' if 'status' in command else 'a'*40
                if command[0]=='id':return 'agentwork'
                if 'deployment/build_linux_worker.py' in command:raise TimeoutError('synthetic build timeout')
                log.write_text('synthetic successful check')
                return ''
            try:
                os.chdir(root)
                with patch.object(native,'validate_runtime'),self.assertRaises(TimeoutError):native.execute(root,'a'*40,fake)
            finally:os.chdir(previous)
            report=json.loads((root/'.review/native-linux/result.json').read_text())
            self.assertEqual(report['state'],'failed')
            self.assertEqual([c['status'] for c in report['checks']],['passed','passed','failed','not_run'])
            self.assertEqual(report['cleanup'],'passed')
            self.assertFalse(Path(report['checks'][3]['log']).exists())

    def test_matching_head_with_modified_source_still_blocks(self):
        import json,os,tempfile
        from pathlib import Path
        from deployment.native_linux_check import execute
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();previous=Path.cwd()
            def fake(command,deadline,log,env=None):
                if command[0]=='git':return ' M app/cli.py\n?? app/extra.py\n' if 'status' in command else 'a'*40
                if command[0]=='id':return 'agentwork'
                return '{}'
            try:
                os.chdir(root)
                with self.assertRaisesRegex(ValueError,'modified or untracked'):execute(root,'a'*40,fake)
            finally:os.chdir(previous)
            report=json.loads((root/'.review/native-linux/result.json').read_text())
            self.assertEqual(report['state'],'failed');self.assertEqual(report['commit'],'a'*40)
            self.assertIn('modified or untracked',report['error'])
            self.assertTrue(all(c['status']=='not_run' for c in report['checks']))

    def test_launch_failure_and_expired_deadline_both_leave_logs(self):
        import tempfile,time
        from pathlib import Path
        from deployment.native_linux_check import run_process
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaises(FileNotFoundError):run_process(['/nonexistent-synthetic-executable'],time.monotonic()+2,root/'launch.log')
            self.assertIn('FileNotFoundError',(root/'launch.log').read_text())
            with self.assertRaises(TimeoutError):run_process(['not-run'],time.monotonic()-1,root/'deadline.log')
            self.assertIn('deadline exhausted',(root/'deadline.log').read_text())

    def test_semantic_failures_have_failed_operation_and_real_log(self):
        import json,os,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from deployment import native_linux_check as native
        for problem,operation in [('invalid-json','engine'),('dirty','source-preflight'),('changed-sha','final-commit'),('success','runtime-validation')]:
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();previous=Path.cwd();commits=[]
                def fake(command,deadline,log,env=None):
                    if 'info' in command:return 'invalid-json' if problem=='invalid-json' else '{}'
                    if command[0]=='git':
                        if 'status' in command:return ' M app/cli.py' if problem=='dirty' else ''
                        commits.append(1);return 'b'*40 if problem=='changed-sha' and len(commits)>1 else 'a'*40
                    if command[0]=='id':return 'agentwork'
                    log.write_text('synthetic check output');return ''
                try:
                    os.chdir(root)
                    with patch.object(native,'validate_runtime'):
                        if problem=='success':native.execute(root,'a'*40,fake)
                        else:
                            with self.assertRaises(ValueError):native.execute(root,'a'*40,fake)
                finally:os.chdir(previous)
                report=json.loads((root/'.review/native-linux/result.json').read_text())
                item=next(x for x in report['preflight']+report['postflight'] if x['name']==operation)
                self.assertTrue(Path(item['log']).is_file())
                self.assertEqual(item['status'],'passed' if problem=='success' else 'failed')
                if problem=='success':self.assertEqual(item['validation'],'runtime-validation');self.assertNotIn('command',item)
                else:self.assertIn('error',item);self.assertIn(item['error'],Path(item['log']).read_text())

    def test_second_output_drain_timeout_preserves_partial_output(self):
        import subprocess,tempfile,time
        from pathlib import Path
        from unittest.mock import Mock,patch
        from deployment import native_linux_check as native
        child=Mock();child.pid=999999
        child.communicate.side_effect=[subprocess.TimeoutExpired('synthetic',1,output=b'first partial'),subprocess.TimeoutExpired('synthetic',2,output=b'first partial and more')]
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'timeout.log'
            with patch.object(native.subprocess,'Popen',return_value=child),patch.object(native.os,'killpg'),self.assertRaises(TimeoutError):
                native.run_process(['synthetic'],time.monotonic()+1,log)
            self.assertIn('first partial and more',log.read_text())
            self.assertIn('Output drain timed out',log.read_text())

    def test_hosted_exception_is_narrow_and_container_user_is_unchanged(self):
        from deployment.verification_identity import hosted_runner
        from pathlib import Path
        root='/home/runner/work/agentwork-promptenglab/agentwork-promptenglab'
        env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64','GITHUB_REPOSITORY':'virtualseal/agentwork-promptenglab','GITHUB_SHA':'a'*40,'GITHUB_WORKSPACE':root}
        self.assertTrue(hosted_runner(env,1001,'Linux','x86_64',root))
        for change in [{'RUNNER_ENVIRONMENT':'self-hosted'},{'GITHUB_REPOSITORY':'other/repo'},{'GITHUB_SHA':'main'},{'GITHUB_WORKSPACE':'/tmp/other'}]:
            self.assertFalse(hosted_runner(dict(env,**change),1001,'Linux','x86_64',root))
        self.assertFalse(hosted_runner(env,0,'Linux','x86_64',root))
        self.assertFalse(hosted_runner(env,1001,'Darwin','arm64',root))
        base={'root':root,'engine':{'OSType':'linux','Architecture':'amd64','SecurityOptions':[]},'username':'runner','system':'Linux','machine':'x86_64','expected':'a'*40,'actual':'a'*40,'hosted':True}
        validate_runtime(**base)
        with self.assertRaises(ValueError):validate_runtime(**dict(base,hosted=False))
        self.assertIn('USER 502:502',Path('deployment/worker.Dockerfile').read_text())
