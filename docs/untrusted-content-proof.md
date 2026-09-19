# MCP untrusted-content boundary proof

The MCP server projects every successful tool result through a field-based disclosure control before serializing it to the agent host. Credential-shaped fields (`authorization`, tokens, secrets, passwords, credentials, connection strings, cookies and headers) become `[REDACTED]`; raw input/payload/body fields become `[UNTRUSTED_CONTENT_REDACTED]`. The response projection is recursive and applies to nested objects and arrays.

This control protects the response boundary; it does not make remaining business text trustworthy or turn it into instructions. Tool authorization remains determined by the fixed MCP schemas, host-bound environment configuration, runtime role checks and tenant-side guards. In particular, deployment settings, credentials, environment selection, queue grants and destination choices are not accepted from untrusted returned content.

Regression coverage is in `src/mcp/test/redaction.test.js`, with the public MCP session covered by `src/mcp/test/integration.test.js`. Local redaction tests do not establish separate-identity authorization, restricted Dataverse privileges, cross-queue denial in a live tenant, or supply-chain signing/repository controls; those criteria remain open in [P7-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/66) and the linked acceptance gates.
