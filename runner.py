import csv
import yaml
import json
from datetime import date, datetime, timezone
from pathlib import Path


ASSESSMENT_RATING_STATUS = {
    "effective": "pass",
    "alternate control": "pass",
    "ineffective": "fail",
    "not implemented": "fail",
    "not applicable": "not_applicable",
}


def yaml_loader(path):
    with open(path, "r") as stream:
        return yaml.safe_load(stream)


def json_default(value):
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=json_default)


with open("data/test_data/test_data.json") as f:
    test_data = json.load(f)

manual_evidence_register = yaml_loader("config/manual_evidence_register.yaml")['manual_evidence']

RUN_DATA = {
    "started_at": datetime.now(timezone.utc),
    "run_id": f"run-{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")}"
}

CONTEXT = {
    **RUN_DATA,
    "manual_evidence_register": {item['id']: item for item in manual_evidence_register}
}


def collect_kql(definition, context):
    print("Collecting KQL queries...")
    workspace_id = definition["source"]["workspace"]
    query_file = definition["source"]["query_file"]

    if workspace_id == 'test_data':
        print(f"Running with test data. Query file: {query_file}")
        test_id = query_file.split("/")[-1]
        return test_data['kql'][test_id]


def collect_manual_reference(definition, context):
    print("Collecting manual references...")
    id = definition["source"]["evidence_register_id"]
    evidence = context["manual_evidence_register"].get(id, None)
    if evidence is None:
        raise Exception(f"Manual reference '{id}' not found.")
    return evidence


def collect_azure_policy(evidence_source, context):
    print("Collecting Azure policies...")
    print(evidence_source)


# def resolve_path(data, path):
#     """Resolve simple dot paths, with [] used to expand lists."""
#     current_values = [data]
#
#     for part in path.split("."):
#         next_values = []
#         expands_list = part.endswith("[]")
#         key = part[:-2] if expands_list else part
#
#         for value in current_values:
#             if not isinstance(value, dict) or key not in value:
#                 continue
#
#             selected_value = value[key]
#
#             if expands_list:
#                 if isinstance(selected_value, list):
#                     next_values.extend(selected_value)
#                 elif selected_value is not None:
#                     next_values.append(selected_value)
#             else:
#                 next_values.append(selected_value)
#
#         current_values = next_values
#
#     return current_values
#
#
# def assert_field_contains_all(assertion, evidence, context):
#     required_values = assertion["values"]
#     actual_values = resolve_path(evidence, assertion["path"])
#     missing_values = sorted(set(required_values) - set(actual_values))
#
#     return {
#         "type": assertion["type"],
#         "status": "pass" if not missing_values else "fail",
#         "reason": f"Required values were checked at path '{assertion['path']}'.",
#         "details": {
#             "path": assertion["path"],
#             "required_values": required_values,
#             "actual_values": sorted(set(actual_values)),
#             "missing_values": missing_values,
#         },
#     }


def assert_result_field_contains_all(assertion, evidence, context):
    field = assertion["field"]
    required_values = assertion["values"]
    actual_values = [row[field] for row in evidence.get("rows", [])]
    missing_values = sorted(set(required_values) - set(actual_values))

    return {
        "type": assertion["type"],
        "status": "pass" if not missing_values else "fail",
        "reason": f"Required values were checked in result field '{field}'.",
        "details": {
            "field": field,
            "required_values": required_values,
            "actual_values": sorted(set(actual_values)),
            "missing_values": missing_values,
        },
    }


# def assert_value_in(assertion, evidence, context):
#     accepted_values = assertion["values"]
#     actual_values = resolve_path(evidence, assertion["path"])
#     matching_values = [value for value in actual_values if value in accepted_values]
#
#     return {
#         "type": assertion["type"],
#         "status": "pass" if matching_values else "fail",
#         "reason": f"Values were checked at path '{assertion['path']}'.",
#         "details": {
#             "path": assertion["path"],
#             "accepted_values": accepted_values,
#             "actual_values": actual_values,
#             "matching_values": matching_values,
#         },
#     }


