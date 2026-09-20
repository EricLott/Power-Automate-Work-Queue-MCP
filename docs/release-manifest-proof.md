# Release manifest proof

`config/release.json` is the versioned compatibility manifest for the local candidate. It binds the four solution packages to the runtime target frameworks, `qmcp_WQ_` API catalog, MCP package and SDK, reference flow catalog, native envelope schema, and synthetic `mail.v1` contract.

The build writes `artifacts/packages/manifest.json` with SHA-256 hashes for every unmanaged and managed package. The installation planner compares those hashes before producing a plan hash. The release remains explicitly `productionReady: false` with `tenantImport: not-run`; package provenance and local round trips do not establish tenant import, connector binding, permissions, activation, or production suitability.

The compatibility matrix is intentionally source-relative and redacted: it contains paths, versions, names, and artifact provenance only. It does not contain customer payloads, credentials, connection tokens, mailbox content, or environment secrets.

## 2026-09-20 local verification

Running `scripts/build.ps1 -SkipRestore` at commit `faae9ff` rebuilt the runtime and plug-in targets for `net462` and `net8.0` with zero errors, generated all four solution packages, and completed unmanaged/managed package round trips for `WQCore`, `WQTesting`, `WQNotificationsEmail`, and `WQReferenceSharedMailbox`. Structural archive checks and generated-flow invariants passed. The redacted machine-readable record is [release-build-2026-09-20.json](evidence/release-build-2026-09-20.json). This advances P7-01 local reproducibility evidence only; `tenantImport` remains `not-run`, and the binding gates above remain open.
