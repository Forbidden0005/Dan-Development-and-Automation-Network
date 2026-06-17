# Sub-Agent Parallelism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable, visible, tool-capable parallel sub-agents with file locking and destructive-action approvals.

**Architecture:** Replace the worker stub with a manager-backed session model, enforce path claims in mutating tools, then expose the new state through CLI commands. Keep the first slice in-process and additive so GUI can consume the same APIs later.

**Tech Stack:** Python 3.11+, pytest, existing tool registry and worker package

---

### Task 1: Add Session And Locking Tests

**Files:**
- Modify: `tests/test_dan.py`
- Create: `tests/test_workers.py`

- [ ] **Step 1: Write failing tests for session lifecycle and path claims**
- [ ] **Step 2: Run targeted worker tests to verify correct failure**
- [ ] **Step 3: Add minimal manager implementation to satisfy lifecycle tests**
- [ ] **Step 4: Re-run targeted tests and keep them green**

### Task 2: Enforce Claims On Mutating Tools

**Files:**
- Modify: `workers/__init__.py`
- Modify: `tools.py`
- Modify: `tool_registry.py` if runtime context helpers are needed
- Modify: `tests/test_dan.py`
- Modify: `tests/test_workers.py`

- [ ] **Step 1: Write failing tests for lock conflicts on write/edit/append/move/copy**
- [ ] **Step 2: Run targeted tool and worker tests to verify failure**
- [ ] **Step 3: Implement runtime claim enforcement with minimal new surface**
- [ ] **Step 4: Re-run targeted tests and keep them green**

### Task 3: Add Approval Blocking For Destructive Actions

**Files:**
- Modify: `workers/__init__.py`
- Modify: `tests/test_workers.py`

- [ ] **Step 1: Write failing tests for blocked approval and explicit approve/deny transitions**
- [ ] **Step 2: Run targeted tests to verify failure**
- [ ] **Step 3: Implement approval request storage and state transitions**
- [ ] **Step 4: Re-run targeted tests and keep them green**

### Task 4: Expose CLI Agent Controls

**Files:**
- Modify: `Dan.py`
- Modify: `tests/test_dan.py`

- [ ] **Step 1: Write failing tests for `/agents`, inspect, and approval command handling**
- [ ] **Step 2: Run targeted CLI tests to verify failure**
- [ ] **Step 3: Implement command handling and output formatting**
- [ ] **Step 4: Re-run targeted CLI tests and keep them green**

### Task 5: Verify And Document

**Files:**
- Modify: `README.md` if agent controls are documented
- Modify: `ROADMAP.md`

- [ ] **Step 1: Run focused pytest selection**
- [ ] **Step 2: Run full pytest suite**
- [ ] **Step 3: Run `python -m ruff check .`**
- [ ] **Step 4: Update roadmap with the actual completed slice**