def assert_manual_status_in(assertion, evidence, context):
    accepted_values = assertion["values"]
    actual_value = evidence["verification_status"]

    return {
        "type": assertion["type"],
        "status": "pass" if actual_value in accepted_values else "fail",
        "reason": f"Manual evidence verification status was '{actual_value}'.",
        "details": {
            "accepted_values": accepted_values,
            "actual_value": actual_value,
        },
    }


def assert_result_numeric_field_sum_gte(assertion, evidence, context):
    field = assertion["field"]
    minimum = assertion["value"]
    rows = evidence.get("rows", [])
    values = []

    for row in rows:
        value = row.get(field, 0)
        if value is None:
            value = 0
        values.append(float(value))

    actual_sum = sum(values)

    return {
        "type": assertion["type"],
        "status": "pass" if actual_sum >= minimum else "fail",
        "reason": f"Numeric result field '{field}' was summed and compared with minimum {minimum}.",
        "details": {
            "field": field,
            "minimum": minimum,
            "actual_sum": actual_sum,
            "actual_values": values,
        },
    }


# def assert_minimum_count(assertion, evidence, context):
#     values = resolve_path(evidence, assertion["path"])
#     minimum = assertion["value"]
#
#     if len(values) == 1 and isinstance(values[0], list):
#         actual_count = len(values[0])
#     else:
#         actual_count = len(values)
#
#     return {
#         "type": assertion["type"],
#         "status": "pass" if actual_count >= minimum else "fail",
#         "reason": f"Minimum count was checked at path '{assertion['path']}'.",
#         "details": {
#             "path": assertion["path"],
#             "minimum": minimum,
#             "actual_count": actual_count,
#         },
#     }


def assert_result_minimum_rows(assertion, evidence, context):
    minimum = assertion["count"]
    actual_count = len(evidence.get("rows", []))

    return {
        "type": assertion["type"],
        "status": "pass" if actual_count >= minimum else "fail",
        "reason": f"Expected at least {minimum} result rows.",
        "details": {
            "minimum": minimum,
            "actual_count": actual_count,
        },
    }


ASSERTIONS = {
    "result_field_contains_all": assert_result_field_contains_all,
    "result_minimum_rows": assert_result_minimum_rows,
    "result_numeric_field_sum_gte": assert_result_numeric_field_sum_gte,
    "manual_status_in": assert_manual_status_in,
    # "field_contains_all": assert_field_contains_all,
    # "value_in": assert_value_in,
    # "minimum_count": assert_minimum_count,
}


def evaluate_definition(definition, evidence, context):
    print("Evaluating definition...")
    evaluation_config = definition["evaluation"]
    mode = evaluation_config.get("mode", "all")
    assertions = evaluation_config.get("assertions", [])
    assertion_results = []

    if not assertions:
        raise ValueError(f"Definition '{definition['id']}' must include at least one assertion.")

    for assertion in assertions:
        assertion_type = assertion["type"]
        assertion_fn = ASSERTIONS.get(assertion_type)
        if assertion_fn is None:
            raise ValueError(f"Unsupported assertion type: {assertion_type}")

        assertion_results.append(assertion_fn(assertion, evidence, context))

    if mode == "all":
        passed = all(result["status"] == "pass" for result in assertion_results)
    elif mode == "any":
        passed = any(result["status"] == "pass" for result in assertion_results)
    else:
        raise ValueError(f"Unsupported evaluation mode: {mode}")

    status = "pass" if passed else "fail"
    evaluation = {
        "status": status,
        "mode": mode,
        "assertions": assertion_results,
    }

    return create_finding(definition, evidence, evaluation, context)


