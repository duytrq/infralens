"""Best-effort checkout metadata, captured before generating scan artifacts."""

import os
import re
import subprocess
from pathlib import Path


def source_metadata(directory):
    fallback = {"relative_path": "."}
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"

    def git(*args, detached_ok=False):
        result = subprocess.run(
            ["git", "-C", str(directory), *args],
            env=env,
            capture_output=True,
            encoding="utf-8",
            timeout=5,
        )
        if detached_ok and result.returncode == 1:
            return None
        result.check_returncode()
        return result.stdout.rstrip("\r\n")

    try:
        directory = Path(directory).resolve()
        root = Path(git("rev-parse", "--show-toplevel")).resolve()
        relative = directory.relative_to(root).as_posix()
        commit = git("rev-parse", "--verify", "HEAD")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            return fallback
        branch = git("symbolic-ref", "--quiet", "--short", "HEAD", detached_ok=True)
        if branch is not None and (
            not branch or len(branch) > 255 or not branch.isprintable()
        ):
            branch = None
        if len(relative) > 512 or not relative.isprintable():
            return fallback
        dirty = bool(git("status", "--porcelain=v1", "--untracked-files=normal"))
        return {
            "relative_path": relative,
            "git": {"commit": commit, "branch": branch, "dirty": dirty},
        }
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError):
        return fallback
