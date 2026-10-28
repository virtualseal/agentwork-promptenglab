"""Stage an additive proxy patch from pinned non-secret installed bytes only.

Does not install, restart, read keys or contact providers. Output must be new.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path('/Library/Application Support/CredentialProxy')
APP = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(output, baseline=ROOT):
    manifest = json.loads((APP / 'admin/railway-package.json').read_text())
    for name, expected in manifest['baseline_sha256'].items():
        if digest(baseline / name) != expected:
            raise ValueError('Installed non-secret baseline drift: ' + name)
    for name, expected in manifest['sha256'].items():
        if digest(APP / name) != expected:
            raise ValueError('Package drift: ' + name)
    source = (baseline / 'railway_projects.py').read_text()
    original = source
    source = source.replace("OPERATIONS = {'project.ensure'}", "OPERATIONS = {'project.ensure', 'deployment.inspect', 'deployment.submit', 'deployment.reconcile'}")
    source = source.replace('    validate_policy(policy)\n    if operation not in OPERATIONS',
        "    validate_policy(policy)\n    if operation.startswith('deployment.'):\n        import railway_adapter\n        return railway_adapter.validate_payload(policy, operation, value)\n    if operation not in OPERATIONS")
    source = source.replace('    result = run(API(key, limits, control), policy, operation, value)',
        "    if operation.startswith('deployment.'):\n        import railway_adapter\n        yield from railway_adapter.dispatch(policy, key, operation, value, limits, control)\n        return\n    result = run(API(key, limits, control), policy, operation, value)")
    proxy = (baseline / 'proxy.py').read_text()
    changed_proxy = proxy.replace("else {'project.ensure'} if service == 'railway-projects'", "else {'project.ensure', 'deployment.inspect', 'deployment.submit', 'deployment.reconcile'} if service == 'railway-projects'")
    if source == original or proxy == changed_proxy:
        raise ValueError('Required patch anchor absent')
    config = json.loads((baseline / 'config.json').read_text())
    policy = config['integrations']['workspace-railway']
    if policy['service'] != 'railway-projects' or policy['workspace_id'] != '1fc03572-3e94-4c8b-bb59-42dbc26e0d28':
        raise ValueError('Credential binding baseline mismatch')
    # Existing integration continues using its existing key entry. No new key
    # alias, key file, secret read, UID grant or provider is introduced.
    for operation in ('deployment.inspect', 'deployment.submit', 'deployment.reconcile'):
        policy['operations'][operation] = {'max_request_bytes': 2048, 'max_response_bytes': 2097152,
                                          'idle_timeout_seconds': 5, 'total_timeout_seconds': 90}
    output.mkdir(mode=0o700)
    for name, text in (('proxy.py', changed_proxy), ('railway_projects.py', source),
                       ('config.json', json.dumps(config, indent=2) + '\n')):
        (output / name).write_text(text)
    shutil.copyfile(APP / 'admin/railway_adapter.py', output / 'railway_adapter.py')
    patch = ''.join(difflib.unified_diff(original.splitlines(True), source.splitlines(True),
                                       fromfile='a/railway_projects.py', tofile='b/railway_projects.py'))
    patch += ''.join(difflib.unified_diff(proxy.splitlines(True), changed_proxy.splitlines(True),
                                        fromfile='a/proxy.py', tofile='b/proxy.py'))
    (output / 'proxy.patch').write_text(patch)
    (output / 'SHA256.json').write_text(json.dumps({p.name: digest(p) for p in output.iterdir() if p.is_file()}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    prepare(args.output)
