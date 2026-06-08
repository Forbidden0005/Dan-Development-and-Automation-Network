# Dan Security Boundaries

This document describes Dan's local execution model, what is restricted by default, and what is permitted. Read this before changing tool behavior, command execution, secret handling, or path validation.

---

## Execution Model

Dan runs entirely on the local machine. There is no cloud relay, no remote execution, and no data exfiltration by design. All tool execution happens in-process or via controlled subprocesses on the user's machine.

This is a trust-by-default model for the local user's own environment, not a sandboxed environment for untrusted code.

---

## Path Validation

**Implemented in:** `security_utils.SecurePathValidator`  
**Used by:** `tools_secure.py` for all file read/write/search operations

All file paths provided to tools are:

1. Resolved to an absolute path via `Path.expanduser().resolve()`
2. Verified to be inside an allowed root directory (default: the current working directory)
3. Rejected with a `ValueError` if the resolved path escapes the allowed roots

This prevents directory traversal attacks (e.g., `../../etc/passwd`).

The allowed roots default to `Path.cwd()` at startup. This is appropriate for the project-local tool context. If Dan is running from the user's home directory or drive root, the effective scope is wider — this is an acceptable tradeoff for a local desktop tool operating on the user's own files.

**Security note:** The path validator does not restrict symlinks beyond resolving them. A symlink that resolves inside the allowed root is permitted.

---

## Command Execution

**Implemented in:** `security_utils.SecureCommandExecutor`  
**Used by:** `tools_secure.py` for the shell tool

Command execution is controlled by two mechanisms applied in order:

### 1. Shell operator rejection

