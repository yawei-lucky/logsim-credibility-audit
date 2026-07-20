import copy
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from validate_hugsim_audit_semantics import (  # noqa: E402
    validate_audit_semantics,
)


def valid_record():
    return {
        "experiment_id": "example",
        "credibility": {
            "claim_decisions": {
                "metric_claim": "rejected",
                "pairing_claim": "accepted",
                "agent_claim": "rejected",
            },
            "rejected_claim_contexts": {
                "metric_claim": {
                    "tested": True,
                    "rejection_basis": "invalidated_by_diagnostic",
                    "reason": "The same prefix changes score when extended.",
                    "evidence_refs": [
                        "docs/hugsim_credibility_decision_rules.md"
                    ],
                    "diagnostic_finding": "tail_padding",
                },
                "agent_claim": {
                    "tested": False,
                    "rejection_basis": "not_tested",
                    "reason": "No AD agent was installed.",
                    "diagnostic_finding": None,
                },
            },
        },
        "diagnostic_findings": {
            "tail_padding": {
                "component": "metric_implementation",
                "expected": (
                    "Frames without required future history are invalidated."
                ),
                "observed": (
                    "The scorer pads the final box and emits a valid score."
                ),
                "expectation_met": False,
                "evidence_decision": "accepted",
                "implication": "Tail events require a history-completeness gate.",
                "evidence_refs": [
                    "docs/hugsim_credibility_decision_rules.md"
                ],
            }
        },
    }


class AuditSemanticsTest(unittest.TestCase):
    def test_valid_dual_layer_record_passes(self):
        result = validate_audit_semantics(valid_record())

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["rejected_claim_count"], 2)
        self.assertEqual(result["linked_diagnostic_findings"], ["tail_padding"])

    def test_rejected_claim_requires_context(self):
        record = valid_record()
        del record["credibility"]["rejected_claim_contexts"]["metric_claim"]

        with self.assertRaisesRegex(ValueError, "do not match"):
            validate_audit_semantics(record)

    def test_untested_bases_require_tested_false(self):
        for basis in ("not_tested", "scope_exceeds_evidence"):
            with self.subTest(basis=basis):
                record = valid_record()
                context = record["credibility"]["rejected_claim_contexts"][
                    "agent_claim"
                ]
                context["rejection_basis"] = basis
                context["tested"] = True
                with self.assertRaisesRegex(
                    ValueError,
                    "requires tested=false",
                ):
                    validate_audit_semantics(record)

    def test_diagnostic_link_must_resolve(self):
        for operation, message in (
            ("delete", "requires a diagnostic_finding"),
            ("dangling", "is missing"),
            ("basis_bypass", "tested=true requires a diagnostic_finding"),
        ):
            with self.subTest(operation=operation):
                record = copy.deepcopy(valid_record())
                context = record["credibility"]["rejected_claim_contexts"][
                    "metric_claim"
                ]
                if operation == "delete":
                    del context["diagnostic_finding"]
                elif operation == "basis_bypass":
                    context["rejection_basis"] = "contradicted_by_evidence"
                    del context["diagnostic_finding"]
                else:
                    context["diagnostic_finding"] = "missing"
                with self.assertRaisesRegex(ValueError, message):
                    validate_audit_semantics(record)

    def test_invalidating_finding_must_be_supported_nonconformance(self):
        for field, value, message in (
            ("evidence_decision", "rejected", "accepted or down-weighted"),
            ("expectation_met", True, "expectation_met=false"),
        ):
            with self.subTest(field=field):
                record = valid_record()
                record["diagnostic_findings"]["tail_padding"][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    validate_audit_semantics(record)

    def test_evidence_refs_are_validated_even_for_untested_claims(self):
        record = valid_record()
        record["credibility"]["rejected_claim_contexts"]["agent_claim"][
            "evidence_refs"
        ] = 42

        with self.assertRaisesRegex(ValueError, "when present"):
            validate_audit_semantics(record)

    def test_evidence_reference_must_be_safe_and_resolvable(self):
        for reference, message in (
            ("artifacts/does-not-exist.json", "missing file"),
            ("../outside.json", "outside the repository"),
            (
                "HUGSIM@not-a-commit:sim/utils/score.py:calculate",
                "malformed HUGSIM reference",
            ),
            (
                "HUGSIM@deadbee:sim/utils/score.py:calculate",
                "commit does not match record",
            ),
        ):
            with self.subTest(reference=reference):
                record = valid_record()
                record["hugsim_commit"] = (
                    "adeca402cad4af8635e13d0a105e2fee6a14de85"
                )
                record["diagnostic_findings"]["tail_padding"][
                    "evidence_refs"
                ] = [reference]
                with self.assertRaisesRegex(ValueError, message):
                    validate_audit_semantics(record)

    def test_required_rejection_fields_fail_closed(self):
        context = valid_record()["credibility"]["rejected_claim_contexts"][
            "metric_claim"
        ]
        for field, message in (
            ("tested", "tested must be boolean"),
            ("rejection_basis", "rejection_basis"),
            ("reason", "reason must be a non-empty string"),
        ):
            with self.subTest(field=field):
                record = valid_record()
                del record["credibility"]["rejected_claim_contexts"][
                    "metric_claim"
                ][field]
                with self.assertRaisesRegex(ValueError, message):
                    validate_audit_semantics(record)
        self.assertTrue(context)

    def test_real_audits_pass(self):
        for filename in (
            "hugsim_horizon_factorial_001_audit.json",
            "hugsim_near_cut_in_001_audit.json",
        ):
            with self.subTest(filename=filename):
                path = REPO_ROOT / "docs" / "runs" / filename
                with path.open("r", encoding="utf-8") as stream:
                    record = json.load(stream)
                self.assertEqual(
                    validate_audit_semantics(record)["status"],
                    "passed",
                )


if __name__ == "__main__":
    unittest.main()
