import json
import tempfile
import unittest
from pathlib import Path
from native_pilot.assets import hydrate_tasks
from native_pilot.util import file_digest


class AssetTests(unittest.TestCase):
    def test_checksum_enforced_without_mutating_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            test=root/'tests.json'; test.write_text('[{"input":"1","output":"2"}]')
            ref=root/'ref.py'; ref.write_text('print(2)')
            spec={'test_asset':{'path':'tests.json','sha256':file_digest(test)},
                  'reference_asset':{'path':'ref.py','sha256':file_digest(ref)}}
            tasks=[{'task_id':'x','domain':'coding','original':spec,'updated':spec}]
            hydrated=hydrate_tasks(tasks,root,root=root)
            self.assertEqual(hydrated[0]['original']['reference_solution'],'print(2)')
            self.assertNotIn('tests',tasks[0]['original'])
            test.write_text('[]')
            with self.assertRaisesRegex(ValueError,'checksum'):
                hydrate_tasks(tasks,root,root=root)
    def test_path_escape_rejected(self):
        tasks=[{'task_id':'x','domain':'coding','original':{'test_asset':{'path':'../secret','sha256':'x'}},'updated':{}}]
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,'outside'):
                hydrate_tasks(tasks,root)
