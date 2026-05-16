import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


Status = Literal[
    "pass",
    "fail",
    "needs_review",
    "missing_evidence",
    "not_applicable",
    "error",
]

EvidenceType = Literal["assessment", "kql", "azure_policy", "manual"]
EvidenceStrength = Literal["authoritative", "supporting", "supplementary"]
Confidence = Literal["high", "medium", "low", "unknown"]


ASSESSMENT_STATUS = {
    "effective": "pass",
    "alternate control": "pass",
    "partially effective": "needs_review",
    "ineffective": "fail",
    "not implemented": "fail",
    "not applicable": "not_applicable",
}


@dataclass
class System:
    system_id: str
    system_name: str
    system_type: Literal["platform", "application"]
    azure_tenant_id: str | None = None
    azure_subscriptions: list[str] = field(default_factory=list)
    log_analytics_workspace_id: str | None = None
    inherits_from_system_id: str | None = None


@dataclass
class AssessmentResult:
    assessment_id: str
    system_id: str
    control_id: str
    assessment_type: Literal["ssp_annex", "irap", "internal_review", "grc_export"]
    assessment_date: str
    rating: str
    summary: str
    source_file: str


@dataclass
class EvidenceCheckDefinition:
    check_id: str
    system_id: str
    control_id: str
    evidence_type: Literal["kql", "azure_policy", "manual"]
    claim: str
    evidence_strength: EvidenceStrength = "supplementary"
    query_file: str | None = None
    fixture_key: str | None = None
    manual_evidence_id: str | None = None


@dataclass
class EvidenceCheck:
    check_id: str
    system_id: str
    control_id: str
    evidence_type: EvidenceType
    evidence_strength: EvidenceStrength
    claim: str
    status: Status
    confidence: Confidence
    summary: str
    observed_at: str
    source: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ControlEvaluation:
    evaluation_id: str
    system_id: str
    control_id: str
    final_status: Status
    confidence: Confidence
    summary: str
    assessment: AssessmentResult | None = None
    evidence: list[EvidenceCheck] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: utc_now())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text_if_exists(path: str | None) -> str | None:
    if path is None:
        return None

    file_path = Path(path)
    if not file_path.exists():
        return None

    return file_path.read_text()


def load_test_data() -> dict[str, Any]:
    with open("data/test_data/test_data.json") as f:
        return json.load(f)


def load_ssp_annex_results(system: System) -> dict[str, AssessmentResult]:
    source_file = "data/assessments/ssp_annex_test_assessment.csv"
    results: dict[str, AssessmentResult] = {}

    with open(source_file, newline="") as f:
        for row in csv.DictReader(f):
            control_id = row["ism_control"].strip().upper()
            rating = row["rating"].strip().lower()
            results[control_id] = AssessmentResult(
                assessment_id="test-assessment-2026",
                system_id=system.system_id,
                control_id=control_id,
                assessment_type="ssp_annex",
                assessment_date="2026-02-10",
                rating=rating,
                summary=f"SSP annex rating is '{rating}'.",
                source_file=source_file,
            )

    return results


def load_manual_evidence_register() -> dict[str, dict[str, str]]:
    # Tiny parser for the existing one-item example file. Replace with PyYAML later.
    register_path = Path("config/manual_evidence_register.yaml")
    current: dict[str, str] = {}
    records: dict[str, dict[str, str]] = {}

    for line in register_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped == "manual_evidence:":
            continue

        if stripped.startswith("- id:"):
            if current:
                records[current["id"]] = current
            current = {"id": stripped.split(":", 1)[1].strip()}
            continue

        if ":" in stripped and current:
            key, value = stripped.split(":", 1)
            current[key.strip()] = value.strip().strip('"')

    if current:
        records[current["id"]] = current

    return records


def evaluate_kql_check(definition: EvidenceCheckDefinition, test_data: dict[str, Any]) -> EvidenceCheck:
    query_text = read_text_if_exists(definition.query_file)
    fixture_key = definition.fixture_key or ""
    fixture = test_data["kql"].get(fixture_key, {})
    rows = fixture.get("rows", [])

    if definition.check_id == "KQL-MFA-SIGNIN":
        mfa_rows = [
            row for row in rows
            if row.get("AuthenticationRequirement") == "multiFactorAuthentication"
        ]
        status: Status = "pass" if mfa_rows else "fail"
        summary = f"Found {len(mfa_rows)} MFA sign-in rows in fixture '{fixture_key}'."

    elif definition.check_id == "KQL-CENTRALISED-LOGGING":
        healthy_tables = [
            row["TableName"] for row in rows
            if row.get("Status") == "Healthy"
        ]
        status = "pass" if len(healthy_tables) >= 3 else "fail"
        summary = f"Found {len(healthy_tables)} healthy log source tables."

    else:
        status = "pass" if rows else "fail"
        summary = f"Found {len(rows)} KQL result rows."

    return EvidenceCheck(
        check_id=definition.check_id,
        system_id=definition.system_id,
        control_id=definition.control_id,
        evidence_type="kql",
        evidence_strength=definition.evidence_strength,
        claim=definition.claim,
        status=status,
        confidence="medium",
        summary=summary,
        observed_at=utc_now(),
        source={
            "query_file": definition.query_file,
            "fixture_key": fixture_key,
            "query_text": query_text,
        },
        raw={"rows": rows},
    )


