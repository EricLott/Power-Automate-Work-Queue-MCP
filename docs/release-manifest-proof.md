# Release manifest proof

`config/release.json` is the versioned compatibility manifest for the local candidate. It binds the four solution packages to the runtime target frameworks, `qmcp_WQ_` API catalog, MCP package and SDK, reference flow catalog, native envelope schema, and synthetic `mail.v1` contract.

The build writes `artifacts/packages/manifest.json` with SHA-256 hashes for every unmanaged and managed package. The installation planner compares those hashes before producing a plan hash. The release remains explicitly `productionReady: false` with `tenantImport: not-run`; package provenance and local round trips do not establish tenant import, connector binding, permissions, activation, or production suitability.

The compatibility matrix is intentionally source-relative and redacted: it contains paths, versions, names, and artifact provenance only. It does not contain customer payloads, credentials, connection tokens, mailbox content, or environment secrets.

