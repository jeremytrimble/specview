"""PyInstaller hook for specview to include version information."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from generate_version_info import generate_version_info
sys.path.pop(0)

import pkgutil

def hook(hook_api):
    """Generate and add version information to the package."""
    # Get the package base directory from PyInstaller
    #pkg_base = Path(hook_api.collect_data_files('specview')[0][0])

    sv_pkg = pkgutil.resolve_name( 'specview' )
    pkg_base = Path(sv_pkg.__file__).parent
    
    # Generate version info files
    generate_version_info(pkg_base)
    
    # Add version info to packaged files
    version_info_file = pkg_base / 'version_info.json'
    hook_api.add_datas([(str(version_info_file), 'specview')])