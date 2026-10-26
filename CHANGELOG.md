# Changelog

## Unreleased

### Added
- Independent Cognito-authenticated storage backend, private per-user projects and
  scan history, immutable JSON uploads, validation, downloads and recoverable deletion.
- SAM infrastructure, exported OpenAPI contract, backend quality workflow and
  browser-PKCE smoke tool; scanner CLI cloud commands remain a separate integration.
- Deployment tags, a tracked Lambda artifacts stack, live resource inventory and
  a cleanup runbook covering retained buckets, DynamoDB and Cognito resources.
- Linux/WSL x64 and Windows x64 wheels containing official Trivy 0.76.0.
- Verified build staging, installed-binary integrity checks and isolated wheel
  verification without a host Trivy installation.
- Native Windows process-tree cleanup and UTF-8 output, including redirected
  reports and paths containing non-ASCII characters.
- Linux/Windows Python 3.10/3.14 artifact-build workflow and Docker smoke checks.

### Fixed
- Sign S3 upload/download URLs for the bucket's regional endpoint so new buckets
  work without waiting for global endpoint routing to propagate.
- Reject symlinked Terraform source files that Trivy would otherwise skip.
- Keep Terraform parser errors fatal when filenames contain checks-fallback text.
- Prevent report output from replacing `.trivyignore`, including file aliases.
- Resolve development Trivy executables before changing the working directory.

### Dashboard backend

- Add asynchronous Trivy finding indexes, filtered cursor APIs and finding detail
  with bounded plain-text source excerpts.
- Add latest-scan project summaries, dashboard Cognito app client and exact-origin
  CORS while preserving CLI login/upload.
- Add failed-analysis retry/backfill, generation-safe derived-data cleanup and
  tagged worker/storage/failure-queue infrastructure.

### Internal-tool simplification

- Remove the SQS analysis-failure queue, its IAM permission and stream failure
  destination. Recover using stored run state, CloudWatch logs and manual
  retry/backfill.

### Dashboard frontend

- Add an English React dashboard for projects, scan history, findings/source detail,
  JSON downloads, project creation, analysis retry and scan deletion.
- Add tab-scoped Cognito PKCE login, exact origin registration and opt-in localhost
  support in dev while preserving CLI authentication.
- Add private S3/CloudFront OAC infrastructure, credential-free frontend CI,
  release archives, verified rollback and real browser/AWS smoke tooling.
- Publish the dev dashboard through private S3 + CloudFront/OAC, with verified
  browser login, cache/security headers and release rollback. Localhost login is
  still supported.
