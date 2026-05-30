"""Version information management for specview."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict

import logging

log = logging.getLogger(__name__)

# Edit this version string in lock-step with the version in pyproject.toml.
__version__ = "0.3.0"  # Should be a PEP 440 compliant version string.

@dataclass
class VersionInfo:
    """Structured version information."""
    version: str
    git_description: str
    git_hash: str
    build_date: str

    def __str__(self) -> str:
        """Format version information for display."""
        return (
            f"specview v{self.version}\n"
            f"Git: {self.git_description}, hash: {self.git_hash[:7]}\n"
            f"Build Date: {self.build_date}"
        )

def _load_version_info() -> Dict[str, str]:
    """Load version information from the version info file."""
    try:
        version_file = Path(__file__).parent / "version_info.json"
        if version_file.exists():
            with open(version_file) as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Failed to load version info from file: {e}")
        pass
    
    # Return development mode values if no version info file exists
    return {
        "git_description": "development",
        "git_hash": "unknown",
        "build_date": "unknown",
    }

def get_version_info() -> VersionInfo:
    """Get structured version information including git version and build date."""
    info = _load_version_info()
    return VersionInfo(
        version=__version__,
        git_description=info['git_description'],
        git_hash=info['git_hash'],
        build_date=info['build_date']
    )