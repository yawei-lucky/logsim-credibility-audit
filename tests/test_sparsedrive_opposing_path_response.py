import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_sparsedrive_opposing_path_response import (  # noqa: E402
    branched_plan_path,
    plan_to_world_xz,
)


class SparseDriveOpposingPathResponseTest(unittest.TestCase):
    def test_plan_right_forward_axes_transform_to_world(self):
        pose = np.eye(4)
        pose[0, 3] = 10.0
        pose[2, 3] = 20.0
        world = plan_to_world_xz(np.asarray([[1.0, 2.0]]), pose)
        np.testing.assert_allclose(world, [[11.0, 20.0]])

    def test_branch_replaces_reference_future(self):
        times, points = branched_plan_path(
            np.asarray([0.0, 1.0, 2.0, 3.0]),
            np.asarray([[0.0, 0.0], [0.0, 1.0], [0.0, 2.0], [0.0, 3.0]]),
            2.0,
            np.asarray([0.0, 2.0]),
            np.asarray([[1.0, 3.0], [2.0, 4.0]]),
            0.5,
        )
        np.testing.assert_allclose(times, [0.0, 1.0, 2.0, 2.5, 3.0])
        np.testing.assert_allclose(points[-2:], [[1.0, 3.0], [2.0, 4.0]])


if __name__ == "__main__":
    unittest.main()
