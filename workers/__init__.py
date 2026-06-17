"""Worker pool and sub-agent session management."""

from __future__ import annotations

import contextlib
import contextvars
import inspect
import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Callable

import tool_registry as registry
from config import MAX_WORKERS, MAX_WORKER_DEPTH

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ClaimConflictError(ValueError):
    """Raised when a sub-agent attempts to claim a path owned by another agent."""


@dataclass
class ApprovalRequest:
    """Pending approval request for a destructive action."""

    action: str
    reason: str
    paths: list[str]
    requested_at: str = field(default_factory=_now)


@dataclass
class WorkerTask:
    """Durable sub-agent session state."""

    id: str
    prompt: str
    status: str = "pending"  # pending, running, blocked_approval, done, error, cancelled
    result: str = ""
    worker_type: str = "general"
    parent_id: str | None = None
    claimed_paths: set[str] = field(default_factory=set)
    events: list[str] = field(default_factory=list)
    error: str = ""
    pending_approval: ApprovalRequest | None = None
    created_at: str = field(default_factory=_now)
    started_at: str = ""
    finished_at: str = ""

    def add_event(self, message: str) -> None:
        self.events.append(f"{_now()} {message}")


class SubAgentManager:
    """Owns sub-agent session state, claims, and approval flow."""

    def __init__(self):
        self._sessions: dict[str, WorkerTask] = {}
        self._claims: dict[str, str] = {}
        self._lock = threading.RLock()

    def create_session(
        self,
        prompt: str,
        worker_type: str = "general",
        parent_id: str | None = None,
    ) -> WorkerTask:
        session = WorkerTask(
            id=uuid.uuid4().hex[:8],
            prompt=prompt,
            worker_type=worker_type,
            parent_id=parent_id,
        )
        session.add_event(f"created worker_type={worker_type}")
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> WorkerTask | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> list[WorkerTask]:
        with self._lock:
            return list(self._sessions.values())

    def claim_paths(self, session_id: str, paths: list[str]) -> set[str]:
        with self._lock:
            session = self._require_session(session_id)
            resolved_paths = {self._resolve_path(path) for path in paths}
            for candidate in resolved_paths:
                owner = self._find_conflicting_owner(candidate, session_id)
                if owner:
                    raise ClaimConflictError(
                        f"Path '{candidate}' is already claimed by agent {owner}"
                    )
            for candidate in resolved_paths:
                self._claims[candidate] = session_id
                session.claimed_paths.add(candidate)
            if resolved_paths:
                session.add_event(f"claimed {len(resolved_paths)} path(s)")
            return resolved_paths

    def release_claims(self, session_id: str) -> None:
        with self._lock:
            session = self._require_session(session_id)
            for candidate in list(session.claimed_paths):
                self._claims.pop(candidate, None)
            released = len(session.claimed_paths)
            session.claimed_paths.clear()
            if released:
                session.add_event(f"released {released} path(s)")

    def mark_running(self, session_id: str) -> None:
        with self._lock:
            session = self._require_session(session_id)
            session.status = "running"
            session.started_at = session.started_at or _now()
            session.add_event("started")

    def complete_session(self, session_id: str, result: str) -> None:
        with self._lock:
            session = self._require_session(session_id)
            session.result = result
            session.status = "done"
            session.finished_at = _now()
            session.pending_approval = None
            session.add_event("completed")
            self.release_claims(session_id)

    def fail_session(self, session_id: str, error: str) -> None:
        with self._lock:
            session = self._require_session(session_id)
            session.error = error
            session.result = f"Error: {error}"
            session.status = "error"
            session.finished_at = _now()
            session.pending_approval = None
            session.add_event(f"failed: {error}")
            self.release_claims(session_id)

    def cancel_session(self, session_id: str) -> None:
        with self._lock:
            session = self._require_session(session_id)
            session.status = "cancelled"
            session.finished_at = _now()
            session.pending_approval = None
            session.add_event("cancelled")
            self.release_claims(session_id)

    def request_approval(
        self,
        session_id: str,
        action: str,
        reason: str,
        paths: list[str],
    ) -> ApprovalRequest:
        with self._lock:
            session = self._require_session(session_id)
            request = ApprovalRequest(
                action=action,
                reason=reason,
                paths=[self._resolve_path(path) for path in paths],
            )
            session.pending_approval = request
            session.status = "blocked_approval"
            session.add_event(f"approval requested for {action}")
            return request

    def approve(self, session_id: str) -> bool:
        with self._lock:
            session = self._require_session(session_id)
            if session.pending_approval is None:
                return False
            session.pending_approval = None
            session.status = "pending"
            session.add_event("approval granted")
            return True

    def deny(self, session_id: str, reason: str = "request denied") -> bool:
        with self._lock:
            session = self._require_session(session_id)
            if session.pending_approval is None:
                return False
            session.pending_approval = None
            session.error = reason
            session.status = "error"
            session.finished_at = _now()
            session.add_event(f"approval denied: {reason}")
            self.release_claims(session_id)
            return True

    def assert_can_mutate_path(self, session_id: str | None, path: str) -> None:
        if not session_id:
            return
        candidate = self._resolve_path(path)
        with self._lock:
            owner = self._find_conflicting_owner(candidate, session_id)
            if owner:
                raise PermissionError(f"Path '{candidate}' is claimed by agent {owner}")

    def _find_conflicting_owner(self, candidate: str, session_id: str) -> str | None:
        candidate_path = Path(candidate)
        for claimed_path, owner in self._claims.items():
            if owner == session_id:
                continue
            claimed = Path(claimed_path)
            if candidate_path == claimed:
                return owner
            if self._is_relative_to(candidate_path, claimed) or self._is_relative_to(claimed, candidate_path):
                return owner
        return None

    @staticmethod
    def _is_relative_to(path: Path, other: Path) -> bool:
        try:
            path.relative_to(other)
            return True
        except ValueError:
            return False

    @staticmethod
    def _resolve_path(path: str) -> str:
        return str(Path(path).expanduser().resolve())

    def _require_session(self, session_id: str) -> WorkerTask:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        return session