def evaluate_azure_policy_check(
    definition: EvidenceCheckDefinition,
    test_data: dict[str, Any],
) -> EvidenceCheck:
    policy_key = definition.fixture_key or ""
    policy = test_data["azure_policy"].get(policy_key, {})
    state = policy.get("compliance_state")
    non_compliant = int(policy.get("non_compliant_resources", 0))
    exempt = int(policy.get("exempt_resources", 0))

    status: Status = "pass" if state == "Compliant" and non_compliant == 0 else "fail"
    summary = (
        f"Azure Policy state is {state}; "
        f"{non_compliant} non-compliant resources and {exempt} exemptions."
    )

    return EvidenceCheck(
        check_id=definition.check_id,
        system_id=definition.system_id,
        control_id=definition.control_id,
        evidence_type="azure_policy",
        evidence_strength=definition.evidence_strength,
        claim=definition.claim,
        status=status,
        confidence="medium",
        summary=summary,
        observed_at=utc_now(),
        source={
            "fixture_key": policy_key,
            "policy_assignment_id": policy.get("policy_assignment_id"),
            "policy_display_name": policy.get("policy_display_name"),
        },
        raw=policy,
    )


def evaluate_manual_check(
    definition: EvidenceCheckDefinition,
    manual_register: dict[str, dict[str, str]],
) -> EvidenceCheck:
    manual_id = definition.manual_evidence_id or ""
    record = manual_register.get(manual_id)

    if record is None:
        return EvidenceCheck(
            check_id=definition.check_id,
            system_id=definition.system_id,
            control_id=definition.control_id,
            evidence_type="manual",
            evidence_strength="supporting",
            claim=definition.claim,
            status="missing_evidence",
            confidence="unknown",
            summary=f"Manual evidence '{manual_id}' was not found.",
            observed_at=utc_now(),
            source={"manual_evidence_id": manual_id},
        )

    verification_status = record.get("verification_status")
    status: Status = "pass" if verification_status in {"human_reviewed", "verified"} else "fail"

    return EvidenceCheck(
        check_id=definition.check_id,
        system_id=definition.system_id,
        control_id=definition.control_id,
        evidence_type="manual",
        evidence_strength="supporting",
        claim=definition.claim,
        status=status,
        confidence="high",
        summary=f"Manual evidence '{record.get('title')}' is {verification_status}.",
        observed_at=utc_now(),
        source={"manual_evidence_id": manual_id},
        raw=record,
    )


def evaluate_check(
    definition: EvidenceCheckDefinition,
    test_data: dict[str, Any],
    manual_register: dict[str, dict[str, str]],
) -> EvidenceCheck:
    if definition.evidence_type == "kql":
        return evaluate_kql_check(definition, test_data)
    if definition.evidence_type == "azure_policy":
        return evaluate_azure_policy_check(definition, test_data)
    if definition.evidence_type == "manual":
        return evaluate_manual_check(definition, manual_register)

    raise ValueError(f"Unsupported evidence type: {definition.evidence_type}")


def evaluate_control(
    system_id: str,
    control_id: str,
    assessment: AssessmentResult | None,
    evidence: list[EvidenceCheck],
) -> ControlEvaluation:
    failed_checks = [item for item in evidence if item.status == "fail"]
    passed_checks = [item for item in evidence if item.status == "pass"]

    if assessment is not None:
        base_status = ASSESSMENT_STATUS.get(assessment.rating, "needs_review")

        if base_status == "pass" and failed_checks:
            return ControlEvaluation(
                evaluation_id=f"EVAL-{system_id}-{control_id}",
                system_id=system_id,
                control_id=control_id,
                final_status="needs_review",
                confidence="medium",
                assessment=assessment,
                evidence=evidence,
                summary=(
                    "Assessment passes, but supplementary automated evidence "
                    "found possible non-compliance."
                ),
                conflicts=[item.check_id for item in failed_checks],
            )

        return ControlEvaluation(
            evaluation_id=f"EVAL-{system_id}-{control_id}",
            system_id=system_id,
            control_id=control_id,
            final_status=base_status,
            confidence="high",
            assessment=assessment,
            evidence=evidence,
            summary=f"Assessment rating is '{assessment.rating}'.",
        )

    if failed_checks:
        return ControlEvaluation(
            evaluation_id=f"EVAL-{system_id}-{control_id}",
            system_id=system_id,
            control_id=control_id,
            final_status="fail",
            confidence="medium",
            evidence=evidence,
            summary="No assessment result exists; available evidence contains failures.",
            conflicts=[item.check_id for item in failed_checks],
            gaps=["missing_assessment"],
        )

    if passed_checks:
        return ControlEvaluation(
            evaluation_id=f"EVAL-{system_id}-{control_id}",
            system_id=system_id,
            control_id=control_id,
            final_status="pass",
            confidence="medium",
            evidence=evidence,
            summary="No assessment result exists; available evidence supports the control.",
            gaps=["missing_assessment"],
        )

    return ControlEvaluation(
        evaluation_id=f"EVAL-{system_id}-{control_id}",
        system_id=system_id,
        control_id=control_id,
        final_status="missing_evidence",
        confidence="unknown",
        evidence=evidence,
        summary="No assessment, automated evidence, or manual evidence found.",
        gaps=["missing_assessment", "missing_evidence"],
    )


