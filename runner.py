import yaml
import json
from datetime import datetime, timezone


def yaml_loader(path):
    with open(path, "r") as stream:
        return yaml.safe_load(stream)


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


def resolve_path(data, path):
    """Resolve simple dot paths, with [] used to expand lists."""
    current_values = [data]

    for part in path.split("."):
        next_values = []
        expands_list = part.endswith("[]")
        key = part[:-2] if expands_list else part

        for value in current_values:
            if not isinstance(value, dict) or key not in value:
                continue

            selected_value = value[key]

            if expands_list:
                if isinstance(selected_value, list):
                    next_values.extend(selected_value)
                elif selected_value is not None:
                    next_values.append(selected_value)
            else:
                next_values.append(selected_value)

        current_values = next_values

    return current_values


def assert_field_contains_all(assertion, evidence, context):
    required_values = assertion["values"]
    actual_values = resolve_path(evidence, assertion["path"])
    missing_values = sorted(set(required_values) - set(actual_values))

    return {
        "type": assertion["type"],
        "status": "pass" if not missing_values else "fail",
        "reason": f"Required values were checked at path '{assertion['path']}'.",
        "details": {
            "path": assertion["path"],
            "required_values": required_values,
            "actual_values": sorted(set(actual_values)),
            "missing_values": missing_values,
        },
    }


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


def assert_value_in(assertion, evidence, context):
    accepted_values = assertion["values"]
    actual_values = resolve_path(evidence, assertion["path"])
    matching_values = [value for value in actual_values if value in accepted_values]

    return {
        "type": assertion["type"],
        "status": "pass" if matching_values else "fail",
        "reason": f"Values were checked at path '{assertion['path']}'.",
        "details": {
            "path": assertion["path"],
            "accepted_values": accepted_values,
            "actual_values": actual_values,
            "matching_values": matching_values,
        },
    }


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


def assert_minimum_count(assertion, evidence, context):
    values = resolve_path(evidence, assertion["path"])
    minimum = assertion["value"]

    if len(values) == 1 and isinstance(values[0], list):
        actual_count = len(values[0])
    else:
        actual_count = len(values)

    return {
        "type": assertion["type"],
        "status": "pass" if actual_count >= minimum else "fail",
        "reason": f"Minimum count was checked at path '{assertion['path']}'.",
        "details": {
            "path": assertion["path"],
            "minimum": minimum,
            "actual_count": actual_count,
        },
    }


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
    "manual_status_in": assert_manual_status_in,
    "field_contains_all": assert_field_contains_all,
    "value_in": assert_value_in,
    "minimum_count": assert_minimum_count,
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


COLLECTORS = {
    "kql": collect_kql,
    "manual_reference": collect_manual_reference,
    "azure_policy": collect_azure_policy,
}

evidence_definitions = yaml_loader("config/evidence_definitions.yaml")

for definition in evidence_definitions["evidence_definitions"]:
    try:
        collector = COLLECTORS[definition['type']]
        evidence = collector(definition, CONTEXT)

        print(evaluate_definition(definition, evidence, CONTEXT))


    except Exception as e:
        print(e)
