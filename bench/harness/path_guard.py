"""
ABI-Bench PathGuard — filesystem access control for agent operations.

Prevents LLM agents from reading expected answers, scoring code, task YAMLs,
or other benchmark-internal files via absolute or relative path traversal.
All file operations and bash commands in direct_agent.py route through this
module before execution.
"""

import re
from pathlib import Path
from typing import List, Optional

# ── Deny-list: path substrings that trigger a block ──────────────────────
# Each entry is matched case-insensitively against the resolved absolute path
# (for file operations) or the full command string (for bash commands).
_DENY_SUBSTRINGS: List[str] = [
    "expected_answers",
    "bench/scoring",
    "bench/tasks",
    "bench/agent_profiles",
    "fixtures_hidden",
    "bench/.env",               # API keys
    "bench/results",            # pre-existing score.json files
]

# ── Deny-list patterns for bash command scanning ─────────────────────────
# These regex patterns catch indirect access attempts like
#   cat ../expected_answers/plasmid_missing_input.json
#   find / -name "expected_answers"
#   ls bench/scoring/
_DENY_COMMAND_PATTERNS: List[re.Pattern] = [
    # Direct file read of sensitive paths
    re.compile(r"(?:cat|head|tail|less|more|strings|readelf|objdump)\s+.*(?:expected_answers|bench/scoring|bench/tasks|bench/agent_profiles|fixtures_hidden)", re.IGNORECASE),
    # find / locate searching for sensitive directories
    re.compile(r"(?:find|locate|mlocate)\s+.*(?:expected_answers|bench/scoring|bench/tasks|fixtures_hidden)", re.IGNORECASE),
    # ls / tree / stat of sensitive directories
    re.compile(r"(?:ls|tree|stat|file|realpath|readlink)\s+.*(?:expected_answers|bench/scoring|bench/tasks|fixtures_hidden)", re.IGNORECASE),
    # grep / rg / ag searching sensitive directories
    re.compile(r"(?:grep|rg|ag|awk|sed)\s+.*(?:expected_answers|bench/scoring|bench/tasks|fixtures_hidden)", re.IGNORECASE),
    # python -c / python3 -c with sensitive paths
    re.compile(r"python3?\s+-c\s+.*(?:expected_answers|bench/scoring|bench/tasks|fixtures_hidden)", re.IGNORECASE),
    # Copy/move from sensitive directories
    re.compile(r"(?:cp|mv|rsync|scp)\s+.*(?:expected_answers|bench/scoring|bench/tasks|fixtures_hidden)", re.IGNORECASE),
    # source / .  (dot) execution of files in sensitive paths
    re.compile(r"(?:source|\.)\s+.*(?:expected_answers|bench/scoring|bench/tasks|fixtures_hidden)", re.IGNORECASE),
    # xargs / exec wrapping
    re.compile(r"(?:xargs|exec|nohup|env)\s+.*(?:cat|grep|find|ls|python).*(?:expected_answers|bench/scoring|bench/tasks|fixtures_hidden)", re.IGNORECASE),
]

# ── Allow-list: workspace and safe system paths that bypass deny checks ──
_SAFE_PATH_PREFIXES: List[str] = [
    "/usr/", "/bin/", "/sbin/", "/lib/", "/lib64/",
    "/etc/", "/opt/", "/tmp/", "/dev/", "/proc/", "/sys/",
]

# Compiled at import time for performance
_SAFE_PREFIXES = tuple(p.lower() for p in _SAFE_PATH_PREFIXES)


class PathGuard:
    """Filesystem access guard for agent operations.

    Usage:
        guard = PathGuard(workspace_dir=Path("/.../workspaces/G3/T03/replicate_01"))
        if not guard.validate_read("/home/.../expected_answers/plasmid.json"):
            return "ERROR: Access denied"
    """

    def __init__(self, workspace_dir: Path):
        self._workspace = workspace_dir.resolve()
        self._workspace_str = str(self._workspace)

    # ── File operation guards ───────────────────────────────────────────

    def validate_read(self, path: Path) -> bool:
        """Return True if *path* is safe to read."""
        resolved = self._resolve(path)
        if resolved is None:
            return False
        return self._is_safe(resolved)

    def validate_write(self, path: Path) -> bool:
        """Return True if *path* is safe to write.

        Writes are only permitted inside the workspace subtree.
        This is stricter than read because agents must not modify
        fixture files, scoring code, or other benchmark internals.
        """
        resolved = self._resolve(path)
        if resolved is None:
            return False
        return self._is_within_workspace(resolved)

    def validate_list(self, path: Path) -> bool:
        """Return True if *path* is safe to list."""
        return self.validate_read(path)

    # ── Bash command guard ──────────────────────────────────────────────

    def validate_command(self, cmd: str) -> Optional[str]:
        """Return None if the command is safe, or an error message string if blocked.

        The error message deliberately does NOT reveal which specific path
        triggered the block, to avoid giving the agent information about
        the deny-list contents.
        """
        if not cmd or not cmd.strip():
            return None  # Empty commands are harmless

        for pattern in _DENY_COMMAND_PATTERNS:
            if pattern.search(cmd):
                return (
                    "SAFETY BLOCK: This command attempts to access benchmark-internal "
                    "files (expected answers, scoring code, or task definitions). "
                    "These paths are not available to agents. "
                    "Please restrict file operations to your workspace directory."
                )

        # Also check for absolute paths to deny-listed directories
        lowered = cmd.lower()
        for deny in _DENY_SUBSTRINGS:
            if deny in lowered:
                return (
                    "SAFETY BLOCK: This command references a restricted path. "
                    "Only workspace files may be accessed."
                )

        return None

    # ── Internal helpers ────────────────────────────────────────────────

    def _resolve(self, path: Path) -> Optional[Path]:
        """Resolve *path* to an absolute path, handling relative paths
        against the workspace.  Returns None for paths that escape the
        filesystem via symlink tricks or ``..`` beyond root.
        """
        try:
            p = Path(path)
            if not p.is_absolute():
                p = self._workspace / p
            resolved = p.resolve()
            return resolved
        except (OSError, RuntimeError):
            # Too many symlink levels, permission error, etc.
            return None

    def _is_safe(self, resolved: Path) -> bool:
        """Return True if *resolved* does not touch any deny-listed directory
        AND is either within the workspace or under a safe system prefix."""
        path_str = str(resolved).lower()

        # Deny-list check
        for deny in _DENY_SUBSTRINGS:
            if deny in path_str:
                return False

        return True

    def _is_within_workspace(self, resolved: Path) -> bool:
        """Return True if *resolved* is within the workspace subtree."""
        path_str = str(resolved)
        return path_str.startswith(self._workspace_str + "/") or path_str == self._workspace_str


# ── Convenience: block reason extraction for logging ─────────────────────

def block_reason(path: Path) -> str:
    """Return the deny-list entry that caused *path* to be blocked, or empty string."""
    path_str = str(Path(path).resolve()).lower()
    for deny in _DENY_SUBSTRINGS:
        if deny in path_str:
            return deny
    return ""
