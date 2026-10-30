import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_motion_occlusion_probe import IDS, judge, load_config, preflight, reference, sample_times, synthetic_occluded_pair, target_points, target_pose
from measure_credibility_marker_identity import measure_tagged_pair


class MotionOcclusionContractTest(unittest.TestCase):
    def setUp(self):
        self.cfg, _ = load_config(ROOT / "configs/motion_occlusion_probe_001.json")

    def test_complete_times_and_scalar_vs_homogeneous_motion(self):
        times = sample_times(self.cfg)
        self.assertEqual(len(times), 45)
        self.assertEqual(len(set(times)), 45)
        np.testing.assert_allclose(np.diff(times), .05, atol=1e-12)
        points = np.column_stack([self.cfg["body_points_m"], np.ones(2)])
        for timestamp in times:
            np.testing.assert_allclose((target_pose(self.cfg, timestamp)@points.T).T[:,:3], target_points(self.cfg,timestamp), atol=1e-12)
        self.assertEqual(preflight(self.cfg)["primary_pair_count"], 360)

    def test_depth_order_phase_and_reference_transition_coverage(self):
        cases = {case["id"]:case for case in self.cfg["cases"]}
        for case in (cases["motion_only"],cases["rear_early"]):
            for t in sample_times(self.cfg):
                self.assertEqual(set(reference(self.cfg,case,t)["visibility"].values()),{"clear"})
        for timestamp in sample_times(self.cfg):
            if timestamp <= 1.7:
                self.assertEqual(reference(self.cfg,cases["front_early"],timestamp)["visibility"], reference(self.cfg,cases["front_late"],round(timestamp+.5,10))["visibility"])
        states = preflight(self.cfg)["per_case_reference_counts_per_background"]
        self.assertEqual(states["front_early"],{"fully_definite_frames":31,"transition_point_count":14})
        self.assertEqual(states["front_late"],states["front_early"])

    def test_transition_does_not_qualify_centroid_or_full_width(self):
        case = self.cfg["cases"][1]
        truth = reference(self.cfg,case,.35)
        self.assertEqual(truth["visibility"]["left"],"transition")
        obs={"identities_qualified":True,"features":[{"identity":"left","u":1,"v":1},{"identity":"right",**dict(zip(("u","v"),truth["uv"]["right"]))}],"width_px":99}
        result=judge(obs,truth,truth,self.cfg)
        self.assertFalse(result["fully_decidable"])
        self.assertEqual(len(result["point_checks"]),1)
        self.assertFalse(result["violations"])
        self.assertIsNone(result["qualified_width_px"])

    def test_known_visibility_contradiction_and_unqualified_readout_are_separate(self):
        truth=reference(self.cfg,self.cfg["cases"][1],.6)
        obs={"identities_qualified":True,"features":[{"identity":key,**dict(zip(("u","v"),truth["uv"][key]))} for key in IDS],"width_px":99}
        self.assertEqual(judge(obs,truth,truth,self.cfg)["violations"][0]["kind"],"visibility_contradiction")
        obs["identities_qualified"]=False
        result=judge(obs,truth,truth,self.cfg)
        self.assertFalse(result["readout_qualified"])
        self.assertFalse(result["violations"])

    def test_partial_opacity_can_move_centroid_without_changing_true_center(self):
        centers=np.asarray(self.cfg["qualification"]["centres_px"])
        black=np.zeros((450,800,3),dtype=np.uint8)
        clear=synthetic_occluded_pair(self.cfg,black,centers,1.25,7.9,6,True,np.eye(3))
        partial=synthetic_occluded_pair(self.cfg,black,centers,1.25,7.9,.75,True,np.eye(3))
        clear_obs=measure_tagged_pair(*clear,self.cfg["suite"]["measurement"])
        partial_obs=measure_tagged_pair(*partial,self.cfg["suite"]["measurement"])
        self.assertLess(abs(clear_obs["features"][0]["u"]-centers[0,0]),.25)
        self.assertGreater(abs(partial_obs["features"][0]["u"]-centers[0,0]),.25)

    def test_single_visible_marker_never_qualifies_full_width(self):
        truth=reference(self.cfg,self.cfg["cases"][1],.6)
        obs={"identities_qualified":True,"features":[{"identity":"right",**dict(zip(("u","v"),truth["uv"]["right"]))}],"width_px":None}
        result=judge(obs,truth,truth,self.cfg)
        self.assertTrue(result["fully_decidable"])
        self.assertFalse(result["violations"])
        self.assertIsNone(result["qualified_width_px"])


if __name__ == "__main__":
    unittest.main()
