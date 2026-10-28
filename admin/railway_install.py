"""Human-admin-only non-secret installer. Never starts services or reads keys."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from .prepare_railway import APP, ROOT, prepare

FILES = ('proxy.py', 'railway_projects.py', 'config.json', 'railway_adapter.py')
BASE = FILES[:3]


def atomic(path, body):
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if os.path.exists(name): os.unlink(name)


def apply(action, stage, backup):
    if os.getuid() != 0:
        raise ValueError('Human administrator session required')
    manifest = json.loads((APP / 'admin/railway-package.json').read_text())
    # Rebuild expected bytes; caller-controlled stage cannot select installed code.
    baseline = ROOT if action == 'install' else backup
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / 'expected'
        prepare(output, baseline)
        expected = {name: (output / name).read_bytes() for name in FILES}
    if any((stage / name).read_bytes() != body for name, body in expected.items()):
        raise ValueError('Reviewed stage differs from pinned package')
    if action == 'install':
        if (ROOT / 'railway_adapter.py').exists():
            raise ValueError('Adapter already installed')
        originals = {name: (ROOT / name).read_bytes() for name in manifest['baseline_sha256']}
        for name, body in originals.items():
            if hashlib.sha256(body).hexdigest() != manifest['baseline_sha256'][name]:
                raise ValueError('Baseline changed before backup')
        backup.mkdir(mode=0o700)
        for name, body in originals.items(): atomic(backup / name, body)
        # Exact rollback bytes exist before any installed mutation.
        for name in FILES: atomic(ROOT / name, expected[name])
    else:
        if any((ROOT / name).read_bytes() != expected[name] for name in FILES):
            raise ValueError('Installed package drift; manual admin recovery required')
        for name in BASE: atomic(ROOT / name, (backup / name).read_bytes())
        (ROOT / 'railway_adapter.py').unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'rollback'])
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    apply(args.action, args.stage, args.backup)
