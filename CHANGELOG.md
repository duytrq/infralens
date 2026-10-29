# Changelog

## Unreleased

### Changed
- **Breaking CLI change:** Drift gates now use one `--fail-on` option: ANY,
  MEDIUM (includes HIGH), HIGH or UNKNOWN; combine with commas (HIGH,UNKNOWN).
  Remove --fail-on-drift, --fail-on-priority and --fail-on-unknown.
- **Breaking CLI change:** `drift --trace DAYS` takes an explicit integer 1–90;
  remove --lookback-days and the implicit seven-day trace default. Trace is off
  when omitted. Report/upload schemas stay compatible; see the migration table
  in docs/USER_GUIDE.md for old-to-new commands.

### Added
- Drift resource cards with priority colors, AST-based current attribute excerpts,
  compact saved/observed leaf diffs and inline bounded CloudTrail candidates.
- Drift --severity display filter and --no-color behavior matching the Security CLI;
  JSON/uploads and gates retain all resources, and source excerpts stay terminal-only.
- `cloud configure list` shows effective API/project/auth without exposing tokens;
  `cloud status` remains available and configure --api-url stays compatible.
- Project create prompts for missing ID/name like setup; CI must supply both fields.
- Persistent per-API Cognito sessions, automatic refresh and cloud login/logout/status.
  Credentials use private user storage and serialized refresh/logout.
- Guided cloud setup and project picker always bind public API/project settings to the repo.
  Remove --local and machine-wide project defaults; legacy selected projects are ignored.
  Resolve scan-input config up to the Git boundary, after flag/environment overrides.
- Default scan/drift input to the current directory. Upload defaults to native JSON
  and a unique report in .infralens/reports; show destination, gate and upload states.
- Save API URL once with `cloud configure`; show defaults with `cloud status` and
  create/list/select authenticated projects from the CLI. Flags override environment
  variables, which override saved defaults; selected projects are API-specific.
- Security terminal finding cards with source excerpts, cause-line markers and
  distinct severity colors. Remove the scanner/version banner; respect --no-color,
  NO_COLOR, non-terminal output and unstyled report/machine formats.
- Install boto3 by default so CloudTrail tracing needs no SDK extra; existing
  `aws-trace` install commands remain compatible.
- Consistent Security/Drift common flags, help order/defaults and upload validation;
  Drift uses `--fail-on` for all gate conditions; Security keeps its severity threshold.
- Security `scan --upload` through Cognito and the existing API, full native JSON
  independent of terminal severity filters and a 50 MiB limit.
- Live browser smoke exercises CLI configuration, projects, Security upload,
  threshold failure, dashboard source display and exact-byte download.
- Terraform drift engine, optional CloudTrail candidates, source locations,
  review priorities and CI gates, integrated from drift_develop.
- Drift upload with Cognito PKCE or supplied CI access tokens,
  project-relative source paths and checksums of the written report bytes.
- Private AWS drift storage, validated report summaries, scoped comparisons,
  and React history/report/comparison views alongside security scans.
- Independent Cognito-authenticated storage backend, private per-user projects and
  scan history, immutable JSON uploads, validation, downloads and recoverable deletion.
- SAM infrastructure, exported OpenAPI contract, backend quality workflow and
  browser-PKCE smoke tool.
- Deployment tags, a tracked Lambda artifacts stack, live resource inventory and
  a cleanup runbook covering retained buckets, DynamoDB and Cognito resources.
- Linux/WSL x64 and Windows x64 wheels containing official Trivy 0.76.0.
- Verified build staging, installed-binary integrity checks and isolated wheel
  verification without a host Trivy installation.
- Native Windows process-tree cleanup and UTF-8 output, including redirected
  reports and paths containing non-ASCII characters.
- Linux/Windows Python 3.10/3.14 artifact-build workflow and Docker smoke checks.

### Changed
- Upload once per command; failures explain network, authentication, permission or
  service errors and keep the local report. Remove `cloud upload` and persisted
  `.upload.json` sidecars; check the dashboard before rerunning an uncertain upload.
- Use red text without a background for CRITICAL, orange for HIGH and yellow for
  MEDIUM in the CLI. Cloud auth still uses browser Cognito or a CI access token;
  local scans need no InfraLens login; saved sessions stay in private user storage.

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
