"""Generate version information at build time."""

import subprocess
import datetime
import json
import os
from pathlib import Path

def get_git_info() -> str:
    """Get git version information using git describe."""
    try:
        result = subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"

def get_git_hash() -> str:
    """Get git version information using git describe."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"

def generate_version_info(target_dir: str | Path) -> None:
    """Generate version information files at build time.
    
    Args:
        target_dir: Directory where the version info files should be written
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate version info
    version_info = {
        "git_description": get_git_info(),
        "git_hash": get_git_hash(),
        "build_date": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    
    # Write version info
    with open(target_dir / "version_info.json", "w") as f:
        json.dump(version_info, f)

if __name__ == "__main__":
    # When run directly, generate in the current package
    pkg_dir = Path(__file__).parent.parent / "src" / "specview"
    generate_version_info(pkg_dir)