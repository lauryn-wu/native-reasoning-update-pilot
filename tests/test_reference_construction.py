import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch

from native_pilot.reference_construction import ConstructionBudget,run_compiled
from native_pilot.sandbox import DockerSandbox


class ConstructionTests(unittest.TestCase):
    def test_separate_resources_do_not_relax_candidate_limits(self):
        with self.assertRaises(ValueError): DockerSandbox(timeout=600)
        with self.assertRaises(ValueError): DockerSandbox(memory_mb=2048)
        process=MagicMock()
        process.stdin=io.BytesIO();process.stdout=io.BytesIO(b'8\n');process.stderr=io.BytesIO()
        process.poll.return_value=0;process.returncode=0
        budget=ConstructionBudget()
        with patch('subprocess.Popen',return_value=process) as launch:
            result=run_compiled('int main(){}',['4\n0 4 5 9'],budget=budget)
        self.assertTrue(result['passed'])
        args=launch.call_args.args[0]
        for token in ['--network','none','--read-only','65534:65534','2048m','--cpus','--pids-limit','--cap-drop','ALL','no-new-privileges']:
            self.assertIn(token,args)
        mounts=[args[i+1] for i,x in enumerate(args[:-1]) if x=='--mount']
        self.assertEqual(len(mounts),1);self.assertTrue(mounts[0].endswith('dst=/source,readonly'))
        self.assertGreater(budget.spent,0);self.assertEqual(len(budget.attempts),1)

    def test_failed_launch_still_charges_and_records_shared_budget(self):
        budget=ConstructionBudget()
        with patch('subprocess.Popen',side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):run_compiled('unused',['2\n1 2'],budget=budget)
        self.assertGreater(budget.spent,0)
        self.assertFalse(budget.attempts[0]['passed'])
        budget.spent=1790
        with self.assertRaisesRegex(RuntimeError,'exhausted'):budget.allowance()

    def test_incomplete_or_failed_outputs_never_qualify(self):
        for output,code in [(b'8\n',2),(b'',0),(b'8\n9\n',0)]:
            process=MagicMock()
            process.stdin=io.BytesIO();process.stdout=io.BytesIO(output);process.stderr=io.BytesIO()
            process.poll.return_value=code;process.returncode=code
            with patch('subprocess.Popen',return_value=process):
                self.assertFalse(run_compiled('unused',['4\n0 4 5 9'])['passed'])

    def test_gold_replay_rejects_tampered_binding_before_execution(self):
        from native_pilot.reference_construction import replay_reference
        from native_pilot.util import file_digest
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'ref.cpp';source.write_text('unused')
            certificate=root/'cert.json';certificate.write_text(json.dumps({'passed':True,'tests_sha256':'wrong'}))
            spec={'offline_reference':{'kind':'compiled_gold_v1','source_asset':{'path':'ref.cpp','sha256':file_digest(source)},'certificate_asset':{'path':'cert.json','sha256':file_digest(certificate)}}}
            with patch('native_pilot.reference_construction.ROOT',root),patch('native_pilot.reference_construction.run_compiled') as run:
                with self.assertRaisesRegex(ValueError,'does not bind'):
                    replay_reference(spec,[{'stdin':'2\n1 2','stdout':'1'}])
                run.assert_not_called()


if __name__=='__main__':unittest.main()

class GoldBindingTests(unittest.TestCase):
    def test_gold_rejects_reordered_missing_or_changed_inputs(self):
        import hashlib
        from native_pilot.reference_construction import apply_gold_outputs
        from native_pilot.util import file_digest
        tests=[{'stdin':'a','stdout':'old'},{'stdin':'b','stdout':'old'}]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'gold.json'
            path.write_text(json.dumps({'input_sha256':[hashlib.sha256(t['stdin'].encode()).hexdigest() for t in tests],'outputs':['1','2']}))
            asset={'path':'gold.json','sha256':file_digest(path)}
            self.assertEqual([t['stdout'] for t in apply_gold_outputs(tests,asset,root=root)],['1','2'])
            self.assertEqual(tests[0]['stdout'],'old')
            for bad in [tests[::-1],tests[:1],[{'stdin':'c','stdout':'old'},tests[1]]]:
                with self.assertRaisesRegex(ValueError,'every ordered input'):apply_gold_outputs(bad,asset,root=root)
