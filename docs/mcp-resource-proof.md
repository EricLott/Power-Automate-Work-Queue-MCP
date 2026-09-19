# MCP resource proof

The stdio server publishes bounded, versioned resources under the `qmcp://wq/` publisher namespace. A host can discover them with `resources/list` and read them explicitly with `resources/read`; no host-side automatic resource injection is assumed.

| Resource family | Example URI | Source | Default handling |
| --- | --- | --- | --- |
| Architecture | `qmcp://wq/architecture/v0.1` | `docs/architecture.md` | Curated text only |
| Flow | `qmcp://wq/flow/ProcessOne/v1` | `templates/ProcessOne.json` | Reference source only |
| Schema | `qmcp://wq/schema/native-envelope/v1` | `templates/native-envelope.schema.json` | Synthetic contract |
| Contract | `qmcp://wq/contract/mail.v1` | `config/reference.json` | Synthetic reference configuration |
| Testing | `qmcp://wq/testing/v1` | `docs/test-cancellation.md` | Evidence guidance |
| Diagnostics | `qmcp://wq/diagnostics/v1` | `docs/validation.md` | Validation and limitations |

Tool results also carry `selectedEnvironment` (`local-simulation` or `bound-development`) and `redaction: default`. The server never returns credentials, tokens, or raw input content through this context. Queue and item reads remain bounded by the existing tool contracts.

This is local protocol evidence. It does not prove host-specific resource rendering, tenant permissions, connector behavior, or live Dataverse results.

