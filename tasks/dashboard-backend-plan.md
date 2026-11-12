# Backend for dashboard

Approved scope: backend first; projects with latest scan, run history, paginated
findings filtered by severity/exact rule/exact file, finding detail, JSON download,
project creation and run deletion. Existing CLI auth/upload remains compatible.

- [x] Normalize native Trivy findings and test suppression/location/large reports.
- [x] Store derived findings, expose paginated APIs and isolated retry state.
- [x] Wire completion, asynchronous processing and deletion/orphan cleanup safely.
- [x] Add project latest-scan summaries and separate dashboard Cognito config.
- [x] Provision tagged storage, stream worker and browser CORS.
- [x] Export OpenAPI, add migration/backfill tooling and update documentation/CI.
- [x] Run regression/build/security checks and review the change.
- [x] Deploy to the existing AWS dev stack, smoke test and refresh inventory.

Defaults: single user ownership, JSON only, no full-text search or scan comparison.
Derived data is versioned by run generation and processing attempt. Background
failures preserve the original downloadable report. No frontend in this change.

User refinement: internal tool uses metadata, CloudWatch logs and manual
retry/backfill for failures; remove the separate SQS failure queue.
