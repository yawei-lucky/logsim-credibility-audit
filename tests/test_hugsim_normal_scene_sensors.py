from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_hugsim_normal_scene_sensors import (  # noqa: E402
    depth_edge_map,
    edge_map,
    frame_camera_metrics,
)


class NormalSceneSensorAuditTests(unittest.TestCase):
    def test_semantic_and_depth_edges_are_detected(self) -> None:
        semantic = np.zeros((6, 8), dtype=np.uint8)
        semantic[:, 4:] = 1
        depth = np.full((6, 8), 10.0, dtype=np.float32)
        depth[:, 4:] = 20.0
        self.assertTrue(edge_map(semantic)[:, 4].all())
        self.assertTrue(depth_edge_map(depth)[:, 4].all())

    def test_aligned_modalities_report_full_boundary_support(self) -> None:
        rgb = np.zeros((6, 8, 3), dtype=np.uint8)
        rgb[:, 4:] = 255
        semantic = np.zeros((6, 8), dtype=np.uint8)
        semantic[:, 4:] = 1
        depth = np.full((6, 8), 10.0, dtype=np.float32)
        depth[:, 4:] = 20.0
        result = frame_camera_metrics(rgb, semantic, depth)
        self.assertEqual(result["semantic_edges_near_depth_edge_fraction"], 1.0)
        self.assertEqual(result["depth_edges_near_semantic_edge_fraction"], 1.0)
        self.assertEqual(result["depth_nonfinite_fraction"], 0.0)

    def test_shape_mismatch_fails(self) -> None:
        with self.assertRaises(ValueError):
            frame_camera_metrics(
                np.zeros((3, 4, 3), dtype=np.uint8),
                np.zeros((3, 5), dtype=np.uint8),
                np.ones((3, 5), dtype=np.float32),
            )


if __name__ == "__main__":
    unittest.main()
