# ISM MVP Evidence Runner

This project is an early prototype for running definition-driven evidence checks against ISM controls. The current goal is to keep control evidence checks in readable YAML while keeping collection and evaluation mechanics in Python.

At a high level, the pipeline is:

```text
evidence definition -> collector -> assertion evaluator -> finding
```

The current implementation lives mostly in `runner.py`.

## Repository Layout

```text
config/
  evidence_definitions.yaml       Evidence checks to run
  manual_evidence_register.yaml   Manually supplied evidence records

data/
  test_data/test_data.json        Local fixture data for collectors
  assessments/                    Assessment fixtures and source files
  oscal/                          Placeholder for OSCAL data

queries/                          Placeholder for KQL query files
output/                           Placeholder for generated findings/reports

runner.py                         Prototype runner, collectors, assertions, finding creation
```

## Current Design

Each evidence definition declares:

- which ISM control it supports
- what evidence source should be collected
- what claim the evidence is intended to support
- how the collected evidence should be evaluated

The runner then:

1. Loads test data and manual evidence into a run context.
2. Loads `config/evidence_definitions.yaml`.
3. Selects a collector based on the definition `type`.
4. Runs the collector to retrieve raw evidence.
5. Runs the generic evaluator against the definition's assertions.
6. Packages the result into a structured finding.
7. Loads assessment manifests from `data/assessments/*.yaml`.
8. Turns each assessment source row into an assessment finding.

## Evidence Definitions

Evidence definitions are stored in `config/evidence_definitions.yaml`.

Example KQL-style evidence definition:

```yaml
evidence_definitions:
  - id: CHECK-ISM-1683-KQL-MFA-LOGGING
    control_id: ISM-1683
    applies_to_ism_version: "2025-02"
    type: kql
    claim: MFA success and failure events are present in centralised sign-in logs.
    source:
      workspace: test_data
      query_file: queries/ism_1683_mfa_logging.kql
    evaluation:
      mode: all
      assertions:
        - type: result_field_contains_all
          field: Outcome
          values:
            - Success
            - Failure
        - type: result_minimum_rows
          count: 2
```

Example manual evidence definition:

```yaml
evidence_definitions:
  - id: CHECK-ISM-1683-MANUAL-TEST-SOP
    control_id: ISM-1683
    applies_to_ism_version: "2025-02"
    type: manual_reference
    claim: A documented process.
    source:
      evidence_register_id: MAN-TEST-SOP
    evaluation:
      mode: all
      assertions:
        - type: manual_status_in
          values:
            - human_reviewed
            - verified
```

## Manual Evidence Register

Manual evidence is stored separately in `config/manual_evidence_register.yaml`.

Example:

```yaml
manual_evidence:
  - id: MAN-TEST-SOP
    title: Test SOP
    location: test_sop.docx
    owner: Security Team
    verification_status: human_reviewed
    last_reviewed: "2026-04-20"
    reviewed_by: analyst.name
    coverage: Test process
```

Evidence definitions reference these records by `source.evidence_register_id`.

## Assessments

Assessments are handled as a separate first-class input rather than as one evidence definition per control. Each YAML file in `data/assessments/` is treated as an assessment manifest. The manifest points to a source file, currently CSV.

Example:

```yaml
assessment:
  id: test-assessment-2026
  type: irap
  system_id: test-system-abc
  system_name: Test System ABC
  ism_version: "2025-12"
  assessment_date: "2026-02-10"
  source:
    file: data/assessments/ssp_annex_test_assessment.csv
    format: csv
    control_id_column: ism_control
    rating_column: rating
```

Each CSV row becomes an assessment finding. Ratings are currently mapped as:

| Rating | Finding status |
| --- | --- |
| `effective` | `pass` |
| `alternate control` | `pass` |
| `ineffective` | `fail` |
| `not implemented` | `fail` |
| `not applicable` | `not_applicable` |

Unknown ratings become `needs_review`.

## Collectors

Collectors are responsible for retrieving raw evidence. The current collector registry is:

```python
COLLECTORS = {
    "kql": collect_kql,
    "manual_reference": collect_manual_reference,
    "azure_policy": collect_azure_policy,
}
```

Current collector behavior:

- `kql`: reads local fixture data from `data/test_data/test_data.json` when `workspace` is `test_data`.
- `manual_reference`: looks up an item from `manual_evidence_register.yaml`.
- `azure_policy`: placeholder only.

The collector returns raw evidence. It does not decide whether the evidence passes or fails.

## Evaluation Model

The project uses a small assertion language rather than one evaluator function per control check. This keeps the YAML extensible without needing a new full evaluator for every variation.

Each definition has:

```yaml
evaluation:
  mode: all
  assertions:
    - type: some_assertion_type
```

Supported modes:

- `all`: all assertions must pass.
- `any`: at least one assertion must pass.

Current assertion types:

