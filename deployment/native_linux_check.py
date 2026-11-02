"""Verification only on an admin-provisioned, dedicated rootless native runner."""
import os
if __package__:
    from .verification_identity import require_verification_identity,verification_hosted
else:
    from verification_identity import require_verification_identity,verification_hosted
require_verification_identity()

from pathlib import Path
import json
import platform
import signal
import subprocess
import sys
import time
import uuid


def validate_runtime(root,engine,username,system,machine,expected,actual,hosted=False):
    root=Path(root).resolve()
    if username!=('runner' if hosted else 'agentwork') or system!='Linux' or machine!='x86_64':
        raise ValueError('Native Linux x86_64 agentwork runner required')
    if not hosted and not root.is_relative_to(Path('/Users/agentwork/apps')):
        raise ValueError('Project must be under /Users/agentwork/apps')
    if not expected or len(expected)!=40 or any(c not in '0123456789abcdef' for c in expected) or actual!=expected:
        raise ValueError('Dispatched immutable commit does not match checkout')
    if engine.get('OSType')!='linux' or engine.get('Architecture') not in ('x86_64','amd64'):
        raise ValueError('Native Linux/amd64 Docker engine required')
    if not hosted and not any(str(value).split(',')[0]=='name=rootless' for value in engine.get('SecurityOptions',[])):
        raise ValueError('Dedicated rootless Docker required; no host-root socket')


def run_process(command,deadline,log,env=None):
    process=None
    try:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Native verification deadline exhausted')
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True,env=env)
        output,_=process.communicate(timeout=remaining)
        log.write_text(output)
        if process.returncode:raise subprocess.CalledProcessError(process.returncode,command,output=output)
        return output
    except subprocess.TimeoutExpired as error:
        def decoded(value):return value.decode(errors='replace') if isinstance(value,bytes) else (value or '')
        captured=decoded(error.output)
        log.write_text(captured+'\nExecution timed out; terminating process group\n')
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        try:
            output,_=process.communicate(timeout=2)
            captured=decoded(output) or captured
        except subprocess.TimeoutExpired as drain_error:
            more=decoded(drain_error.output)
            captured=more if more.startswith(captured) else captured+'\n'+more
            captured+='\nOutput drain timed out; pipe closed\n'
            process.stdout.close()
        log.write_text(captured+'\nTimed out; process group terminated\n')
        raise TimeoutError('Check execution deadline exhausted') from error
    except BaseException as error:
        if not log.exists():log.write_text(type(error).__name__+': '+str(error)+'\n')
        raise
    finally:
        if process is not None:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait(timeout=2)


def execute(root,expected,runner=run_process):
    # Reserve cleanup within the total fourteen-minute allowance, including preflight.
    deadline=time.monotonic()+800
    root=Path(root);state=root/'.review/native-linux';state.mkdir(parents=True,exist_ok=True)
    invocation=uuid.uuid4().hex;directory=state/invocation;directory.mkdir()
    hosted=verification_hosted()
    host='unix:///var/run/docker.sock' if hosted else 'unix:///run/user/502/docker.sock'
    config=directory/'docker-client';config.mkdir()
    command=['docker','--config',str(config),'--host',host]
    checks=[['-m','unittest','discover','-s','tests','-p','test_worker_context.py','-v'],['-m','unittest','discover','-s','evals','-v'],['deployment/build_linux_worker.py','--host',host],['deployment/verify_linux_worker.py','--host',host]]
    report={'invocation':invocation,'expected_commit':expected,'commit':None,'state':'preflight','ready':False,'deployed':False,'provider_calls':0,'preflight':[], 'postflight':[], 'checks':[{'command':[sys.executable,'-B',*args],'status':'not_run','log':str(directory/('check-'+str(i)+'.log'))} for i,args in enumerate(checks)]}
    def save():
        # Replace latest immediately, including failures before checkout validation.
        for path in [directory/'result.json',state/'result.json']:
            temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(report,indent=2)+'\n');os.replace(temporary,path)
    def operation(group,name,argv=None,callback=None,validate=lambda value:value):
        item={'name':name,'status':'running','log':str(directory/(name+'.log'))}
        item.update({'command':argv} if argv else {'validation':name})
        report[group].append(item);save()
        try:
            output=runner(argv,deadline,Path(item['log'])) if argv else callback()
            output=validate(output)
            with Path(item['log']).open('a') as log:log.write('\nValidation passed: '+name+'\n')
            item['status']='passed';save();return output
        except BaseException as error:
            item.update({'status':'failed','error':type(error).__name__+': '+str(error)})
            with Path(item['log']).open('a') as log:log.write('\n'+item['error']+'\n')
            save();raise
    save();started=False
    environment=dict(os.environ,THURSDAY_VERIFY_RUN=invocation)
    try:
        if Path.cwd().resolve()!=root.resolve():raise ValueError('Run from reviewed repository root')
        info=operation('preflight','engine',command+['info','--format','{{json .}}'],validate=json.loads)
        head=operation('preflight','commit',['git','rev-parse','HEAD']).strip();report['commit']=head
        username=operation('preflight','identity',['id','-un']).strip()
        def pristine(group):
            def clean(value):
                if value.strip():raise ValueError('Checkout contains modified or untracked source')
                return value
            operation(group,'source-'+group,['git','status','--porcelain','--untracked-files=all'],validate=clean)
        pristine('preflight')
        operation('preflight','runtime-validation',callback=lambda:validate_runtime(root,info,username,platform.system(),platform.machine(),expected,head,hosted))
        report['state']='verifying';save()
        for check in report['checks']:
            check['status']='running';started=True;save()
            try:runner(check['command'],deadline,Path(check['log']),environment)
            except BaseException as error:
                check.update({'status':'failed','error':type(error).__name__+': '+str(error)})
                if not Path(check['log']).exists():Path(check['log']).write_text(check['error']+'\n')
                save();raise
            check['status']='passed';save()
        pristine('postflight')
        def unchanged(value):
            if value.strip()!=expected:raise ValueError('Checkout changed during verification')
            return value
        operation('postflight','final-commit',['git','rev-parse','HEAD'],validate=unchanged)
        report.update({'state':'native_checks_passed','note':'Native checks only; exact-head review, Slack/cloud activation and rollout authorization remain separate'})
    except BaseException as error:
        report.update({'state':'failed','error':type(error).__name__+': '+str(error)});raise
    finally:
        if started:
            cleanup_deadline=min(deadline+30,time.monotonic()+25)
            report['cleanup']='passed'
            # Verifier resource names are derived from this invocation only.
            for kind,name in [('container','thursday-check-'+invocation),('volume','thursday-verify-'+invocation)]:
                args=[kind,'rm']+(['--force'] if kind=='container' else [])+[name]
                try:runner(command+args,cleanup_deadline,directory/('cleanup-'+kind+'.log'))
                except subprocess.CalledProcessError as error:
                    if ('no such '+kind) not in (error.output or '').lower():report['cleanup']='failed'
                except BaseException:report['cleanup']='failed'
            if report['cleanup']=='failed':report['state']='failed'
        save()
        print(json.dumps(report),flush=True)
        for item in report['preflight']+report['checks']+report['postflight']:
            if item['status']=='failed' and Path(item['log']).is_file():
                print('Failed operation: '+item.get('name',str(item.get('command'))),flush=True)
                print(Path(item['log']).read_text()[-32768:],flush=True)
    if report['state']!='native_checks_passed':raise RuntimeError('Native verification or cleanup failed')
    return report


def main():execute(Path(__file__).resolve().parent.parent,os.environ.get('EXPECTED_COMMIT'))

if __name__=='__main__':main()