def create_finding(definition, evidence, evaluation, context):
    return {
        "run": {
            "run_id": context["run_id"],
            "started_at": context["started_at"],
        },
        "definition": {
            "id": definition["id"],
            "control_id": definition["control_id"],
            "applies_to_ism_version": definition["applies_to_ism_version"],
            "type": definition["type"],
            "claim": definition["claim"],
            "source": definition["source"],
            "evaluation": definition["evaluation"],
        },
        "evidence": {
            "raw": evidence,
        },
        "evaluation": evaluation,
    }


def create_error_finding(definition, error, context):
    return {
        "run": {
            "run_id": context["run_id"],
            "started_at": context["started_at"],
        },
        "definition": {
            "id": definition.get("id"),
            "control_id": definition.get("control_id"),
            "applies_to_ism_version": definition.get("applies_to_ism_version"),
            "type": definition.get("type"),
            "claim": definition.get("claim"),
            "source": definition.get("source"),
            "evaluation": definition.get("evaluation"),
        },
        "evidence": {
            "raw": None,
        },
        "evaluation": {
            "status": "error",
            "mode": definition.get("evaluation", {}).get("mode"),
            "assertions": [],
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        },
    }


def load_assessment_manifests(path="data/assessments"):
    manifests = []
    assessment_ids = set()

    for manifest_path in sorted(Path(path).glob("*.yaml")):
        data = yaml_loader(manifest_path)
        assessment = data["assessment"]
        assessment_id = assessment["id"]

        if assessment_id in assessment_ids:
            raise ValueError(f"Duplicate assessment id found: {assessment_id}")

        assessment_ids.add(assessment_id)
        assessment["_manifest_file"] = str(manifest_path)
        manifests.append(assessment)

    return manifests


def load_assessment_rows(assessment):
    source = assessment["source"]

    if source["format"] != "csv":
        raise ValueError(f"Unsupported assessment source format: {source['format']}")

    source_file = Path(source["file"])
    control_id_column = source["control_id_column"]
    rating_column = source["rating_column"]
    rows = []

    with open(source_file, newline="") as f:
        reader = csv.DictReader(f)
        missing_columns = {control_id_column, rating_column} - set(reader.fieldnames or [])

        if missing_columns:
            raise ValueError(
                f"Assessment '{assessment['id']}' source is missing columns: {sorted(missing_columns)}"
            )

        for row in reader:
            rows.append({
                "assessment_id": assessment["id"],
                "assessment_type": assessment["type"],
                "system_id": assessment["system_id"],
                "system_name": assessment["system_name"],
                "ism_version": assessment["ism_version"],
                "assessment_date": assessment["assessment_date"],
                "control_id": str(row[control_id_column]).strip().upper(),
                "rating": str(row[rating_column]).strip().lower(),
                "source_file": str(source_file),
                "source_row": row,
            })

    return rows


def create_assessment_finding(assessment_row, context):
    rating = assessment_row["rating"]
    status = ASSESSMENT_RATING_STATUS.get(rating, "needs_review")
    control_id = assessment_row["control_id"]
    assessment_id = assessment_row["assessment_id"]

    return {
        "run": {
            "run_id": context["run_id"],
            "started_at": context["started_at"],
        },
        "definition": {
            "id": f"ASSESSMENT-{assessment_id}-{control_id}",
            "control_id": control_id,
            "applies_to_ism_version": assessment_row["ism_version"],
            "type": "assessment",
            "claim": f"{assessment_row['assessment_type'].upper()} assessment rating for {control_id}.",
            "source": {
                "assessment_id": assessment_id,
                "source_file": assessment_row["source_file"],
            },
            "evaluation": {
                "mode": "assessment_rating",
                "assertions": [
                    {
                        "type": "assessment_rating",
                        "rating": rating,
                    }
                ],
            },
        },
        "evidence": {
            "raw": assessment_row,
        },
        "evaluation": {
            "status": status,
            "mode": "assessment_rating",
            "assertions": [
                {
                    "type": "assessment_rating",
                    "status": status,
                    "reason": f"Assessment rating was '{rating}'.",
                    "details": {
                        "rating": rating,
                        "system_id": assessment_row["system_id"],
                        "system_name": assessment_row["system_name"],
                        "assessment_id": assessment_id,
                        "assessment_type": assessment_row["assessment_type"],
                        "assessment_date": assessment_row["assessment_date"],
                    },
                }
            ],
        },
    }


