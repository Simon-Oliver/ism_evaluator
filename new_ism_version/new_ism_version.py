import csv
import json
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, List, Any
from datetime import date
from pathlib import Path
import yaml

# ------------- Literal definitions -------------

SourceType = Literal[
    "assessment",
    "control_set",
    "kql",
    "manual",
    "azure_policy",
    "graph_api",
]

# ControlStatus = Literal[
#     "effective",
#     "alternate_control",
#     "ineffective",
#     "no_visibility",
#     "not_implemented",
#     "not_applicable",
#     "not_assessed",
#     "expired",
# ]

AssertionType = Literal[
    "exists_any_row",
    "no_rows",
    "row_count_gte",
    "field_contains_all",
    "field_contains_any",
    "any_row_matches",
    "all_rows_match",
]


# ------------- Class definitions -------------

class Assertion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AssertionType
    field: str | None = None
    # I'm allowing these types but in the assertion check values are changed to strings
    value: str | int | bool | None = None
    values: list[str | int | bool] = Field(default_factory=list)
    minimum: int | None = None  # Not sure if needed


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["kql"]
    title: str

    ism_version: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")
    controls: list[str] = Field(default_factory=list)

    # default means "run this as part of the default set"
    tags: list[str] = Field(default_factory=lambda: ["default"])

    query_file: str
    scope_ref: str = "log_analytics_workspace"

    assertion: Assertion


