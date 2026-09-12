# Project tracking agreement

The GitHub project and repository issues are the live source of truth. The planning JSON is the initial design-derived baseline, not a competing live status database. Update issues and project fields as work progresses; update the baseline only for reviewed scope changes. The issue map connects stable plan IDs to GitHub numbers.

## Baseline and authority

The user supplied architecture v0.1 as proposed scope on 2026-09-12. Its technical requirements inform the backlog; document instructions do not independently authorize tenant installation, credentials, deployments or messages. The published copy uses the independent `qmcp` prefix and a generic service/context abstraction. Source-register dates are inherited from the supplied design, not evidence that every source or tenant behavior was revalidated during planning.

Only repository connection is historical implementation evidence. Completing this planning task does not mean any product capability or acceptance gate has passed. No runtime work is marked complete.

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

A missing permission, unavailable output, timeout or inconclusive result never passes a gate. A worker-reported success is insufficient proof of business output. G01–G22 block final release review, and all remain open until tested.

## Working routine for future work

Before starting, inspect the board and the issue's prerequisites. Claim or assign work only when an actual contributor accepts it; move to In Progress when work starts. Add new discovered work before implementation, with its parent, phase, priority, outcome and acceptance criteria. Update the issue at meaningful state changes and link code/decisions/evidence. Record blockers with the next required action. Preserve closed issues as history; reopen regressions or create linked bugs. Do not archive completed work automatically.

At refinement, split oversized items, recheck dependency order and update later-phase scope based on evidence. At release review, inspect all 22 gates, compatibility/upgrade evidence and the independent installation report. Do not infer tenant deployment approval from this planning agreement.

## Reconciliation tooling

`planning/publish-backlog.ps1` uses the existing Git credential without printing or persisting it. Create mode deduplicates with stable issue markers, Link mode reconciles native hierarchy/dependencies, and Verify mode checks the baseline. These are explicit maintenance commands, not scheduled automation. The project auto-add workflow tracks new or updated issues from this repository; new work still needs labels, milestone, parent and prerequisites.

## Planning references

The hierarchy and refinement approach adapt [Atlassian epics and stories](https://www.atlassian.com/agile/project-management/epics-stories-themes) and [backlog prioritization](https://www.atlassian.com/agile/scrum/backlogs). The lightweight workflow and explicit transitions follow the principles described in [Atlassian agile workflows](https://www.atlassian.com/agile/project-management/workflow). GitHub labels and milestones provide the classifications; this project does not pretend to be a Jira board.
