# Versioning

NOVU Builder follows Semantic Versioning.

## Pilot Phase

During the pilot phase, NOVU Builder uses `v0.x.y` versions. Compatibility expectations still matter, but production contracts may continue to mature until `v1.0.0`.

## Version Meaning

- Patch: bugfix, stabilization, documentation correction, or internal hardening.
- Minor: new capability behind a stable contract.
- Major: breaking production contract or coordinated migration boundary.

## Tag Rules

- Tags must match releases.
- Tags must be reproducible from committed source.
- Do not tag with failing tests, failing `mypy`, known fail-open behaviour, or dirty working tree.

## Examples

- `v0.8.4` AI offer measurements-only contract.
- `v0.8.5` backend stabilization.
- `v0.9.0` pricing engine integration milestone.
- `v1.0.0` production-ready release.