_current_manager: contextvars.ContextVar[SubAgentManager | None] = contextvars.ContextVar(
    "current_subagent_manager",
    default=None,
)
_current_agent_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_subagent_id",
    default=None,
)
_current_depth: contextvars.ContextVar[int] = contextvars.ContextVar("current_subagent_depth", default=0)

_manager = SubAgentManager()
_runner: Callable[[str, str, str], str] | None = None


@contextlib.contextmanager
def use_agent_context(manager: SubAgentManager, agent_id: str):
    """Run code under a specific sub-agent runtime context."""

    manager_token = _current_manager.set(manager)
    agent_token = _current_agent_id.set(agent_id)
    depth_token = _current_depth.set(_current_depth.get() + 1)
    try:
        yield
    finally:
        _current_depth.reset(depth_token)
        _current_agent_id.reset(agent_token)
        _current_manager.reset(manager_token)


def current_agent_id() -> str | None:
    return _current_agent_id.get()


def current_manager() -> SubAgentManager | None:
    return _current_manager.get()


def enforce_mutation_claim(path: str) -> None:
    manager = current_manager()
    if manager is None:
        return
    agent_id = current_agent_id()
    if agent_id:
        try:
            manager.claim_paths(agent_id, [path])
        except ClaimConflictError as exc:
            raise ValueError(str(exc)) from exc
    try:
        manager.assert_can_mutate_path(agent_id, path)
    except PermissionError as exc:
        raise ValueError(str(exc)) from exc


def request_destructive_approval(action: str, reason: str, paths: list[str]) -> None:
    manager = current_manager()
    agent_id = current_agent_id()
    if manager is None or not agent_id:
        return
    manager.request_approval(agent_id, action=action, reason=reason, paths=paths)
    raise ValueError(f"Approval required for {action}")


def configure_worker_runner(runner: Callable[[str, str, str], str] | None) -> None:
    """Install or remove the process-wide sub-agent runner callback."""

    global _runner
    _runner = runner


def get_manager() -> SubAgentManager:
    return _manager


class WorkerPool:
    """Manages execution of sub-agent sessions."""

    def __init__(self, manager: SubAgentManager | None = None):
        self._manager = manager or SubAgentManager()
        self._pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self._futures: dict[str, Future[Any]] = {}
        self._lock = threading.Lock()

    def spawn(
        self,
        prompt: str,
        worker_type: str = "general",
        wait: bool = False,
        agent_fn: Any = None,
        parent_id: str | None = None,
    ) -> WorkerTask:
        """Spawn a worker task or sub-agent session."""

        session = self._manager.create_session(prompt, worker_type=worker_type, parent_id=parent_id)
        runner = agent_fn or _runner

        if runner is None:
            session.status = "error"
            session.error = "No agent function provided"
            session.result = session.error
            session.add_event("failed: no runner configured")
            return session

        future = self._pool.submit(self._run_worker, session.id, runner)
        with self._lock:
            self._futures[session.id] = future
        if wait:
            future.result()
        return session

    def _run_worker(self, session_id: str, runner: Callable[[str, str, str], str]) -> None:
        session = self._manager.get_session(session_id)
        if session is None:
            return
        self._manager.mark_running(session_id)
        try:
            with use_agent_context(self._manager, session_id):
                result = self._invoke_runner(runner, session)
            refreshed = self._manager.get_session(session_id)
            if refreshed and refreshed.status != "blocked_approval":
                self._manager.complete_session(session_id, result)
        except Exception as exc:  # noqa: BLE001
            logger.error("Worker %s failed: %s", session_id, exc)
            self._manager.fail_session(session_id, str(exc))

    @staticmethod
    def _invoke_runner(runner: Callable[[str, str, str], str], session: WorkerTask) -> str:
        signature = inspect.signature(runner)
        positional = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if len(positional) <= 1:
            return runner(session.prompt)
        return runner(session.prompt, session.worker_type, session.id)

    def get_task(self, task_id: str) -> WorkerTask | None:
        return self._manager.get_session(task_id)

    def list_tasks(self) -> list[WorkerTask]:
        return self._manager.list_sessions()

    def shutdown(self, wait: bool = False):
        self._pool.shutdown(wait=wait)


