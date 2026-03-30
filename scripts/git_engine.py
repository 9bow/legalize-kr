"""Git operations for committing law files with historical dates."""

import logging
import os
import subprocess
from pathlib import Path

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)


def _run_git(*args: str, env: dict | None = None) -> str:
    """Run a git command and return stdout."""
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=merged_env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def file_has_changes(file_path: str) -> bool:
    """Check if a file has uncommitted changes or is untracked."""
    status = _run_git("status", "--porcelain", "--", file_path)
    return bool(status)


def commit_exists(mst: str, date: str) -> bool:
    """Check if a commit for this MST+date already exists (idempotency)."""
    try:
        log = _run_git(
            "log", "--oneline", "--all",
            f"--grep=법령MST: {mst}",
        )
        return bool(log)
    except RuntimeError:
        return False


def commit_law(
    file_path: str,
    message: str,
    date: str,
    mst: str,
) -> str | None:
    """Stage and commit a law file with historical date.

    Args:
        file_path: Relative path to the law file (e.g., kr/법률/253527.md)
        message: Commit message
        date: Date in YYYY-MM-DD format for GIT_AUTHOR_DATE and GIT_COMMITTER_DATE
        mst: 법령MST for idempotency tag in commit message

    Returns:
        Commit hash if committed, None if skipped.
    """
    abs_path = PROJECT_ROOT / file_path
    if not abs_path.exists():
        logger.error(f"File not found: {abs_path}")
        return None

    if commit_exists(mst, date):
        logger.info(f"Commit already exists for MST:{mst} on {date}, skipping")
        return None

    # Stage the file
    _run_git("add", file_path)

    if not file_has_changes(file_path):
        logger.info(f"No changes for {file_path}, skipping")
        return None

    # Commit with historical date (git cannot handle dates before Unix epoch)
    if date < "1970-01-01":
        date = "1970-01-01"
    iso_date = f"{date}T12:00:00+09:00"

    env = {
        "GIT_AUTHOR_DATE": iso_date,
        "GIT_COMMITTER_DATE": iso_date,
    }

    _run_git("commit", "-m", message, "--", file_path, env=env)

    commit_hash = _run_git("rev-parse", "HEAD")
    logger.info(f"Committed {file_path} [{commit_hash[:8]}] date={date}")
    return commit_hash