def build_example_checks(system: System) -> list[EvidenceCheckDefinition]:
    return [
        EvidenceCheckDefinition(
            check_id="KQL-MFA-SIGNIN",
            system_id=system.system_id,
            control_id="ISM-1683",
            evidence_type="kql",
            evidence_strength="supplementary",
            claim="MFA activity is visible in sign-in logs.",
            query_file="queries/ism_kql_intent_coverage/q_mfa_signin.kql",
            fixture_key="recent_signin_activity",
        ),
        EvidenceCheckDefinition(
            check_id="MAN-MFA-PROCESS",
            system_id=system.system_id,
            control_id="ISM-1683",
            evidence_type="manual",
            evidence_strength="supporting",
            claim="A documented process exists for the control.",
            manual_evidence_id="MAN-TEST-SOP",
        ),
        EvidenceCheckDefinition(
            check_id="AZPOL-KEYVAULT-SOFT-DELETE",
            system_id=system.system_id,
            control_id="ISM-1542",
            evidence_type="azure_policy",
            evidence_strength="supplementary",
            claim="Key Vault soft delete is enabled.",
            fixture_key="key_vault_soft_delete",
        ),
        EvidenceCheckDefinition(
            check_id="AZPOL-STORAGE-SECURE-TRANSFER",
            system_id=system.system_id,
            control_id="ISM-1544",
            evidence_type="azure_policy",
            evidence_strength="supplementary",
            claim="Storage accounts require secure transfer.",
            fixture_key="storage_accounts_secure_transfer",
        ),
        EvidenceCheckDefinition(
            check_id="AZPOL-DEFENDER-FOR-SERVERS",
            system_id=system.system_id,
            control_id="ISM-1585",
            evidence_type="azure_policy",
            evidence_strength="supplementary",
            claim="Defender for Servers is enabled.",
            fixture_key="defender_for_servers_enabled",
        ),
        EvidenceCheckDefinition(
            check_id="KQL-CENTRALISED-LOGGING",
            system_id=system.system_id,
            control_id="ISM-1984",
            evidence_type="kql",
            evidence_strength="supplementary",
            claim="Central log sources are present and healthy.",
            query_file="queries/ism_kql_intent_coverage/q_centralised_logging.kql",
            fixture_key="log_source_health",
        ),
        EvidenceCheckDefinition(
            check_id="AZPOL-DIAGNOSTIC-SETTINGS",
            system_id=system.system_id,
            control_id="ISM-1984",
            evidence_type="azure_policy",
            evidence_strength="supplementary",
            claim="Resources send diagnostic logs to Log Analytics.",
            fixture_key="diagnostic_settings_to_log_analytics",
        ),
    ]


def summarize(evaluations: list[ControlEvaluation]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for item in evaluations:
        by_status[item.final_status] = by_status.get(item.final_status, 0) + 1

    return {
        "control_count": len(evaluations),
        "by_status": by_status,
        "with_assessment": sum(item.assessment is not None for item in evaluations),
        "with_evidence": sum(bool(item.evidence) for item in evaluations),
        "with_conflicts": sum(bool(item.conflicts) for item in evaluations),
    }


def main() -> None:
    system = System(
        system_id="test-system-abc",
        system_name="Test System ABC",
        system_type="application",
        azure_tenant_id="tenant-test",
        azure_subscriptions=["11111111-1111-1111-1111-111111111111"],
        log_analytics_workspace_id="test_data",
        inherits_from_system_id="platform-tenant",
    )

    test_data = load_test_data()
    assessment_by_control = load_ssp_annex_results(system)
    manual_register = load_manual_evidence_register()
    check_definitions = build_example_checks(system)

    evidence_by_control: dict[str, list[EvidenceCheck]] = {}
    for definition in check_definitions:
        evidence = evaluate_check(definition, test_data, manual_register)
        evidence_by_control.setdefault(definition.control_id, []).append(evidence)

    control_ids = sorted(set(assessment_by_control) | set(evidence_by_control))
    evaluations = [
        evaluate_control(
            system_id=system.system_id,
            control_id=control_id,
            assessment=assessment_by_control.get(control_id),
            evidence=evidence_by_control.get(control_id, []),
        )
        for control_id in control_ids
    ]

    output = {
        "generated_at": utc_now(),
        "system": asdict(system),
        "summary": summarize(evaluations),
        "evaluations": [asdict(item) for item in evaluations],
    }

    output_path = Path("output/mvp_dashboard_example.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2))

    print(json.dumps(output["summary"], indent=2))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
