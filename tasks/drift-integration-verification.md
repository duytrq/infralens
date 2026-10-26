# Drift integration verification

## Engine port

- Source snapshot: origin/drift_develop 4213a2d.
- CLI pytest: 564 passed, 2 platform skips, 16 external-tool tests deselected.
- Engine tests demonstrated missing module before port, then passed after port.
- FastAPI/SQLite tests are not runtime dependencies of the integrated CLI.
  Their persistence/comparison scenarios belong to the AWS backend integration suite.

The implementation checklist is complete in todo.md. External rollout checks are
explicitly separated below.

## Storage and upload

- Backend full suite before the backfill guard: 150 passed. Focused regression
  coverage includes owner isolation, report validation, comparison, cursor scopes,
  trace errors, deletion, and the security backfill boundary.
- CLI full suite with cloud upload: 576 passed, 2 platform skips, 16 opt-in tests
  deselected. PKCE tested with a real loopback callback, invalid then valid state;
  transport tests confirm S3 receives no Cognito access token and PUT 412 completes.
- Cloud manifests bind report bytes/checksum, API origin, run UUID and metadata.
- cfn-lint accepted the extended SAM routes; OpenAPI matches runtime schemas.

## Final integration checks (Linux/WSL, 2026-10-26)

| Requirement | Evidence |
| --- | --- |
| CLI drift/trace/review/gate and scanner regressions | Full pytest: 580 passed, 2 platform skips, 16 external-tool tests deselected |
| Real Terraform behavior and source locations | Terraform 1.15.7: 4 integration tests passed with --run-terraform --run-network; only isolated local resources |
| API ownership, upload lifecycle, history and comparison | Backend full suite: 157 passed, including Moto S3/DynamoDB, runtime OpenAPI response validation and rule-context comparison uncertainty |
| Real security scanner regressions | Trivy 0.76.0: all 9 real integration tests passed with --run-integration --run-network |
| Real CLI/API contract compatibility | Three CLI-generated examples (basic, review, network) validate both actual reports and manifests against exported OpenAPI |
| PKCE and CI authentication | Real loopback callback rejects wrong state, accepts correct state; verifier/challenge checked; token absent from output/files |
| Retry and byte integrity | Retry never runs Terraform, binds UUID/origin/report bytes; simulated Windows CRLF regression passes; PUT 412 proceeds to complete |
| Test sensitivity | Inverted checksum comparison was caught by the transport test, then original code restored |
| Stable generated types | OpenAPI export verified under PYTHONHASHSEED=1 and 2; frontend types generated from the fixed contract |
| React reporting and failure states | 14 Vitest tests; 36 Playwright tests passed; updated drift gate fixture also passed its 9 focused browser tests |
| Accessibility and responsive UI | Axe and overflow checks at 320/768/1024/1440px; screenshots inspected; scrollable diff/network/comparison regions keyboard accessible |
| Deployment artifacts | SAM validate/build passed; dev/prod rendering verified all 16 routes/JWT scopes; Api/Cleanup/Analysis artifacts passed python -S runtime isolation checks |
| CLI distribution | Source/universal/Linux bundled wheel builds passed; installed Linux wheel verified outside checkout with empty PATH, real Trivy, imported drift, safe failed upload/manifest, plus 10 process/I/O tests |
| Dependency audit | npm audit: 0 vulnerabilities; CLI and backend runtime/development pip-audit: no known vulnerabilities |

Formatting/lint/type checking, OpenAPI export checks, frontend production build and
git diff whitespace checks passed. Review preserved separate engine, cloud storage
and UI boundaries; security history/latest_scan/backfill do not consume drift runs.

The real-scanner fixture originally placed its default cache inside its input
directory in some cases. The cache now lives alongside the input directory; the
assertion that source inputs remain unchanged is retained. A mutation probe left
timestamp-based Python bytecode cached after the source was restored; its generated
cache was cleared, then the focused transport test and the full 580-test CLI suite
passed again against the restored source.

## Limits of this verification

- No AWS deployment or live Cognito/S3/CloudTrail smoke was performed. The existing
  dev dashboard/API stay on their deployed release until an operator rolls out
  backend then frontend and performs the documented authenticated smoke.
- Backend service tests use Moto and trusted API Gateway claim fixtures. They do
  not prove live JWT authorizer, bucket-policy or presigned signature behavior.
- Windows newline behavior has a regression test; actual Windows runtime and
  Windows wheel execution require the existing Windows CI matrix. Docker was not
  rebuilt in this session; Terraform remains external to the scanner image.
- Generated local artifacts are not published. Changes are on feature/drift-integration.
