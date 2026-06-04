"""Authentication tools for Dan AI Agent"""

import logging
import time
from typing import Dict, Any

import tool_registry as registry
from auth_system import get_auth_manager, get_current_session, require_auth, require_role

logger = logging.getLogger(__name__)

@require_auth()
def login_user(api_key: str) -> str:
    """Authenticate user with API key"""
    try:
        auth_manager = get_auth_manager()
        session = auth_manager.authenticate(api_key)
        
        if session:
            return f"Successfully authenticated as {session.username} with roles: {auth_manager.users[session.username].roles}"
        else:
            return "Authentication failed: Invalid API key"
            
    except Exception as e:
        logger.error(f"Login failed: {e}")
        return f"Error during login: {e}"

@require_auth()
def logout_user() -> str:
    """Logout current user"""
    try:
        session = get_current_session()
        if not session:
            return "No active session to logout"
        
        auth_manager = get_auth_manager()
        auth_manager.logout(session.session_id)
        return f"Successfully logged out user: {session.username}"
        
    except Exception as e:
        logger.error(f"Logout failed: {e}")
        return f"Error during logout: {e}"

@require_auth()
def get_auth_status() -> str:
    """Get current authentication status"""
    try:
        auth_manager = get_auth_manager()
        session = get_current_session()
        
        if not session:
            return "No active session"
        
        user = auth_manager.users.get(session.username)
        status = auth_manager.get_auth_status()
        
        info = {
            "current_user": session.username,
            "user_roles": user.roles if user else [],
            "session_expires": session.expires,
            "permissions": list(session.permissions)[:10],  # Show first 10
            "system_status": status
        }
        
        return f"Authentication Status:\n" + \
               f"User: {info['current_user']}\n" + \
               f"Roles: {info['user_roles']}\n" + \
               f"Session expires: {info['session_expires']}\n" + \
               f"System users: {info['system_status']['total_users']}\n" + \
               f"Active sessions: {info['system_status']['active_sessions']}"
        
    except Exception as e:
        logger.error(f"Auth status failed: {e}")
        return f"Error getting auth status: {e}"

@require_role(["admin"])
def create_user(username: str, roles: str = "guest") -> str:
    """Create a new user (admin only)"""
    try:
        auth_manager = get_auth_manager()
        session = get_current_session()
        
        # Parse roles
        role_list = [r.strip() for r in roles.split(",")]
        
        # Validate roles
        valid_roles = set(["admin", "developer", "analyst", "readonly", "guest"])
        invalid_roles = set(role_list) - valid_roles
        if invalid_roles:
            return f"Error: Invalid roles: {invalid_roles}. Valid roles: {valid_roles}"
        
        # Create user
        api_key = auth_manager.create_user(username, role_list, session.username)
        
        return f"User '{username}' created successfully!\n" + \
               f"Roles: {role_list}\n" + \
               f"API Key: {api_key}\n" + \
               f"Save this API key securely - it won't be shown again!"
        
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.error(f"User creation failed: {e}")
        return f"Error creating user: {e}"

@require_role(["admin"])
def list_users() -> str:
    """List all users (admin only)"""
    try:
        auth_manager = get_auth_manager()
        
        if not auth_manager.users:
            return "No users found"
        
        lines = ["Users:"]
        for username, user in auth_manager.users.items():
            status = "active" if user.is_active else "inactive"
            if user.locked_until > time.time():
                status = "locked"
            
            lines.append(f"  {username}: roles={user.roles}, status={status}, last_login={user.last_login}")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"List users failed: {e}")
        return f"Error listing users: {e}"

@require_auth("knowledge.write")
def test_permission(action: str = "read") -> str:
    """Test permission system with different actions"""
    try:
        auth_manager = get_auth_manager()
        session = get_current_session()
        
        test_permissions = [
            "tools.read", "tools.write", "tools.bash",
            "knowledge.read", "knowledge.write",
            "ml.train", "ml.predict",
            "admin.users"
        ]
        
        results = []
        for perm in test_permissions:
            has_perm = auth_manager.check_permission(session, perm)
            results.append(f"  {perm}: {'✓' if has_perm else '✗'}")
        
        return f"Permission test for {session.username}:\n" + "\n".join(results)
        
    except Exception as e:
        logger.error(f"Permission test failed: {e}")
        return f"Error testing permissions: {e}"

def register_auth_tools():
    """Register authentication tools"""
    
    registry.register(
        name="AuthStatus",
        description="Get current authentication status and user information",
        parameters={
            "type": "object",
            "properties": {}
        },
        handler=get_auth_status,
        category="auth"
    )
    
    registry.register(
        name="CreateUser",
        description="Create a new user account (admin only)",
        parameters={
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "Username for new account"},
                "roles": {"type": "string", "description": "Comma-separated roles (admin,developer,analyst,readonly,guest)", "default": "guest"}
            },
            "required": ["username"]
        },
        handler=create_user,
        category="auth"
    )
    
    registry.register(
        name="ListUsers",
        description="List all user accounts (admin only)",
        parameters={
            "type": "object",
            "properties": {}
        },
        handler=list_users,
        category="auth"
    )
    
    registry.register(
        name="TestPermissions",
        description="Test permission system and show current user's access levels",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Test action", "default": "read"}
            }
        },
        handler=test_permission,
        category="auth"
    )
    
    logger.info("Authentication tools registered successfully")

if __name__ == "__main__":
    register_auth_tools()
    print("Auth tools registered")