class System(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[str] = Field(default_factory=lambda: ["default"])
    id: str
    system_name: str
    description: str | None = None


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^ism-\d{4}$")
    prose: str
    ism_version: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    system_id: str
    type: Literal["irap", "ato", "self_assessment", "other"]
    ism_version: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")
    assessed_on: date
    expires_on: date | None = None
    csv_path: str

    control_id_column: str = "controlid"
    rating_column: str = "rating"
    comment_column: str | None = "comment"

    source_document: str | None = None


class SystemControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_id: str
    ism_version: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")
    control_id: str = Field(pattern=r"^ism-\d{4}$")

    source_type: Literal["assessment", "control_set"]
    source_id: str


class SystemControlAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_id: str
    ism_version: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")
    control_id: str = Field(pattern=r"^ism-\d{4}$")

    status: str  # ControlStatus

    source_type: Literal["assessment"]
    source_id: str
    assessed_on: date
    comment: str | None = None


class ManualEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    type: Literal[
        "document",
        "attestation",
        "ticket",
        "risk_acceptance",
        "architecture",
        "procedure",
    ]
    systems: list[str] = Field(default_factory=list)
    ism_version: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")
    controls: list[str] = Field(default_factory=list)
    status: str  # ControlStatus
    reviewed_on: date
    expires_on: date | None = None
    location: str | None = None
    owner: str | None = None
    comment: str | None = None


class SystemControlResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str
    ism_version: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")
    control_id: str = Field(pattern=r"^ism-\d{4}$")
    status: str  # ControlStatus
    source_type: SourceType
    source_id: str
    source_name: str | None = None
    evaluated_on: date
    expires_on: date | None = None
    evidence_location: str | None = None
    comment: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class QueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[str]
    rows: list[dict[str, Any]]


# ------------- File loaders -------------

def yaml_loader(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


# ------------- Load all yaml files -------------

systems = [System(**system) for system in yaml_loader("./data/systems.yaml")["systems"]]
controls = [Control(**control) for control in yaml_loader("./data/controls.yaml")["controls"]]
assessments = [Assessment(**assessment) for assessment in
               yaml_loader("./data/assessments/assessment.yaml")["assessments"]]
manual_evidence = [ManualEvidence(**evidence) for evidence in
                   yaml_loader("./data/manual_evidence.yaml")["manual_evidence"]]
checks = [Check(**check) for check in yaml_loader("./data/checks.yaml")["checks"]]


# ------------- Dummy KQL runner -------------

def kql_runner(query_file: str | Path, scope_value: str | None = None) -> QueryResult:
    with open(query_file, "r") as f:
        query = f.read()
    # print("Query and scope is running: ", query, scope_value)
    return QueryResult(
        columns=["EventID", "Count"],
        rows=[
            {
                "Result": "placeholder",
                "EventID": "4103",
                "Count": 1,
                "QueryPreview": query,
                "Scope": scope_value,
            },
            {
                "Result": "placeholder",
                "EventID": "4104",
                "Count": 5,
                "QueryPreview": query,
                "Scope": scope_value,
            }
        ]
    )


# ------------- Evaluate assertion -------------
def exists_any_row(result: QueryResult, assertion: Assertion) -> bool:
    return len(result.rows) > 0


def no_rows(result: QueryResult, assertion: Assertion) -> bool:
    return len(result.rows) == 0


def field_contains_all(result: QueryResult, assertion: Assertion) -> bool:
    if assertion.field is None:
        raise ValueError("field_contains_all requires assertion.field")

    actual = set(str(value.get(assertion.field)).strip() for value in result.rows)
    expected = set(str(value).strip() for value in assertion.values)
    # print("Field contains all ---", actual, expected)
    return expected.issubset(actual)


# Must match AssertionType
ASSERTIONS = {
    "exists_any_row": exists_any_row,
    "field_contains_all": field_contains_all,
    "no_rows": no_rows
    # "row_count_gte",
    # "field_contains_all",
    # "field_contains_any",
    # "any_row_matches",
    # "all_rows_match",
}

# Must match SourceType
RUNNERS = {
    "kql": kql_runner,
}


def evaluate_assertion(result: QueryResult, assertion: Assertion) -> bool:
    evaluator = ASSERTIONS.get(assertion.type, None)
    if evaluator is None:
        raise ValueError(f"Unknown assertion type: {assertion.type}")
    # print("Evaluate Assertion ---" ,assertion.type, evaluator(result, assertion))
    return evaluator(result, assertion)


# ------------- Results generator -------------

def results_from_assessment(assessment: Assessment) -> list[SystemControlResult]:
    results: list[SystemControlResult] = []

    with open(assessment.csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            control_id = row.get(assessment.control_id_column).lower()
            control_status = row.get(assessment.rating_column).lower()
            comment = row.get(assessment.comment_column, None)

            results.append(
                SystemControlResult(
                    system_id=assessment.system_id,
                    ism_version=assessment.ism_version,
                    control_id=control_id,
                    status=control_status,
                    source_type="assessment",
                    source_id=assessment.id,
                    source_name=assessment.type,
                    evaluated_on=assessment.assessed_on,
                    expires_on=assessment.expires_on,
                    evidence_location=assessment.source_document,
                    comment=comment,
                    details={
                        "assessment_type": assessment.type,
                        "csv_path": assessment.csv_path,
                        # TODO: Implement a check or evaluation if an assessment is expired
                        "is_expired": "Implement later",
                    }
                )
            )

    return results


def results_from_manual_evidence(manual_evidence: ManualEvidence) -> list[SystemControlResult]:
    results: list[SystemControlResult] = []
    systems = manual_evidence.systems
    controls = manual_evidence.controls

    for system in systems:
        for control in controls:
            results.append(
                SystemControlResult(
                    system_id=system,
                    ism_version=manual_evidence.ism_version,
                    control_id=control,
                    status=manual_evidence.status,
                    source_type="manual",
                    source_id=manual_evidence.id,
                    source_name=manual_evidence.title,
                    evaluated_on=manual_evidence.reviewed_on,
                    expires_on=manual_evidence.expires_on,
                    evidence_location=manual_evidence.location,
                    comment=manual_evidence.comment,
                    details={
                        "owner": manual_evidence.owner
                    }
                )
            )

    return results


def results_from_checks(systems: list[System], checks: list[Check]) -> list[SystemControlResult]:
    results: list[SystemControlResult] = []
    for system in systems:
        for check in checks:
            if not set(system.tags).intersection(check.tags):
                # print("No match", system.system_name, system.tags, check.tags)
                continue

            runner = RUNNERS.get(check.type)

            if runner is None:
                raise ValueError(f"No runner configured for check type: {check.type}")

            result = runner(check.query_file, check.scope_ref)

            passed = evaluate_assertion(result, check.assertion)
            status = "effective" if passed else "ineffective"
            # print("Checks results",system.id, status, check.query_file,evaluate_assertion(result, check.assertion))
            # print(system.system_name, system.tags, check.tags, check.query_file)

            for control_id in check.controls:
                control_id = control_id.lower()

                results.append(
                    SystemControlResult(
                        system_id=system.id,
                        ism_version=check.ism_version,
                        control_id=control_id,
                        status=status,
                        source_type="kql",
                        source_id=check.id,
                        source_name=check.title,
                        evaluated_on=date.today(),
                        evidence_location=check.query_file,
                        comment=f"KQL assertion {'passed' if passed else 'failed'}: {check.assertion.type}",
                        details={
                            "assertion": check.assertion.model_dump(),
                            "row_count": len(result.rows),
                            "columns": result.columns,
                            "scope_ref": check.scope_ref
                        }
                    )
                )
    return results


output: list[SystemControlResult] = []
for assessment in assessments:
    output.extend(results_from_assessment(assessment))

for evidence in manual_evidence:
    output.extend(results_from_manual_evidence(evidence))

output.extend(results_from_checks(systems, checks))

for res in output:
    print(res.system_id, res.control_id, res.status, res.source_type)
