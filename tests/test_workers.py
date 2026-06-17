"""Tests for sub-agent session management, locking, and approvals."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestSubAgentManager:
    def test_create_session_tracks_metadata(self):
        from workers import SubAgentManager

        manager = SubAgentManager()

        session = manager.create_session("analyze parser", worker_type="analysis")

        assert session.prompt == "analyze parser"
        assert session.worker_type == "analysis"
        assert session.status == "pending"
        assert session.id
        assert manager.get_session(session.id) is session

    def test_claim_path_blocks_other_session_until_release(self, tmp_path):
        from workers import ClaimConflictError, SubAgentManager

        manager = SubAgentManager()
        first = manager.create_session("first")
        second = manager.create_session("second")
        claimed = tmp_path / "demo.py"

        manager.claim_paths(first.id, [str(claimed)])

        with pytest.raises(ClaimConflictError):
            manager.claim_paths(second.id, [str(claimed)])

        manager.release_claims(first.id)
        manager.claim_paths(second.id, [str(claimed)])
        assert str(claimed.resolve()) in manager.get_session(second.id).claimed_paths

    def test_complete_session_releases_claims(self, tmp_path):
        from workers import SubAgentManager

        manager = SubAgentManager()
        first = manager.create_session("finish")
        second = manager.create_session("other")
        claimed = tmp_path / "owned.py"

        manager.claim_paths(first.id, [str(claimed)])
        manager.complete_session(first.id, "done")

        manager.claim_paths(second.id, [str(claimed)])
        assert manager.get_session(first.id).status == "done"
        assert manager.get_session(first.id).result == "done"

    def test_request_dangerous_action_blocks_until_approved(self):
        from workers import SubAgentManager

        manager = SubAgentManager()
        session = manager.create_session("rename files")

        request = manager.request_approval(
            session.id,
            action="move",
            reason="broad rename",
            paths=["C:/demo/a.py"],
        )

        assert session.status == "blocked_approval"
        assert session.pending_approval is request

        manager.approve(session.id)
        assert session.status == "pending"
        assert session.pending_approval is None

    def test_deny_dangerous_action_marks_error(self):
        from workers import SubAgentManager

        manager = SubAgentManager()
        session = manager.create_session("delete file")

        manager.request_approval(
            session.id,
            action="delete",
            reason="remove obsolete file",
            paths=["C:/demo/old.py"],
        )
        manager.deny(session.id, "user denied")

        assert session.status == "error"
        assert "user denied" in session.error
        assert session.pending_approval is None


class TestAgentContextLockEnforcement:
    def test_write_file_auto_claims_path_for_current_agent(self, tmp_path, monkeypatch):
        import tools
        from workers import SubAgentManager, use_agent_context

        manager = SubAgentManager()
        owner = manager.create_session("owner")
        target = tmp_path / "auto.txt"

        monkeypatch.setattr(
            tools, "_path_validator", tools.SecurePathValidator(allowed_roots=[str(tmp_path)])
        )

        with use_agent_context(manager, owner.id):
            result = tools.write_file(str(target), "hello")

        assert result.startswith("✓ Wrote")
        assert str(target.resolve()) in manager.get_session(owner.id).claimed_paths

    def test_write_file_blocked_when_another_session_owns_path(self, tmp_path, monkeypatch):
        import tools
        from workers import SubAgentManager, use_agent_context

        manager = SubAgentManager()
        owner = manager.create_session("owner")
        intruder = manager.create_session("intruder")
        target = tmp_path / "locked.txt"

        monkeypatch.setattr(
            tools, "_path_validator", tools.SecurePathValidator(allowed_roots=[str(tmp_path)])
        )
        manager.claim_paths(owner.id, [str(target)])

        with use_agent_context(manager, intruder.id):
            result = tools.write_file(str(target), "hello")

        assert result.startswith("Security error:")
        assert "claimed" in result.lower()

    def test_write_file_allowed_for_claim_owner(self, tmp_path, monkeypatch):
        import tools
        from workers import SubAgentManager, use_agent_context

        manager = SubAgentManager()
        owner = manager.create_session("owner")
        target = tmp_path / "owned.txt"

        monkeypatch.setattr(
            tools, "_path_validator", tools.SecurePathValidator(allowed_roots=[str(tmp_path)])
        )
        manager.claim_paths(owner.id, [str(target)])

        with use_agent_context(manager, owner.id):
            result = tools.write_file(str(target), "hello")

        assert result.startswith("✓ Wrote")
        assert target.read_text(encoding="utf-8") == "hello"

    def test_move_path_requests_approval_for_current_agent(self, tmp_path, monkeypatch):
        import tools
        from workers import SubAgentManager, use_agent_context

        manager = SubAgentManager()
        owner = manager.create_session("rename file")
        source = tmp_path / "from.txt"
        dest = tmp_path / "to.txt"
        source.write_text("payload", encoding="utf-8")

        monkeypatch.setattr(
            tools, "_path_validator", tools.SecurePathValidator(allowed_roots=[str(tmp_path)])
        )

        with use_agent_context(manager, owner.id):
            result = tools.move_path(str(source), str(dest))

        session = manager.get_session(owner.id)
        assert result.startswith("Security error:")
        assert session.status == "blocked_approval"
        assert session.pending_approval is not None
        assert session.pending_approval.action == "move"

    def test_run_bash_delete_command_requests_approval_for_current_agent(self, tmp_path, monkeypatch):
        import tools
        from workers import SubAgentManager, use_agent_context

        manager = SubAgentManager()
        owner = manager.create_session("delete file")
        target = tmp_path / "dead.txt"
        target.write_text("payload", encoding="utf-8")

        monkeypatch.setattr(
            tools, "_path_validator", tools.SecurePathValidator(allowed_roots=[str(tmp_path)])
        )

        with use_agent_context(manager, owner.id):
            result = tools.run_bash(f'del "{target}"')

        session = manager.get_session(owner.id)
        assert result.startswith("Security error:")
        assert session.status == "blocked_approval"
        assert session.pending_approval is not None
        assert session.pending_approval.action == "del"

    def test_run_bash_package_uninstall_requests_approval_for_current_agent(self):
        import tools
        from workers import SubAgentManager, use_agent_context

        manager = SubAgentManager()
        owner = manager.create_session("remove dep")

        with use_agent_context(manager, owner.id):
            result = tools.run_bash("pip uninstall requests -y")

        session = manager.get_session(owner.id)
        assert result.startswith("Security error:")
        assert session.status == "blocked_approval"
        assert session.pending_approval is not None
        assert session.pending_approval.action == "pip uninstall"


class TestWorkerExecution:
    def test_spawn_uses_configured_runner_when_agent_fn_not_provided(self):
        from workers import WorkerPool, configure_worker_runner

        pool = WorkerPool()
        configure_worker_runner(lambda prompt, worker_type, session_id: f"{worker_type}:{prompt}:{session_id}")
        try:
            task = pool.spawn("index repo", worker_type="research", wait=True)
        finally:
            configure_worker_runner(None)
            pool.shutdown()

        assert task.status == "done"
        assert task.result.startswith("research:index repo:")
