# Bundled Trivy verification

## Delivered behavior

- Separate Linux/WSL x64 and native Windows x64 wheels bundle official Trivy
  0.76.0. No host Trivy or Docker required for these wheels.
- Source/ordinary `py3-none-any` installations retain absolute PATH lookup.
- Packaged marker, manifest, platform, version and executable SHA-256 are checked
  before execution. Missing/corrupted bundle never silently falls back to PATH.
- Downloads occur only in the explicit build-preparation script. Both direct
  HTTPS-download and local-archive modes were executed successfully on their
  native platforms; pinned archive digests verified before extraction.
- Each wheel includes its binary, upstream LICENSE, attribution README and
  manifest. Official archives contain no NOTICE. Binary is not tracked in Git.
- Terraform-only checks, checks updates/cache, native JSON/SARIF, filtering,
  threshold evaluation and source/state protection are retained.
- Windows uses pywin32 Job Objects, assigns suspended children before resume,
  terminates descendants on timeout/interrupt and emits UTF-8 when redirected.
- All four prior review findings have regression tests and fixes.

## Native runtime matrix

Tests included the default suite and real Trivy integration/network suite:

| OS | Python | Result |
| --- | --- | --- |
| Linux/WSL x64 | 3.10.12 | 183 passed, 1 Windows-only test skipped, 3 Docker tests deselected |
| Linux/WSL x64 | 3.14.4 | 183 passed, 1 Windows-only test skipped, 3 Docker tests deselected |
| Windows x64 | 3.10.20 | 176 passed, 8 privileged symlink tests skipped, 3 Docker tests deselected |
| Windows x64 | 3.14.4 | 176 passed, 8 privileged symlink tests skipped, 3 Docker tests deselected |

The Windows user token cannot create symlinks (WinError 1314); the eight skips
are conditional on that exact OS error. The same cases pass on Linux. CI sets
`INFRALENS_REQUIRE_SYMLINKS=1`, making lack of Windows symlink privilege a test
failure rather than a skip. No production machine policy was changed.

Actual Trivy integration covers clean/unsafe/invalid Terraform, `.tf.json`,
local and remote Git modules, ignore/config isolation, report IDs and source
locations, severity versus fail-on, source invariance and official SARIF schema.

## Installed-wheel verification

`scripts/verify_bundle.py` completed on all four OS/Python combinations above.
Each run installed the wheel using `uv tool install` in a new temporary tool
directory, outside the checkout. Installation uses `--link-mode copy` to keep
deliberate tampering isolated from uv's shared cache. It checked:

- Wheel platform metadata, exact bundled files, binary digest and license.
- Eight process/atomic-I/O tests using the installed tool's Python: literal
  arguments, streams, controlled failures, timeout and interrupt descendant
  cleanup, explicit environment, UTF-8 report publication, POSIX permissions,
  and preservation of an existing report after replacement failure.
- CLI scans with PATH empty: table, native JSON, SARIF 2.1.0 schema, filter/
  threshold, ignore policy, clean source and malformed Terraform whose filename
  contains the embedded-checks fallback text.
- Unicode directory/source/report filenames without relying on PYTHONUTF8 for
  CLI output, and unchanged source bytes/mtime.
- Damaged installed executable and deleted installation marker both fail with
  reinstall guidance before attempting execution/PATH fallback.

The Linux wheel was built on Linux, and the delivered Windows wheel was staged
and built natively on Windows. A Windows wheel cross-build also succeeded.

## Artifact sizes and integrity

Artifacts are local under ignored `dist/`; none were published externally.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| infralens-0.1.0-py3-none-linux_x86_64.whl | 51,458,016 | 6123a67f87cfdb3f827a105a1da2e268bb3befa08e5e6caf35c485ddcd365225 |
| infralens-0.1.0-py3-none-win_amd64.whl | 52,439,348 | e84c57b328e588bf5670cdc8d1a015b40d0e94c5c001d4b330890e2504abb03c |

Installed executable sizes: Linux 174,563,488 bytes; Windows 178,127,360 bytes.
Each artifact also has a `.whl.sha256` file and is listed in `dist/SHA256SUMS`.
Source distribution and ordinary source wheel build successfully; the sdist
contains build helpers, notices, tests and changelog, with no bundled binary.

## Quality and review

- Ruff check, Ruff format check and git diff whitespace check pass.
- actionlint 1.7.12 validates `.github/workflows/bundle.yml`; the actionlint
  executable was verified against its official release checksum before use.
- Workflow pins action commits and uv, runs the native Python matrix, stages
  verified scanners, runs actual integration and installed-wheel verification,
  and uploads wheels/checksums. GitHub Actions itself was not triggered remotely.
- Docker build and its three integration smoke tests passed. The build caught
  the required hatch_build.py COPY, which was fixed and rebuilt successfully.
  The final image manifest list is
  `sha256:43615f57651db9a7c9c456ff6e4e8a20672dad62a0e1b9f2bdb62259b2446a72`.
  Full Linux test selection including Docker: **186 passed, 1 Windows-only skip**.
- Independent read-only review identified runtime checksum and missing-marker
  gaps; both were fixed with regression tests. Follow-up review found no further
  substantive issue.
- Mutation check: removing the platform guard made its regression test fail;
  the original code was restored immediately afterward.

The existing README edits were preserved and extended. macOS/ARM64, standalone
installers, Terraform/AWS bundling, cloud upload and binary auto-updates remain
outside this change.
