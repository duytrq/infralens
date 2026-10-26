# Security scanner: approved implementation contract

Implement Terraform security scanning using Trivy, retaining the existing drift
placeholder. Provide native CLI (Trivy on PATH) and Docker (bundled Trivy), with
manual `docker run` mounts. No launcher, auto-downloader, cloud upload or drift
implementation. Baseline: 100 passing tests; Python >=3.10.

## Behavior

- Scan `.tf`/`.tf.json` recursively. Keep drift's direct-file validation.
- Trivy baseline 0.76.0; accept 0.76.x. Dependency checks are scan-only.
- Scan once to native JSON at all severities; normalize findings internally.
- Evaluate fail-on across unsuppressed findings before severity filtering.
- Default stdout: plain table with severity, rule, message and source location.
- JSON/SARIF without output: stdout is machine-readable only.
- With output: table on stdout, selected report in file, diagnostics on stderr.
- Convert native JSON using Trivy; preserve its report schema.
- Timeout: scan 300s (positive CLI override), version 10s, convert 60s.
- Exit 0 success, 1 threshold, 2 input, 3 execution/I/O, 4 drift unavailable,
  130 interrupted. Export before returning 1; execution errors take precedence.
- Ignore project trivy.yaml and inherited Trivy behavior overrides. Honor inline
  ignores and root .trivyignore. Keep cache/proxy configuration usable.
- Never log raw engine stderr, exception payloads, source or credentials.
- Clean process groups on interruption/timeout; private temporary JSON; atomic
  output replacement; protect Terraform/tfvars/state from output collision.
- Docker: pinned image digests, lockfile build, non-root, UID/GID override,
  /workspace read-only, /reports and /cache writable, no Docker socket or AWS.
- Linux/WSL and linux/amd64 first. No registry publication. Document network use
  for checks and remote modules; no Terraform/AWS calls during scan.

## Architecture

CLI -> scan handler -> Trivy adapter -> reusable process runner.
Handler evaluates fail-on and renders/exports. Future Terraform/AWS adapters
may reuse runner; do not create unused abstractions. Internal Finding,
ScanResult and ProcessResult dataclasses do not change native JSON format.

## Verification

Behavior tests with fixture JSON and fake executable; real process timeout and
SIGINT tests; actual Trivy integration (clean/unsafe/invalid/nested/module,
filter policy, JSON/SARIF and locations); SARIF 2.1.0 schema validation; Docker
source read-only, file ownership, cache, exits and interrupts. Full pytest,
ruff check, ruff format --check, uv build, docker build/smoke. Retain drift tests.

## Environment findings

- The WSL `docker` shim is unavailable, but Docker Desktop works through
  `docker.exe` outside the sandbox. Build stdin uses a gzip GNU-format tar
  context to work across WSL/Windows. This is verification setup, not a launcher.
- Trivy 0.76.0 was downloaded into /tmp/infralens-tools and SHA-256 verified
  against the official release checksums. No product downloader was added.
- Official OASIS SARIF schema is vendored for offline validation; jsonschema is
  development-only. Actual Terraform parse errors can return Trivy exit 0, so
  controlled stderr classification is required before rendering a clean result.
