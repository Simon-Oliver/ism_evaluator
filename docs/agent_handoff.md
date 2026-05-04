# ISM MVP Agent Handoff

This document is for a future LLM agent or developer continuing work on this repository without access to the previous chat context.

## Project Purpose

This repository is an early MVP for an ASD ISM evidence runner. The intended product is a Python program that evaluates whether selected ISM control intents have supporting evidence in an Azure environment.

The current design keeps control evidence checks in readable YAML, while Python handles evidence collection, assertion evaluation, and finding creation.

Current pipeline:

```text
evidence definition -> collector -> assertion evaluator -> finding
```

## Current Repository State

Important files:

- `runner.py`: prototype runner, collector registry, assertion functions, finding creation.
- `README.md`: current project explanation and usage model.
- `config/evidence_definitions.yaml`: active evidence definitions consumed by `runner.py`.
- `config/manual_evidence_register.yaml`: manually supplied evidence records.
- `data/test_data/test_data.json`: local test fixture data for KQL and Azure Policy style collectors.
- `docs/proposed_ism_kql_evidence_definitions.yaml`: review-only generated YAML containing proposed KQL evidence definitions from the vault research note.
- `queries/ism_kql_intent_coverage/`: generated KQL files referenced by the proposed definitions.

Expected placeholder directories from the README:

- `queries/`: intended future location for `.kql` files.
- `output/`: intended future location for generated findings and reports.
- `data/oscal/`: intended future location for OSCAL/catalog data.

These placeholder directories may not exist in the current checkout if they are empty and not tracked.

## Current Runner Behavior

`runner.py` currently:

1. Loads `data/test_data/test_data.json`.
2. Loads `config/manual_evidence_register.yaml`.
3. Creates a run context with `run_id`, `started_at`, and manual evidence keyed by ID.
4. Loads `config/evidence_definitions.yaml`.
5. For each evidence definition, dispatches to a collector based on `definition["type"]`.
6. Evaluates configured assertions.
7. Prints the resulting finding dictionary to stdout.
8. Loads assessment manifests from `data/assessments/*.yaml`.
9. Creates one assessment finding per source assessment row.
10. Writes full findings and dashboard summary JSON under `output/runs/<run_id>/`.

Current collectors:

- `kql`: for now, reads fixture data from `data/test_data/test_data.json` when `source.workspace` is `test_data`.
- `manual_reference`: looks up an entry in `config/manual_evidence_register.yaml`.
- `azure_policy`: placeholder only.

Assessment ingestion is separate from the collector registry. Assessment manifests are not added to `config/evidence_definitions.yaml`; instead, each source row becomes an assessment finding with `type: assessment`.

Current enabled assertion types:

- `result_field_contains_all`
- `result_minimum_rows`
- `result_numeric_field_sum_gte`
- `manual_status_in`

Path-based assertion support is currently commented out in `runner.py`:

- `field_contains_all`
- `value_in`
- `minimum_count`

Those disabled assertions depended on the commented-out `resolve_path` helper.

The evaluator supports:

- `mode: all`
- `mode: any`

## Evidence Definition Format

The active YAML shape is:

```yaml
evidence_definitions:
  - id: CHECK-ISM-1683-KQL-MFA-LOGGING
    control_id: ISM-1683
    applies_to_ism_version: "2025-02"
    type: kql
    system_id: test-system-abc
    system_name: Test System ABC
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

Collectors receive the full evidence definition dictionary and the run context. Assertions receive the assertion dictionary, raw evidence, and context.

## Review-Only KQL Proposal File

`docs/proposed_ism_kql_evidence_definitions.yaml` was generated from this vault note:

```text
codex_vault/wiki/projects/ISM MVP/Research - ISM KQL Intent Coverage.md
```

The generated review file now uses the same top-level schema as `config/evidence_definitions.yaml`:

```yaml
evidence_definitions:
  - id: ...
    control_id: ...
    applies_to_ism_version: ...
    type: kql
    system_id: ...
    system_name: ...
    claim: ...
    source:
      workspace: ...
      query_file: ...
    evaluation:
      mode: all
      assertions:
        - type: result_numeric_field_sum_gte
          field: Events
          value: 1
