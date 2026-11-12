# Bundle Trivy: approved contract

Ship official Trivy 0.76.0 inside separate Python wheels for Linux/WSL x64 and
Windows x64. Install with uv; scan Terraform only; no Docker or host Trivy needed
for bundled wheels. Keep current checks updates/cache and embedded fallback.
No Terraform-only fork, macOS/ARM64, runtime executable downloader, standalone
installer, AWS/Terraform bundling, or cloud upload.

Build from pinned HTTPS archives verified against committed SHA-256 values.
Ship licenses and a manifest. Platform-tagged wheels contain one binary; source
installs and Docker retain PATH discovery, normalized before changing cwd.
Broken bundles fail closed. Windows uses a suspended child assigned to a Job
Object before resume, with pywin32 conditional dependency; preserve runner API,
timeouts, Ctrl+C/130, safe diagnostics and process-tree cleanup.

Keep existing CLI/report contracts. Resolve the four review findings before
release: reject symlinked Terraform, classify fallback log message precisely,
protect ignore policy outputs/aliases, resolve relative executable paths.

Verify Linux and native Windows installs outside checkout without Trivy on PATH;
JSON/SARIF/table, filtering/thresholds, ignores, invalid source, modules, Unicode
paths, timeout/interrupts, source invariance and atomic output. CI matrix Python
3.10/3.14, both OSes; artifacts/checksums only, no automatic publishing.
