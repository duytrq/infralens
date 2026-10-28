# Consistent Security/Drift CLI

Verified on Linux/WSL, 2026-10-28.

- Both commands take positional `PATH`, followed by the same common option order:
  `--format`, `--output`, `--fail-on`, `--timeout`, `--upload`, `--project`, `--api-url`.
  Shared options use the same declarations/help/defaults; upload validation is shared.
- Drift accepts `--fail-on MEDIUM|HIGH`, case-insensitive, with `--fail-on-priority`
  retained as a compatible alias. Security retains LOW/MEDIUM/HIGH/CRITICAL severity
  thresholds; Drift retains its review-priority policy. The policy scales are distinct.
- JSON/output/project/API requirements and retry-manifest safeguards are unchanged.
  Drift still needs `--scope` for comparable uploads; Security does not accept a
  meaningless scope. Security keeps SARIF; Drift keeps its Terraform/trace flags.
- Initial contract tests reproduced the missing Drift `--fail-on`, inconsistent
  help/default descriptions and incomplete shared upload errors before implementation.
  All 18 new contract tests pass, including equal gate output through the old alias.
- Full CLI suite: **626 passed**, 2 existing Windows-only skips, 17 external-tool
  tests deselected. Ruff lint/format and Markdown links/CLI example flags passed.
- Three real imported Drift fixtures generate schema-valid upload reports/manifests
  through the canonical `--fail-on` spelling. Scanner/Drift lifecycle regression tests pass.

Guide: [shared CLI syntax](../docs/USER_GUIDE.md#cú-pháp-chung-của-security-và-drift).
No backend/frontend API or execution-engine behavior changed; no AWS rollout is needed.
This change was not re-deployed or re-smoked against AWS.

## Current local artifact

`dist/infralens-0.1.0-py3-none-linux_x86_64.whl`, 51,493,198 bytes, SHA-256:
`768b53827d21755d2d0b4cb97eeb8e4a82b4509439a87b263f54f71728a1ecde`.

The CLI/validation sources inside the wheel match the checkout. This local build
replaces the previous same-named Security-upload wheel; the earlier AWS smoke
record describes that earlier artifact. No PyPI/registry release was published.

Installed-wheel verification passed outside the checkout with no PATH Trivy:
real scans, JSON/SARIF, canonical Drift gate, upload/retry manifests and 10
process/I/O tests. Actual Windows execution was not run in this session.
