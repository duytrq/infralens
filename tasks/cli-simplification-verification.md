# Simplify Drift CLI — 2026-10-29

## Result

- One public gate option: --fail-on ANY, MEDIUM, HIGH or UNKNOWN. Commas combine
  criteria with OR; MEDIUM includes HIGH, UNKNOWN is independent, ANY includes all.
  Case/whitespace/duplicate criteria are normalized. Omitted gate leaves findings
  nonfatal; execution/trace/upload errors still take precedence.
- --trace DAYS requires an integer 1–90. Omitted trace is disabled. Removed public
  --fail-on-drift, --fail-on-priority, --fail-on-unknown and --lookback-days.
- Help includes short examples and defaults. Current README, guide, integration
  docs and demo examples use the new syntax. The guide includes a migration table.
  Updated the sibling drift-demo README trace command as well.
- Kept existing internal engine options, report criteria and cloud manifest schema:
  a small CLI parser maps the new syntax onto the existing contracts. No backend
  or frontend deployment and no dependency changes.

## Verification

- TDD: new CLI tests initially failed (18 failures), then all 28 passed. Tests cover
  ANY/UNKNOWN, threshold and comma semantics, full results despite display filters,
  invalid input before execution/output, explicit trace range/default and removed flags.
- Existing behavior tests were migrated to the approved syntax; no tests were
  skipped or disabled for this change. Full default suite: **744 passed**, 2 existing
  Windows-only skips, 17 opt-in integration tests deselected. Ruff lint and format
  checks passed (147 files).
- API contract checks cover 3 imported fixtures × 4 gate selections, validate both
  DriftReport and RunInput, and confirm report criteria equal cloud metadata criteria.
- Mutation experiment inverted UNKNOWN selection. Match-count regressions failed;
  restored the exact source and reran the 28 CLI tests successfully.
- Isolated installed Linux wheel verifier passed: new gate/trace syntax and help,
  removed flags rejected, trace with no resources avoids AWS, bundled native Trivy
  JSON/SARIF scanning, offline SDK trace, and 10 process/atomic-I/O checks.
- Linux/Windows wheels rebuilt; all 29 Python source files in each match checkout.
  Linux CLI reinstalled in the existing uv tool. Native Windows was not rerun.
- Real PTY invocation of installed CLI in /home/lozshi/uet/drift-demo:
  --trace 1 --region ap-southeast-1 --fail-on HIGH,UNKNOWN --format json --output …
  returned exit 1 with 4 resources and 3 gate matches. The CloudTrail start/end
  window is exactly 86400 seconds. Candidates for 3 resources, one unsupported VPC;
  partial coverage, has_errors=false. Colors, changed-field code and exact rule ID
  correlation remain visible. Saved JSON has no ANSI.
- Live evidence: /home/lozshi/uet/drift-demo/reports/cli-simplified.json and
  cli-simplified-preview.txt. No upload or AWS mutation was performed; Terraform
  state unchanged, SHA-256
  5fbee5264eb544dc1084da6cbbfc78bc57f47534427b24a22fa33f844d0f98cd.

Current unpublished local wheels replace older snapshots of the same filenames:

- infralens-0.1.0-py3-none-linux_x86_64.whl: 51,509,017 bytes; SHA-256
  fc435e022c876b8a621915a51ea151d74fac553fab6b5fc2070a8307fca05c4e.
- infralens-0.1.0-py3-none-win_amd64.whl: 52,490,339 bytes; SHA-256
  7ff57e305abecbf213aa16ca62d26b0c2f4962606aaf3a731dda71a140982e03.

Reviewed correctness, clarity, input validation, bounded behavior and report/cloud
compatibility; no remaining required findings. Breaking CLI syntax is intentional
and approved; migration is documented. No release/tag/push was performed.
