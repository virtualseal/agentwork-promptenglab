"""Synthetic administration upgrade failures; never root or real service operations."""
import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from admin import upgrade_personal_discovery as upgrade

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.old=b'synthetic old adapter';self.new=b'synthetic new adapter'
        self.target=self.root/'personal_railway.py';self.target.write_bytes(self.old)
        self.source=self.root/'source.py';self.source.write_bytes(self.new)
        self.config=self.root/'config.json';self.policy={'integrations':{'work':{'unchanged':True},'personal-thursday-railway':{'service':'railway-personal','railway_project':upgrade.PROJECT,'environment_id':upgrade.ENVIRONMENT,'repo':upgrade.REPO,'operations':{'connection.inspect':{}}}}}
        self.config.write_text(json.dumps(self.policy));self.original=self.config.read_bytes()
        self.backup=self.root/'admin-backups/change'
        self.sock=Mock();self.sock.connect.side_effect=ConnectionRefusedError()
        changes=[patch.object(upgrade,'ROOT',self.root),patch.object(upgrade,'SOURCE',self.source),
                 patch.object(upgrade,'BACKUP',self.backup),patch.object(upgrade,'BEFORE',hashlib.sha256(self.old).hexdigest()),
                 patch.object(upgrade,'AFTER',hashlib.sha256(self.new).hexdigest()),patch.object(upgrade,'protected'),
                 patch.object(upgrade.os,'getuid',return_value=0),patch.object(upgrade.socket,'socket',return_value=self.sock),
                 patch.object(upgrade.subprocess,'run')]
        for item in changes:item.start();self.addCleanup(item.stop)

    def test_upgrade_only_adapter_backups_before_service_stop_and_keeps_config(self):
        def command(*args,**kwargs):self.assertTrue((self.backup/'personal_railway.before.py').exists())
        upgrade.subprocess.run.side_effect=command
        upgrade.upgrade()
        self.assertEqual(self.target.read_bytes(),self.new);self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual((self.backup/'personal_railway.before.py').read_bytes(),self.old)
        self.assertEqual(upgrade.subprocess.run.call_count,2)
        self.assertIn('bootout',upgrade.subprocess.run.call_args_list[0].args[0]);self.assertIn('bootstrap',upgrade.subprocess.run.call_args_list[1].args[0])
        with self.assertRaises(ValueError):upgrade.upgrade()
        self.assertEqual(upgrade.subprocess.run.call_count,2)

    def test_changed_source_wrong_scope_or_running_socket_cannot_overwrite(self):
        self.source.write_bytes(b'unreviewed')
        with self.assertRaises(ValueError):upgrade.upgrade()
        upgrade.subprocess.run.assert_not_called();self.assertEqual(self.target.read_bytes(),self.old)
        self.source.write_bytes(self.new);self.sock.connect.side_effect=None
        clock=iter([0,0,11])
        with patch.object(upgrade.time,'monotonic',side_effect=lambda:next(clock)):
            with self.assertRaises(ValueError):upgrade.upgrade()
        self.assertEqual(self.target.read_bytes(),self.old);self.assertEqual(upgrade.subprocess.run.call_count,1)

    def test_delayed_shutdown_finishes_before_replacement(self):
        self.sock.connect.side_effect=[None,None,ConnectionRefusedError()]
        with patch.object(upgrade.time,'sleep'):
            upgrade.upgrade()
        self.assertEqual(self.sock.connect.call_count,3)
        self.assertEqual(self.target.read_bytes(),self.new)
        self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual(upgrade.subprocess.run.call_count,2)

    def test_explicit_resume_preserves_backup_and_never_reissues_stop(self):
        self.backup.mkdir(parents=True)
        backup=self.backup/'personal_railway.before.py';backup.write_bytes(self.old)
        upgrade.upgrade(resume_stopped=True)
        self.assertEqual(self.target.read_bytes(),self.new)
        self.assertEqual(backup.read_bytes(),self.old)
        self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual(upgrade.subprocess.run.call_count,1)
        self.assertIn('bootstrap',upgrade.subprocess.run.call_args.args[0])

    def test_resume_rejects_changed_backup_or_live_socket_without_mutation(self):
        self.backup.mkdir(parents=True)
        backup=self.backup/'personal_railway.before.py';backup.write_bytes(b'changed')
        with self.assertRaises(ValueError):upgrade.upgrade(resume_stopped=True)
        upgrade.subprocess.run.assert_not_called()
        backup.write_bytes(self.old);self.sock.connect.side_effect=None
        with patch.object(upgrade.time,'monotonic',side_effect=[0,0,11]):
            with self.assertRaises(ValueError):upgrade.upgrade(resume_stopped=True)
        upgrade.subprocess.run.assert_not_called()
        self.assertEqual(self.target.read_bytes(),self.old)
        self.assertEqual(backup.read_bytes(),self.old)

    def test_unknown_stop_or_restart_outcomes_never_reissued(self):
        upgrade.subprocess.run.side_effect=subprocess.TimeoutExpired('synthetic stop',15)
        with self.assertRaises(subprocess.TimeoutExpired):upgrade.upgrade()
        self.assertEqual(self.target.read_bytes(),self.old);self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual(upgrade.subprocess.run.call_count,1)
        with self.assertRaises((ValueError,FileExistsError)):upgrade.upgrade()
        self.assertEqual(upgrade.subprocess.run.call_count,1)

    def test_configuration_change_during_stop_leaves_adapter_untouched(self):
        def stop(*args,**kwargs):self.config.write_text(json.dumps({'changed':True}))
        upgrade.subprocess.run.side_effect=stop
        with self.assertRaises(ValueError):upgrade.upgrade()
        self.assertEqual(self.target.read_bytes(),self.old);self.assertEqual(upgrade.subprocess.run.call_count,1)

    def test_foreign_or_missing_repository_fails_before_backup_and_stop(self):
        for repo in [None,'other/repository']:
            self.policy['integrations']['personal-thursday-railway']['repo']=repo
            self.config.write_text(json.dumps(self.policy))
            with self.assertRaises(ValueError):upgrade.upgrade()
            self.assertFalse(self.backup.exists());upgrade.subprocess.run.assert_not_called()
            self.assertEqual(self.target.read_bytes(),self.old)

    def assert_restart_failure(self,failure):
        from contextlib import redirect_stdout
        import io
        output=io.StringIO();upgrade.subprocess.run.side_effect=[None,failure]
        with redirect_stdout(output),self.assertRaises(type(failure)):upgrade.upgrade()
        self.assertEqual(output.getvalue(),'');self.assertEqual(self.target.read_bytes(),self.new)
        self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual((self.backup/'personal_railway.before.py').read_bytes(),self.old)
        self.assertEqual(upgrade.subprocess.run.call_count,2)
        with self.assertRaises(ValueError):upgrade.upgrade()
        self.assertEqual(upgrade.subprocess.run.call_count,2)

    def test_restart_timeout_preserves_evidence_and_never_reissues(self):
        self.assert_restart_failure(subprocess.TimeoutExpired('synthetic restart',15))

    def test_restart_nonzero_preserves_evidence_and_never_reissues(self):
        self.assert_restart_failure(subprocess.CalledProcessError(1,'synthetic restart'))

    def test_atomic_replace_failure_preserves_old_module_and_refuses_retry(self):
        from contextlib import redirect_stdout
        import io
        output=io.StringIO()
        with patch.object(upgrade.os,'replace',side_effect=OSError('synthetic replace failed')),redirect_stdout(output),self.assertRaises(OSError):upgrade.upgrade()
        self.assertEqual(output.getvalue(),'');self.assertEqual(self.target.read_bytes(),self.old)
        self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual((self.backup/'personal_railway.before.py').read_bytes(),self.old)
        self.assertEqual(upgrade.subprocess.run.call_count,1)
        with self.assertRaises(FileExistsError):upgrade.upgrade()
        self.assertEqual(upgrade.subprocess.run.call_count,1)

    def test_post_replace_verification_failure_never_restarts_or_reports_success(self):
        from contextlib import redirect_stdout
        import io
        original=upgrade.os.replace
        def corrupt(source,target):original(source,target);self.target.write_bytes(b'synthetic corrupt module')
        output=io.StringIO()
        with patch.object(upgrade.os,'replace',side_effect=corrupt),redirect_stdout(output),self.assertRaises(ValueError):upgrade.upgrade()
        self.assertEqual(output.getvalue(),'');self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual((self.backup/'personal_railway.before.py').read_bytes(),self.old)
        self.assertEqual(upgrade.subprocess.run.call_count,1)
        with self.assertRaises(ValueError):upgrade.upgrade()
        self.assertEqual(upgrade.subprocess.run.call_count,1)

class UpgradeBoundaryTests(unittest.TestCase):
    def test_nonadmin_refuses_before_reading_installed_files(self):
        with patch.object(upgrade.os,'getuid',return_value=502),patch.object(upgrade.subprocess,'run') as command:
            with self.assertRaises(ValueError):upgrade.upgrade()
            command.assert_not_called()
    def test_root_from_mutable_checkout_is_rejected(self):
        with patch.object(upgrade.os,'getuid',return_value=0),patch.object(upgrade.subprocess,'run') as command:
            with self.assertRaises(ValueError):upgrade.upgrade()
            command.assert_not_called()
