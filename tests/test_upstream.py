import contextlib
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from native_pilot.data import SourceBlocked
from native_pilot.upstream import match_rows, initial_test_inputs, decode_tests, stdin_tests, _reference_outputs, _reference_stdin_outputs, prepare_coding_assets
from native_pilot.reference_construction import apply_gold_outputs
from native_pilot.util import file_digest


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

    @contextlib.contextmanager
    def gold_rebuild_fixture(self, *, wrong_input_order=False, wrong_asset_hash=False,
                             replay_passed=True):
        """Synthetic 43+162-case transport fixture; no compiled code is run."""
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);cache=root/'cache';cache.mkdir()
            refdir=root/'references/coding';refdir.mkdir(parents=True)
            historical=refdir/'independent_cases.json'
            historical.write_text(json.dumps({'tasks':{'276':{'original':[{'stdin':'do not use historical fixture','stdout':'bad'}],
                                                                     'updated':[]}}}))
            historical_bytes=historical.read_bytes()
            official=[{'stdin':f'published {i}\n','stdout':f'updated {i}\n'} for i in range(43)]
            fixture={variant:[{'stdin':f'independent {i}\n','stdout':f'{variant} {i}\n'}
                              for i in range(162)] for variant in ('original','updated')}
            fixture_path=refdir/'276-cases.json';fixture_path.write_text(json.dumps(fixture))
            reference=refdir/'updated.py';reference.write_text('raise AssertionError("not executed on host")')
            originals=copy.deepcopy(official)+copy.deepcopy(fixture['original'])
            for i,test in enumerate(originals):test['stdout']=f'gold {i}\n'
            updated=copy.deepcopy(official)+copy.deepcopy(fixture['updated'])
            gold_path=refdir/'gold.json'
            hashes=[hashlib.sha256(t['stdin'].encode()).hexdigest() for t in originals]
            if wrong_input_order:hashes[0],hashes[1]=hashes[1],hashes[0]
            gold_path.write_text(json.dumps({'input_sha256':hashes,'outputs':[t['stdout'] for t in originals]}))
            def asset(path):return {'path':str(path.relative_to(root)),'sha256':file_digest(path)}
            def test_asset(variant,tests):
                encoded=(json.dumps(tests,separators=(',',':'),ensure_ascii=False)+'\n').encode()
                return {'path':f'lcb/qualified/276-{variant}.json','sha256':hashlib.sha256(encoded).hexdigest()}
            entry={'status':'qualified','task_id':'livecodebench:276','source_id':276,
                'matching':{'raw_line_sha256':'unit-match'},'independent_cases_asset':asset(fixture_path),
                'original':{'mode':'stdin','offline_reference':{'kind':'compiled_gold_v1'},
                            'gold_asset':asset(gold_path),'test_asset':test_asset('original',originals)},
                'updated':{'mode':'stdin','reference_asset':asset(reference),
                           'test_asset':test_asset('updated',updated)}}
            if wrong_asset_hash:entry['original']['test_asset']['sha256']='incorrect-frozen-hash'
            review_path=root/'review.json';review_path.write_text(json.dumps({
                'independent_cases_sha256':file_digest(historical),'reviewed_candidates':[entry]}))
            source={'id':276,'original_problem':'unit statement','original_starter_code':''}
            match={'row':{'question_content':'unit statement','starter_code':''},'raw_line_sha256':'unit-match'}
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch('native_pilot.upstream.ROOT',root))
                stack.enter_context(patch('native_pilot.data.verify_sources',return_value={'verified':True}))
                stack.enter_context(patch('native_pilot.data._read_rows',return_value=([],[source])))
                stack.enter_context(patch('native_pilot.upstream.prepare_upstream'))
                stack.enter_context(patch('native_pilot.upstream.match_rows',return_value={276:match}))
                stack.enter_context(patch('native_pilot.upstream.stdin_tests',return_value=copy.deepcopy(official)))
                stack.enter_context(patch('native_pilot.reference_construction.apply_gold_outputs',
                    side_effect=lambda tests,descriptor:apply_gold_outputs(tests,descriptor,root=root)))
                replay=stack.enter_context(patch('native_pilot.reference_construction.replay_reference',
                    return_value={'passed':replay_passed}))
                stack.enter_context(patch('native_pilot.upstream._reference_stdin_outputs',
                    return_value=[t['stdout'] for t in official]))
                yield cache,review_path,originals,updated,historical,historical_bytes,replay

    def test_gold_rebuild_retains_all_ordered_cases_and_entry_specific_fixture(self):
        with self.gold_rebuild_fixture() as (cache,review,originals,updated,historical,before,replay):
            result=prepare_coding_assets(cache,review)
            self.assertEqual(result['prepared_task_ids'],['livecodebench:276'])
            self.assertEqual(json.loads((cache/'lcb/qualified/276-original.json').read_text()),originals)
            self.assertEqual(json.loads((cache/'lcb/qualified/276-updated.json').read_text()),updated)
            self.assertEqual(len(originals),205)
            self.assertEqual(historical.read_bytes(),before)
            replay.assert_called_once()
            self.assertEqual(replay.call_args.args[1],originals)

    def test_gold_rebuild_rejects_input_reordering_before_replay(self):
        with self.gold_rebuild_fixture(wrong_input_order=True) as (cache,review,*rest):
            replay=rest[-1]
            with self.assertRaisesRegex(ValueError,'every ordered input'):
                prepare_coding_assets(cache,review)
            replay.assert_not_called()
            self.assertFalse((cache/'lcb/qualified/276-original.json').exists())

    def test_gold_rebuild_requires_fresh_replay_and_final_asset_hash(self):
        for kwargs,message in [({'replay_passed':False},'compiled reference fails'),
                               ({'wrong_asset_hash':True},'differs from reviewed hash')]:
            with self.subTest(kwargs=kwargs),self.gold_rebuild_fixture(**kwargs) as (cache,review,*rest):
                with self.assertRaisesRegex(SourceBlocked,message):
                    prepare_coding_assets(cache,review)
                rest[-1].assert_called_once()
                self.assertFalse((cache/'lcb/qualified/276-original.json').exists())


if __name__=='__main__':unittest.main()
