"""Result-only deployment client. No default mutation and no retries."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
from admin.railway_adapter import PROJECT, REPO, validate_payload, WORKSPACE


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
    operation = 'deployment.' + args.operation
    validate_payload({'workspace_id': WORKSPACE, 'owner': 'virtualseal'}, operation, value)
    path = Path('/Library/Application Support/CredentialProxy/client.py')
    spec = importlib.util.spec_from_file_location('installed_credential_client', path)
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    # The installed framed client validates the complete transfer receipt.
    events = client.request('/Library/Application Support/CredentialProxy/run/api.sock',
                            {'integration': 'workspace-railway', 'operation': operation, 'payload': value})
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