def create_assessment_findings(context):
    findings = []

    for assessment in load_assessment_manifests():
        print(f"Loading assessment: {assessment['id']}")

        for assessment_row in load_assessment_rows(assessment):
            findings.append(create_assessment_finding(assessment_row, context))

    return findings


def create_summary_row(finding):
    evaluation = finding["evaluation"]
    definition = finding["definition"]
    assertion_results = evaluation.get("assertions", [])
    source = definition.get("source") or {}
    raw_evidence = finding.get("evidence", {}).get("raw")
    evidence_rows = raw_evidence.get("rows", []) if isinstance(raw_evidence, dict) else []
    assessment_evidence = raw_evidence if definition["type"] == "assessment" else {}

    return {
        "run_id": finding["run"]["run_id"],
        "started_at": finding["run"]["started_at"],
        "definition_id": definition["id"],
        "control_id": definition["control_id"],
        "ism_version": definition["applies_to_ism_version"],
        "type": definition["type"],
        "status": evaluation["status"],
        "claim": definition["claim"],
        "source_workspace": source.get("workspace"),
        "source_query_file": source.get("query_file"),
        "manual_evidence_id": source.get("evidence_register_id"),
        "assessment_id": assessment_evidence.get("assessment_id"),
        "assessment_type": assessment_evidence.get("assessment_type"),
        "system_id": assessment_evidence.get("system_id"),
        "system_name": assessment_evidence.get("system_name"),
        "assessment_date": assessment_evidence.get("assessment_date"),
        "assessment_rating": assessment_evidence.get("rating"),
        "assertion_count": len(assertion_results),
        "passed_assertions": sum(result.get("status") == "pass" for result in assertion_results),
        "failed_assertions": sum(result.get("status") == "fail" for result in assertion_results),
        "evidence_row_count": len(evidence_rows),
        "error_type": evaluation.get("error", {}).get("type"),
        "error_message": evaluation.get("error", {}).get("message"),
    }


COLLECTORS = {
    "kql": collect_kql,
    "manual_reference": collect_manual_reference,
    "azure_policy": collect_azure_policy,
}

evidence_definitions = yaml_loader("config/evidence_definitions.yaml")
findings = []

for definition in evidence_definitions["evidence_definitions"]:
    try:
        collector = COLLECTORS[definition['type']]
        evidence = collector(definition, CONTEXT)

        finding = evaluate_definition(definition, evidence, CONTEXT)
        findings.append(finding)
        print(finding)


    except Exception as e:
        print(f"ERROR {definition.get('id', 'unknown')}: {type(e).__name__}: {e}")
        findings.append(create_error_finding(definition, e, CONTEXT))

try:
    findings.extend(create_assessment_findings(CONTEXT))

except Exception as e:
    print(f"ERROR assessments: {type(e).__name__}: {e}")
    findings.append(create_error_finding({
        "id": "ASSESSMENTS",
        "control_id": None,
        "applies_to_ism_version": None,
        "type": "assessment",
        "claim": "Assessment ingestion.",
        "source": {
            "path": "data/assessments",
        },
        "evaluation": {
            "mode": "assessment_ingestion",
        },
    }, e, CONTEXT))

summary = [create_summary_row(finding) for finding in findings]
run_output_dir = Path("output") / "runs" / CONTEXT["run_id"]

write_json(run_output_dir / "findings.json", findings)
write_json(run_output_dir / "summary.json", summary)

print(f"Wrote findings to {run_output_dir / 'findings.json'}")
print(f"Wrote summary to {run_output_dir / 'summary.json'}")
