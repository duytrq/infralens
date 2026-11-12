# Drift terminal presentation — 2026-10-29

- Per-resource cards show HIGH orange, MEDIUM yellow and UNKNOWN magenta. Resource
  addresses/headings are bold; source locations and trace headings are cyan. Changed
  source expressions use priority color; saved values are red and observed values green.
- Reused Security's color controls. NO_COLOR, --no-color and non-TTY disable ANSI;
  JSON and file output stay clean. --severity filters displayed cards only; full
  counts, JSON/upload and CI gate evaluation remain unchanged.
- AST source excerpts show matching changed expressions only, with bounded source
  reads/output and sensitive/unknown masking. Forged source paths are not followed.
  Provider-computed fields and unsupported expressions report source unavailable.
  Source excerpts are not serialized or uploaded.
- Generic reconciliation paragraphs are removed from terminal output. Structured
  JSON guidance remains available. Trace candidates appear inside each resource
  card, with at most two events and a pointer to remaining JSON events.
- Full default suite: **707 passed**, 2 existing Windows-only skips, 17 opt-in tests
  deselected. Ruff lint and format checks passed (144 files).
- Mutation experiment disabled source redaction: the sensitive-literal regression
  failed as expected. Original source was restored before verification/build.
- Isolated installed Linux wheel verifier passed: native bundled Trivy scanning,
  JSON/SARIF, source excerpts, common CLI controls, offline trace using default
  boto3, new Drift cards/filter/no-color and 10 process/atomic-I/O checks.
- Both wheels rebuilt; all 29 Python source files in each match the checkout.
  The Linux wheel was reinstalled in the user's uv tool. Native Windows execution
  was not rerun for this terminal presentation change.
- Real PTY run of the installed CLI against /home/lozshi/uet/drift-demo verified all
  seven styles above, source line markers, no generic Choice/Confirm paragraphs,
  exact rule ID correlation and ModifySecurityGroupRules candidates. Four resources
  remain drifted: HIGH 2, MEDIUM 1, UNKNOWN 1. Gate HIGH correctly exits 1.
- CloudTrail returned candidates for 3/4 resources; VPC tag tracing is unsupported.
  Overall partial coverage has has_errors=false; this is not a lookup failure.
  Report: ../drift-demo/reports/drift-terminal-v3.json; plain/ANSI previews in the
  same directory. No AWS mutation, Terraform apply or upload was performed.
- Terraform state unchanged: SHA-256
  5fbee5264eb544dc1084da6cbbfc78bc57f47534427b24a22fa33f844d0f98cd.

Current unpublished local wheels (same filenames replace previous snapshots):

- Linux: 51,508,776 bytes; SHA-256
  d0b12af333de3ce52a273343c750450f65a02e5227f531e83a420d370babb22c.
- Windows: 52,490,099 bytes; SHA-256
  30cffc0c0ae6f0509158e25616b4573df8d6c52afe39fa5c8982be66ae01c719.

Review found no remaining required changes in correctness, source privacy, bounds
  or report compatibility. No dependencies were added or upgraded. No backend or
  frontend redeployment is needed for this CLI change.
