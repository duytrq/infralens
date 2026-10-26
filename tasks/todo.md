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