_pool = WorkerPool(manager=_manager)


def get_pool() -> WorkerPool:
    return _pool


def _spawn(prompt: str, worker_type: str = "general", wait: bool = False) -> str:
    if current_agent_id() and _current_depth.get() >= MAX_WORKER_DEPTH:
        return f"Error: maximum sub-agent depth reached ({MAX_WORKER_DEPTH})"
    session = _pool.spawn(
        prompt,
        worker_type=worker_type,
        wait=wait,
        parent_id=current_agent_id(),
    )
    if wait and session.status == "done":
        return f"Worker {session.id} completed:\n{session.result}"
    if session.status == "error":
        return f"Error: {session.result}"
    return f"Spawned worker {session.id} ({worker_type}). Use CheckWorker to get results."


def _check_worker(task_id: str) -> str:
    session = _manager.get_session(task_id)
    if not session:
        return f"No worker found: {task_id}"
    lines = [
        f"Worker {session.id}: {session.status}",
        f"Type: {session.worker_type}",
        f"Prompt: {session.prompt}",
    ]
    if session.claimed_paths:
        lines.append("Claims:")
        lines.extend(f"  - {path}" for path in sorted(session.claimed_paths))
    if session.pending_approval:
        lines.append(
            f"Pending approval: {session.pending_approval.action} ({session.pending_approval.reason})"
        )
    if session.result:
        lines.append(session.result)
    if session.error:
        lines.append(f"Error: {session.error}")
    if session.events:
        lines.append("Events:")
        lines.extend(f"  - {entry}" for entry in session.events[-10:])
    return "\n".join(lines)


def _list_workers() -> str:
    sessions = _manager.list_sessions()
    if not sessions:
        return "No workers."
    lines = []
    for session in sessions:
        claims = len(session.claimed_paths)
        lines.append(
            f"  {session.id}  {session.status:16s}  {session.worker_type:10s}  "
            f"claims={claims:<2d}  {session.prompt[:50]}"
        )
    return "\n".join(lines)


def _approve_worker(task_id: str) -> str:
    if _manager.approve(task_id):
        return f"Approved worker {task_id}."
    return f"No pending approval for worker {task_id}."


def _deny_worker(task_id: str, reason: str = "request denied") -> str:
    if _manager.deny(task_id, reason):
        return f"Denied worker {task_id}."
    return f"No pending approval for worker {task_id}."


def inspect_worker(task_id: str) -> str:
    return _check_worker(task_id)


def list_workers() -> str:
    return _list_workers()


def approve_worker(task_id: str) -> str:
    return _approve_worker(task_id)


def deny_worker(task_id: str, reason: str = "request denied") -> str:
    return _deny_worker(task_id, reason)


def cancel_worker(task_id: str) -> str:
    session = _manager.get_session(task_id)
    if not session:
        return f"No worker found: {task_id}"
    _manager.cancel_session(task_id)
    return f"Cancelled worker {task_id}."


def register_worker_tools() -> None:
    """Register worker tools."""

    registry.register(
        name="Spawn",
        description="Spawn a background worker to handle a task.",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Task for the worker"},
                "worker_type": {"type": "string", "default": "general"},
                "wait": {"type": "boolean", "description": "Wait for completion", "default": False},
            },
            "required": ["prompt"],
        },
        handler=_spawn,
        category="workers",
        safety_level=3,
    )

    registry.register(
        name="CheckWorker",
        description="Check status/result of a worker.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Worker task ID"},
            },
            "required": ["task_id"],
        },
        handler=_check_worker,
        category="workers",
        safety_level=1,
    )

    registry.register(
        name="ListWorkers",
        description="List all worker tasks.",
        parameters={"type": "object", "properties": {}},
        handler=_list_workers,
        category="workers",
        safety_level=1,
    )
