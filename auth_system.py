#!/usr/bin/env python3
"""
Authentication and Authorization System for Dan AI Agent
Provides API key validation, role-based access control, and session management
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from functools import wraps

from config import USER_DATA_DIR

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

AUTH_CONFIG = {
    "api_key_length": 32,
    "session_timeout": 3600,  # 1 hour
    "max_failed_attempts": 5,
    "lockout_duration": 900,  # 15 minutes
    "require_auth": False,  # Set to False to disable auth (dev mode)
    "admin_override_key": os.getenv("DAN_ADMIN_OVERRIDE", ""),
    "auth_database": USER_DATA_DIR / "auth_data.json",
    "audit_log": USER_DATA_DIR / "auth_audit.log",
    "salt_file": USER_DATA_DIR / "auth_salt.bin",
    "bootstrap_admin_key_file": USER_DATA_DIR / "bootstrap_admin_key.txt",
}

# ── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class User:
    """User account with roles and permissions"""
    username: str
    api_key_hash: str
    roles: List[str]
    created: float
    last_login: float = 0.0
    failed_attempts: int = 0
    locked_until: float = 0.0
    is_active: bool = True

@dataclass 
class Session:
    """Active user session"""
    session_id: str
    username: str
    created: float
    expires: float
    last_activity: float
    permissions: Set[str]

@dataclass
class AuthAttempt:
    """Authentication attempt log"""
    timestamp: float
    username: str
    api_key_fingerprint: str
    success: bool
    ip_address: str = ""
    user_agent: str = ""

# ── Role Definitions ────────────────────────────────────────────────────────

ROLE_PERMISSIONS = {
    "admin": {
        # Full access to everything
        "*"  # Wildcard means all permissions
    },
    "developer": {
        "tools.read", "tools.write", "tools.edit", "tools.bash", 
        "tools.glob", "tools.grep", "tools.listdir",
        "knowledge.*", "skills.*", "workers.*", "actions.*"
    },
    "analyst": {
        "tools.read", "tools.glob", "tools.grep", "tools.listdir",
        "knowledge.read", "knowledge.recall", "web.*", "image.*", "ml.predict", "ml.list"
    },
    "readonly": {
        "tools.read", "tools.listdir", "knowledge.recall", "knowledge.list"
    },
    "guest": {
        "tools.read", "knowledge.recall"
    }
}

# ── Authentication Manager ──────────────────────────────────────────────────

class AuthManager:
    """Centralized authentication and authorization manager"""
    
    def __init__(self):
        self.users: Dict[str, User] = {}
        self.sessions: Dict[str, Session] = {}
        self.auth_attempts: List[AuthAttempt] = []
        self._salt = self._load_or_create_salt()
        self._setup_audit_logging()
        self._load_auth_data()

    def _load_or_create_salt(self) -> bytes:
        """Load a persistent auth salt or create one on first run."""
        env_salt = os.getenv("DAN_AUTH_SALT", "").strip()
        if env_salt:
            return env_salt.encode("utf-8")

        salt_path = AUTH_CONFIG["salt_file"]
        salt_path.parent.mkdir(parents=True, exist_ok=True)

        if salt_path.exists():
            return salt_path.read_bytes()

        salt = secrets.token_bytes(32)
        salt_path.write_bytes(salt)
        try:
            os.chmod(salt_path, 0o600)
        except OSError:
            pass
        return salt

    def _setup_audit_logging(self):
        """Setup dedicated audit logging"""
        audit_log_path = AUTH_CONFIG["audit_log"]
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        audit_base_filename = str(audit_log_path.resolve())
        self.audit_logger = logging.getLogger("dan.auth.audit")

        for handler in list(self.audit_logger.handlers):
            if not isinstance(handler, logging.FileHandler):
                continue
            if getattr(handler, "baseFilename", None) != audit_base_filename:
                self.audit_logger.removeHandler(handler)
                handler.close()

        if not any(isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", None) == audit_base_filename
                   for handler in self.audit_logger.handlers):
            audit_handler = logging.FileHandler(audit_log_path)
            audit_handler.setFormatter(logging.Formatter(
                '%(asctime)s [AUTH] %(levelname)s: %(message)s'
            ))
            self.audit_logger.addHandler(audit_handler)
        self.audit_logger.setLevel(logging.INFO)
    
    def _load_auth_data(self):
        """Load users and sessions from persistent storage"""
        if not AUTH_CONFIG["auth_database"].exists():
            self._create_default_admin()
            return
        
        try:
            with open(AUTH_CONFIG["auth_database"], 'r') as f:
                data = json.load(f)
            
            # Load users
            for username, user_data in data.get("users", {}).items():
                self.users[username] = User(**user_data)
            
            # Load active sessions (filter expired ones)
            current_time = time.time()
            for session_id, session_data in data.get("sessions", {}).items():
                session_data["permissions"] = set(session_data["permissions"])
                session = Session(**session_data)
                if session.expires > current_time:
                    self.sessions[session_id] = session
            
            logger.info(f"Loaded {len(self.users)} users, {len(self.sessions)} active sessions")
            
        except Exception as e:
            logger.error(f"Failed to load auth data: {e}")
            self._create_default_admin()
    
    def _save_auth_data(self):
        """Save users and sessions to persistent storage"""
        try:
            AUTH_CONFIG["auth_database"].parent.mkdir(parents=True, exist_ok=True)
            data = {
                "users": {username: asdict(user) for username, user in self.users.items()},
                "sessions": {
                    session_id: {
                        **asdict(session),
                        "permissions": list(session.permissions)
                    } for session_id, session in self.sessions.items()
                }
            }
            
            with open(AUTH_CONFIG["auth_database"], 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save auth data: {e}")
    
    def _create_default_admin(self):
        """Create default admin user if none exists"""
        admin_key = secrets.token_urlsafe(AUTH_CONFIG["api_key_length"])
        admin_user = User(
            username="admin",
            api_key_hash=self._hash_api_key(admin_key),
            roles=["admin"],
            created=time.time()
        )
        self.users["admin"] = admin_user
        self._save_auth_data()

        bootstrap_file = AUTH_CONFIG["bootstrap_admin_key_file"]
        bootstrap_file.parent.mkdir(parents=True, exist_ok=True)
        bootstrap_file.write_text(
            "\n".join(
                [
                    "DEFAULT ADMIN USER CREATED",
                    "Username: admin",
                    f"API Key: {admin_key}",
                    "Roles: admin (full access)",
                    "",
                    "Store this key securely and remove this file after onboarding.",
                ]
            ),
            encoding="utf-8",
        )
        try:
            os.chmod(bootstrap_file, 0o600)
        except OSError:
            pass

        print(f"\n{'='*60}")
        print("DEFAULT ADMIN USER CREATED")
        print(f"{'='*60}")
        print("Username: admin")
        print(f"Bootstrap file: {bootstrap_file}")
        print("Store the key securely, then delete the bootstrap file.")
        print(f"{'='*60}\n")

        self.audit_logger.info("Default admin user created")
    
    def _hash_api_key(self, api_key: str) -> str:
        """Hash API key for secure storage"""
        return hashlib.pbkdf2_hmac("sha256", api_key.encode(), self._salt, 100_000).hex()

    def _fingerprint_api_key(self, api_key: str) -> str:
        """Return a non-secret audit identifier for correlating auth attempts."""
        if not api_key:
            return "empty"
        return hmac.new(self._salt, api_key.encode(), hashlib.sha256).hexdigest()[:12]
    
    def _get_permissions_for_roles(self, roles: List[str]) -> Set[str]:
        """Get all permissions for given roles"""
        permissions = set()
        for role in roles:
            role_perms = ROLE_PERMISSIONS.get(role, set())
            if "*" in role_perms:  # Admin wildcard
                permissions.add("*")
            else:
                permissions.update(role_perms)
        return permissions
    
    def create_user(self, username: str, roles: List[str], creator_username: str = "system") -> str:
        """Create a new user with roles"""
        if username in self.users:
            raise ValueError(f"User {username} already exists")
        
        # Generate API key
        api_key = secrets.token_urlsafe(AUTH_CONFIG["api_key_length"])
        
        # Create user
        user = User(
            username=username,
            api_key_hash=self._hash_api_key(api_key),
            roles=roles,
            created=time.time()
        )
        
        self.users[username] = user
        self._save_auth_data()
        
        self.audit_logger.info(f"User {username} created by {creator_username} with roles: {roles}")
        return api_key
    
    def authenticate(self, api_key: str, ip_address: str = "", user_agent: str = "") -> Optional[Session]:
        """Authenticate user with API key and create session"""
        if not AUTH_CONFIG["require_auth"]:
            # Auth disabled - create guest session
            return self._create_guest_session()
        
        # Check admin override
        if api_key == AUTH_CONFIG["admin_override_key"] and api_key:
            return self._create_admin_session()
        
        api_key_hash = self._hash_api_key(api_key)
        current_time = time.time()
        
        # Find user by API key hash
        user = None
        for u in self.users.values():
            if hmac.compare_digest(u.api_key_hash, api_key_hash):
                user = u
                break
        
        # Log attempt
        attempt = AuthAttempt(
            timestamp=current_time,
            username=user.username if user else "unknown",
            api_key_fingerprint=self._fingerprint_api_key(api_key),
            success=False,
            ip_address=ip_address,
            user_agent=user_agent
        )

        if not user:
            self.audit_logger.warning(
                "Authentication failed - invalid API key fingerprint %s from %s",
                attempt.api_key_fingerprint,
                ip_address,
            )
            self.auth_attempts.append(attempt)
            return None

        # Wrong key for known user can't be inferred directly from hash lookup,
        # but once a matching user is found, all remaining checks apply below.
        
        # Check if user is locked out
        if user.locked_until > current_time:
            self.audit_logger.warning(f"Authentication failed - user {user.username} locked until {datetime.fromtimestamp(user.locked_until)}")
            self.auth_attempts.append(attempt)
            return None
        
        # Check if user is active
        if not user.is_active:
            self.audit_logger.warning(f"Authentication failed - user {user.username} is inactive")
            self.auth_attempts.append(attempt)
            return None
        
        # Successful authentication
        attempt.success = True
        self.auth_attempts.append(attempt)
        
        # Reset failed attempts and update last login
        user.failed_attempts = 0
        user.last_login = current_time
        self._save_auth_data()
        
        # Create session
        session = self._create_session(user)
        self.audit_logger.info(f"User {user.username} authenticated successfully from {ip_address}")
        
        return session

    def record_failed_attempt(self, username: str) -> None:
        """Increment failed attempts and apply lockout when threshold is reached."""
        user = self.users.get(username)
        if not user:
            return
        user.failed_attempts += 1
        if user.failed_attempts >= AUTH_CONFIG["max_failed_attempts"]:
            user.locked_until = time.time() + AUTH_CONFIG["lockout_duration"]
        self._save_auth_data()
    
    def _create_session(self, user: User) -> Session:
        """Create a new session for authenticated user"""
        session_id = secrets.token_urlsafe(32)
        current_time = time.time()
        
        session = Session(
            session_id=session_id,
            username=user.username,
            created=current_time,
            expires=current_time + AUTH_CONFIG["session_timeout"],
            last_activity=current_time,
            permissions=self._get_permissions_for_roles(user.roles)
        )
        
        self.sessions[session_id] = session
        self._save_auth_data()
        return session
    
    def _create_guest_session(self) -> Session:
        """Create guest session when auth is disabled"""
        return Session(
            session_id="guest",
            username="guest",
            created=time.time(),
            expires=time.time() + 86400,  # 24 hours
            last_activity=time.time(),
            permissions={"*"}  # Full access when auth disabled
        )
    
    def _create_admin_session(self) -> Session:
        """Create admin session for override key"""
        return Session(
            session_id="admin_override",
            username="admin_override", 
            created=time.time(),
            expires=time.time() + 3600,  # 1 hour
            last_activity=time.time(),
            permissions={"*"}
        )
    
    def validate_session(self, session_id: str) -> Optional[Session]:
        """Validate and refresh session"""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        current_time = time.time()
        
        # Check if session expired
        if session.expires < current_time:
            del self.sessions[session_id]
            self._save_auth_data()
            return None
        
        # Refresh session
        session.last_activity = current_time
        session.expires = current_time + AUTH_CONFIG["session_timeout"]
        self._save_auth_data()
        
        return session
    
    def check_permission(self, session: Session, permission: str) -> bool:
        """Check if session has specific permission"""
        if not session:
            return False
        
        # Admin wildcard
        if "*" in session.permissions:
            return True
        
        # Direct permission match
        if permission in session.permissions:
            return True
        
        # Wildcard permission match (e.g., tools.* matches tools.read)
        for perm in session.permissions:
            if perm.endswith(".*"):
                prefix = perm[:-1]  # Remove the *
                if permission.startswith(prefix):
                    return True
        
        return False
    
    def logout(self, session_id: str):
        """Logout user and destroy session"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            del self.sessions[session_id]
            self._save_auth_data()
            self.audit_logger.info(f"User {session.username} logged out")
    
    def get_auth_status(self) -> Dict[str, Any]:
        """Get current authentication system status"""
        current_time = time.time()
        active_sessions = len([s for s in self.sessions.values() if s.expires > current_time])
        
        return {
            "auth_enabled": AUTH_CONFIG["require_auth"],
            "total_users": len(self.users),
            "active_sessions": active_sessions,
            "recent_attempts": len([a for a in self.auth_attempts if a.timestamp > current_time - 3600]),
            "failed_attempts": len([a for a in self.auth_attempts if not a.success and a.timestamp > current_time - 3600])
        }

