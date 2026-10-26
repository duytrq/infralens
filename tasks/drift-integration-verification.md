# Drift integration verification

## Engine port

- Source snapshot: origin/drift_develop 4213a2d.
- CLI pytest: 564 passed, 2 platform skips, 16 external-tool tests deselected.
- Engine tests demonstrated missing module before port, then passed after port.
- FastAPI/SQLite tests are not runtime dependencies of the integrated CLI.
  Their persistence/comparison scenarios belong to the AWS backend integration suite.

Remaining slices and final verification are tracked in todo.md.

## Storage and upload

- Backend full suite before the backfill guard: 150 passed. Focused regression
  coverage includes owner isolation, report validation, comparison, cursor scopes,
  trace errors, deletion, and the security backfill boundary.
- CLI full suite with cloud upload: 576 passed, 2 platform skips, 16 opt-in tests
  deselected. PKCE tested with a real loopback callback, invalid then valid state;
  transport tests confirm S3 receives no Cognito access token and PUT 412 completes.
- Cloud manifests bind report bytes/checksum, API origin, run UUID and metadata.
- cfn-lint accepted the extended SAM routes; OpenAPI matches runtime schemas.