Commands containing unquoted shell control characters (`|`, `>`, `<`, `&`, `;`, `` ` ``) are rejected. The executor does not use `shell=True` for commands without shell features.

### 2. Command allowlist

Only commands in `SAFE_COMMANDS` (defined in `SecureCommandExecutor`) are permitted when the executor is initialized with `use_whitelist=True` (the default).

The allowlist includes:

- **File operations:** `ls`, `cat`, `cp`, `mv`, `rm`, `mkdir`, `find`, `dir`, `type`, `del`, `robocopy`, etc.
- **Text processing:** `grep`, `awk`, `sed`, `sort`, `diff`, `findstr`, etc.
- **Development:** `git`, `python`, `py`, `pip`, `npm`, `pytest`, `ruff`, `cargo`, `make`, etc.
- **System info (read-only):** `ps`, `df`, `whoami`, `hostname`, `tasklist`, `systeminfo`, etc.
- **Archives:** `tar`, `zip`, `unzip`
- **Network (limited):** `ping`, `curl`, `wget`, `nslookup`

**Known limitation:** `powershell` and `cmd` are in the allowlist, which means the allowlist is not a hard sandbox — a user could ask Dan to run `powershell -Command "rm -rf /"`. The allowlist is a first-pass safety gate for LLM-generated commands, not a security boundary against deliberate user abuse. The user is running Dan with their own credentials on their own machine.

### 3. Dangerous pattern blocking

A set of regex patterns blocks known-dangerous constructs regardless of the allowlist:
- `rm -rf /`, `mkfs`, `dd if=/dev/zero`, `format`
- Privilege escalation: `sudo`, `su root`, `chmod 777`
- Fork bombs, infinite loops
- `export PATH=`, `unset PATH`
- etc.

---

## Secret Handling

Dan does not store API keys. Provider API keys are:

- Read from environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `VENICE_API_KEY`)
- Or read from a local `.env` file at the project root (not committed to git; listed in `.gitignore`)
- Never written to disk by Dan itself

**What is stored in `%APPDATA%\Dan\`:** session history (chat messages), knowledge embeddings, and auth-system metadata. No API keys or raw credentials are stored there.

**`.env` hygiene:** The `.env` file is gitignored. Users should never commit it.

**Secret scanning:** `scripts/scan_secrets.py` scans all Git-tracked files for common secret patterns (Anthropic, OpenAI, and Venice API keys, AWS Access Key IDs, and generic high-entropy credential assignments). Run it manually or integrate it into CI with `python scripts/scan_secrets.py`. Exit code 0 means clean; exit code 1 means findings. Individual lines can be suppressed with a trailing `# noqa: scan-secrets` comment for confirmed false positives. The test `test_scan_secrets_finds_no_real_secrets_in_tracked_files` in `tests/test_repo_hygiene.py` runs this check automatically as part of the test suite.

---

## Tool Safety Levels

Tools are organized into three implicit safety levels:

### Level 1 — Always safe (read-only, no side effects)

These tools read information but cannot modify state:

- File read: `read_file`, `list_files`, `search_files`, `grep`
- System info: `get_system_info`, `list_processes`, `repo_health`
- Knowledge read: `knowledge_search`, `knowledge_list`
- Project index: `index_project`, `get_project_structure`

### Level 2 — Standard (reversible or low-risk writes)

These tools modify state but the changes are visible and typically reversible:

- File write/edit: `write_file`, `edit_file`, `create_directory`
- Git: `git_status`, `git_diff`, `git_add`, `git_commit` (commit is logged in git history)
- Session management: `save_session`, `load_session`
- Web fetch: `fetch_url`, `search_web` (outbound read, no local mutation)

### Level 3 — Elevated (shell execution, potential for destructive effects)

These tools execute arbitrary subprocess commands within the allowlist:

- Shell execution: `bash`, `run_command`
- Code execution: `execute_python`, `run_code`
- Worker dispatch: `create_worker`, `dispatch_task`

Level 3 tools pass through `SecureCommandExecutor` validation but are inherently more powerful.

**Confirmation gate:** A consent callback can be installed at runtime via `tool_registry.set_confirmation_gate(fn)`. When installed, the gate is invoked before any Level 3 tool executes. The callback receives `(tool_name, tool_input, safety_level)` and returns `True` to allow or `False` to deny. Denying a tool call records a `"denied"` entry in the audit log and returns an error string to the caller. The gate is not installed by default — existing CLI and GUI sessions are unaffected. To add a gate, call `set_confirmation_gate` at session startup. Example:

```python
def cli_gate(tool_name, tool_input, safety_level):
    answer = input(f"Allow {tool_name}? [y/N] ")
    return answer.strip().lower() == "y"

tool_registry.set_confirmation_gate(cli_gate)
```

### Optional tool families (not loaded by default without dependencies)

These are registered only when their import succeeds:

- `auth_tools` — local auth-state management
- `image_tools` — image read/OCR (requires `Pillow`, `pytesseract`, etc.)
- `ml_tools` — local ML inference (requires `pandas`, `sklearn`, etc.)

---

## URL Validation

**Implemented in:** `security_utils.validate_fetch_url`  
**Used by:** web fetch tools

Outbound HTTP(S) fetches validate the target URL before executing:

- Only `http` and `https` schemes are permitted
- Loopback (`127.0.0.1`, `localhost`), link-local, private network, multicast, and reserved addresses are blocked unless `allow_local=True` is explicitly passed
- Redirects are re-validated via `validate_redirect_url` before following

---

## Input Sanitization

**Implemented in:** `security_utils.sanitize_user_input`

User input fed into tools is:
- Length-checked (default max 10,000 characters)
- Stripped of null bytes and C0/C1 control characters (except newlines and tabs)
- Normalized for excessive consecutive newlines

---

## Tool Audit Log

**Implemented in:** `security_utils.ToolAuditLog`
**Wired by:** `tool_registry.execute_tool`

Every tool invocation appends one JSON-lines entry to `%APPDATA%\Dan\tool_audit.log` (or `~/.dan/tool_audit.log` on non-Windows). Each entry records:

- `timestamp` — ISO-8601 UTC
- `tool_name` — name of the tool
- `input_keys` — parameter *names* only (never values, which may be sensitive)
- `safety_level` — declared level of the tool (1, 2, or 3)
- `outcome` — `"success"`, `"error"`, or `"denied"`
- `duration_ms` — execution wall-clock time
- `error` — truncated error message when outcome is `"error"`

The log is append-only plain text. To rotate it, rename or move the file. Write failures are silently swallowed so a missing or unwritable log directory never breaks tool execution. The log file itself is listed in `.gitignore` (`*.log`) and is never committed.

## Known Gaps

- The command allowlist permits `powershell` and `cmd`, which can bypass other restrictions if invoked deliberately.
- The audit log records parameter names but not values — full forensic replay of tool calls is not possible from the log alone. This is intentional (values may be sensitive) but means the log is a detection aid, not a complete audit trail.
- The confirmation gate is opt-in and off by default — autonomous or unattended sessions do not prompt before Level 3 tool execution unless the gate is explicitly installed.
