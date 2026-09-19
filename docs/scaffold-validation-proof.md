# Customer scaffold validation proof

`validate_scaffold` now performs a bounded static safety inspection in addition to template drift and JSON checks. It reports (without pretending to prove runtime behavior):

- direct Create/Update/Delete writes to native queue entities;
- completion actions with no dependency gate; and
- literal production destinations on test-run operations.

The validator also returns explicit limitations for tenant permissions, connector behavior, dynamic expressions, runtime outcomes, and authentication-profile ownership/serialization.

## Reproduction

```powershell
npm test --prefix src/mcp
```

The focused tests cover all three detections and all generated reference flows. Tenant import, customer connector behavior, and dynamic expression evaluation remain separate acceptance work.