```

It contains 179 proposed `evidence_definitions`. Review-only metadata and inline KQL query text are not stored in that file anymore, because the intent is for it to be easy to copy entries into the active config. Most proposed KQL assertions now use `result_numeric_field_sum_gte` against the specific summarized column produced by the query, such as `Events`, `Findings`, `MFARequired`, `Success`, or `Failure`.

Important: this file is intentionally separate from `config/evidence_definitions.yaml`. It is not currently consumed by the runner.

The generated definitions use this placeholder source workspace:

```yaml
workspace: REPLACE_WITH_LOG_ANALYTICS_WORKSPACE_ID
```

Many definitions use a review-default minimum evidence threshold:

```yaml
evaluation:
  mode: all
  assertions:
    - type: result_numeric_field_sum_gte
      field: Events
      value: 1
```

That assertion means "the query returned the expected evidence signal at least once." It does not prove compliance. A human needs to review each query and decide whether row presence, row absence, field values, counts, or thresholds are the correct evaluation semantics.

## Likely Next Steps

Good next tasks:

1. Pick a small subset of proposed KQL definitions, review them manually, and promote only those into `config/evidence_definitions.yaml`.
2. Replace `REPLACE_WITH_LOG_ANALYTICS_WORKSPACE_ID` with the target workspace identifier or local fixture workspace.
3. Tune the review-default assertion thresholds for the selected environment.
4. Extend `collect_kql` so it can either:
   - continue using `test_data` fixtures, or
   - execute against Azure Log Analytics using a real workspace ID.
5. Review whether any promoted query needs absence-based, threshold-based, or manual-review assertions instead of the current evidence-signal assertions.
6. Add schema validation for evidence definitions, probably using Pydantic once the YAML shape settles.
7. Write findings to files under `output/` instead of only printing dictionaries.
8. Add tests around collectors, enabled assertion functions, and finding creation.

## Known Design Decisions

- Keep control/evidence definitions in YAML for readability.
- Keep collectors responsible only for retrieving raw evidence.
- Keep pass/fail logic in assertion functions, not collectors.
- Prefer domain-specific assertions for common checks, with generic path-based assertions as an escape hatch.
- Treat KQL evidence as intent coverage, not automatic compliance, unless the assertion semantics have been reviewed.

## Known Limitations And Risks

- `azure_policy` collection is currently a placeholder.
- The KQL collector only supports local fixture data when `workspace` is `test_data`.
- Assessment source ingestion currently supports CSV only.
- There is no active packaging file such as `pyproject.toml` or `requirements.txt` in the current repo.
- There are no tests yet.
- Findings are persisted under `output/runs/<run_id>/`, but the output format is still early and should be treated as an MVP contract.
- `resolve_path` and the path-based assertions are currently commented out. If re-enabled, remember that the helper is intentionally simple: dot paths plus `[]` list expansion only.
- Current assertion functions assume certain evidence shapes and may raise `KeyError` if YAML or evidence is malformed.
- Proposed KQL definitions in `docs/proposed_ism_kql_evidence_definitions.yaml` need human review before use.
- Check `runner.py` before running: the working tree currently shows it as modified, and the current `run_id` f-string should be verified for valid quoting before execution.

## How To Continue Safely

Recommended approach for the next agent:

1. Run `git status --short` first and do not overwrite user changes.
2. Read `README.md`, `runner.py`, and this handoff file.
3. Treat `docs/proposed_ism_kql_evidence_definitions.yaml` as review material, not production config.
4. Make small, reviewable changes.
5. If changing runner behavior, add or preserve fixture-based behavior so the project can still run locally without Azure access.
6. Do not bulk-promote all proposed KQL definitions into the active config without human review.
