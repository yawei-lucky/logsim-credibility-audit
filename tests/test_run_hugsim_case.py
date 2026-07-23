from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_hugsim_case import run_writer_with_runner_monitor  # noqa: E402


class RunHugsimCaseTest(unittest.TestCase):
    def test_fails_when_runner_exits_while_writer_waits(self) -> None:
        runner = subprocess.Popen(
            ["/bin/sh", "-c", "printf 'runner boom\\n'; exit 7"],
            stdout=subprocess.PIPE,
            text=True,
        )
        runner_log = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as directory:
                log = Path(directory) / "writer.log"
                with self.assertRaisesRegex(RuntimeError, "runner code=7"):
                    run_writer_with_runner_monitor(
                        ["/bin/sh", "-c", "sleep 5"],
                        os.environ.copy(),
                        log,
                        runner,
                        runner_exit_grace_s=0.05,
                        runner_log=runner_log,
                    )
        finally:
            assert runner.stdout is not None
            runner.stdout.close()
        self.assertIn("runner boom", runner_log.getvalue())

    def test_returns_writer_status_while_runner_is_alive(self) -> None:
        runner = subprocess.Popen(
            ["/bin/sh", "-c", "sleep 5"],
            stdout=subprocess.DEVNULL,
            text=True,
        )
        try:
            with tempfile.TemporaryDirectory() as directory:
                code = run_writer_with_runner_monitor(
                    ["/bin/sh", "-c", "exit 0"],
                    os.environ.copy(),
                    Path(directory) / "writer.log",
                    runner,
                    runner_exit_grace_s=0.05,
                )
            self.assertEqual(code, 0)
        finally:
            runner.terminate()
            runner.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
