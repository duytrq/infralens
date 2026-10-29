# CLI cloud defaults and projects verification

Verified 2026-10-29 on Linux/WSL x64, Python 3.10.

## Result

- Public `cloud upload` and `.upload.json` sidecars were removed at the user's request.
  Existing sidecars are not deleted. Upload metadata and exact-byte checksums remain
  in memory; backend registration, signed S3 PUT and completion validation remain.
- Each HTTP request is attempted once. Network, auth, permission and service failures
  produce safe actionable messages. Upload failures return 3 and retain the local JSON.
  An uncertain outcome tells the user to check the dashboard before starting a new run.
- Critical is red text without a background, High ANSI-256 orange 208, Medium yellow.
  No-color/non-TTY and clean JSON/SARIF/file behavior remain covered.
- `cloud configure` and `cloud status` manage public local defaults. Project
  create/list/use use the existing private API and Cognito; create selects by default,
  use checks ownership before saving. Flags override env, env overrides saved settings.
  Saved selected projects only apply to the matching API. Tokens are never persisted.
- Local scans require no Cognito. Interactive cloud operations use browser PKCE;
  noninteractive operations require `INFRALENS_ACCESS_TOKEN`.

## Checks

- Root suite: **660 passed**, 2 existing platform-specific Windows skips,
  17 explicitly opt-in integration tests deselected.
- Real Trivy 0.76.0 suite, including remote modules: **10 passed**.
- Ruff for source/tests/bundle verifier/operator smoke and frontend ESLint: passed.
- Mutation experiment: removing the API match before reusing a selected project
  caused the cross-origin regression test to fail. Restored source, all 16 config/
  project tests passed afterward.
- AWS/real-browser smoke: **22 checks passed** across published CloudFront and
  localhost. CLI configured its isolated API, created/listed/selected a private
  project, uploaded using saved defaults, returned gate failure, then dashboard
  indexing/source/exact-byte JSON download succeeded. Security/Drift isolation,
  deletion and logout also passed. Temporary users removed: 2; project rows removed: 4.
  See [machine evidence](../infra/deployments/infralens-dev-cloud-cli-browser-verification.json).
- Installed-wheel verifier passed without host Trivy on PATH: native JSON/SARIF,
  Security/Drift failed-upload preservation without sidecars, config/status,
  noninteractive project auth, default boto3/offline CloudTrail, integrity failures
  and **10 process/atomic-I/O regressions**.
- Real installed CLI PTY against `/home/lozshi/uet/security-demo` confirmed Critical
  red/no background, High orange and Medium yellow. Native scan found 17 findings
  (1 Critical, 10 High, 4 Medium, 2 Low), gate exit 1. Plain terminal preview updated.
- Locked production and installed-tool dependency audits: no known vulnerabilities.
  No dependency declarations or backend/frontend application changes were needed.

## Local artifact and setup

Rebuilt `dist/infralens-0.1.0-py3-none-linux_x86_64.whl`:

- Size: **51,498,017 bytes**.
- SHA-256: `662fe8a8909f8b8b4b9e96f642694abfae5c9abcf61f6455f3ee918c4f3fa90b`.
- All **26** Python source files in the wheel exactly matched this checkout.
- Reinstalled the user's existing `uv tool` CLI from this wheel. Saved the dev API
  at `/home/lozshi/.config/infralens/config.json`; project remains unselected so no
  temporary smoke project or another account's choice is persisted.

This is the current local development artifact, replacing the earlier wheel of
this same 0.1.0 filename. Historical verification hashes refer to earlier snapshots.
No PyPI release, Windows rebuild, Git push or backend/frontend redeployment occurred.
Windows-specific checks were not run on this Linux host.

## Review

Reviewed correctness, input/response validation, private project ownership,
credential routing (API bearer only, never S3), config precedence and permissions,
bounded pagination, output sanitization and retained scanner/process regressions.
No outstanding findings in the requested scope. AWS API contracts are unchanged.
