"""Human-admin-only one-module discovery upgrade. Never opens credential files."""
import argparse,hashlib,json,os,socket,stat,subprocess,tempfile,time
from pathlib import Path
ROOT=Path('/Library/Application Support/CredentialProxy')
SOURCE=Path('/Users/agentwork/apps/thursday-restaurants/admin/personal_railway.py')
BEFORE='80ebaa51ec8bf4f1f02f8d70082da41bbba46d0efc388d17187946573b530459'
AFTER='8b24d28c19daa28c8e6d4fbebe0d2a1521f81e22b1360056e412ad52f276bca2'
PROJECT='2d6b15bd-cdab-4978-9518-2d44820cfc85'
REPO='virtualseal/agentwork-promptenglab'
ENVIRONMENT='b862c0ae-b2e6-430f-9abf-5e55b4ba1e66'
SERVICE='system/local.credential-proxy'
PLIST='/Library/LaunchDaemons/local.credential-proxy.plist'
BACKUP=ROOT/'admin-backups/personal-discovery-20261029'


def protected(path,directory=False):
    info=path.lstat()
    valid=stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('Unprotected administration path')


def wait_stopped(timeout=10):
    deadline=time.monotonic()+timeout
    while True:
        check=socket.socket(socket.AF_UNIX);check.settimeout(min(1,max(0.01,deadline-time.monotonic())))
        try:check.connect(str(ROOT/'run/api.sock'))
        except (FileNotFoundError,ConnectionRefusedError):return
        finally:check.close()
        if time.monotonic()>=deadline:
            raise ValueError('Proxy still accepts connections; leave stopped and inspect')
        time.sleep(min(0.1,max(0,deadline-time.monotonic())))


def upgrade(resume_stopped=False):
    if os.getuid()!=0:raise ValueError('Human admin session required; development/runtime must stay UID502')
    # The human copies this reviewed standalone helper into protected ROOT first.
    helper=Path(__file__).absolute();protected(helper)
    for path in helper.parents:protected(path,True)
    for path in [ROOT,*ROOT.parents]:protected(path,True)
    target=ROOT/'personal_railway.py';config=ROOT/'config.json';protected(target);protected(config)
    previous=target.read_bytes();configuration=config.read_bytes()
    if hashlib.sha256(previous).hexdigest()!=BEFORE:raise ValueError('Installed adapter changed or upgrade already attempted; inspect before retry')
    if SOURCE.resolve()!=SOURCE:raise ValueError('Unsafe reviewed source path')
    proposed=SOURCE.read_bytes()
    if hashlib.sha256(proposed).hexdigest()!=AFTER:raise ValueError('Reviewed adapter bytes changed')
    policy=json.loads(configuration)['integrations']['personal-thursday-railway']
    if (policy.get('service')!='railway-personal' or policy.get('railway_project')!=PROJECT
            or policy.get('environment_id')!=ENVIRONMENT or policy.get('repo')!=REPO
            or not isinstance(policy.get('operations'),dict) or set(policy['operations'])!={'connection.inspect'}):
        raise ValueError('Personal policy scope changed')
    parent=BACKUP.parent
    if resume_stopped:
        # Explicit recovery only: original source and protected source-only backup
        # must agree. Never reissue bootout after an uncertain stop.
        protected(parent,True);protected(BACKUP,True)
        backup=BACKUP/'personal_railway.before.py';protected(backup)
        if backup.read_bytes()!=previous:raise ValueError('Recovery backup changed')
    else:
        if not parent.exists():parent.mkdir(mode=0o755)
        protected(parent,True);BACKUP.mkdir(mode=0o700)
        (BACKUP/'personal_railway.before.py').write_bytes(previous)
        subprocess.run(['/bin/launchctl','bootout',SERVICE],check=True,timeout=15)
    wait_stopped()
    if target.read_bytes()!=previous or config.read_bytes()!=configuration:raise ValueError('Installed files changed while stopping; leave stopped')
    fd,name=tempfile.mkstemp(dir=ROOT)
    try:
        with os.fdopen(fd,'wb') as output:output.write(proposed);output.flush();os.fsync(output.fileno())
        os.chmod(name,0o644);os.replace(name,target)
        directory=os.open(ROOT,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(name):os.unlink(name)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=AFTER or config.read_bytes()!=configuration:
        raise ValueError('Upgrade verification failed; leave proxy stopped')
    subprocess.run(['/bin/launchctl','bootstrap','system',PLIST],check=True,timeout=15)
    print('Personal read-only service discovery installed; configuration and credentials unchanged. No deploy or Slack send.')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume-stopped',action='store_true',help='Resume only the inspected pre-replacement stopped state')
    upgrade(parser.parse_args().resume_stopped)
