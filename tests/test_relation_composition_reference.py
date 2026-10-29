import unittest
from scripts.run_relation_composition_reference import execute, reference, relation_predict


class RelationCompositionReferenceTest(unittest.TestCase):
    def test_repair_pairing_changes_results_with_identical_marginals(self):
        result = execute()
        self.assertEqual([c['reference'] for c in result['cases']], [True, True, False, False])
        self.assertEqual(result['checks']['heldout_relation_correct'], 2)
        self.assertEqual(result['checks']['heldout_marginal_correct'], 0)

    def test_missing_deadline_or_different_lengths_is_unknown(self):
        for method in (reference, relation_predict):
            self.assertIsNone(method([0, 1], [1, 1], 2))
            self.assertIsNone(method([0, 1], [1], 1))
            self.assertIsNone(method([0, 1], [1, 1], -1))
            self.assertIsNone(method([0, 1], [1, 1], True))


if __name__ == '__main__':
    unittest.main()
