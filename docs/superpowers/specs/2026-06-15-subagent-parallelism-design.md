# Sub-Agent Parallelism Design

## Goal

Give Dan the ability to spawn durable, visible, tool-capable sub-agents that can work in parallel on the same workspace without touching the same files at the same time.

## Non-Negotiable Requirements

- Sub-agents share the parent agent's workspace and filesystem permissions.
- Sub-agents may use tools and modify files on their own by default.
- Destructive actions still require user approval.
- A file or directory claimed by one agent cannot be mutated by another until the claim is released.
- Agent state must be durable and visible during the session.

## Architecture

Dan already has a worker package, but the current implementation is only a thread pool plus task records. It does not run real sub-agents. The replacement design adds a real in-process coordination layer:

- `SubAgentManager`
  - owns all agent sessions
  - owns file and directory claims
  - owns destructive-action approvals
  - exposes inspection and listing APIs for CLI and GUI
- `SubAgentSession`
  - durable per-agent state
  - isolated message history
  - status, event log, claimed paths, final output, and pending approval state
- `WorkerPool`
  - remains the execution runner
  - runs actual agent functions instead of inert prompt stubs
  - delegates session creation and mutation control to `SubAgentManager`

This keeps the first implementation in-process and additive. If stronger crash isolation is needed later, the manager contract can stay stable while the executor changes from threads to subprocesses.

## Session Model

Each sub-agent session needs:

- `id`
- `parent_id` or parent task marker
- `prompt`
- `worker_type`
- `status`
  - `pending`
  - `running`
  - `blocked_approval`
  - `done`
  - `error`
  - `cancelled`
- `message_history`
- `claimed_paths`
- `events`
- `result`
- `error`
- `created_at`
- `started_at`
- `finished_at`

The manager is the source of truth. `WorkerPool` stores runnable futures, not authoritative business state.

## Locking Model

Locking is path-based and manager-owned.

### Rules

- An agent must claim paths before mutating them.
- Claims are visible immediately to all other agents.
- A claimed file blocks write, edit, append, move, copy-to, delete, and directory creation beneath it by any other agent.
- A claimed directory blocks new child claims by any other agent.
- Read-only actions stay allowed.
- Claims can be expanded during execution, but only through the manager.
- Claims release automatically on completion, cancellation, or error.

### Conflict Policy

- File claims are preferred over broad directory claims whenever possible.
- Same-agent overlapping claims are allowed.
- Different-agent overlapping claims are rejected with a clear conflict error naming the owner.

## Tool Enforcement

The lock system must be enforced where mutations actually happen, not only in prompts.

Mutating tools in `tools.py` should consult a runtime agent context before acting:

- `Write`
- `Edit`
- `Append`
- `Move`
- `Copy`

Non-file elevated tools should also participate:

- `Bash`
- `code_execution` tools

For the first slice, file-mutation lock enforcement is mandatory. Shell and code-execution escalation should be wired into approval and audit context first, with deeper filesystem intent parsing left for a later pass.

## Approval Model

Destructive actions remain approval-gated even when the acting sub-agent owns the file claim.

First-slice destructive actions:

- delete
- broad move/rename
- dependency removal
- auth or secret-handling changes
- config mutations explicitly marked sensitive

The manager stores a pending approval request on the session. The session moves to `blocked_approval` until the user approves or denies it.

## Visibility

### CLI

Add session-aware agent controls:

- `/agents`
- `/agent inspect <id>`
- `/agent cancel <id>`
- `/agent approve <id>`
- `/agent deny <id>`

The existing `/workers` view can remain as a compatibility alias to `/agents`.

### GUI

The GUI should consume the same manager APIs. The first slice does not need a full custom pane if that would slow the core implementation, but the manager must expose enough state for a dedicated pane to be added cleanly.

## Auditability

Agent-aware tool calls should include agent identity in the runtime event stream. The first slice should add session event logging in the manager even if the JSONL audit log remains tool-name focused for now.

## Failure Handling

- Unhandled sub-agent exceptions mark the session `error`.
- Errors release claims deterministically.
- Cancellation marks the session `cancelled` and releases claims.
- Shutdown should terminate the pool and release all claims.

## Scope Of First Implementation Slice

Included:

- manager-owned durable sub-agent sessions
- real worker execution using agent functions
- path claims and conflict checks
- destructive approval gate for sub-agents
- CLI visibility and control
- tests for locking, approvals, and session lifecycle

Deferred:

- full GUI agent pane
- nested sub-agent spawning
- subprocess isolation
- shell command path-intent parsing strong enough to lock arbitrary file targets from free-form commands

## Risks

- concurrent session state corruption if manager locking is weak
- tool enforcement gaps if mutation paths bypass the manager
- approval deadlocks if blocked sessions are not surfaced clearly
- user trust loss if claims are invisible or stale

## Acceptance Criteria

- Dan can spawn multiple real sub-agents that run in parallel.
- Each sub-agent has an ID, status, result, event log, and claimed paths.
- Two agents cannot mutate the same claimed file or directory concurrently.
- Destructive actions by sub-agents pause for user approval.
- CLI can list, inspect, and approve or deny sub-agent work.
