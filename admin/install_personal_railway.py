"""Human-admin-only install and new personal-token import; never starts services."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import warnings
from .prepare_personal_railway import ROOT,APP,prepare,render_proxy
from .personal_railway import INTEGRATION
from .railway_install import atomic


def require_directory(path,uid,private=False):
    info=path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=uid
            or info.st_mode&(0o077 if private else 0o022)
            or path.resolve()!=path):
        raise ValueError('Installation requires protected directory ownership/mode')


def require_file(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
        raise ValueError('Package files must be root-owned and not group/world writable')


def require_protected_package(package):
    for parent in [package,*package.absolute().parents]:require_directory(parent,0)
    require_directory(package/'admin',0)
    manifest=package/'admin/personal-railway-package.json';require_file(manifest)
    entries=json.loads(manifest.read_text())['sha256']
    for name in entries:
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid protected package path')
        path=package/relative
        for parent in path.parents:
            require_directory(parent,0)
            if parent==package:break
        require_file(path)


def install(stage,backup,environment):
    if os.getuid()!=0:raise ValueError('Human administrator required; do not run development as root')
    require_protected_package(APP)
    # No live proxy may be changed. Unknown socket outcomes fail closed.
    sock=socket.socket(socket.AF_UNIX);sock.settimeout(2)
    try:
        sock.connect(str(ROOT/'run/api.sock'))
    except (FileNotFoundError,ConnectionRefusedError):pass
    else:raise ValueError('Stop the existing credential proxy through its known admin service manager first')
    finally:sock.close()
    for parent in [ROOT,*ROOT.parents]:
        require_directory(parent,0)
    with tempfile.TemporaryDirectory() as temporary:
        expected=Path(temporary)/'stage';prepare(expected,environment)
        names=['proxy.patch','policy-addition.json','personal_railway.py','railway.connection.json']
        if any((stage/n).is_symlink() or (stage/n).read_bytes()!=(expected/n).read_bytes() for n in names):raise ValueError('Stage differs from reviewed package')
        config=json.loads((ROOT/'config.json').read_text())
        private=Path(config['private_dir'])
        # Inspect directory metadata only; never read any existing private key file.
        require_directory(private,503,private=True)
        keyfile=private/(INTEGRATION+'.key')
        if os.path.lexists(keyfile) or (ROOT/'personal_railway.py').exists():raise ValueError('Personal installation already exists; do not overwrite')
        for parent in backup.absolute().parents:
            require_directory(parent,0)
        if backup.exists() or backup.is_symlink():raise ValueError('Use a new protected backup path')
        backup.mkdir(mode=0o700)
        for name in ['proxy.py','config.json']:atomic(backup/name,(ROOT/name).read_bytes())
        with warnings.catch_warnings():
            warnings.simplefilter('error',getpass.GetPassWarning)
            token=getpass.getpass('Personal Railway PROJECT token (hidden; never paste in chat): ')
        if not 20<=len(token)<=4096 or any(ord(c)<33 or ord(c)>126 for c in token):raise ValueError('Invalid project token format')
        fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'w') as stream:
                os.fchown(stream.fileno(),503,503)
                stream.write(token);stream.flush();os.fsync(stream.fileno())
        finally:token=None
        # Proxy is stopped; backups exist before these mutations. On partial error leave stopped.
        config['integrations'].update(json.loads((expected/'policy-addition.json').read_text()))
        atomic(ROOT/'personal_railway.py',(expected/'personal_railway.py').read_bytes())
        atomic(ROOT/'proxy.py',render_proxy((ROOT/'proxy.py').read_text()).encode())
        atomic(ROOT/'config.json',(json.dumps(config,indent=2)+'\n').encode())
    print('Personal read-only adapter installed. Keep proxy stopped until installed package checks pass. No deployment enabled.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',type=Path,required=True);p.add_argument('--backup',type=Path,required=True);p.add_argument('--environment',required=True)
    a=p.parse_args();install(a.stage,a.backup,a.environment)
