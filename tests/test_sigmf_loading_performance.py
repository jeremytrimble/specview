"""
The test uses Qt's event processing mechanisms to ensure that all UI updates
and rendering operations have completed before measuring elapsed time.
"""

import pytest
from dataclasses import dataclass
from typing import NamedTuple


@dataclass
class TestParams:
    """Parameters for SigMF file loading performance tests."""
    name: str
    sample_rate: float
    duration_sec: float
    num_annotations: int
    max_load_time: float
    center_frequency: float = 2.4e9
    description: str = ""


# Test case configurations
TEST_CASES = [
    TestParams(
        name="small_file",
        sample_rate=1e6,
        duration_sec=1.0,
        num_annotations=10,
        max_load_time=2.0,
        description="Small file with moderate annotations"
    ),
    TestParams(
        name="large_file",
        sample_rate=1e6,
        duration_sec=5.0,
        num_annotations=50,
        max_load_time=10.0,
        description="Large file with many annotations"
    ),
    TestParams(
        name="no_annotations",
        sample_rate=1e6,
        duration_sec=2.0,
        num_annotations=0,
        max_load_time=2.0,
        description="Moderate file with no annotations"
    ),
    TestParams(
        name="many_annotations",
        sample_rate=1e6,
        duration_sec=2.0,
        num_annotations=600,
        max_load_time=10.0,
        description="Moderate file with high annotation count"
    ),
]
import numpy as np
from pathlib import Path
from typing import Any, Iterator
from sigmf import SigMFFile
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings, QThreadPool, QTimer, QEventLoop
from PyQt5.QtTest import QTest
import time

from specview.main import MainWindow
from specview.app_state import AppState
from specview.ui_constants import SETTINGS_ORGANIZATION, SETTINGS_APPLICATION


