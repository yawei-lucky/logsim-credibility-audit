import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_physics_alphabet_probe import cases, camera_points, project, predict, judge


class PhysicsAlphabetTest(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((ROOT / 'configs/physics_alphabet_probe_001.json').read_text())
        self.cases = cases(self.cfg)

    def test_same_single_operators_cannot_identify_order_but_combinations_can(self):
        for case in self.cases:
            difference = np.max(np.abs(camera_points(self.cfg, case) - camera_points(self.cfg, case, 'T_R_P_V')))
            if case['split'] == 'single':
                self.assertLess(difference, 1e-12)
            else:
                self.assertGreater(difference, .1)
        self.assertEqual(sum(c['split'] == 'single' for c in self.cases), 8)
        self.assertEqual(len({c['id'] for c in self.cases}), 24)

    def test_scalar_prediction_matches_separate_homogeneous_placement(self):
        points = np.column_stack([self.cfg['body_points_m'], np.ones(2)])
        for case in self.cases:
            theta = np.deg2rad(case['angle'])
            r = np.array([[np.cos(theta),0,np.sin(theta)],[0,1,0],[-np.sin(theta),0,np.cos(theta)]])
            matrix = np.eye(4)
            matrix[:3,:3] = r
            matrix[:3,3] = np.array(self.cfg['base_center_camera_m']) + case['translation']
            np.testing.assert_allclose((matrix@points.T).T[:,:3], camera_points(self.cfg, case), atol=1e-12)

    def test_image_sum_matches_each_single_effect_but_not_all_combinations(self):
        atoms = {c['id']:project(self.cfg, camera_points(self.cfg,c)) for c in self.cases if c['split']=='single' and c['occlusion']=='none'}
        worst = 0
        for case in self.cases:
            complete = predict(self.cfg, case, 'R_T_P_V')
            summed = predict(self.cfg, case, 'image_additive', atoms)
            error = max(np.max(np.abs(np.asarray(complete[k])-summed[k])) for k in complete)
            if case['split']=='single':
                self.assertLess(error,1e-12)
            else:
                worst=max(worst,error)
        self.assertGreater(worst,1)

    def test_visible_count_contradiction_is_distinct_from_unqualified_code(self):
        observation={'identities_qualified':True,'features':[{'identity':'right','u':470,'v':228}]}
        good=judge(observation, {'right':[470,228]}, .25)
        self.assertTrue(good['contract_passed'])
        bad=judge(observation, {'left':[427,228], 'right':[470,228]}, .25)
        self.assertTrue(bad['tested'])
        self.assertEqual(bad['failure_kind'],'visible_identity_contradiction')
        observation['identities_qualified']=False
        self.assertFalse(judge(observation, {'right':[470,228]}, .25)['tested'])

    def test_occluder_order_and_marker_identity_are_preserved(self):
        for case in self.cases:
            expected={'right'} if case['occlusion']=='front_left' else {'left'} if case['occlusion']=='front_right' else {'left','right'}
            self.assertEqual(set(predict(self.cfg,case,'R_T_P_V')),expected)
            self.assertEqual(set(predict(self.cfg,case,'without_V')),{'left','right'})


if __name__ == '__main__':
    unittest.main()
