"""Worker pool — parallel sub-agent delegation."""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from typing import Any

import tool_registry as registry
from config import MAX_WORKERS, MAX_WORKER_DEPTH

logger = logging.getLogger(__name__)


@dataclass
class WorkerTask:
    """A worker task."""

    id: str
    prompt: str
    status: str = "pending"  # pending, running, done, error
    result: str = ""
    worker_type: str = "general"


class WorkerPool:
    """Manages a pool of sub-agent workers."""

    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self._tasks: dict[str, WorkerTask] = {}
        self._lock = threading.Lock()

    def spawn(
        self, prompt: str, worker_type: str = "general", wait: bool = False, agent_fn: Any = None
    ) -> WorkerTask:
        """Spawn a worker task."""
        task = WorkerTask(
            id=uuid.uuid4().hex[:8],
            prompt=prompt,
            worker_type=worker_type,
        )

        with self._lock:
            self._tasks[task.id] = task

        if agent_fn:
            future = self._pool.submit(self._run_worker, task, agent_fn)
            if wait:
                future.result()  # block until done
        else:
            task.status = "error"
            task.result = "No agent function provided"

        return task

    def _run_worker(self, task: WorkerTask, agent_fn: Any) -> None:
        """Run a worker in a thread."""
        task.status = "running"
        try:
            result = agent_fn(task.prompt)
            task.result = result
            task.status = "done"
        except Exception as e:
            task.result = f"Error: {e}"
            task.status = "error"
            logger.error("Worker %s failed: %s", task.id, e)

    def get_task(self, task_id: str) -> WorkerTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[WorkerTask]:
        return list(self._tasks.values())

    def shutdown(self):
        self._pool.shutdown(wait=False)


# Global pool
_pool = WorkerPool()


def get_pool() -> WorkerPool:
    return _pool


# ── Tool Handlers ────────────────────────────────────────────────────────────


def _spawn(prompt: str, worker_type: str = "general", wait: bool = False) -> str:
    task = _pool.spawn(prompt, worker_type, wait=wait)
    if wait and task.status == "done":
        return f"Worker {task.id} completed:\n{task.result}"
    return f"Spawned worker {task.id} ({worker_type}). Use CheckWorker to get results."


def _check_worker(task_id: str) -> str:
    task = _pool.get_task(task_id)
    if not task:
        return f"No worker found: {task_id}"
    lines = [f"Worker {task.id}: {task.status}"]
    if task.result:
        lines.append(task.result)
    return "\n".join(lines)


def _list_workers() -> str:
    tasks = _pool.list_tasks()
    if not tasks:
        return "No workers."
    lines = []
    for t in tasks:
        lines.append(f"  {t.id}  {t.status:8s}  {t.worker_type:10s}  {t.prompt[:50]}")
    return "\n".join(lines)


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
    )

    registry.register(
        name="ListWorkers",
        description="List all worker tasks.",
        parameters={"type": "object", "properties": {}},
        handler=_list_workers,
        category="workers",
    )
