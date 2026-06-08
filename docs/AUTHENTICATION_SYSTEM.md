# Dan Authentication System

## Overview

Dan includes an optional authentication and authorization system in `auth_system.py` / `auth_tools.py`. It provides:

- **API Key Authentication**: Token-based access control
- **Role-Based Access Control (RBAC)**: Granular permissions by role
- **Session Management**: Session handling with configurable timeouts
- **Audit Logging**: Authentication events written to a dedicated log file
- **User Management Tools**: `CreateUser`, `ListUsers`, `AuthStatus`, `TestPermissions`

> **Default behavior**: Authentication is **disabled** by default (`require_auth = False`). In this mode, every operation runs with full permissions under a guest session. To enable auth, set `require_auth: True` in `AUTH_CONFIG` in `auth_system.py` or set the `DAN_ADMIN_OVERRIDE` environment variable.

---

## Data File Locations

All auth-related files are stored under the Dan user data directory:

| File | Windows path | Purpose |
|------|-------------|---------|
| `auth_data.json` | `%APPDATA%\Dan\auth_data.json` | User accounts and active sessions |
| `auth_audit.log` | `%APPDATA%\Dan\auth_audit.log` | Auth event audit trail |
| `auth_salt.bin` | `%APPDATA%\Dan\auth_salt.bin` | Persistent random PBKDF2 salt |
| `bootstrap_admin_key.txt` | `%APPDATA%\Dan\bootstrap_admin_key.txt` | One-time admin key on first run |

---

## First-Time Setup

When `auth_data.json` does not exist, Dan creates a default admin user automatically and writes the API key to the bootstrap file:

```
%APPDATA%\Dan\bootstrap_admin_key.txt
```

The console prints the path to that file — not the key itself:

```
============================================================
DEFAULT ADMIN USER CREATED
============================================================
Username: admin
Bootstrap file: C:\Users\<you>\AppData\Roaming\Dan\bootstrap_admin_key.txt
Store the key securely, then delete the bootstrap file.
============================================================
```

Open the bootstrap file to retrieve the key, then:

```powershell
# Windows
$env:DAN_API_KEY = "<your-admin-key>"
```

Delete `bootstrap_admin_key.txt` after saving the key elsewhere. It is created with `0o600` permissions on platforms that support it.

---

## Configuration

`AUTH_CONFIG` in `auth_system.py` controls all runtime behavior:

```python
AUTH_CONFIG = {
    "require_auth": False,        # Set True to enforce authentication
    "session_timeout": 3600,      # Session timeout in seconds (default: 1 hour)
    "max_failed_attempts": 5,     # Failed attempts before lockout
    "lockout_duration": 900,      # Lockout duration in seconds (default: 15 min)
    "api_key_length": 32,         # Generated key length
    "admin_override_key": os.getenv("DAN_ADMIN_OVERRIDE", ""),
    "auth_database": USER_DATA_DIR / "auth_data.json",
    "audit_log":     USER_DATA_DIR / "auth_audit.log",
    "salt_file":     USER_DATA_DIR / "auth_salt.bin",
    "bootstrap_admin_key_file": USER_DATA_DIR / "bootstrap_admin_key.txt",
}
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DAN_API_KEY` | API key for the current user session |
| `DAN_ADMIN_OVERRIDE` | Emergency override key — grants full admin access if set |
| `DAN_AUTH_SALT` | Override the file-backed salt with a fixed string (not recommended; primarily for testing) |

**Salt behavior**: If `DAN_AUTH_SALT` is not set, Dan generates a random 32-byte salt on first run and persists it to `auth_salt.bin`. This file is the source of truth for hashing. Deleting it invalidates all existing API keys. Do not rotate it unless you intend to invalidate all credentials.

---

## User Roles and Permissions

### Built-in Roles

| Role | Permissions |
|------|-------------|
| `admin` | `*` — all permissions |
| `developer` | `tools.read/write/edit/bash/glob/grep/listdir`, `knowledge.*`, `skills.*`, `workers.*`, `actions.*` |
| `analyst` | `tools.read/glob/grep/listdir`, `knowledge.read/recall`, `web.*`, `image.*`, `ml.predict/list` |
| `readonly` | `tools.read/listdir`, `knowledge.recall/list` |
| `guest` | `tools.read`, `knowledge.recall` |

