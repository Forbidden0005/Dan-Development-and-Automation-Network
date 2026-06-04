"""Security utilities for Dan AI agent."""

import logging
import os
import re
import shlex
import tempfile
from pathlib import Path
from typing import List, Optional, Set
import subprocess

logger = logging.getLogger(__name__)

# ── Path Security ────────────────────────────────────────────────────────────

class SecurePathValidator:
    """Validates file paths to prevent directory traversal attacks."""
    
    def __init__(self, allowed_roots: Optional[List[str]] = None):
        """
        Initialize with allowed root directories.
        If None, uses current working directory as root.
        """
        self.allowed_roots = []
        if allowed_roots:
            for root in allowed_roots:
                self.allowed_roots.append(Path(root).resolve())
        else:
            self.allowed_roots.append(Path.cwd().resolve())
    
    def validate_path(self, path: str) -> Path:
        """
        Validate and resolve a path safely.
        
        Args:
            path: User-provided path string
            
        Returns:
            Resolved Path object if safe
            
        Raises:
            ValueError: If path is invalid or outside allowed roots
        """
        if not path or not isinstance(path, str):
            raise ValueError("Path must be a non-empty string")
        
        # Normalize and resolve the path
        try:
            resolved_path = Path(path).expanduser().resolve()
        except (OSError, ValueError) as e:
            raise ValueError(f"Invalid path: {e}")
        
        # Check if path is within allowed roots
        for allowed_root in self.allowed_roots:
            try:
                resolved_path.relative_to(allowed_root)
                return resolved_path
            except ValueError:
                continue
        
        # If we get here, path is not within any allowed root
        allowed_roots_str = ", ".join(str(r) for r in self.allowed_roots)
        raise ValueError(
            f"Path '{resolved_path}' is outside allowed directories: {allowed_roots_str}"
        )

    def is_safe_path(self, path: str) -> bool:
        """Return True when a path resolves inside an allowed root."""
        try:
            self.validate_path(path)
            return True
        except ValueError:
            return False

# ── Command Security ─────────────────────────────────────────────────────────

