import unittest
from native_pilot.exact_math import parse_exact, exact_equal
from native_pilot.grading import InvalidAnswer, grade_response, qualify_references

class ExactMathTests(unittest.TestCase):
    def test_actual_released_radical_equivalence(self):
        target=parse_exact('sqrt(241330)')
        for expression in (r'\boxed{\sqrt{241330}}','sqrt(965320)/2','(363**2+331**2)**(1/2)',r'(241330)^{1/2}'):
            self.assertTrue(exact_equal(parse_exact(expression),target))
    def test_exact_not_numeric_tolerance(self):
        self.assertFalse(exact_equal(parse_exact('491.253498'),parse_exact('sqrt(241330)')))
        self.assertFalse(exact_equal(parse_exact('-sqrt(241330)'),parse_exact('sqrt(241330)')))
    def test_rationalization_exact(self):
        self.assertTrue(exact_equal(parse_exact('1/(1+sqrt(2))'),parse_exact('sqrt(2)-1')))
        self.assertTrue(exact_equal(parse_exact('2sqrt(2)'),parse_exact('sqrt(8)')))
    def test_reject_code_and_unbounded_or_nonreal(self):
        for text in ('__import__("os").system("true")','sqrt(-1)','sqrt(sqrt(2))','sqrt(2)**1000000','sqrt(1e100)','float(2)','sqrt(2,3)'):
            with self.subTest(text=text),self.assertRaises(InvalidAnswer):
                parse_exact(text)
    def test_actual_pair_stale_grading_and_reference_validation(self):
        task={'task_id':'aime2024:1012','domain':'math','original':{'answer':'sqrt(241330)'},'updated':{'answer':'540'}}
        self.assertEqual(grade_response(task,'original',r'\boxed{\sqrt{241330}}')['status'],'correct')
        self.assertEqual(grade_response(task,'updated','sqrt(965320)/2')['status'],'old_answer_match')
        self.assertTrue(qualify_references([task])['passed'])
