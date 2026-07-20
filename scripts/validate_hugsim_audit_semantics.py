#!/usr/bin/env python3
"""Validate claim decisions and diagnostic findings in HUGSIM audit JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_LABELS = {"accepted", "down-weighted", "rejected"}
SUPPORTED_INVALIDATING_LABELS = {"accepted", "down-weighted"}
REJECTION_BASES = {
    "contradicted_by_evidence",
    "invalidated_by_diagnostic",
    "not_tested",
    "scope_exceeds_evidence",
}
TESTED_REQUIRED = {
    "contradicted_by_evidence",
    "invalidated_by_diagnostic",
}
UNTESTED_REQUIRED = {"not_tested", "scope_exceeds_evidence"}
HUGSIM_REF = re.compile(
    r"^HUGSIM@(?P<commit>[0-9a-f]{7,40}):"
    r"(?P<path>[^:]+):(?P<symbol>[A-Za-z_][A-Za-z0-9_.]*)$"
)


def require_nonempty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def validate_evidence_refs(
    evidence_refs: Any,
    field: str,
    repo_root: Path,
    hugsim_commit: Any,
    *,
    required: bool,
) -> None:
    if evidence_refs is None and not required:
        return
    if (
        not isinstance(evidence_refs, list)
        or not evidence_refs
        or not all(
            isinstance(reference, str) and reference.strip()
            for reference in evidence_refs
        )
    ):
        requirement = "a non-empty string list"
        if not required:
            requirement += " when present"
        raise ValueError(f"{field} must be {requirement}")

    root = repo_root.resolve()
    for reference in evidence_refs:
        if reference.startswith("HUGSIM@"):
            match = HUGSIM_REF.fullmatch(reference)
            if not match:
                raise ValueError(
                    f"{field} contains malformed HUGSIM reference "
                    f"{reference!r}"
                )
            require_nonempty_string(
                hugsim_commit,
                "hugsim_commit required by HUGSIM evidence reference",
            )
            if not hugsim_commit.startswith(match.group("commit")):
                raise ValueError(
                    f"{field} HUGSIM commit does not match record: "
                    f"{reference!r}"
                )
            source_path = PurePosixPath(match.group("path"))
            if source_path.is_absolute() or ".." in source_path.parts:
                raise ValueError(
                    f"{field} contains unsafe HUGSIM path {reference!r}"
                )
            continue

        relative_path = PurePosixPath(reference)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(
                f"{field} contains path outside the repository: {reference!r}"
            )
        resolved = (root / Path(*relative_path.parts)).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(
                f"{field} contains path outside the repository: {reference!r}"
            ) from error
        if not resolved.is_file():
            raise ValueError(
                f"{field} references a missing file: {reference!r}"
            )


def validate_diagnostic_findings(
    findings: dict[str, Any],
    repo_root: Path,
    hugsim_commit: Any,
) -> None:
    for finding_id, finding in findings.items():
        require_nonempty_string(finding_id, "diagnostic finding id")
        if not isinstance(finding, dict):
            raise ValueError(
                f"diagnostic_findings.{finding_id} must be an object"
            )
        for field in ("component", "expected", "observed", "implication"):
            require_nonempty_string(
                finding.get(field),
                f"diagnostic_findings.{finding_id}.{field}",
            )
        if not isinstance(finding.get("expectation_met"), bool):
            raise ValueError(
                f"diagnostic_findings.{finding_id}.expectation_met "
                "must be boolean"
            )
        decision = finding.get("evidence_decision")
        if decision not in EVIDENCE_LABELS:
            raise ValueError(
                f"diagnostic_findings.{finding_id}.evidence_decision "
                f"must be one of {sorted(EVIDENCE_LABELS)}"
            )
        validate_evidence_refs(
            finding.get("evidence_refs"),
            f"diagnostic_findings.{finding_id}.evidence_refs",
            repo_root,
            hugsim_commit,
            required=True,
        )


def validate_audit_semantics(
    record: dict[str, Any],
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    credibility = record.get("credibility")
    if not isinstance(credibility, dict):
        raise ValueError("credibility must be an object")
    claim_decisions = credibility.get("claim_decisions")
    if not isinstance(claim_decisions, dict) or not claim_decisions:
        raise ValueError("credibility.claim_decisions must be a non-empty object")

    for claim_id, decision in claim_decisions.items():
        require_nonempty_string(claim_id, "claim id")
        if decision not in EVIDENCE_LABELS:
            raise ValueError(
                f"claim {claim_id!r} uses invalid decision {decision!r}"
            )

    rejected_claims = {
        claim_id
        for claim_id, decision in claim_decisions.items()
        if decision == "rejected"
    }
    contexts = credibility.get("rejected_claim_contexts")
    if not isinstance(contexts, dict):
        raise ValueError(
            "credibility.rejected_claim_contexts must be an object"
        )
    if set(contexts) != rejected_claims:
        missing = sorted(rejected_claims - set(contexts))
        extra = sorted(set(contexts) - rejected_claims)
        raise ValueError(
            "rejected claim contexts do not match rejected claims: "
            f"missing={missing}, extra={extra}"
        )

    findings = record.get("diagnostic_findings", {})
    if not isinstance(findings, dict):
        raise ValueError("diagnostic_findings must be an object")
    hugsim_commit = record.get("hugsim_commit")
    validate_diagnostic_findings(findings, repo_root, hugsim_commit)

    linked_findings = set()
    basis_counts = {basis: 0 for basis in sorted(REJECTION_BASES)}
    for claim_id, context in contexts.items():
        if not isinstance(context, dict):
            raise ValueError(
                f"rejected_claim_contexts.{claim_id} must be an object"
            )
        tested = context.get("tested")
        if not isinstance(tested, bool):
            raise ValueError(
                f"rejected_claim_contexts.{claim_id}.tested must be boolean"
            )
        basis = context.get("rejection_basis")
        if basis not in REJECTION_BASES:
            raise ValueError(
                f"rejected_claim_contexts.{claim_id}.rejection_basis "
                f"must be one of {sorted(REJECTION_BASES)}"
            )
        basis_counts[basis] += 1
        if basis in TESTED_REQUIRED and not tested:
            raise ValueError(
                f"{claim_id}: rejection_basis={basis} requires tested=true"
            )
        if basis in UNTESTED_REQUIRED and tested:
            raise ValueError(
                f"{claim_id}: rejection_basis={basis} requires tested=false"
            )
        require_nonempty_string(
            context.get("reason"),
            f"rejected_claim_contexts.{claim_id}.reason",
        )
        validate_evidence_refs(
            context.get("evidence_refs"),
            f"rejected_claim_contexts.{claim_id}.evidence_refs",
            repo_root,
            hugsim_commit,
            required=tested,
        )
        finding_id = context.get("diagnostic_finding")
        if finding_id is not None:
            require_nonempty_string(
                finding_id,
                f"rejected_claim_contexts.{claim_id}.diagnostic_finding",
            )
            if finding_id not in findings:
                raise ValueError(
                    f"{claim_id}: diagnostic finding {finding_id!r} is missing"
                )
            linked_findings.add(finding_id)
        if tested and finding_id is None:
            raise ValueError(
                f"{claim_id}: tested=true requires a diagnostic_finding"
            )
        if (
            tested
            and findings[finding_id]["evidence_decision"]
            not in SUPPORTED_INVALIDATING_LABELS
        ):
            raise ValueError(
                f"{claim_id}: linked diagnostic finding must be "
                "accepted or down-weighted"
            )
        if (
            basis == "invalidated_by_diagnostic"
            and finding_id is None
        ):
            raise ValueError(
                f"{claim_id}: invalidated_by_diagnostic requires a "
                "diagnostic_finding"
            )
        if basis == "invalidated_by_diagnostic":
            finding = findings[finding_id]
            if finding["evidence_decision"] not in SUPPORTED_INVALIDATING_LABELS:
                raise ValueError(
                    f"{claim_id}: invalidating diagnostic finding "
                    "must be accepted or down-weighted"
                )
            if finding["expectation_met"]:
                raise ValueError(
                    f"{claim_id}: invalidating diagnostic finding "
                    "must record expectation_met=false"
                )

    return {
        "experiment_id": record.get("experiment_id"),
        "claim_count": len(claim_decisions),
        "rejected_claim_count": len(rejected_claims),
        "rejection_basis_counts": basis_counts,
        "diagnostic_finding_count": len(findings),
        "linked_diagnostic_findings": sorted(linked_findings),
        "status": "passed",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate claim/finding separation in HUGSIM audits."
    )
    parser.add_argument("audits", nargs="+", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = []
    for path in args.audits:
        resolved = path.expanduser().resolve()
        with resolved.open("r", encoding="utf-8") as stream:
            record = json.load(stream)
        result = validate_audit_semantics(record, REPO_ROOT)
        result["path"] = str(resolved)
        results.append(result)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