| Assertion type | Intended use | Example |
| --- | --- | --- |
| `result_field_contains_all` | Check a field across result rows contains required values | `field: Outcome`, `values: [Success, Failure]` |
| `result_minimum_rows` | Check a result has at least a minimum number of rows | `count: 2` |
| `result_numeric_field_sum_gte` | Sum a numeric field across result rows and check it meets a minimum | `field: Events`, `value: 1` |
| `manual_status_in` | Check manual evidence has an accepted verification status | `values: [human_reviewed, verified]` |
| `field_contains_all` | Currently disabled path-based check | `path: rows[].Outcome` |
| `value_in` | Currently disabled path-based accepted-value check | `path: verification_status` |
| `minimum_count` | Currently disabled path-based count check | `path: rows`, `value: 2` |

The path-based assertions above are currently commented out in `runner.py`.

The design decision here is to prefer readable, domain-specific assertions for common cases, while keeping generic path-based assertions as an escape hatch for more complex evidence shapes.

## Path-Based Assertions

Path-based assertions are currently disabled in `runner.py`. The commented-out `resolve_path()` helper supported simple dot paths and list expansion using `[]`.

Example:

```yaml
path: rows[].Outcome
```

Given evidence like:

```json
{
  "rows": [
    {"Outcome": "Success"},
    {"Outcome": "Failure"}
  ]
}
```

the path returns:

```json
["Success", "Failure"]
```

This is intentionally limited. It does not support filters, comparisons, or indexes. If the project needs complex querying later, a library such as JMESPath would be a better option than growing a custom query language.

## Finding Output

The evaluator creates a structured finding. A simplified example:

```python
{
    "run": {
        "run_id": "run-20260501-105550",
        "started_at": datetime(...)
    },
    "definition": {
        "id": "CHECK-ISM-1683-KQL-MFA-LOGGING",
        "control_id": "ISM-1683",
        "applies_to_ism_version": "2025-02",
        "type": "kql",
        "claim": "MFA success and failure events are present in centralised sign-in logs.",
        "source": {
            "workspace": "test_data",
            "query_file": "queries/ism_1683_mfa_logging.kql"
        },
        "evaluation": {
            "mode": "all",
            "assertions": [
                {
                    "type": "result_field_contains_all",
                    "field": "Outcome",
                    "values": ["Success", "Failure"]
                }
            ]
        }
    },
    "evidence": {
        "raw": {
            "query_name": "mfa_authentication_events",
            "rows": [...]
        }
    },
    "evaluation": {
        "status": "pass",
        "mode": "all",
        "assertions": [
            {
                "type": "result_field_contains_all",
                "status": "pass",
                "reason": "Required values were checked in result field 'Outcome'.",
                "details": {
                    "field": "Outcome",
                    "required_values": ["Success", "Failure"],
                    "actual_values": ["Failure", "Success"],
                    "missing_values": []
                }
            }
        ]
    }
}
```

The current runner prints findings to stdout and writes dashboard-friendly JSON output for each run.

Output is written to:

```text
output/runs/<run_id>/findings.json
output/runs/<run_id>/summary.json
```

- `findings.json` contains the full finding records, including raw evidence and assertion details.
- `summary.json` contains one flat row per evidence definition, including `run_id`, `control_id`, `definition_id`, `status`, assertion counts, source fields, evidence row count, and error fields.

If collection or evaluation fails for a definition, the runner prints the error during the run and saves an error finding with `status: error`, `error_type`, and `error_message`.

## Extending the Pipeline

### Add a New Evidence Definition

Add a new entry to `config/evidence_definitions.yaml` with:

- a unique `id`
- a `control_id`
- a source `type`
- source configuration
- one or more assertions

### Add a New Collector

1. Implement a collector function:

```python
def collect_new_source(definition, context):
    source = definition["source"]
    return collected_evidence
```

2. Register it:

```python
COLLECTORS = {
    "new_source": collect_new_source,
}
```

3. Use it in YAML:

```yaml
type: new_source
source:
  ...
```

### Add a New Assertion

1. Implement an assertion function:

```python
def assert_some_condition(assertion, evidence, context):
    return {
        "type": assertion["type"],
        "status": "pass",
        "reason": "Human-readable explanation.",
        "details": {}
    }
```

2. Register it:

```python
ASSERTIONS = {
    "some_condition": assert_some_condition,
}
```

3. Use it in YAML:

```yaml
evaluation:
  mode: all
  assertions:
    - type: some_condition
      ...
```

## Current Limitations

This is still a prototype. Known limitations:

- No schema validation for YAML definitions yet.
- Findings are printed rather than written to structured output files.
- Raw evidence is embedded directly in findings.
- Result statuses are currently `pass` and `fail` only.
- `azure_policy` is a placeholder collector.
- There are no tests yet for assertions or path resolution.
- The runner is a single script and should be split into modules as behavior grows.

## Recommended Next Steps

The next useful hardening steps are:

1. Add schema validation for `evidence_definitions.yaml`.
2. Add unit tests for each enabled assertion function.
3. Write findings as JSON into `output/`.
4. Add result statuses such as `error`, `not_collected`, `inconclusive`, and `not_applicable`.
5. Normalize collector outputs into a common evidence envelope.
6. Add real collectors for KQL and Azure Policy.
