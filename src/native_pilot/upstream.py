"""Pinned LiveCodeBench acquisition and Docker-only compressed test decoding."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import tempfile
import copy
import re
from pathlib import Path
from .data import SourceBlocked, prepare_sources
from .sandbox import DEFAULT_IMAGE, DockerSandbox

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'provenance/upstream_tests_lock.json'
REFERENCE_BATCH_CASE_LIMIT = 8


def prepare_upstream(cache_dir, lock_path=LOCK):
    return prepare_sources(cache_dir, lock_path)


def _reference_outputs(code, method, arguments):
    """Evaluate our reference only inside Docker; expected values stay outside."""
    batches, current, size = [], [], 0
    for args in arguments:
        length = len(json.dumps(args).encode())
        if length > 2_800_000:
            raise SourceBlocked('Single upstream case exceeds qualified Docker input bound')
        if current and (len(current) >= REFERENCE_BATCH_CASE_LIMIT or size + length > 2_800_000):
            batches.append(current); current = []; size = 0
        current.append(args); size += length
    if current:
        batches.append(current)
    outputs = []
    for batch in batches:
        harness = code + '\nimport json,sys\nargs=json.load(sys.stdin)\nprint(json.dumps([getattr(Solution(),'+repr(method)+')(*a) for a in args]))\n'
        result = DockerSandbox(timeout=60, memory_mb=768, output_limit=4_000_000).run(harness, json.dumps(batch))
        if result['status'] != 'completed' or result['returncode'] != 0:
            raise SourceBlocked(f"Reference construction failed in Docker: {result['status']}, exit {result['returncode']}")
        part = json.loads(result['stdout'])
        if not isinstance(part, list) or len(part) != len(batch):
            raise SourceBlocked('Reference output shape mismatch')
        outputs.extend(part)
    return outputs


def _reference_stdin_outputs(code, inputs):
    """Run fresh program globals per case in Docker, returning text only.

    No expected answers enter the container. Both transport size and case count
    bound each batch; every case is retained in its source order. The count
    limit prevents many small but expensive inputs sharing one 60-second run.
    """
    batches, current, size = [], [], 0
    for value in inputs:
        length = len(json.dumps(value).encode())
        if length > 3_800_000:
            raise SourceBlocked('Single upstream input exceeds qualified Docker bound')
        if current and (len(current) >= REFERENCE_BATCH_CASE_LIMIT or size + length > 3_800_000):
            batches.append(current); current = []; size = 0
        current.append(value); size += length
    if current:
        batches.append(current)
    harness = ('import json,sys,io\ninputs=json.load(sys.stdin)\nanswers=[]\ncode='
        + repr(code) + '\noriginal_stdout=sys.stdout\nfor data in inputs:\n'
        ' sys.stdin=io.TextIOWrapper(io.BytesIO(data.encode()))\n'
        ' sys.stdout=io.StringIO()\n'
        ' exec(compile(code,"reference.py","exec"),{"__name__":"__main__"})\n'
        ' answers.append(sys.stdout.getvalue())\nsys.stdout=original_stdout\n'
        'print(json.dumps(answers))\n')
    outputs = []
    for batch in batches:
        result = DockerSandbox(timeout=60, memory_mb=768, output_limit=4_000_000).run(harness, json.dumps(batch))
        if result['status'] != 'completed' or result['returncode'] != 0:
            raise SourceBlocked(f"Reference construction failed in Docker: {result['status']}, exit {result['returncode']}")
        part = json.loads(result['stdout'])
        if not isinstance(part, list) or len(part) != len(batch) or not all(isinstance(v, str) for v in part):
            raise SourceBlocked('Reference output shape mismatch')
        outputs.extend(part)
    return outputs


def initial_test_inputs(source_id, updated_tests):
    """Published-variant domain mappings, fixed before any paid outputs."""
    tests = copy.deepcopy(updated_tests)
    if source_id == 299:
        for test in tests:
            test['args'][0] = [row[::-1] for row in test['args'][0]]
    elif source_id == 331:
        for test in tests:
            s, p = test['args']
            test['args'] = [p.replace('*', '**', 1), s]
    elif source_id == 154:
        for test in tests:
            n, m, k = test['args']
            test['args'] = [n, n-1-k, m]
    elif source_id == 325:
        for test in tests:
            test['expected'] = test['expected'] * 2 % (10**9+7)
    elif source_id == 337:
        for test in tests:
            words, k = test['args']
            if len(words)-1 < k:
                test['expected'] = [-1] * len(words)
    return tests


def prepare_coding_assets(cache_dir, review_path=None, *, progress=None):
    """Rebuild all independently qualified test assets without host code execution.

    Bulk published tests remain in the user cache. SHA-256 values committed in
    the review bind the exact transformed suites and our reference programs.
    """
    from .data import _read_rows, verify_sources
    cache = Path(cache_dir)
    verification = verify_sources(cache)
    if not verification['verified']:
        raise SourceBlocked('Prepare the pinned update sources first')
    prepare_upstream(cache)
    review = json.loads(Path(review_path or ROOT/'provenance/coding_review.json').read_text())
    independent_path = ROOT/'references/coding/independent_cases.json'
    if hashlib.sha256(independent_path.read_bytes()).hexdigest() != review['independent_cases_sha256']:
        raise SourceBlocked('Independent verification fixture changed')
    independent = json.loads(independent_path.read_text())['tasks']
    _, released = _read_rows(cache)
    released_by_id = {row['id']: row for row in released}
    required_ids={entry['source_id'] for entry in review['reviewed_candidates'] if entry['status']=='qualified'}
    matches = match_rows([row for row in released if row['id'] in required_ids],
                         [cache/'lcb/test5.jsonl', cache/'lcb/test6.jsonl'])
    result = []
    target = cache/'lcb/qualified'; target.mkdir(parents=True, exist_ok=True)
    for entry in review['reviewed_candidates']:
        if entry['status'] != 'qualified':
            continue
        source_id = entry['source_id']
        if progress is not None:
            progress(entry['task_id'])
        match = matches[source_id]
        if match['raw_line_sha256'] != entry['matching']['raw_line_sha256']:
            raise SourceBlocked('Published source match changed')
        source_row = released_by_id[source_id]
        if (' '.join(source_row['original_problem'].split()) not in ' '.join(match['row']['question_content'].split())
                or source_row['original_starter_code'] != match['row'].get('starter_code', '')):
            raise SourceBlocked('Joined statement or starter differs from released source')
        mode = entry['updated']['mode']
        if mode == 'function':
            method, updated = function_tests(match['row'])
            initial = initial_test_inputs(source_id, updated)
        elif mode == 'stdin':
            updated = stdin_tests(match['row'])
            for adjudication in entry.get('test_adjudications', []):
                test = updated[adjudication['source_case_index']]
                if hashlib.sha256(json.dumps(test, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != adjudication['upstream_case_sha256']:
                    raise SourceBlocked('Adjudicated upstream case changed')
                test['stdout'] = adjudication['corrected_stdout']
            initial = copy.deepcopy(updated)
        else:
            raise SourceBlocked('Unsupported reviewed coding interface')
        case_fixture = independent.get(str(source_id))
        if entry.get('independent_cases_asset'):
            from .assets import checked_path
            case_fixture=json.loads(checked_path(ROOT,entry['independent_cases_asset']).read_text())
        if case_fixture is None:
            raise SourceBlocked('Missing independent fixtures')
        for variant, tests in [('original', initial), ('updated', updated)]:
            spec = entry[variant]
            if spec.get('offline_reference'):
                from .reference_construction import apply_gold_outputs, replay_reference
                tests.extend(case_fixture[variant])
                tests=apply_gold_outputs(tests,spec['gold_asset'])
                if not replay_reference(spec,tests)['passed']:
                    raise SourceBlocked('Offline compiled reference fails immutable gold')
                encoded=(json.dumps(tests,separators=(',', ':'),ensure_ascii=False)+'\n').encode()
                if hashlib.sha256(encoded).hexdigest()!=spec['test_asset']['sha256']:
                    raise SourceBlocked('Rebuilt immutable gold asset differs from reviewed hash')
                destination=cache/spec['test_asset']['path']
                destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(encoded)
                continue
            code_path = ROOT/spec['reference_asset']['path']
            code_bytes = code_path.read_bytes()
            if hashlib.sha256(code_bytes).hexdigest() != spec['reference_asset']['sha256']:
                raise SourceBlocked('Reference source changed')
            if mode == 'function':
                outputs = _reference_outputs(code_bytes.decode(), spec['entrypoint']['method'], [t['args'] for t in tests])
                if variant == 'updated' or source_id in (124,299,331,154,325,337):
                    if outputs != [t['expected'] for t in tests]:
                        raise SourceBlocked('Reference fails official tests/proven transformation')
                else:
                    for test, output in zip(tests, outputs):
                        test['expected'] = output
            else:
                outputs = _reference_stdin_outputs(code_bytes.decode(), [t['stdin'] for t in tests])
                if variant == 'updated':
                    normalize = (lambda s: s.lower().split()) if spec.get('case_insensitive') else (lambda s: s.split())
                    if [normalize(s) for s in outputs] != [normalize(t['stdout']) for t in tests]:
                        raise SourceBlocked('Reference fails official or proof-adjudicated tests')
                for test, output in zip(tests, outputs):
                    test['stdout'] = output
            tests.extend(case_fixture[variant])
            encoded = (json.dumps(tests, separators=(',', ':'), ensure_ascii=False)+'\n').encode()
            expected = spec['test_asset']['sha256']
            if hashlib.sha256(encoded).hexdigest() != expected:
                raise SourceBlocked('Rebuilt test asset differs from independently reviewed hash')
            destination = cache/spec['test_asset']['path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(encoded)
        result.append(entry['task_id'])
    return {'prepared_task_ids': result, 'source_tests_host_executed': False, 'paid_calls': 0}


def match_rows(released, upstream_paths):
    """Join published semantic identities, never trust release row positions."""
    keys = {}
    for row in released:
        key = (row['platform'], row['contest_id'], row['question_title'])
        if key in keys:
            raise SourceBlocked('Duplicate release coding identity')
        keys[key] = row['id']
    matches = {}
    for path in upstream_paths:
        with Path(path).open() as source:
            for line_number, line in enumerate(source, 1):
                row = json.loads(line)
                key = (row['platform'], row['contest_id'], row['question_title'])
                if key not in keys:
                    continue
                identity = keys[key]
                if identity in matches:
                    raise SourceBlocked('Ambiguous upstream match')
                if not row.get('question_id') or not row.get('metadata'):
                    raise SourceBlocked('Missing upstream question identity/function metadata')
                matches[identity] = {'row': row, 'source_file': Path(path).name,
                    'line_number': line_number, 'raw_line_sha256': hashlib.sha256(line.encode()).hexdigest(),
                    'join_key': list(key)}
    return matches


DECODER = r'''
import base64, io, json, pickle, sys, zlib
class SafeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise ValueError('Pickle globals forbidden')
    def persistent_load(self, pid):
        raise ValueError('Persistent pickle references forbidden')
raw = sys.stdin.buffer.read(32_000_001)
if len(raw) > 32_000_000: raise ValueError('Payload too large')
payload = json.loads(raw)
try:
    cases = json.loads(payload)
except json.JSONDecodeError:
    compressed = base64.b64decode(payload, validate=True)
    decoder = zlib.decompressobj()
    inflated = decoder.decompress(compressed, 128_000_001)
    if len(inflated) > 128_000_000 or not decoder.eof:
        raise ValueError('Decompression limit')
    value = SafeUnpickler(io.BytesIO(inflated)).load()
    if not isinstance(value, (str, bytes)): raise ValueError('Expected serialized JSON string')
    cases = json.loads(value)
if not isinstance(cases, list): raise ValueError('Expected test list')
for case in cases:
    if not isinstance(case, dict) or not isinstance(case.get('input'), str) or not isinstance(case.get('output'), str):
        raise ValueError('Malformed source test')
result = json.dumps(cases, separators=(',', ':'))
if len(result.encode()) > 128_000_000: raise ValueError('Output limit')
sys.stdout.write(result)
'''


def decode_tests(payload: str) -> list[dict]:
    """Decode even plain test JSON in an isolated resource-bounded container.

    Pickle is never imported or interpreted by the host. A restricted unpickler
    inside Docker accepts the source's pickled JSON strings and rejects globals.
    This decoder runs no contestant/reference programs and receives no secrets.
    """
    if not isinstance(payload, str) or len(payload.encode()) > 24_000_000:
        raise SourceBlocked('Missing/oversized test payload')
    sandbox = DockerSandbox()
    command = [sandbox.docker, 'run', '--rm', '--pull=never', '--network', 'none',
        '--read-only', '--user', '65534:65534', '--cpus', '1', '--memory', '768m',
        '--memory-swap', '768m', '--pids-limit', '16', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--entrypoint', '/usr/bin/timeout',
        '-i', DEFAULT_IMAGE, '--signal=KILL', '30s', 'python', '-I', '-B', '-c', DECODER]
    try:
        process = subprocess.run(command, input=json.dumps(payload), capture_output=True,
            text=True, timeout=40, env=sandbox._environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceBlocked('Docker test decoding unavailable; no host fallback') from exc
    if process.returncode or len(process.stdout.encode()) > 128_000_000:
        raise SourceBlocked('Docker rejected source test payload')
    return json.loads(process.stdout)


def function_tests(row: dict) -> tuple[str, list[dict]]:
    metadata = json.loads(row['metadata'])
    method = metadata.get('func_name')
    if not isinstance(method, str) or not method.isidentifier():
        raise SourceBlocked('Not a supported function-call case')
    cases = decode_tests(row['public_test_cases']) + decode_tests(row['private_test_cases'])
    tests = []
    for case in cases:
        args = [json.loads(line) for line in case['input'].strip().splitlines()]
        tests.append({'args': args, 'expected': json.loads(case['output'])})
    if not tests:
        raise SourceBlocked('Empty official test suite')
    return method, tests


def stdin_tests(row: dict) -> list[dict]:
    if json.loads(row['metadata']).get('func_name'):
        raise SourceBlocked('Function-call source cannot be reinterpreted as stdin')
    cases = decode_tests(row['public_test_cases']) + decode_tests(row['private_test_cases'])
    if not cases:
        raise SourceBlocked('Empty official test suite')
    return [{'stdin': case['input'], 'stdout': case['output']} for case in cases]
