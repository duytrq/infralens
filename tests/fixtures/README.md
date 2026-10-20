# Scanner fixtures

`unsafe/main.tf` intentionally exposes SSH; never apply this fixture.
`clean/main.tf` contains no infrastructure resources.

`sarif-schema-2.1.0.json` is the unmodified OASIS SARIF 2.1.0 Errata 01
schema, retrieved from:
https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json

The schema contains its original OASIS copyright notice. It is vendored to make
report validation independent of network availability.
