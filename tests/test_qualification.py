import unittest
from native_pilot.qualification import assert_ordered_prefix, assemble_prompts
from native_pilot.data import SourceBlocked


class ReviewOrderTests(unittest.TestCase):
    def test_pending_earlier_candidate_cannot_be_replaced(self):
        inventory=[{'task_id':x,'domain':'coding'} for x in ['earlier','later']]
        reviews={'earlier':{'status':'pending','independent_review':'passed'},
                 'later':{'status':'qualified','independent_review':'passed'}}
        with self.assertRaisesRegex(SourceBlocked,'Earlier candidate'):
            assert_ordered_prefix(inventory,reviews,{'later'},None)
    def test_exclusion_requires_reason_and_independent_review(self):
        inventory=[{'task_id':'x','domain':'math'}]
        review={'x':{'status':'excluded','independent_review':'passed'}}
        with self.assertRaisesRegex(SourceBlocked,'no documented reason'):
            assert_ordered_prefix(inventory,review,{'x'},None)
        review['x']['reason']='Exact contradiction'
        assert_ordered_prefix(inventory,review,{'x'},None)
    def test_prompt_composition_preserves_every_source_byte(self):
        row={'revised_problem':' initial\n','original_problem':'updated\n',
             'update':' exact correction\n','revised_starter_code':'class Old:\n pass',
             'original_starter_code':'class New:\n pass'}
        p=assemble_prompts(row,'coding')
        self.assertTrue(p['original_prompt'].startswith(row['revised_problem']))
        self.assertIn(row['original_starter_code'],p['updated_prompt'])
        self.assertEqual(p['correction_prompt'],row['update'])
        self.assertEqual(p['released_fields'],row)