class SecureCommandExecutor:
    """Secure command execution with sandboxing and validation."""
    
    # Dangerous command patterns (expanded from original)
    DANGEROUS_PATTERNS = [
        # System damage
        r'\brm\s+-rf\s+/',
        r'\bmkfs\b',
        r'\bdd\s+if=/dev/zero',
        r'\bformat\b',
        r'\bdel\s+/[sqf]\b',
        
        # Network/system access
        r'\bnc\s+-[le]',  # netcat listeners
        r'\btelnet\b',
        r'\bssh\b',
        r'\bftp\b',
        r'\bwget\b.*\|\s*sh',
        r'\bcurl\b.*\|\s*sh',
        
        # Process manipulation
        r'\bkill\s+-9',
        r'\bkillall\b',
        r'\bpkill\b',
        
        # Privilege escalation
        r'\bsudo\b',
        r'\bsu\s+root',
        r'\bchmod\s+777',
        r'\bchown\s+root',
        
        # Fork bombs and resource exhaustion
        r':\(\)\{.*:\|:.*\}',  # bash fork bomb
        r'\bwhile\s+true.*do\b',  # infinite loops
        
        # File system manipulation
        r'\bmount\b',
        r'\bumount\b',
        r'\bfsck\b',
        
        # Environment manipulation
        r'>\s*/dev/null\s*2>&1.*&',  # background processes
        r'\bexport\s+PATH=',
        r'\bunset\s+PATH',
    ]
    
    # Allowed safe commands (whitelist approach for maximum security)
    SAFE_COMMANDS = {
        # File operations (Linux + Windows)
        'ls', 'cat', 'head', 'tail', 'wc', 'grep', 'find', 'file',
        'cp', 'mv', 'rm', 'mkdir', 'rmdir', 'touch', 'ln', 'chmod',
        'stat', 'readlink', 'realpath', 'basename', 'dirname',
        'dir', 'copy', 'xcopy', 'robocopy', 'move', 'del', 'ren',
        'type', 'more', 'attrib', 'mklink',
        # Text processing  
        'awk', 'sed', 'sort', 'uniq', 'cut', 'tr', 'diff', 'comm',
        'tee', 'xargs', 'less', 'findstr', 'fc',
        # Shell builtins / utilities (Linux + Windows)
        'echo', 'printf', 'env', 'which', 'where', 'pwd', 'cd', 'test',
        'true', 'false', 'sleep', 'timeout', 'yes', 'set', 'cls',
        'cmd', 'powershell', 'pwsh',
        # Development
        'git', 'pip', 'pip3', 'python', 'python3', 'py',
        'node', 'npm', 'npx', 'yarn', 'pnpm', 'bun',
        'pytest', 'black', 'flake8', 'mypy', 'ruff', 'cargo', 'make',
        'gcc', 'g++', 'javac', 'java', 'go', 'rustc', 'dotnet',
        # System info (read-only)
        'ps', 'top', 'df', 'du', 'free', 'uname', 'whoami', 'id', 'date',
        'uptime', 'hostname', 'arch', 'nproc', 'lsb_release',
        'systeminfo', 'tasklist', 'ver', 'wmic',
        # Archives
        'tar', 'zip', 'unzip', 'gzip', 'gunzip',
        # Network (limited)
        'ping', 'nslookup', 'dig', 'curl', 'wget', 'ipconfig', 'netstat',
    }

    WINDOWS_SHELL_BUILTINS = {
        'echo', 'dir', 'copy', 'del', 'move', 'ren', 'type', 'more',
        'cd', 'set', 'cls',
    }
    
    def __init__(self, use_whitelist: bool = True, max_execution_time: int = 30):
        """
        Initialize secure command executor.
        
        Args:
            use_whitelist: If True, only allow whitelisted commands
            max_execution_time: Maximum execution time in seconds
        """
        self.use_whitelist = use_whitelist
        self.max_execution_time = max_execution_time
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) 
                                for pattern in self.DANGEROUS_PATTERNS]
    
    def validate_command(self, command: str) -> None:
        """
        Validate a command for security risks.
        
        Args:
            command: Command string to validate
            
        Raises:
            ValueError: If command is deemed unsafe
        """
        if not command or not isinstance(command, str):
            raise ValueError("Command must be a non-empty string")
        
        # Check for dangerous patterns
        for pattern in self.compiled_patterns:
            if pattern.search(command):
                raise ValueError(f"Blocked dangerous command pattern: {pattern.pattern}")
        
        # Check whitelist if enabled
        if self.use_whitelist:
            try:
                import platform
                # Parse command to get the base command
                if platform.system() == "Windows":
                    # On Windows, split on spaces simply — shlex chokes on backslash paths
                    parsed = command.split()
                else:
                    parsed = shlex.split(command)
                if parsed:
                    base_command = parsed[0].split('/')[-1].split('\\')[-1]  # strip path
                    # Strip .exe/.cmd/.bat extension on Windows
                    if '.' in base_command:
                        base_no_ext = base_command.rsplit('.', 1)[0]
                        if base_no_ext in self.SAFE_COMMANDS:
                            return
                    if base_command not in self.SAFE_COMMANDS:
                        raise ValueError(f"Command '{base_command}' not in whitelist")
            except ValueError as e:
                if "not in whitelist" in str(e):
                    raise
                raise ValueError(f"Failed to parse command safely: {e}")
    
    def execute_command(self, command: str, cwd: Optional[str] = None) -> str:
        """
        Execute a command in a secure manner.
        
        Args:
            command: Command to execute
            cwd: Working directory (must be validated)
            
        Returns:
            Command output
            
        Raises:
            ValueError: If command is unsafe
            subprocess.TimeoutExpired: If command times out
            subprocess.CalledProcessError: If command fails
        """
        # Validate the command first
        self.validate_command(command)
        
        # Validate working directory if provided
        if cwd:
            validator = SecurePathValidator()
            cwd_path = validator.validate_path(cwd)
            cwd = str(cwd_path)
        
        logger.info("Executing secure command: %s", command[:100])
        
        try:
            # Use more secure execution without shell=True when possible
            if self._is_simple_command(command):
                if self._needs_windows_shell(command):
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=self.max_execution_time,
                        cwd=cwd,
                        env=self._get_restricted_env()
                    )
                else:
                    # For simple commands, avoid shell=True
                    args = self._split_command(command)
                    result = subprocess.run(
                        args,
                        capture_output=True,
                        text=True,
                        timeout=self.max_execution_time,
                        cwd=cwd,
                        env=self._get_restricted_env()
                    )
            else:
                # For complex commands, use shell=True but with restrictions
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self.max_execution_time,
                    cwd=cwd,
                    env=self._get_restricted_env()
                )
            
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            
            if result.returncode != 0:
                output += f"\nCommand failed with exit code {result.returncode}"
            
            return output.strip()
            
        except subprocess.TimeoutExpired:
            raise ValueError(f"Command timed out after {self.max_execution_time} seconds")
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Command failed: {e}")
        except Exception as e:
            raise ValueError(f"Execution error: {e}")
    
    def _is_simple_command(self, command: str) -> bool:
        """Check if command is simple enough to avoid shell=True."""
        # Avoid shell=True for commands without shell features
        shell_features = ['|', '>', '<', '&', ';', '`', '$', '(', ')', '[', ']']
        return not any(feature in command for feature in shell_features)

    def _split_command(self, command: str) -> list[str]:
        """Split a simple command using platform-safe defaults."""
        import platform
        if platform.system() == "Windows":
            return command.split()
        return shlex.split(command)

    def _base_command(self, command: str) -> str:
        parsed = self._split_command(command)
        if not parsed:
            return ""
        base_command = parsed[0].split('/')[-1].split('\\')[-1]
        if '.' in base_command:
            base_command = base_command.rsplit('.', 1)[0]
        return base_command.lower()

    def _needs_windows_shell(self, command: str) -> bool:
        """Windows builtins like echo and dir require cmd.exe even without operators."""
        import platform
        return (
            platform.system() == "Windows"
            and self._base_command(command) in self.WINDOWS_SHELL_BUILTINS
        )
    
    def _get_restricted_env(self) -> dict:
        """Get a restricted environment for command execution."""
        import platform
        
        if platform.system() == "Windows":
            # On Windows, inherit PATH so commands are actually found
            restricted_env = {
                'PATH': os.environ.get('PATH', ''),
                'SYSTEMROOT': os.environ.get('SYSTEMROOT', r'C:\Windows'),
                'COMSPEC': os.environ.get('COMSPEC', r'C:\Windows\system32\cmd.exe'),
                'TEMP': os.environ.get('TEMP', ''),
                'TMP': os.environ.get('TMP', ''),
                'USERPROFILE': os.environ.get('USERPROFILE', ''),
                'HOME': os.environ.get('USERPROFILE', ''),
            }
        else:
            restricted_env = {
                'PATH': '/usr/local/bin:/usr/bin:/bin',
                'LANG': 'en_US.UTF-8',
                'HOME': str(Path.home()),
                'USER': os.environ.get('USER', 'unknown'),
                'SHELL': '/bin/bash',
            }
        
        # Add Python-specific vars if present
        python_vars = ['PYTHONPATH', 'VIRTUAL_ENV', 'CONDA_DEFAULT_ENV', 'PYTHONHOME']
        for var in python_vars:
            if var in os.environ:
                restricted_env[var] = os.environ[var]
        
        return restricted_env

