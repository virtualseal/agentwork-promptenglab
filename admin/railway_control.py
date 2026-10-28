"""Human-admin binding controls; never reads provider credentials or calls APIs."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from .railway_adapter import BINDING, PROJECT, REPO, approval, protected_json, validate_binding
import time


def save(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o644)  # Binding contains no credentials; admin-only writes.
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['initialize', 'bind', 'enable', 'disable'])
    parser.add_argument('--service')
    parser.add_argument('--environment')
    parser.add_argument('--approval', type=Path)
    args = parser.parse_args()
    if os.getuid() != 0:
        raise SystemExit('Human administrator session required; not an app startup command')
    if args.action == 'initialize':
        if BINDING.exists(): raise SystemExit('Binding already exists')
        value = {'project': PROJECT, 'repo': REPO, 'service': None, 'environment': None,
                 'writes_enabled': False, 'approval': None}
    else:
        value = protected_json(BINDING)
        validate_binding(value)
        if args.action == 'disable':
            value.update(writes_enabled=False, approval=None)
        elif args.action == 'bind':
            if not args.service or not args.environment: raise SystemExit('Both existing IDs required')
            value.update(service=args.service, environment=args.environment, writes_enabled=False, approval=None)
        else:
            if not args.approval or not value['service'] or not value['environment']:
                raise SystemExit('Bound IDs and protected approval required')
            value['approval'] = protected_json(args.approval)
            approval(value, value['approval']['sha'], time.time())
            value['writes_enabled'] = True
    validate_binding(value)
    save(BINDING, value)


if __name__ == '__main__':
    main()
