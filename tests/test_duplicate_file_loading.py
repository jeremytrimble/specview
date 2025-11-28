"""Test that duplicate file loading is prevented."""
import pytest
from pathlib import Path
import numpy as np
from sigmf import SigMFFile

from specview.app_state import AppState


@pytest.fixture(scope="module")
def qtapplication():
    """Fixture to initialize a Qt application for testing."""
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    yield app

def generate_example_sigmffile(tmpdir, filename="example") -> Path:
    """Generate a simple SigMF file for testing."""
    TOTAL_NUM_SAMPLES = 1000
    np.zeros(TOTAL_NUM_SAMPLES, dtype=np.complex64).tofile(tmpdir / f"{filename}.sigmf-data")

    smf = SigMFFile()
    smf.set_global_field(SigMFFile.DATATYPE_KEY, "cf32_le")
    smf.set_global_field(SigMFFile.SAMPLE_RATE_KEY, 1e6)
    smf.add_capture(start_index=0, metadata={SigMFFile.FREQUENCY_KEY: 2.4e9})
    smf.set_data_file(str(tmpdir / f"{filename}.sigmf-data"))
    smf.tofile(tmpdir / f"{filename}.sigmf-meta")

    return Path(tmpdir / f"{filename}.sigmf-meta")


def test_duplicate_file_loading_prevention(tmpdir, qtapplication):
    """Test that attempting to load the same file twice returns None the second time."""
    app_state = AppState(parent=qtapplication)
    sigmf_path = generate_example_sigmffile(tmpdir)

    # First load should succeed
    loaded_file1 = app_state.load_sigmf_file(sigmf_path)
    assert loaded_file1 is not None
    assert len(app_state._loaded_files.loaded_file_dict) == 1

    # Second load of the same file should return None
    loaded_file2 = app_state.load_sigmf_file(sigmf_path)
    assert loaded_file2 is None
    assert len(app_state._loaded_files.loaded_file_dict) == 1  # Still only one file loaded


def test_loading_different_files(tmpdir, qtapplication):
    """Test that loading different files works correctly."""
    app_state = AppState(parent=qtapplication)
    sigmf_path1 = generate_example_sigmffile(tmpdir, "file1")
    sigmf_path2 = generate_example_sigmffile(tmpdir, "file2")

    # Load first file
    loaded_file1 = app_state.load_sigmf_file(sigmf_path1)
    assert loaded_file1 is not None
    assert len(app_state._loaded_files.loaded_file_dict) == 1

    # Load second file
    loaded_file2 = app_state.load_sigmf_file(sigmf_path2)
    assert loaded_file2 is not None
    assert len(app_state._loaded_files.loaded_file_dict) == 2

    # Verify they are different files
    assert loaded_file1.file_id != loaded_file2.file_id


# TODO: should we do any special handling for symlinks?  seems confusing and maybe impossible to be right in all cases
@pytest.mark.xfail
def test_duplicate_detection_with_symlinks(tmpdir, qtapplication):
    """Test that duplicate detection works even with symlinks."""
    app_state = AppState(parent=qtapplication)
    sigmf_path = generate_example_sigmffile(tmpdir)

    # Create a symlink to the file
    symlink_path = tmpdir / "symlink.sigmf-meta"
    symlink_path.mksymlinkto(sigmf_path)

    # Load via the original path
    loaded_file1 = app_state.load_sigmf_file(sigmf_path)
    assert loaded_file1 is not None
    assert len(app_state._loaded_files.loaded_file_dict) == 1

    # Try to load via the symlink - should be detected as duplicate
    loaded_file2 = app_state.load_sigmf_file(symlink_path)
    assert loaded_file2 is None
    assert len(app_state._loaded_files.loaded_file_dict) == 1


def test_loading_multiple_files_at_once(tmpdir, qtapplication):
    """Test that loading multiple different files works correctly."""
    app_state = AppState(parent=qtapplication)
    
    # Generate multiple files
    sigmf_paths = [
        generate_example_sigmffile(tmpdir, f"file{i}")
        for i in range(3)
    ]

    # Load all files
    loaded_files = []
    for path in sigmf_paths:
        loaded_file = app_state.load_sigmf_file(path)
        assert loaded_file is not None
        loaded_files.append(loaded_file)

    # Verify all files are loaded
    assert len(app_state._loaded_files.loaded_file_dict) == 3
    
    # Verify they are all different
    file_ids = [lf.file_id for lf in loaded_files]
    assert len(set(file_ids)) == 3

    # Try to reload the first file - should return None
    loaded_file_duplicate = app_state.load_sigmf_file(sigmf_paths[0])
    assert loaded_file_duplicate is None
    assert len(app_state._loaded_files.loaded_file_dict) == 3  # Still only 3 files