### Permission Matching

`check_permission()` resolves permissions in priority order:

1. Wildcard `*` grants everything (admin and auth-disabled guest sessions)
2. Exact match: `"tools.read"` in the session's permission set
3. Namespace wildcard: session has `"tools.*"` and the requested permission starts with `"tools."`

---

## User Management Tools

These tools are registered by `register_auth_tools()` in `auth_tools.py` and require an active session.

| Tool | Required role | Description |
|------|--------------|-------------|
| `LoginUser` | — | Authenticate with an API key |
| `LogoutUser` | any | Destroy the current session |
| `AuthStatus` | any | Show current session, roles, and system status |
| `CreateUser` | admin | Create a new user account |
| `ListUsers` | admin | List all users and their status |
| `TestPermissions` | any | Show which permissions the current session holds |

### Examples

```
CreateUser username="alice" roles="developer,analyst"
ListUsers
AuthStatus
TestPermissions
```

---

## API Reference

### Core Functions

```python
from auth_system import authenticate_user, get_auth_manager, require_auth, require_role

# Authenticate and get a session
session = authenticate_user(api_key)

# Check a permission on a session
has_access = get_auth_manager().check_permission(session, "tools.write")

# Create a new user (returns the new API key)
api_key = get_auth_manager().create_user("alice", ["developer"], creator_username="admin")

# Get system-wide auth status
status = get_auth_manager().get_auth_status()
```

### Decorators

```python
@require_auth("knowledge.write")
def sensitive_function():
    # Runs only if the current session has knowledge.write (or *)
    pass

@require_role(["admin", "developer"])
def admin_function():
    # Runs only if the current user has admin or developer role
    pass
```

The decorators resolve the session from `get_current_session()`. The agent loop or tool registry is responsible for calling `set_current_session(session)` before dispatching tool calls.

---

## Audit Logging

Authentication events are appended to `%APPDATA%\Dan\auth_audit.log`:

```
2024-12-19 10:30:15,123 [AUTH] INFO: User admin authenticated successfully from 127.0.0.1
2024-12-19 10:30:20,456 [AUTH] WARNING: Authentication failed - invalid API key fingerprint 1a2b3c4d from
2024-12-19 10:35:10,789 [AUTH] INFO: User alice created by admin with roles: ['developer']
```

Failed authentication logs include a short HMAC fingerprint of the key (not the key itself) for correlation without exposing credentials.

---

## Security Notes

### What the auth system does
- PBKDF2-SHA256 (100,000 iterations) for key hashing
- Timing-safe comparison (`hmac.compare_digest`) for key lookups
- Account lockout after configurable failed attempts
- Expired session cleanup on load and validate

### What the auth system does not do
- It does not enforce auth at the network layer — Dan is a local desktop application, not a network service. "Enable HTTPS" does not apply.
- It does not currently scan for accidentally committed API keys (tracked in security backlog).
- It does not produce an audit log for tool invocations beyond auth events (tracked in security backlog).
- There is no confirmation gate before Level 3 (shell execution) tools in autonomous workflows (tracked in security backlog).

---

## Emergency Access

If you lose access:

1. **Admin override**: Set `DAN_ADMIN_OVERRIDE=<any-key>` and use that key to authenticate. This bypasses user lookup.
2. **Reset the auth database**: Delete `%APPDATA%\Dan\auth_data.json`. Dan recreates it with a new admin user and writes a new bootstrap file on next startup. Existing API keys for other users are invalidated.
3. **Disable auth temporarily**: Set `AUTH_CONFIG["require_auth"] = False` in `auth_system.py` (already the default in dev mode).

---

## Troubleshooting

**"Authentication required" error but I set `DAN_API_KEY`:**
Verify that `require_auth` is `True` in `AUTH_CONFIG`. If it is `False`, the env var is not checked — every request runs as guest with full permissions.

**"Invalid API key":**
Check that `DAN_API_KEY` matches the key that was generated. If the `auth_salt.bin` file was deleted or replaced, all keys must be regenerated.

**Lost bootstrap key:**
Delete `auth_data.json` to force recreation of the admin user. A new bootstrap file will be written on next startup.

**Permission denied for a tool:**
Run `TestPermissions` to see which permissions your session holds, then verify the required permission against the role table above.
