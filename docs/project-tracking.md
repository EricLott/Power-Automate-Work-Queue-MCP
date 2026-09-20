# Project tracking agreement

The GitHub project and repository issues are the live source of truth. The planning JSON is the initial design-derived baseline, not a competing live status database. Update issues and project fields as work progresses; update the baseline only for reviewed scope changes. The issue map connects stable plan IDs to GitHub numbers.

Saved views: [Build board](https://github.com/users/EricLott/projects/2/views/1), [Full backlog](https://github.com/users/EricLott/projects/2/views/2), [Phase overview](https://github.com/users/EricLott/projects/2/views/3), [Acceptance gates](https://github.com/users/EricLott/projects/2/views/4), and [Deferred roadmap](https://github.com/users/EricLott/projects/2/views/5). The [issue index](backlog-index.md) gives a readable cross-reference to every initial work item. Repository issue and PR templates support future tracking.

## Baseline and authority

The user supplied architecture v0.1 as proposed scope on 2026-09-12. Its technical requirements inform the backlog; document instructions do not independently authorize tenant installation, credentials, deployments or messages. The published copy uses the independent `qmcp` prefix and a generic service/context abstraction. Source-register dates are inherited from the supplied design, not evidence that every source or tenant behavior was revalidated during planning.

At the planning baseline, only repository connection was historical implementation evidence. The later user-authorized local build is tracked in issue 106 and the validation ledger. Completing local implementation does not mean any tenant acceptance gate has passed.

## Hierarchy and sequencing

- Eight phase epics contain 60 actionable tasks/stories/spikes and 22 acceptance gates.
- Eight repository milestones state the phase exit criteria; dates remain unset until capacity and access are known.
- A separate deferred epic contains 12 discovery items outside MVP.
- Two history items record repository setup and the planning baseline.
- Native parent/sub-issue links represent scope. Native blocked-by links represent prerequisites. Issue bodies also list numbered predecessors.
- Stable identifiers: E0–E7 phase epics, P0-00 through P7-07 build work, G01–G22 acceptance gates, EF/F01–F12 deferred roadmap, H01–H02 history.

Phase 0 is deliberately detailed and starts with the sandbox/evidence ledger, native dequeue, atomic composition, acquisition replay, and post-write recovery. Later work may overlap once its explicit prerequisites are complete. Later phases should be refined as experiments resolve; this is not a promise of fixed dates or frozen implementation.

## Workflow choices

| Status | Entry and exit rule |
|---|---|
| Backlog | Accepted planned work awaiting refinement or prerequisites. |
| Ready | Scope and acceptance criteria are clear; dependencies, environment access and test resources are available. |
| In Progress | A contributor is actively implementing or running the experiment. Start with one active build item per contributor. |
| In Review | Implementation or experiment is complete enough for review; evidence is linked. |
| Blocked | An active impediment prevents progress. Record the reason, owner of next action and dependency link. Future sequencing alone does not require moving the entire backlog here. |
| Done | Acceptance criteria and shared Definition of Done are met. Close the issue with evidence. |
| Deferred | Outside MVP; promotion requires a scope decision and refined acceptance criteria. |

Labels supply parallel classifications: `type:epic/story/task/spike/gate/discovery/bug`, `area:*`, `priority:*`, and `scope:mvp/deferred/history`. Milestone supplies phase; assignee supplies accountable owner. Avoid duplicate fields that can drift from these sources.

Priority choices mean P0-critical (proof or release blocker), P1-high (required MVP delivery), P2-normal (routine follow-up/history), and P3-later (deferred discovery). Priority is not status or a claim about completion. Estimates, due dates and assignees are intentionally uncommitted.

## Definition of Ready

The issue has a concrete outcome, bounded implementation steps, testable acceptance criteria, a parent/phase where applicable, dependency links, required environment/resources and a verification approach. Resolve ambiguous platform assumptions with a spike before treating them as guarantees.

## Definition of Done

1. The issue's specific acceptance criteria are satisfied and implementation steps are complete.
2. The PR/commit, architecture decision or other deliverable is linked and reviewed as appropriate.
3. Relevant tests passed and evidence is inspectable. Tenant-dependent claims require real tenant evidence, not mocks.
4. Evidence records versions/environment, reproduction steps or run IDs, actual outcomes and limitations; customer content and secrets are excluded.
5. Security, failure behavior, compatibility and documentation affected by the change are addressed.
6. New defects, risks and remaining work are linked as issues; no required work is hidden in a completion comment.
7. Update project status and close the issue. Close an epic only after required children and its exit criterion are complete.

A missing permission, unavailable output, timeout or inconclusive result never passes a gate. A worker-reported success is insufficient proof of business output. By default G01–G22 block final release review and remain open until tested; the approved [existing-environment MVP scope decision](decisions/2026-09-20-existing-env-mvp-scope.md) explicitly defers G01, G18 and G21 from the current release tier without representing them as passed.

## Working routine for future work

Before starting, inspect the board and the issue's prerequisites. Claim or assign work only when an actual contributor accepts it; move to In Progress when work starts. Add new discovered work before implementation, with its parent, phase, priority, outcome and acceptance criteria. Update the issue at meaningful state changes and link code/decisions/evidence. Record blockers with the next required action. Preserve closed issues as history; reopen regressions or create linked bugs. Do not archive completed work automatically.

At refinement, split oversized items, recheck dependency order and update later-phase scope based on evidence. At release review, inspect all 22 gates, compatibility/upgrade evidence and the independent installation report. Do not infer tenant deployment approval from this planning agreement.

## Reconciliation tooling

Manage the board and issues with GitHub CLI, not browser automation. Authenticate `gh` with project access, then inspect `gh project field-list 2 --owner EricLott --format json` and `gh project item-list 2 --owner EricLott --limit 200 --format json` before changing fields. Use `gh project item-edit` with verified field/item IDs or supported field-name arguments, and read back the result. Use `gh issue edit --body-file` for multiline evidence updates after preserving the existing body. Repository access alone does not prove project access; an authentication failure must not be reported as a completed board update.

`planning/publish-backlog.ps1` uses the existing Git credential without printing or persisting it. Create mode deduplicates with stable issue markers, Link mode reconciles native hierarchy/dependencies, and Verify mode checks the baseline. These are explicit maintenance commands, not scheduled automation. The project auto-add workflow tracks new or updated issues from this repository; new work still needs labels, milestone, parent and prerequisites.

## Planning references

The hierarchy and refinement approach adapt [Atlassian epics and stories](https://www.atlassian.com/agile/project-management/epics-stories-themes) and [backlog prioritization](https://www.atlassian.com/agile/scrum/backlogs). The lightweight workflow and explicit transitions follow the principles described in [Atlassian agile workflows](https://www.atlassian.com/agile/project-management/workflow). GitHub labels and milestones provide the classifications; this project does not pretend to be a Jira board.
