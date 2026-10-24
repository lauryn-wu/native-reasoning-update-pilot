"""Bounded offline compiled reference execution, separate from candidate grading.

Only source and invocation inputs enter this Docker container. Authoritative
expected outputs remain on the host. This module never invokes a model/provider.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from .assets import checked_path
from .sandbox import DockerSandbox, SandboxUnavailable
from .util import digest, file_digest

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'provenance/reference_construction_policy.json'


class ConstructionBudget:
    def __init__(self, seconds=1800):
        if not 0 < seconds <= 1800:
            raise ValueError('Construction campaign must fit the uniform 1800-second bound')
        self.limit = seconds
        self.spent = 0.0
        self.attempts = []

    def allowance(self):
        remaining = self.limit - self.spent
        if remaining <= 40:
            raise RuntimeError('Offline construction budget exhausted')
        return min(600, remaining - 40)  # Reserve bounded client cleanup/transport overhead.


def run_compiled(source, inputs, *, budget=None, flags=None, purpose='reference', force_exact=False):
    """Compile and run a batch interface under the immutable construction policy."""
    if type(force_exact) is not bool:
        raise ValueError('force_exact must be boolean')
    policy = json.loads(POLICY.read_text())
    limits = policy['uniform_limits']
    if len(source.encode()) > limits['source_bytes'] or not inputs:
        raise ValueError('Missing or oversized construction source/inputs')
    payload = str(len(inputs)) + '\n' + '\n'.join(inputs) + '\n'
    if len(payload.encode()) > limits['input_bytes']:
        raise ValueError('Construction input exceeds transport bound')
    selected_flags = flags or policy['compiler_flags']
    if selected_flags not in (policy['compiler_flags'], ['-std=c++17','-O2','-Wall','-Wextra']):
        raise ValueError('Unreviewed compiler flags')
    budget = budget or ConstructionBudget()
    timeout = budget.allowance()
    docker = DockerSandbox().docker
    name = 'native-reference-' + uuid.uuid4().hex
    start = time.monotonic()
    record = {'purpose':purpose, 'compiler_image':policy['compiler_image'],
              'compiler_flags':selected_flags, 'force_exact':force_exact, 'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
              'inputs_sha256':digest(inputs), 'input_count':len(inputs), 'timeout_seconds':timeout,
              'construction_policy_sha256':file_digest(POLICY)}
    try:
        with tempfile.TemporaryDirectory(prefix='native-reference-') as temp:
            folder=Path(temp); folder.chmod(0o755)
            path=folder/'reference.cpp'; path.write_text(source); path.chmod(0o444)
            # Compiler flags are validated literals, not user-provided shell text.
            command='g++ ' + ' '.join(selected_flags) + ' /source/reference.cpp -o /tmp/reference && /tmp/reference --batch' + (' --force-exact' if force_exact else '')
            argv=[docker,'run','--rm','--pull=never','--name',name,'--network','none','--read-only',
                  '--user','65534:65534','--cpus','1','--memory','2048m','--memory-swap','2048m',
                  '--pids-limit','64','--ulimit','nofile=64:64','--cap-drop','ALL',
                  '--security-opt','no-new-privileges','--tmpfs','/tmp:rw,exec,nosuid,size=256m',
                  '--mount',f'type=bind,src={folder.resolve()},dst=/source,readonly',
                  '--workdir','/tmp','--env','LANG=C.UTF-8','--entrypoint','/usr/bin/timeout','-i',
                  policy['compiler_image'],'--signal=KILL',f'{timeout}s','/bin/sh','-c',command]
            process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                     env=DockerSandbox._environment())
            buffers={'stdout':bytearray(),'stderr':bytearray()}; overflow=threading.Event()
            def drain(stream,key):
                while chunk:=stream.read(8192):
                    room=limits['output_bytes_per_stream']-len(buffers[key])
                    buffers[key].extend(chunk[:max(0,room)])
                    if len(chunk)>room: overflow.set()
            def feed():
                try:
                    process.stdin.write(payload.encode()); process.stdin.close()
                except (BrokenPipeError,OSError): pass
            workers=[threading.Thread(target=drain,args=(process.stdout,'stdout'),daemon=True),
                     threading.Thread(target=drain,args=(process.stderr,'stderr'),daemon=True),
                     threading.Thread(target=feed,daemon=True)]
            for worker in workers: worker.start()
            while process.poll() is None and not overflow.is_set() and time.monotonic()-start < timeout+15:
                time.sleep(.02)
            if process.poll() is None:
                cleanup_ok=False
                try:
                    cleanup=subprocess.run([docker,'rm','-f',name],capture_output=True,timeout=15,
                                           env=DockerSandbox._environment())
                    cleanup_ok=cleanup.returncode==0
                except (OSError,subprocess.TimeoutExpired): pass
                finally:
                    process.kill(); process.wait(timeout=5)
                raise SandboxUnavailable('Offline construction output/deadline limit; cleanup '+('confirmed' if cleanup_ok else 'unconfirmed'))
            for worker in workers: worker.join(timeout=1)
            stdout=buffers['stdout'].decode(errors='replace'); stderr=buffers['stderr'].decode(errors='replace')
            outputs=stdout.splitlines()
            record.update(returncode=process.returncode,stdout=stdout,stderr=stderr,
                          outputs=outputs,outputs_sha256=digest(outputs),
                          passed=process.returncode==0 and len(outputs)==len(inputs) and not overflow.is_set())
            return record
    except Exception as exc:
        record.update(passed=False,error_type=type(exc).__name__,error=str(exc))
        raise
    finally:
        elapsed=time.monotonic()-start
        budget.spent+=elapsed
        record['elapsed_seconds']=round(elapsed,6)
        budget.attempts.append(record)


def replay_reference(spec, tests):
    """Reconstruct every immutable gold output and verify certificate bindings."""
    offline=spec['offline_reference']
    if offline.get('kind')!='compiled_gold_v1': raise ValueError('Unknown offline reference type')
    source_path=checked_path(ROOT,offline['source_asset'])
    certificate=json.loads(checked_path(ROOT,offline['certificate_asset']).read_text())
    inputs=[test['stdin'] for test in tests]; outputs=[test['stdout'] for test in tests]
    required={'tests_sha256':digest(tests),'inputs_sha256':digest(inputs),'outputs_sha256':digest(outputs),
              'source_sha256':file_digest(source_path),'construction_policy_sha256':file_digest(POLICY),
              'compiler_image':json.loads(POLICY.read_text())['compiler_image'],
              'compiler_flags':json.loads(POLICY.read_text())['compiler_flags'],'case_count':len(tests)}
    if certificate.get('passed') is not True or any(certificate.get(k)!=v for k,v in required.items()):
        raise ValueError('Offline reference certificate does not bind current gold inputs/outputs/source/policy')
    if certificate.get('independent_review',{}).get('status')!='passed':
        raise ValueError('Missing independent compiled reference review')
    checked_path(ROOT,certificate['independent_review']['evidence'])
    result=run_compiled(source_path.read_text(),inputs,purpose='immutable_gold_replay')
    if not result['passed']:
        raise RuntimeError('Compiled gold replay failed: '+result.get('stderr',''))
    # Output whitespace is a grading concern; certificate binds exact stored bytes.
    from .sandbox.stdin import compare_stdin
    return {'passed':all(compare_stdin(a,b) for a,b in zip(result['outputs'],outputs)),
            'outputs':result['outputs'],'execution':result}


def apply_gold_outputs(tests, asset, *, root=ROOT):
    """Bind immutable finite-suite gold to each exact input without removing any."""
    import copy
    gold=json.loads(checked_path(root,asset).read_text())
    outputs=gold.get('outputs'); hashes=gold.get('input_sha256')
    actual=[hashlib.sha256(test['stdin'].encode()).hexdigest() for test in tests]
    if (hashes!=actual or not isinstance(outputs,list) or len(outputs)!=len(tests)
            or not all(isinstance(output,str) for output in outputs)):
        raise ValueError('Immutable gold does not match every ordered input')
    result=copy.deepcopy(tests)
    for test,output in zip(result,outputs):test['stdout']=output
    return result
