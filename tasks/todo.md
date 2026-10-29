# Security scan implementation

- [x] 1. Process runner and Trivy adapter, with focused tests.
- [x] 2. Recursive scan validation, handler, terminal report and fail-on.
- [x] 3. JSON/SARIF conversion and atomic exports.
- [x] 4. Failure paths, input protection, SIGINT/timeout cleanup.
- [x] 5. Docker image, manual mount instructions and runtime verification.
- [x] 6. README/help, full regression/lint/build, integration and final review.

Evidence and environment-specific verification commands: [verification.md](verification.md).

## Bundled Trivy (see bundle-plan.md)

- [x] 1. Reproduce and fix the four reviewed scanner defects.
- [x] 2. Pinned archives, verified staging, Hatch hook and platform wheel tests.
- [x] 3. Bundle resolver, fail-closed validation and development fallback.
- [x] 4. Windows Job Object runner and portable test fixtures.
- [x] 5. Linux and Windows installed-wheel verification, CI and Docker smoke.
- [x] 6. Documentation, measured sizes, final regression and review.

Bundle evidence and artifact hashes: [bundle-verification.md](bundle-verification.md).

## Frontend (see frontend-plan.md)

- [x] 1. Dashboard origins contract and dev-only localhost authentication; backend tests.
- [x] 2. React foundation, generated types, session/auth and API boundary tests.
- [x] 3. Projects, create project and history with cursor/filter browser tests.
- [x] 4. Scan/findings detail, polling, retry, download and delete; failure states.
- [x] 5. S3/CloudFront template, cache/rewrite/security checks and inventory support.
- [x] 6. Frontend CI, deploy/rollback tooling, docs and full verification/review.
- [x] 7. Deploy dev, real AWS/browser smoke, rollback and deployment inventory.

Published at https://ddsw2osqv2rj2.cloudfront.net. Real CloudFront/localhost browser
smoke, private S3/header/cache/deep-link checks, two-release rollback and restoration,
demo login and deployment inventory all passed. The prior AWS account block is
resolved; the failed stack and its verified empty retained bucket were removed.
See frontend-verification.md and infra/deployments/infralens-dev-frontend-verification.json.

## Drift integration (see drift-integration-plan.md)

- [x] 1. Port drift engine and retain scanner/process regressions.
- [x] 2. Backend drift contract, upload lifecycle, history and report API.
- [x] 3. CLI PKCE/CI token authentication, sanitized upload and manifest retry.
- [x] 4. Backend comparison and React history/report/comparison flows.
- [x] 5. Full verification, documentation, compatibility and final review.

## Security scan upload

- [x] 1. Add opt-in JSON scan upload with full findings, thresholds and metadata.
- [x] 2. Share resumable upload transport with Drift; validate type, bytes and limits.
- [x] 3. Cover scanner failures, gates, filters, native newline checksums and retries.
- [x] 4. Verify real Trivy, AWS/browser ingestion and installed wheel; update user guide.

Evidence: [security-upload-verification.md](security-upload-verification.md).

## Consistent CLI interface

- [x] Share common flag declarations, order, defaults and upload validation.
- [x] Add Drift `--fail-on` with legacy alias and distinct engine policy validation.
- [x] Verify contract/regressions, update guide and rebuild the CLI wheel.

Evidence: [cli-consistency-verification.md](cli-consistency-verification.md).

## Default AWS SDK

- [x] Move boto3 to runtime dependencies and retain the legacy extra as compatibility.
- [x] Verify normal installs and offline CloudTrail without SDK extras; update guide/wheel.

Evidence: [default-sdk-verification.md](default-sdk-verification.md).

## Security terminal presentation

- [x] Replace the scanner/version banner with readable finding cards and source excerpts.
- [x] Add severity/cause colors with no-color controls and clean report/machine outputs.
- [x] Verify unit, native scanner, PTY and installed-wheel behavior; update user guide.

Evidence: [security-terminal-verification.md](security-terminal-verification.md).


## CLI cloud defaults, projects and upload errors

- [x] Replace the public upload retry command/sidecars with single-attempt uploads and actionable errors that retain the local report.
- [x] Use red Critical text without a background, orange High and yellow Medium.
- [x] Persist public API/project defaults, support environment/flag overrides and prevent cross-API selected-project reuse.
- [x] Add authenticated project create/list/use with ownership validation and bounded pagination.
- [x] Document local versus cloud authentication, verify AWS/browser behavior and rebuild/install the Linux wheel.

Evidence: [cli-cloud-ux-verification.md](cli-cloud-ux-verification.md). This supersedes
older manifest/retry instructions above; those entries describe their original implementation.