# ── Input Sanitization ───────────────────────────────────────────────────────

def sanitize_user_input(user_input: str, max_length: int = 10000) -> str:
    """
    Sanitize user input to prevent injection attacks.
    
    Args:
        user_input: Raw user input
        max_length: Maximum allowed length
        
    Returns:
        Sanitized input
        
    Raises:
        ValueError: If input is invalid or too long
    """
    if not isinstance(user_input, str):
        raise ValueError("Input must be a string")
    
    if len(user_input) > max_length:
        raise ValueError(f"Input too long: {len(user_input)} > {max_length}")
    
    # Remove null bytes and control characters (except newlines and tabs)
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', user_input)
    
    # Limit consecutive newlines to prevent formatting abuse
    sanitized = re.sub(r'\n{3,}', '\n\n', sanitized)
    
    return sanitized.strip()

# ── File Size Validation ─────────────────────────────────────────────────────

def validate_file_size(file_path: Path, max_size_mb: int = 50) -> None:
    """
    Validate file size to prevent DoS attacks.
    
    Args:
        file_path: Path to file
        max_size_mb: Maximum size in megabytes
        
    Raises:
        ValueError: If file is too large
    """
    if not file_path.exists():
        return
    
    size_bytes = file_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    
    if size_mb > max_size_mb:
        raise ValueError(f"File too large: {size_mb:.2f}MB > {max_size_mb}MB")
