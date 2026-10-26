# Drift integration

Approved direction: reuse the drift engine from origin/drift_develop at 4213a2d,
keep the existing Lambda/API Gateway, Cognito, DynamoDB/S3 and React architecture.
Terraform and CloudTrail run on the CLI/CI host. No hosted execution or SQLite migration.

## Contract

- Security uploads remain compatible. Add a discriminated drift run manifest and
  normalized drift report schema 1.0, with a 2 MiB report limit.
- Reuse register, conditional presigned PUT, complete, download, deletion and cleanup.
- Report source locations become project-relative before upload. Never upload raw plans,
  state, tfvars, raw CloudTrail events, credentials or machine paths.
- CLI upload requires JSON output, project, scope and API URL. Persist immutable upload
  metadata next to the report for retry without running Terraform again.
- Browser PKCE login uses memory-only tokens. CI supplies INFRALENS_ACCESS_TOKEN.
- Comparison stays within owner/project/scope/input mode and preserves uncertain values.
- React provides history, resource diffs, source, network context, review/gate, trace,
  downloads and comparison. No run/cancel controls.

## Ordered slices

1. Port engine, adapters, process changes and corresponding regression tests.
2. Add drift ingestion/report/history contracts and API tests, preserving security.
3. Add CLI authentication, sanitized report/manifest and retryable upload.
4. Add complete React reporting, history filters and comparison.
5. Verify packaging, contracts, infra, browser flows and update operator/user docs.

Each slice must pass its focused tests. Final verification includes CLI/backend full
tests and lint, contract generation, frontend lint/types/unit/browser/build, SAM
template/build/artifact checks, and a requirement-by-requirement review. AWS live
checks require an authenticated test session and must be reported separately.

See tasks/todo.md for progress and drift-integration-verification.md for evidence.
