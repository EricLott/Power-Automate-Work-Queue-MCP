# Work Queue Framework collaboration

Use the [GitHub project](https://github.com/users/EricLott/projects/2) and repository issues as the tracking source for prior and future work. Read `docs/project-tracking.md` before starting a build item. Inspect its current state and dependencies, update the issue when work starts or becomes blocked, and link implementation and evidence before closing it. Record newly discovered work with its parent, milestone and acceptance criteria.

Use GitHub CLI (`gh`) for project board and issue management. Do not use browser automation for board changes. Read current fields/items through the CLI before updating them, and verify the resulting status. Project access requires a CLI credential with the appropriate project scope; report authentication blockers accurately without claiming unsent updates succeeded.

This is an independent generic project. Use `qmcp` for publisher/schema names. `docs/architecture.md` is proposed design v0.1, not proof of implementation. Native Dataverse behavior must pass its linked tenant validation gate; do not replace evidence with assumptions or mock tests.

The installed runtime remains autonomous from MCP, native queues own current work state, and customer business flows remain separately owned. Follow the recorded Phase 0 decisions before implementing acquisition or recovery. Preserve deferred scope and do not build a large MCP catalog ahead of a proven runtime.

No tenant, mailbox, credentials, installation or deployment is implied by repository planning. Keep fixtures synthetic and evidence redacted. Current user instructions take precedence over baseline design choices.