def generate_sigmf_file_with_annotations(
    tmpdir: Path,
    sample_rate: float = 1e6,
    duration_sec: float = 1.0,
    num_annotations: int = 10,
    center_frequency: float = 2.4e9,
    filename: str = "test_performance",
    description: str = ""
) -> Path:
    """
    Generate a SigMF file with specified parameters for performance testing.
    
    Args:
        tmpdir: pytest temporary directory fixture
        sample_rate: Sample rate in Hz (default: 1 MHz)
        duration_sec: Duration of the recording in seconds (default: 1 second)
        num_annotations: Number of annotations to create (default: 10)
        center_frequency: Center frequency in Hz (default: 2.4 GHz)
        filename: Base filename without extension
        description: Optional description to add to metadata
        
    Returns:
        Path to the generated .sigmf-meta file
    """
    # Calculate total number of samples
    num_samples = int(sample_rate * duration_sec)
    
    # Generate complex64 data (random noise for testing)
    # Using zeros for faster file creation, as actual data doesn't matter for performance testing
    data = np.zeros(num_samples, dtype=np.complex64)
    
    # Write data file
    data_path = tmpdir / f"{filename}.sigmf-data"
    data.tofile(data_path)
    
    # Create SigMF metadata
    smf = SigMFFile()
    smf.set_global_field(SigMFFile.DATATYPE_KEY, "cf32_le")
    smf.set_global_field(SigMFFile.SAMPLE_RATE_KEY, sample_rate)
    smf.set_global_field(SigMFFile.DESCRIPTION_KEY, 
                        f"Performance test file: {num_samples} samples, {num_annotations} annotations{' - ' + description if description else ''}")
    
    # Add a single capture segment
    smf.add_capture(start_index=0, metadata={
        SigMFFile.FREQUENCY_KEY: center_frequency,
    })
    
    # Set the data file
    smf.set_data_file(str(data_path))
    
    # Add annotations distributed throughout the recording
    if num_annotations > 0:
        # Distribute annotations evenly across the recording
        annotation_spacing = num_samples // (num_annotations + 1)
        annotation_length = max(1000, num_samples // (num_annotations * 10))  # 10% of spacing
        
        for i in range(num_annotations):
            start_idx = annotation_spacing * (i + 1)
            # Ensure annotation doesn't exceed file bounds
            if start_idx + annotation_length > num_samples:
                annotation_length = num_samples - start_idx - 1
                
            if annotation_length > 0:
                smf.add_annotation(
                    start_index=start_idx,
                    length=annotation_length,
                    metadata={
                        SigMFFile.FLO_KEY: center_frequency - 50e3,
                        SigMFFile.FHI_KEY: center_frequency + 50e3,
                        SigMFFile.LABEL_KEY: f"Test Signal {i+1}",
                    }
                )
    
    # Write metadata file
    meta_path = tmpdir / f"{filename}.sigmf-meta"
    smf.tofile(meta_path)
    
    return Path(meta_path)


@pytest.fixture
def app_with_window(qtbot: Any) -> Iterator[MainWindow]:
    """
    Create QApplication with MainWindow for testing.
    
    This fixture sets up a complete application environment including:
    - QApplication instance
    - AppState for managing application state
    - ThreadPool for async operations
    - MainWindow with all dock widgets
    
    The window is shown to ensure proper rendering behavior.
    Each test gets a fresh app_state to ensure test isolation.
    """
    # Initialize app
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    
    # Create a fresh app_state for each test to ensure isolation
    app.app_state = AppState(parent=app)
    
    # Set up thread pool if not already present
    if not hasattr(app, 'thread_pool'):
        app.thread_pool = QThreadPool()
        app.thread_pool.setMaxThreadCount(4)
    
    # Clear settings before test to ensure consistent state
    settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
    settings.clear()
    
    # Create and show window
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    
    # Process events to ensure window is fully initialized
    qtbot.waitExposed(window)
    
    yield window
    
    # Cleanup
    window.close()
    settings.clear()


def wait_for_rendering_complete(qtbot: Any, timeout_ms: int = 5000) -> None:
    """
    Wait for all pending UI rendering operations to complete.
    
    This function processes all pending Qt events and waits for any
    asynchronous rendering operations to finish. It uses a timer-based
    approach to ensure that the event queue is empty and stable.
    
    Args:
        qtbot: pytest-qt bot fixture
        timeout_ms: Maximum time to wait in milliseconds
    """
    # Process all pending events multiple times to ensure completion
    # This is necessary because some operations may queue additional events
    print("exiting wait_for_rendering_complete")
    for _ in range(5):
        QApplication.processEvents()
        qtbot.wait(10)  # Small delay between processing rounds
    
    # Additional wait to ensure any delayed rendering completes
    qtbot.wait(100)
    print("exiting wait_for_rendering_complete")


@pytest.mark.parametrize("test_params", TEST_CASES, ids=lambda p: p.name)
def test_sigmf_loading_performance(
    app_with_window: MainWindow, 
    qtbot: Any, 
    tmpdir: Path, 
    test_params: TestParams
) -> None:
    """
    Test SigMF file loading performance with various configurations.
    
    This test runs with different parameters to verify performance across
    various file sizes and annotation counts. Each configuration has its
    own performance threshold defined in the test parameters.
    
    Args:
        app_with_window: MainWindow fixture
        qtbot: Qt bot fixture for UI testing
        tmpdir: Temporary directory fixture
        test_params: TestParams instance containing test configuration
    """
    window = app_with_window
    app_state = QApplication.instance().app_state
    
    # Generate test file based on parameters
    sigmf_path = generate_sigmf_file_with_annotations(
        tmpdir=tmpdir,
        sample_rate=test_params.sample_rate,
        duration_sec=test_params.duration_sec,
        num_annotations=test_params.num_annotations,
        center_frequency=test_params.center_frequency,
        filename=test_params.name,
        description=test_params.description
    )
    print(f"Generated file at {sigmf_path}")
    
    # Measure loading time
    start_time = time.monotonic()
    
    # Load the file
    loaded_file = app_state.load_sigmf_file(sigmf_path)
    print(f"Loading {sigmf_path}")
    
    # Wait for all rendering to complete
    wait_for_rendering_complete(qtbot)
    
    end_time = time.monotonic()
    elapsed_time = end_time - start_time
    
    # Verify file was loaded
    assert loaded_file is not None
    assert len(app_state._loaded_files.loaded_file_dict) == 1
    
    # Verify annotations were loaded
    annotations = loaded_file.get_annotations_dict()
    assert len(annotations) == test_params.num_annotations
    
    # Performance assertion
    assert elapsed_time < test_params.max_load_time, \
        f"Loading took {elapsed_time:.3f}s, expected < {test_params.max_load_time:.1f}s"
    
    print(f"\n{test_params.name} loaded in {elapsed_time:.3f}s")


def test_sigmf_loading_multiple_files_sequentially(app_with_window: MainWindow, qtbot: Any, tmpdir: Path) -> None:
    """
    Test performance of loading multiple files sequentially.
    
    This test ensures that loading multiple files doesn't degrade performance
    due to resource accumulation or memory issues.
    
    Expected performance: Each file should load in < 2 seconds
    """
    window = app_with_window
    app_state = QApplication.instance().app_state
    
    # Create a test params for multiple small files
    multi_test_params = TestParams(
        name="multi_test",
        sample_rate=1e6,
        duration_sec=1.0,
        num_annotations=5,
        max_load_time=2.0,
        description="Small file for multiple file test"
    )
    
    num_files = 3
    load_times = []
    
    for i in range(num_files):
        # Create a copy of params with unique name for each file
        file_params = TestParams(
            **{**multi_test_params.__dict__, "name": f"multi_test_{i}"}
        )
        
        # Generate a test file
        sigmf_path = generate_sigmf_file_with_annotations(tmpdir=tmpdir,
            sample_rate=file_params.sample_rate,
            duration_sec=file_params.duration_sec,
            num_annotations=file_params.num_annotations,
            center_frequency=file_params.center_frequency,
            filename=file_params.name,
            description=file_params.description
        )
        
        # Measure loading time for this file
        start_time = time.monotonic()
        
        loaded_file = app_state.load_sigmf_file(sigmf_path)
        wait_for_rendering_complete(qtbot)
        
        end_time = time.monotonic()
        elapsed_time = end_time - start_time
        load_times.append(elapsed_time)
        
        # Verify file was loaded
        assert loaded_file is not None
    
    # Verify all files are loaded
    assert len(app_state._loaded_files.loaded_file_dict) == num_files
    
    # Performance assertion: each file should load reasonably quickly
    for i, elapsed_time in enumerate(load_times):
        assert elapsed_time < multi_test_params.max_load_time, \
            f"File {i} loading took {elapsed_time:.3f}s, expected < {multi_test_params.max_load_time:.1f}s"
    
    # Check that performance doesn't significantly degrade
    avg_time = sum(load_times) / len(load_times)
    max_time = max(load_times)
    
    print(f"\nLoaded {num_files} files sequentially:")
    print(f"  Average time: {avg_time:.3f}s")
    print(f"  Max time: {max_time:.3f}s")
    print(f"  Individual times: {[f'{t:.3f}s' for t in load_times]}")
    
    # The slowest file should not be more than 100% slower than average
    # (allows for normal CI environment variation but catches serious degradation)
    assert max_time < avg_time * 2.0, \
        f"Performance degraded: max {max_time:.3f}s vs avg {avg_time:.3f}s"
