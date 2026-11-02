"""Narrow verification-host exception; never used by the application launcher."""
import os
from pathlib import Path
import platform
import re


def hosted_runner(environ,uid,system,machine,root):
    workspace=environ.get('GITHUB_WORKSPACE','')
    return (uid==1001 and system=='Linux' and machine=='x86_64'
            and environ.get('GITHUB_ACTIONS')=='true'
            and environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
            and environ.get('RUNNER_OS')=='Linux' and environ.get('RUNNER_ARCH')=='X64'
            and environ.get('GITHUB_REPOSITORY')=='virtualseal/agentwork-promptenglab'
            and bool(re.fullmatch(r'[0-9a-f]{40}',environ.get('GITHUB_SHA','')))
            and Path(workspace).is_absolute() and Path(workspace).resolve()==Path(root).resolve())


def verification_hosted():
    root=Path(__file__).resolve().parent.parent
    return hosted_runner(os.environ,os.getuid(),platform.system(),platform.machine(),root)


def require_verification_identity():
    if os.getuid()==502:return
    if not verification_hosted():
        raise SystemExit('Verification requires agentwork UID502 or the authorized GitHub-hosted verification runner')