# ── Global Auth Manager Instance ────────────────────────────────────────────

_auth_manager = None

def get_auth_manager() -> AuthManager:
    """Get global auth manager instance"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager

# ── Decorators ──────────────────────────────────────────────────────────────

def require_auth(permission: str = None):
    """Decorator to require authentication for functions"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get current session from context (set by agent or tool registry)
            session = getattr(wrapper, '_current_session', None)
            
            if not session:
                return "Error: Authentication required. Please provide valid API key."
            
            # Check permission if specified
            if permission:
                auth_manager = get_auth_manager()
                if not auth_manager.check_permission(session, permission):
                    return f"Error: Permission denied. Required: {permission}"
            
            # Execute function with auth context
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Authenticated function {func.__name__} failed: {e}")
                return f"Error: {e}"
        
        return wrapper
    return decorator

def require_role(required_roles: List[str]):
    """Decorator to require specific roles"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            session = getattr(wrapper, '_current_session', None)
            
            if not session:
                return "Error: Authentication required."
            
            # Check if user has required role
            auth_manager = get_auth_manager()
            user = auth_manager.users.get(session.username)
            
            if not user or not any(role in user.roles for role in required_roles):
                return f"Error: Access denied. Required roles: {required_roles}"
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

# ── Authentication Tools ────────────────────────────────────────────────────

def authenticate_user(api_key: str) -> Optional[Session]:
    """Authenticate user and return session"""
    auth_manager = get_auth_manager()
    return auth_manager.authenticate(api_key)

def get_current_session() -> Optional[Session]:
    """Get current session from context"""
    # This will be set by the agent loop
    return getattr(get_current_session, '_current_session', None)

def set_current_session(session: Session):
    """Set current session in context"""
    setattr(get_current_session, '_current_session', session)

if __name__ == "__main__":
    # Test the auth system
    auth = AuthManager()
    print(f"Auth system initialized with {len(auth.users)} users")
    
    # Show status
    status = auth.get_auth_status()
    print(f"Status: {status}")
