# CODEX.md

This file defines how Codex must operate in this repository.

## Mandatory First Step

Before every single task, change, edit, cleanup, refactor, rename, deletion, review, or roadmap update:

1. Read [ROADMAP.md](/C:/Users/tyler/Desktop/Dan/ROADMAP.md)
2. Read [PROJECT_INTEGRITY.md](/C:/Users/tyler/Desktop/Dan/PROJECT_INTEGRITY.md)
3. Confirm the requested work matches the roadmap and does not violate project integrity

If you have not checked the roadmap first, you are not ready to act.

## Mandatory Last Step

After every completed task in this repository:

1. Update [ROADMAP.md](/C:/Users/tyler/Desktop/Dan/ROADMAP.md)
2. Mark newly completed work in the `Completed` section or move completed items out of active phases
3. Keep the roadmap truthful

Leaving the roadmap stale is a process failure.

## Project Posture

Dan is a local-first Windows development assistant built in Python. Treat it like a long-lived desktop product, not a prototype.

Priorities:

- trust
- explicit behavior
- secure local execution
- maintainability
- Windows usability
- repeatable verification

Do not steer the project toward:

- vague “AI magic”
- uncontrolled autonomy
- speculative rewrites
- cloud dependence without a reason
- release claims that are not backed by verification

## Operating Rules

- Inspect real files before changing them.
- Verify before asserting.
- Prefer small, low-risk changes.
- Preserve working behavior unless it is clearly wrong.
- Do not invent missing architecture.
- Do not delete uncertain files without approval.
- Do not make packaging, dependency, auth, or structural changes casually.
- If docs and code disagree, resolve the mismatch or document it explicitly.

## Required Task Framing For Non-Trivial Work

Before a non-trivial change, briefly state:

- regression risk
- architectural fit
- failure or safety implications
- maintainability impact
- risk level

Then make the smallest safe change.

## Cleanup Rules

For repository cleanup:

- prefer archive or quarantine over deletion
- do not remove historical artifacts unless their lack of value is verified
- record uncertain cleanup candidates in the roadmap backlog
- keep filenames, folder roles, and ownership explicit

## Production Readiness Rules

Do not call Dan production-ready just because tests pass.

Production-ready here means at minimum:

- docs are coherent
- Windows packaging is defined
- startup behavior is predictable
- security boundaries are explicit
- release verification is repeatable
- the roadmap reflects reality

Until then, say exactly what is done and what is not.
