"""Result-only deployment client. No default mutation and no retries."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
from admin.personal_railway import PROJECT, REPO, INTEGRATION, validate_payload


CONNECTION=Path(__file__).resolve().parents[1]/'railway.connection.json'

def load_connection():
    if CONNECTION.is_symlink() or CONNECTION.stat().st_size>4096:
        raise ValueError('Unsafe personal connection configuration')
    value=json.loads(CONNECTION.read_text())
    if set(value)!={'schema','integration','project','environment','repo','writes_enabled'} or value['schema']!=1 or value['integration']!=INTEGRATION or value['project']!=PROJECT or value['repo']!=REPO or value['writes_enabled'] is not False:
        raise ValueError('Personal connection scope mismatch; no fallback permitted')
    validate_payload({'railway_project':PROJECT,'repo':REPO,'environment_id':value['environment']},'connection.inspect',{'project':PROJECT,'environment':value['environment'],'repo':REPO})
    return value

def main():
    if os.getuid() != 502:
        raise SystemExit('Requires agentwork UID 502')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['inspect', 'submit', 'reconcile'])
    parser.add_argument('--sha')
    args = parser.parse_args()
    value = {'project': PROJECT, 'repo': REPO}
    if args.sha is not None:
        value['sha'] = args.sha
    if args.operation != 'inspect' or args.sha is not None:
        raise ValueError('Personal Railway connection is read-only; deployment operations disabled')
    connection = load_connection()
    value['environment'] = connection['environment']
    operation = 'connection.inspect'
    validate_payload({'railway_project':PROJECT,'repo':REPO,'environment_id':connection['environment']}, operation, value)
    path = Path('/Library/Application Support/CredentialProxy/client.py')
    spec = importlib.util.spec_from_file_location('installed_credential_client', path)
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    # The installed framed client validates the complete transfer receipt.
    events = client.request('/Library/Application Support/CredentialProxy/run/api.sock',
                            {'integration': INTEGRATION, 'operation': operation, 'payload': value})
    result = None
    received = False
    complete = False
    try:
        for event in events:
            if complete:
                raise RuntimeError('Unexpected event after transfer receipt')
            if event['type'] == 'response' and not received:
                result = event['body']
                received = True
            elif event['type'] == 'done' and received:
                complete = True
            elif event['type'] != 'start':
                raise RuntimeError('Unexpected deployment response')
        if not complete:
            raise RuntimeError('Incomplete deployment response; reconcile before retrying writes')
    finally:
        events.close()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
