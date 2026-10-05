# rec-console v0.1.0

Released: 2026-10-05

Recommendation control plane. First coordinated OpenRec source release.

## Features

- React/TypeScript UI and FastAPI APIs for runtime serving graphs, experiment variants and rollback.
- Versioned recall-index preparation, validation, atomic alias activation, retention and rollback, including BM25 indexes.
- Airflow DAG control and versioned offline job configuration.
- Selected-feature model training, evaluation-gated publication, checksums, retained releases and explicit rollback.
- Entity diagnostics, business analytics, dependency monitoring and embedded Grafana dashboards.

## Installation and compatibility

Standalone exposes monitoring, entity diagnostics and serving-graph operations. Cluster enables the offline, recall and model lifecycle modules.

Authentication/RBAC is not implemented. Run the console only in a trusted environment and protect access to its mutation APIs. Replace example tokens before sharing a deployment. Release mutations use locks on the shared data volume; this does not establish a general distributed HA control plane.

## Validation and known boundaries

See this repository's README for build/test commands and deployment requirements. The coordinated release's [validation record](https://github.com/open-rec/openrec/blob/v0.1.0/release/VALIDATION.md) distinguishes checks executed for this release from historical integration evidence.

This initial release establishes a versioned source baseline. Source archives and checksums are published; external package registries and container registries are not populated by the source-release workflow. Upgrade the complete compatible distribution, retain data/checkpoints/artifacts, and preserve prior component refs for rollback.
