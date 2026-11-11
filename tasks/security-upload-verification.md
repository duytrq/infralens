# Security scan upload verification

Verified on Linux/WSL, 2026-10-28.

## Behavior

- `scan --upload` requires JSON format, output, an existing project and HTTPS API
  origin. Upload is opt-in; project/API flags without upload are rejected before scanning.
- Upload JSON preserves the full native Trivy schema-2 report. Severity only filters
  the terminal table in this mode; counts and threshold use all unsuppressed findings.
  Existing local JSON/SARIF filtering remains unchanged.
- Manifest binds run UUID, timestamps, API origin and actual file bytes, including
  native Windows newlines. Metadata includes Trivy version, counts, threshold,
  selected severities, ignore-file checksum and safe diagnostic codes.
- Gate failure uploads before exit 1. Scan failure creates no cloud run. Upload
  failure retains report/manifest and exits 3; retry preserves UUID/metadata and
  does not rerun Trivy. Security accepts up to 50 MiB; Drift retains its 2 MiB limit.
- Shared transport validates report type/schema/checksum and API origin before
  authentication. Bearer tokens are sent only to the configured API, never S3.

## Evidence

| Check | Result |
| --- | --- |
| Initial feature reproduction | Successful-upload tests failed with `No such option: --upload` before implementation |
| Full CLI suite | 608 passed, 2 existing Windows-only skips, 17 opt-in tests deselected |
| Real Trivy 0.76.0 integration | 10 passed, including unfiltered upload with LOW terminal filter and HIGH gate |
| Backend suite | 157 passed; existing Security/Drift API contract unchanged |
| Contract and lint | Exported OpenAPI check, Ruff check/format and frontend ESLint passed |
| Live AWS/browser | 22 checks passed on CloudFront and localhost; real CLI scan/upload, failed gate, retry without PATH Trivy, stream indexing with counts_match=true, source rendering and byte-identical download |
| Test cleanup | Two temporary users and their project rows removed; runs deleted via API with protected scheduled physical cleanup |
| Linux bundled wheel | Installed outside checkout with no PATH Trivy: real scans, JSON/SARIF, drift, upload-manifest failures/retries and 10 lifecycle/I/O tests passed |

Live evidence: [browser verification](../infra/deployments/infralens-dev-security-upload-browser-verification.json).
The smoke command is documented in [frontend operations](../infra/FRONTEND.md).

The final live smoke used the installed bundled wheel, not the editable checkout.
Its CLI/cloud/handler/options sources match the checkout and the installed package.
Artifact: `dist/infralens-0.1.0-py3-none-linux_x86_64.whl` (51,492,847 bytes), SHA-256:
`2ce59427c5c2eec792e735d4a8aa8d0aabf38ee306a9fc87ede64a45038e89d2`.
A companion `.whl.sha256` is available in `dist/`; artifacts remain local.

## Boundaries

No server schema, Lambda or React application deployment is needed: the deployed
backend/dashboard already consume the Security contract. Users need the updated
CLI. Upload authentication reuses the existing Cognito PKCE/CI-token flow; no new
machine identity or token persistence was added.

Native Trivy reports can include source snippets/configuration values. The CLI
uploads only when requested; the complete report is not automatically redacted.
Live verification scans a local test fixture, not real AWS infrastructure. Actual
Windows runtime and Windows wheel execution were not run in this session and need
the existing Windows CI matrix. No new Docker image or PyPI/registry release was published.
