from __future__ import annotations

import sys
import pickle
import tempfile
import unittest
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_hugsim_debug_smoke import (  # noqa: E402
    build_scoring_frame,
    replay_source_warm_start,
)


def warm_info(timestamp: float, forward: float) -> dict:
    return {
        "timestamp": timestamp,
        "ego_box": [forward, 0.0, 0.0, 1.6, 3.0, 1.5, 0.0],
        "ego_pos": [0.0, 0.0, forward],
        "ego_rot": [0.0, 0.0, 0.0],
        "ego_velo": 1.0,
        "ego_steer": 0.0,
        "obj_boxes": [[10.0 + forward, 0.0, 0.0, 1.6, 3.0, 1.5, 0.0]],
    }


def warm_observation(value: int) -> dict:
    return {
        "rgb": {
            "CAM_FRONT": np.full((2, 2, 3), value, dtype=np.uint8),
        }
    }


class FakeWarmStartEnv:
    def __init__(
        self,
        observations: list[dict],
        infos: list[dict],
    ) -> None:
        self.observations = observations
        self.infos = infos
        self.index = 0
        self.actions = []

    def step(self, action: dict) -> tuple:
        self.actions.append(action)
        self.index += 1
        return (
            self.observations[self.index],
            0.0,
            False,
            False,
            self.infos[self.index],
        )


class ScoringFrameAlignmentTest(unittest.TestCase):
    def test_plan_and_state_use_same_post_step_pose(self) -> None:
        plan = np.array([[0.0, 1.0], [0.0, 2.0]], dtype=np.float32)
        post_step_box = [4.0, 5.0, 0.0, 1.6, 3.0, 1.5, 0.2]
        info_after = {
            "timestamp": 1.25,
            "ego_box": post_step_box,
            "obj_boxes": [],
            "collision": False,
            "rc": 0.1,
        }
        captured: dict[str, object] = {}

        def fake_transform(
            transformed_plan: np.ndarray,
            anchor_box: list[float],
        ) -> list[tuple[float, float, float]]:
            captured["plan"] = transformed_plan
            captured["anchor_box"] = anchor_box
            return [(5.0, 5.0, 0.2)]

        frame = build_scoring_frame(plan, info_after, fake_transform)

        self.assertIs(captured["anchor_box"], post_step_box)
        self.assertIs(frame["ego_box"], post_step_box)
        self.assertEqual(frame["time_stamp"], info_after["timestamp"])
        np.testing.assert_allclose(
            captured["plan"],
            np.array([[1.0, -0.0], [2.0, -0.0]]),
        )

    def test_source_warm_start_replays_actions_and_checks_boundary(self) -> None:
        observations = [warm_observation(0), warm_observation(1)]
        infos = [warm_info(0.0, 0.0), warm_info(0.25, 0.25)]
        steps = [{"step_id": 0, "action": {"acc": 0.5, "steer_rate": 0.0}}]
        env = FakeWarmStartEnv(observations, infos)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("observations.pkl", observations),
                ("infos.pkl", infos),
                ("audit_steps.pkl", steps),
            ):
                with (root / name).open("wb") as stream:
                    pickle.dump(value, stream)

            observation, info, audit = replay_source_warm_start(
                env,
                observations[0],
                infos[0],
                root,
                1,
            )

        self.assertIs(observation, observations[1])
        self.assertIs(info, infos[1])
        self.assertEqual(env.actions, [steps[0]["action"]])
        self.assertEqual(audit["maximum_state_residual"], 0.0)
        self.assertEqual(audit["maximum_rgb_difference"], 0)


if __name__ == "__main__":
    unittest.main()
