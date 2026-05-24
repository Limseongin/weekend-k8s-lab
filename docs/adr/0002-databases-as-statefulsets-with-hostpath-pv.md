# Run Postgres and MongoDB as in-cluster StatefulSets with hostPath PVs

The academy VM cluster (1 master + 2 workers, 2–4GB each) has no managed-DB option and limited memory, but running databases on the host as systemd services would skip the K8s primitives this lab exists to teach. Each DB runs as a `replicas: 1` StatefulSet pinned to a specific worker node via `nodeAffinity`, backed by a hostPath PersistentVolume on that node; seeding is a separate idempotent Kubernetes Job that only writes when the DB is empty.

## Consequences

- Moving a DB Pod to a different node requires moving (or re-seeding) the hostPath data — pinning is deliberate.
- Resource requests/limits must be tight (e.g. Postgres ~256Mi req / 512Mi limit, Mongo ~512Mi req / 768Mi limit) to fit alongside the app workloads on the same 2–4GB worker.
- A node going down takes its DB with it. Acceptable for a 1-day lab; HA is explicitly out of scope.
- The seed Job is the source of truth for dummy data; PV wipes are recoverable by re-running it.
