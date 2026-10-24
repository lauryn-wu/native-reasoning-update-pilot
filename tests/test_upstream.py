import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from native_pilot.data import SourceBlocked
from native_pilot.upstream import match_rows, initial_test_inputs, decode_tests, stdin_tests, _reference_outputs, _reference_stdin_outputs


class UpstreamTests(unittest.TestCase):
    def test_join_uses_published_identity_not_row_order(self):
        source=[dict(id=7,platform='leetcode',contest_id='c1',question_title='p1')]
        rows=[dict(platform='leetcode',contest_id='unrelated',question_title='p1',question_id='u',metadata='{}'),
              dict(platform='leetcode',contest_id='c1',question_title='p1',question_id='q',metadata='{"func_name":"f"}')]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'rows.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            result=match_rows(source,[path])
            self.assertEqual(result[7]['line_number'],2)
            self.assertEqual(result[7]['row']['question_id'],'q')
            with self.assertRaisesRegex(SourceBlocked,'Ambiguous upstream'):
                match_rows(source,[path,path])

    def test_initial_transform_does_not_mutate_official_suite(self):
        suite=[{'args':[5,3,2],'expected':108}]
        transformed=initial_test_inputs(154,suite)
        self.assertEqual(transformed[0]['args'],[5,2,3])
        self.assertEqual(suite[0]['args'],[5,3,2])
        self.assertEqual(initial_test_inputs(325,[{'args':[2,2,2],'expected':8}])[0]['expected'],16)

    def test_three_star_domain_and_argument_order(self):
        suite=[{'args':['abcdef','a*c*f'],'expected':6}]
        original=initial_test_inputs(331,suite)
        self.assertEqual(original[0]['args'],['a**c*f','abcdef'])
        self.assertEqual(original[0]['expected'],6)

    def test_missing_docker_has_no_decode_fallback(self):
        with patch('native_pilot.upstream.subprocess.run',side_effect=OSError):
            with self.assertRaisesRegex(SourceBlocked,'no host fallback'):
                decode_tests('[]')

    def test_decoder_launch_has_required_isolation(self):
        class Result:
            returncode=0
            stdout='[]'
        with patch('native_pilot.upstream.subprocess.run',return_value=Result()) as run:
            self.assertEqual(decode_tests('[]'),[])
        argv=run.call_args.args[0]
        for token in ['--network','none','--read-only','65534:65534','--cpus','--memory','--pids-limit','--cap-drop','ALL','no-new-privileges']:
            self.assertIn(token,argv)
        self.assertNotIn('--privileged',argv)

    def test_stdin_fixture_retains_public_then_private_cases(self):
        public=[{'input':'2\n','output':'first\n'}]
        private=[{'input':'3\n','output':'second\n'}]
        with patch('native_pilot.upstream.decode_tests',side_effect=[public,private]):
            result=stdin_tests({'metadata':'{}','public_test_cases':'a','private_test_cases':'b'})
        self.assertEqual(result,[{'stdin':'2\n','stdout':'first\n'},{'stdin':'3\n','stdout':'second\n'}])
        with self.assertRaises(SourceBlocked):
            stdin_tests({'metadata':'{"func_name":"solve"}'})

    def test_stdin_reference_execution_fails_closed(self):
        with patch('native_pilot.upstream.DockerSandbox.run',return_value={'status':'unavailable','returncode':None}):
            with self.assertRaisesRegex(SourceBlocked,'failed in Docker'):
                _reference_stdin_outputs('raise AssertionError("must not run on host")',['input'])

    def test_function_reference_batches_cap_case_count_and_preserve_order(self):
        arguments=[[i] for i in range(43)]
        batches=[]
        def isolated_result(code,payload):
            batch=json.loads(payload); batches.append(batch)
            return {'status':'completed','returncode':0,'stdout':json.dumps([args[0] for args in batch])}
        with patch('native_pilot.upstream.DockerSandbox.run',side_effect=isolated_result):
            actual=_reference_outputs('raise AssertionError("must not run on host")','solve',arguments)
        self.assertEqual(actual,list(range(43)))
        self.assertEqual([len(batch) for batch in batches],[8,8,8,8,8,3])
        self.assertEqual([args for batch in batches for args in batch],arguments)

    def test_stdin_reference_batches_cap_case_count_and_preserve_order(self):
        inputs=[f'case {i}\n' for i in range(43)]
        batches=[]
        def isolated_result(code,payload):
            batch=json.loads(payload); batches.append(batch)
            return {'status':'completed','returncode':0,'stdout':json.dumps(batch)}
        with patch('native_pilot.upstream.DockerSandbox.run',side_effect=isolated_result):
            actual=_reference_stdin_outputs('raise AssertionError("must not run on host")',inputs)
        self.assertEqual(actual,inputs)
        self.assertEqual([len(batch) for batch in batches],[8,8,8,8,8,3])
        self.assertEqual([value for batch in batches for value in batch],inputs)

    def test_reference_batch_count_limit_keeps_transport_limits(self):
        for mode,width in [('function',1_500_000),('stdin',2_000_000)]:
            with self.subTest(mode=mode):
                values=['a'*width,'b'*width]
                batches=[]
                def isolated_result(code,payload):
                    batch=json.loads(payload); batches.append(batch)
                    return {'status':'completed','returncode':0,'stdout':json.dumps(['ok']*len(batch))}
                with patch('native_pilot.upstream.DockerSandbox.run',side_effect=isolated_result):
                    if mode=='function':
                        actual=_reference_outputs('unused','solve',[[value] for value in values])
                    else:
                        actual=_reference_stdin_outputs('unused',values)
                self.assertEqual(actual,['ok','ok'])
                self.assertEqual([len(batch) for batch in batches],[1,1])


if __name__=='__main__':unittest.main()
