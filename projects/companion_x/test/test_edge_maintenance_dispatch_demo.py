from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

DEMO = Path(__file__).parents[1] / "experiments/edge_models/edge-maintenance-dispatch-demo-001/dispatch_demo.py"
_SPEC = importlib.util.spec_from_file_location("edge_maintenance_dispatch_demo", DEMO)
assert _SPEC is not None and _SPEC.loader is not None
demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(demo)


def fixture() -> tuple[dict, dict, dict]:
    model = {"threshold": 0.7}
    model["sha256"] = demo.payload_digest(model)
    rows = []
    predictions = []
    for engine_id in range(1, 101):
        probability = 0.95 - engine_id * 0.005
        rows.append({"engine_id": engine_id, "expected_probability": probability,
                     "rul_label": int(engine_id <= 10)})
        predictions.append({"engine_id": engine_id, "observed_probability": probability})
    cohort = {"model_sha256": model["sha256"], "rows": rows}
    cohort["sha256"] = demo.payload_digest(cohort)
    result = {"status": "passed", "model_sha256": model["sha256"], "cohort_sha256": cohort["sha256"],
              "predictions": predictions}
    return model, cohort, result


class EdgeMaintenanceDispatchDemoTests(unittest.TestCase):
    def test_queue_prioritizes_scores_without_using_ground_truth_for_action(self) -> None:
        model, cohort, result = fixture()
        queue = demo.build_queue(model, cohort, result)

        self.assertEqual(queue[0]["action"], "DISPATCH_TECH")
        self.assertEqual(queue[1]["action"], "DISPATCH_TECH")
        self.assertEqual(queue[2]["action"], "REVIEW_NEXT_SHIFT")
        self.assertEqual(queue[3]["action"], "QUEUE_BACKLOG")
        self.assertEqual(queue[-1]["action"], "MONITOR")
        self.assertEqual({row["worker"] for row in queue}, {"cell-agent-a", "cell-agent-b"})
        self.assertNotIn("rul_label", queue[0])

    def test_replay_does_not_duplicate_session_or_work_items(self) -> None:
        model, cohort, result = fixture()
        queue = demo.build_queue(model, cohort, result)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.db"
            self.assertEqual(demo.persist_queue(state, "shift-test", queue), (1, 100))
            self.assertEqual(demo.persist_queue(state, "shift-test", queue), (1, 100))

    def test_stale_or_incomplete_results_are_rejected(self) -> None:
        model, cohort, result = fixture()
        result["cohort_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "provenance"):
            demo.build_queue(model, cohort, result)

        model, cohort, result = fixture()
        model["threshold"] = 0.1
        with self.assertRaisesRegex(ValueError, "payload hash"):
            demo.build_queue(model, cohort, result)

        model, cohort, result = fixture()
        result["predictions"].pop()
        with self.assertRaisesRegex(ValueError, "100"):
            demo.build_queue(model, cohort, result)


if __name__ == "__main__":
    unittest.main()
