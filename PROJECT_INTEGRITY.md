# Project Integrity

This document is mandatory. Apply it before every task, change, refactor, rename, deletion, dependency update, or roadmap edit.

## Primary Rule

Do not blindly execute instructions. Protect the long-term quality of Dan first.

Every requested change must be evaluated against:

- product direction
- architecture
- safety
- maintainability
- reversibility
- release impact
- user trust

## Three-Way Decision Gate

### Category A: Safe Improvement

The change aligns with the roadmap, improves the repo, preserves behavior, and keeps risk contained.

Action: proceed carefully.

### Category B: Risky Change

The change may help, but it introduces notable regression risk, architectural drift, unclear ownership, or maintenance cost.

Action: warn clearly, reduce scope, and prefer the safer path.

### Category C: Project Degradation

The change would lower quality, increase confusion, bypass safeguards, introduce hacks, weaken maintainability, or move the project away from the roadmap.

Action: stop, explain why, and protect the repo from the change.

## Required Analysis Before Work

Before making any non-trivial edit, decide:

1. What problem is actually being solved?
2. Which files and systems are affected?
3. What could break?
4. Does the change fit the current roadmap?
5. Is there a smaller or more reversible version of the same change?
6. Will this still make sense in six months?

If the answer to any of those is weak, the work is not ready.

## Permanent Rules

- Prefer additive, reviewable changes over rewrites.
- Reuse existing systems before creating new ones.
- Do not invent behavior that has not been verified in the code.
- Do not claim health, readiness, or security without evidence.
- Do not delete or move uncertain files just to make the tree look cleaner.
- Archive, quarantine, or document uncertain artifacts first.
- Keep docs and roadmap synchronized with reality.
- If a task completes, update the roadmap before leaving the repo.

## Destructive Action Gate

These require explicit user approval before execution:

- deleting files or folders
- broad renames or moves
- rewriting history
- removing dependencies
- changing auth or secret-handling behavior
- replacing a major subsystem
- changing packaging or release strategy in a way that is hard to undo

For any of those, state:

- what will change
- why it is necessary
- what it touches
- what could break
- what the reversible fallback is

## Documentation Integrity Rules

- `ROADMAP.md` is the canonical direction document.
- `PROJECT_INTEGRITY.md` is the execution gate.
- `README.md` explains the project to humans.
- `ONBOARDING.md` explains how to safely enter the repo.
- `CODEX.md` explains how Codex must behave here.

If those files drift apart, fix that drift before doing unrelated work.

## Definition Of Acceptable Progress

Good progress is not “lots of edits.” Good progress is:

- a clearer repository
- fewer contradictions
- stronger safety boundaries
- better release confidence
- a roadmap that matches reality
- small changes that make future work easier instead of harder
