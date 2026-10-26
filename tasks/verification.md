# Security scanner verification — 2026-10-20

## Result

All approved implementation steps are complete. Native CLI and Docker share the
same handler/adapter/runner. Cloud upload, drift implementation, launchers and
binary download management remain outside this change.

## Final gates

- Full suite: **159 passed**, no skipped/deselected tests when all external
  suites are explicitly enabled. Includes 147 default tests, 9 real-Trivy tests
  (including remote module download), and 3 Docker tests.
- `ruff check`: passed.
- `ruff format --check`: 27 files already formatted.
- `git diff --check`: passed.
- `uv build`: wheel and sdist built successfully. Wheel contains the new
  process, Trivy and reporting modules.
- Final Docker image: `infralens:local`, linux/amd64, manifest list
  `sha256:5d6d5f89f1e35e84b2fe44e30c937e5843cce238082eeff4ff816bf47919c0f5`.

## Runtime evidence

- Actual Trivy 0.76.0 binary verified using official release SHA-256 checksums.
- Unsafe Terraform produces AWS-0107 HIGH at main.tf:7, plus two LOW findings.
- Actual JSON and SARIF findings match the terminal table; SARIF validates
  against the vendored official OASIS 2.1.0 Errata 01 schema.
- LOW report filtering still exits 1 with fail-on HIGH when HIGH exists.
- Clean source, invalid Terraform, nested local module, remote Git module,
  native .tf.json, root ignore and hostile project/env overrides covered.
- Source bytes/mtime preserved; remote module scan creates no project files.
- Real child-process timeout and SIGINT tests exercise cleanup; fake engine
  failures verify private error presentation and atomic report preservation.
- Docker runtime has Trivy and defaults to UID/GID 10001. UID/GID override
  creates a report owned by UID 1000 with mode 0600. Source mounts reject writes,
  persisted cache is populated, and SIGINT returns 130.
- A separate manual bind-mount scan through Docker Desktop using WSL UNC paths
  wrote `/tmp/infralens-bind-reports/security.json` on the host, owner 1000,
  native schema 2, with all three findings. Exit 1 correctly reflected HIGH.

## Environment and reproduction

This WSL distro's `docker` shim reports missing integration. Docker Desktop was
verified through `docker.exe` outside the sandbox. Tests support either client
through INFRALENS_TEST_DOCKER; volumes used by tests are isolated and removed.
The manual smoke check additionally exercised real bind mounts.

The final combined command was:

```bash
rtk uv run --env-file /tmp/infralens-all.env pytest -q --run-integration --run-network --run-docker
```

That temporary env file specified:

```text
INFRALENS_TEST_TRIVY=/tmp/infralens-tools/trivy
TRIVY_CACHE_DIR=/tmp/infralens-trivy-cache
INFRALENS_TEST_DOCKER=docker.exe
```

For normal environments, use the README commands with installed Trivy and a
working `docker` client. External suites fail on missing tools when selected.

## Review

Reviewed tests, source, Dockerfile, package/lockfile changes and README against
the approved contract. Particular cases addressed during runtime verification:

- Trivy can return 0 after Terraform parse errors: classify stderr before
  presenting scan success; raw diagnostic payloads stay private.
- Explicitly passing a nonexistent .trivyignore is fatal in Trivy 0.76:
  disable ignore-file loading when the project has no file.
- Docker can reset empty-volume directory metadata on automatic population:
  test volumes use volume-nocopy so their seeded permissions persist.
- Report privacy is intentional: a different container UID cannot read a
  0600 report. Runtime assertions use the same UID as the scan.

No outstanding correctness findings from this review. No registry publication
or git commit was performed.
