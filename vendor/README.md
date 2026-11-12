# Third-party scanner

InfraLens bundled wheels redistribute an unmodified official Trivy executable
from Aqua Security: https://github.com/aquasecurity/trivy.

The pinned release, original asset URLs and archive SHA-256 values are recorded
in `trivy.json`. Checksums were obtained from the official release's checksum
file named in that manifest. The release assets themselves are not committed.

Trivy is licensed under Apache License 2.0. Each bundled wheel carries the
upstream LICENSE distributed with its executable at
`infralens/_vendor/trivy/LICENSE`, plus manifests identifying the exact release,
platform, archive digest and executable digest. The official archives used here
do not include a NOTICE file. The upstream release also publishes its dependency
SBOM as `bom.json` on https://github.com/aquasecurity/trivy/releases/tag/v0.76.0.
This attribution document is also included in each bundle next to the license.

The Terraform scanner and checks remain maintained by upstream Trivy; InfraLens
does not extract or fork its Go packages or policy bundle. The executable is
updated only by preparing and distributing a new InfraLens wheel. Check-bundle
updates and Terraform module downloads retain Trivy's existing behavior.
