"""Build using an explicit source-only context, never the private checkout root."""
import os
if __package__:
    from .verification_identity import require_verification_identity,verification_hosted
else:
    from verification_identity import require_verification_identity,verification_hosted
require_verification_identity()

import argparse
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile


def stage_context(root,destination):
    root=Path(root).resolve();destination=Path(destination)
    directories=[root/'app',root/'deployment']
    if any(p.is_symlink() or not p.is_dir() for p in directories):
        raise ValueError('Source directories must be real directories')
    paths=[*sorted((root/'app').glob('*.py')),root/'run',root/'deployment/worker.py',root/'deployment/worker.config.json',root/'deployment/worker.Dockerfile']
    for path in paths:
        if not stat.S_ISREG(path.lstat().st_mode) or path.resolve()!=path:
            raise ValueError('Build source must be a regular non-symlink file')
    # Validate every source before copying any of it.
    for path in paths:
        target=destination/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
    return [str(p.relative_to(root)) for p in paths]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    parser.add_argument('--image',default='thursday-worker:local')
    args=parser.parse_args();root=Path(__file__).resolve().parent.parent
    state=root/'.review/build-runtime';state.mkdir(parents=True,exist_ok=True)
    config=state/'docker-client';config.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='worker-context-',dir=state) as directory:
        stage_context(root,directory)
        command=['docker','--config',str(config),'--host',args.host,'build','--platform','linux/amd64','-f','deployment/worker.Dockerfile','-t',args.image,directory]
        subprocess.run(command,check=True,timeout=420)


if __name__=='__main__':main()
