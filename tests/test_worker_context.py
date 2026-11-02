"""Private workspace files and symlink escapes must not enter build contexts."""
from pathlib import Path
import tempfile
import unittest
from deployment.build_linux_worker import stage_context


class WorkerContextTests(unittest.TestCase):
    def test_private_artifacts_and_nested_files_never_enter_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()/'source';out=Path(directory)/'context'
            for name in ['app/__init__.py','run','deployment/worker.py','deployment/worker.config.json','deployment/worker.Dockerfile','.env.local','.git/config','admin/token','local-data/saved.json','app/__pycache__/cached.pyc','app/nested/private.py']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic')
            stage_context(root,out)
            actual={str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()}
            self.assertEqual(actual,{'app/__init__.py','run','deployment/worker.py','deployment/worker.config.json','deployment/worker.Dockerfile'})
            (root/'app/escape.py').symlink_to(root/'.env.local')
            rejected=Path(directory)/'rejected'
            with self.assertRaises(ValueError):stage_context(root,rejected)
            self.assertFalse(rejected.exists())
