# rec-console v0.2.0

Released: 2026-10-18

Part of the coordinated OpenRec v0.2.0 source release.

## Changes since v0.1.0

- Refactor control-plane modules and unify console state-directory configuration.
- Align ALS/text-search publication and manage scheduled title embedding releases.
- Keep online query encoding and scheduled title generation opt-in for CPU-only deployments.

## Installation and compatibility

Standalone retains monitoring, entity diagnostics and serving graphs; cluster enables the full control plane. Republish persisted DAG configurations when migrating recall names and task IDs. Authentication/RBAC is not implemented; retain the documented trusted-environment deployment boundary.

See the [distribution upgrade and rollback instructions](https://github.com/open-rec/openrec/blob/v0.2.0/RELEASE_NOTES.md) for the complete compatible component set and persisted configuration migrations.

## Validation and publication

The [validation record](https://github.com/open-rec/openrec/blob/v0.2.0/release/VALIDATION.md) distinguishes release checks from maintainer-reported prior CI and integration results. GitHub Actions publishes source archives and SHA-256 checksums; Maven Central, PyPI and versioned container registries are not populated by this workflow.
