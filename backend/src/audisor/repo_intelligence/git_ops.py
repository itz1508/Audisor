"""Git operations - status, diff, history, and historical file access."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError
from .path_security import validate_repository_root


class GitError(RepositoryIntelligenceError):
    """Raised when Git operations fail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


@dataclass
class GitStatusEntry:
    """A single entry in git status."""

    status: str  # "staged", "unstaged", "untracked", "renamed", "deleted"
    path: str
    original_path: str | None = None  # For renames

    def as_dict(self) -> dict:
        result = {"status": self.status, "path": self.path}
        if self.original_path:
            result["original_path"] = self.original_path
        return result


@dataclass
class GitCommit:
    """A git commit."""

    hash: str
    parent_hashes: list[str]
    author_name: str
    author_email: str
    author_timestamp: int
    subject: str
    body: str

    def as_dict(self) -> dict:
        return {
            "hash": self.hash,
            "parent_hashes": self.parent_hashes,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "author_timestamp": self.author_timestamp,
            "subject": self.subject,
            "body": self.body,
        }


def _run_git(
    repository_root: Path,
    args: list[str],
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Run a git command; raises GitError on timeout or missing git."""
    cmd = ["git", "-C", str(repository_root)] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(repository_root),
        )
        return result
    except subprocess.TimeoutExpired:
        raise GitError("git_timeout", f"Git command timed out: {' '.join(args)}")
    except FileNotFoundError:
        raise GitError("git_not_found", "Git is not installed or not in PATH")
    except Exception as exc:
        raise GitError("git_error", f"Git command failed: {exc}")


def is_git_repository(repository_root: Path) -> bool:
    """Check if the path is a git repository."""
    result = _run_git(repository_root, ["rev-parse", "--git-dir"])
    return result.returncode == 0


def get_current_branch(repository_root: Path) -> str | None:
    """Get the current branch name, or None if detached HEAD."""
    result = _run_git(repository_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return None if branch == "HEAD" else branch


def get_head_commit(repository_root: Path) -> str | None:
    """Get the HEAD commit hash, or None if not available."""
    result = _run_git(repository_root, ["rev-parse", "HEAD"])
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def is_dirty(repository_root: Path) -> bool:
    """Check if the repository has uncommitted changes."""
    result = _run_git(repository_root, ["status", "--porcelain"])
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


_STAGED_STATUS = {
    "A": "staged_added",
    "M": "staged_modified",
    "D": "staged_deleted",
    "C": "staged_copied",
    "T": "staged_type_changed",
}

_UNSTAGED_STATUS = {
    "M": "unstaged_modified",
    "D": "unstaged_deleted",
    "T": "unstaged_type_changed",
}


def _entries_for_codes(x: str, y: str, path: str) -> list[GitStatusEntry]:
    """Build status entries for non-rename porcelain codes."""
    entries: list[GitStatusEntry] = []
    # Staged changes
    if x != " " and x != "?":
        entries.append(GitStatusEntry(status=_STAGED_STATUS.get(x, "staged"), path=path))
    # Unstaged changes
    if y != " " and y != "?":
        entries.append(GitStatusEntry(status=_UNSTAGED_STATUS.get(y, "unstaged"), path=path))
    return entries


def _parse_porcelain(output: str) -> list[GitStatusEntry]:
    """Parse null-separated porcelain v1 output into status entries."""
    entries: list[GitStatusEntry] = []
    parts = output.split("\0")
    i = 0
    while i < len(parts):
        part = parts[i]
        if len(part) < 3:
            i += 1
            continue

        xy = part[:2]
        path = part[3:]
        x, y = xy[0], xy[1]

        if xy == "??":
            entries.append(GitStatusEntry(status="untracked", path=path))
        elif xy == "!!":
            entries.append(GitStatusEntry(status="ignored", path=path))
        elif x == "R" or y == "R":
            # Rename - next part is original path
            original_path = parts[i + 1] if i + 1 < len(parts) else ""
            entries.append(GitStatusEntry(
                status="renamed",
                path=path,
                original_path=original_path,
            ))
            i += 1
        else:
            entries.extend(_entries_for_codes(x, y, path))

        i += 1

    return entries


def git_status(
    repository_root: Path,
    config: Config = DEFAULT_CONFIG,
) -> list[GitStatusEntry]:
    """Get structured git status."""
    repository_root = validate_repository_root(repository_root)

    result = _run_git(repository_root, ["status", "--porcelain=v1", "-z"])
    if result.returncode != 0:
        raise GitError("git_status_failed", f"Git status failed: {result.stderr}")

    if not result.stdout:
        return []
    return _parse_porcelain(result.stdout)


def git_diff(
    repository_root: Path,
    path: str | None = None,
    staged: bool = False,
    max_bytes: int | None = None,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Get git diff, truncated to the configured byte limit."""
    repository_root = validate_repository_root(repository_root)

    args = ["diff"]
    if staged:
        args.append("--staged")
    if path:
        args.append("--")
        args.append(path)

    result = _run_git(repository_root, args)
    if result.returncode != 0:
        raise GitError("git_diff_failed", f"Git diff failed: {result.stderr}")

    diff_content = result.stdout
    truncated = False

    # Apply byte limit
    if max_bytes is None:
        max_bytes = config.max_git_diff_bytes

    if len(diff_content.encode("utf-8")) > max_bytes:
        truncated = True
        diff_bytes = diff_content.encode("utf-8")[:max_bytes]
        diff_content = diff_bytes.decode("utf-8", errors="ignore")

    return {
        "diff": diff_content,
        "truncated": truncated,
        "staged": staged,
        "path": path,
    }


def _parse_commit_block(block: str) -> GitCommit | None:
    """Parse one commit block from formatted git log output."""
    block = block.strip()
    if not block:
        return None

    lines = block.split("\n")
    if len(lines) < 6:
        return None

    try:
        return GitCommit(
            hash=lines[0].strip(),
            parent_hashes=lines[1].strip().split() if lines[1].strip() else [],
            author_name=lines[2].strip(),
            author_email=lines[3].strip(),
            author_timestamp=int(lines[4].strip()),
            subject=lines[5].strip(),
            body="\n".join(lines[6:]).strip(),
        )
    except (ValueError, IndexError):
        return None


def git_history(
    repository_root: Path,
    path: str | None = None,
    max_commits: int | None = None,
    config: Config = DEFAULT_CONFIG,
) -> list[GitCommit]:
    """Get git commit history."""
    repository_root = validate_repository_root(repository_root)

    if max_commits is None:
        max_commits = config.max_git_history_commits

    # Format: hash, parent hashes, author name, author email, author timestamp, subject, body
    format_str = "%H%n%P%n%an%n%ae%n%at%n%s%n%b%n---COMMIT_END---"

    args = ["log", f"--max-count={max_commits}", f"--format={format_str}"]
    if path:
        args.append("--")
        args.append(path)

    result = _run_git(repository_root, args)
    if result.returncode != 0:
        raise GitError("git_history_failed", f"Git log failed: {result.stderr}")

    commits: list[GitCommit] = []
    for block in result.stdout.split("---COMMIT_END---"):
        commit = _parse_commit_block(block)
        if commit:
            commits.append(commit)

    return commits


def git_show_file(
    repository_root: Path,
    revision: str,
    path: str,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Get file content from a historical revision."""
    repository_root = validate_repository_root(repository_root)

    # Verify revision exists
    result = _run_git(repository_root, ["rev-parse", "--verify", revision])
    if result.returncode != 0:
        raise GitError("revision_not_found", f"Revision not found: {revision}")

    resolved_revision = result.stdout.strip()

    # Get file content
    result = _run_git(repository_root, ["show", f"{revision}:{path}"])
    if result.returncode != 0:
        raise GitError("file_not_in_revision", f"File not found in revision {revision}: {path}")

    content = result.stdout

    return {
        "path": path,
        "revision": revision,
        "resolved_revision": resolved_revision,
        "content": content,
    }


def get_repository_info(repository_root: Path) -> dict:
    """Get repository information."""
    repository_root = validate_repository_root(repository_root)

    if not is_git_repository(repository_root):
        return {
            "is_git_repository": False,
            "error": "Not a git repository",
        }

    branch = get_current_branch(repository_root)
    head = get_head_commit(repository_root)
    dirty = is_dirty(repository_root)

    # Get remote URL
    result = _run_git(repository_root, ["remote", "get-url", "origin"])
    remote_url = result.stdout.strip() if result.returncode == 0 else None

    return {
        "is_git_repository": True,
        "repository_root": str(repository_root),
        "branch": branch,
        "head": head,
        "dirty": dirty,
        "remote_url": remote_url,
    }
