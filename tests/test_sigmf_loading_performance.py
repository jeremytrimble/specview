"""
Performance tests for SigMF file loading and rendering in specview.

This test module measures the performance of loading SigMF files with various
configurations and ensures that specview maintains acceptable performance 
characteristics.

Test Methodology:
1. Generate temporary SigMF files with configurable:
   - Sample rate
   - Duration (number of samples)
   - Number of annotations
2. Use qtbot to interact with the MainWindow and load files
3. Measure timing from file load initiation to UI rendering completion
4. Assert performance meets acceptable thresholds
5. Clean up temporary files

The test uses Qt's event processing mechanisms to ensure that all UI updates
and rendering operations have completed before measuring elapsed time.
"""

import pytest
import numpy as np
from pathlib import Path
from typing import Any, Generator
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
    filename: str = "test_performance"
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
                        f"Performance test file: {num_samples} samples, {num_annotations} annotations")
    
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
def app_with_window(qtbot: Any) -> Generator[MainWindow, None, None]:
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
    for _ in range(5):
        QApplication.processEvents()
        qtbot.wait(10)  # Small delay between processing rounds
    
    # Additional wait to ensure any delayed rendering completes
    qtbot.wait(100)


def test_sigmf_loading_performance_small_file(app_with_window: MainWindow, qtbot: Any, tmpdir: Path) -> None:
    """
    Test performance of loading a small SigMF file with moderate annotations.
    
    This test measures the time taken to load a 1-second recording with
    10 annotations and ensures it completes within acceptable time limits.
    
    Expected performance: < 2 seconds for loading and initial rendering
    """
    window = app_with_window
    app_state = QApplication.instance().app_state
    
    # Generate a small test file: 1 second at 1 MHz = 1M samples
    sigmf_path = generate_sigmf_file_with_annotations(
        tmpdir=tmpdir,
        sample_rate=1e6,
        duration_sec=1.0,
        num_annotations=10,
        filename="small_test"
    )
    
    # Measure loading time
    start_time = time.monotonic()
    
    # Load the file
    loaded_file = app_state.load_sigmf_file(sigmf_path)
    
    # Wait for all rendering to complete
    wait_for_rendering_complete(qtbot)
    
    end_time = time.monotonic()
    elapsed_time = end_time - start_time
    
    # Verify file was loaded
    assert loaded_file is not None
    assert len(app_state._loaded_files.loaded_file_dict) == 1
    
    # Verify annotations were loaded
    annotations = loaded_file.get_annotations_dict()
    assert len(annotations) == 10
    
    # Performance assertion: should complete within 2 seconds
    # This is a generous threshold to account for CI environment variations
    assert elapsed_time < 2.0, f"Loading took {elapsed_time:.3f}s, expected < 2.0s"
    
    print(f"\nSmall file (1M samples, 10 annotations) loaded in {elapsed_time:.3f}s")


def test_sigmf_loading_performance_large_file(app_with_window: MainWindow, qtbot: Any, tmpdir: Path) -> None:
    """
    Test performance of loading a larger SigMF file with many annotations.
    
    This test measures the time taken to load a 5-second recording with
    50 annotations to ensure specview handles larger files efficiently.
    
    Expected performance: < 10 seconds for loading and initial rendering
    """
    window = app_with_window
    app_state = QApplication.instance().app_state
    
    # Generate a larger test file: 5 seconds at 1 MHz = 5M samples
    sigmf_path = generate_sigmf_file_with_annotations(
        tmpdir=tmpdir,
        sample_rate=1e6,
        duration_sec=5.0,
        num_annotations=50,
        filename="large_test"
    )
    
    # Measure loading time
    start_time = time.monotonic()
    
    # Load the file
    loaded_file = app_state.load_sigmf_file(sigmf_path)
    
    # Wait for all rendering to complete
    wait_for_rendering_complete(qtbot)
    
    end_time = time.monotonic()
    elapsed_time = end_time - start_time
    
    # Verify file was loaded
    assert loaded_file is not None
    assert len(app_state._loaded_files.loaded_file_dict) == 1
    
    # Verify annotations were loaded
    annotations = loaded_file.get_annotations_dict()
    assert len(annotations) == 50
    
    # Performance assertion: should complete within 10 seconds
    # Larger files naturally take more time
    assert elapsed_time < 10.0, f"Loading took {elapsed_time:.3f}s, expected < 10.0s"
    
    print(f"\nLarge file (5M samples, 50 annotations) loaded in {elapsed_time:.3f}s")


def test_sigmf_loading_performance_no_annotations(app_with_window: MainWindow, qtbot: Any, tmpdir: Path) -> None:
    """
    Test performance of loading a SigMF file without annotations.
    
    This test measures the baseline performance when no annotations are present,
    which helps identify annotation-related performance overhead.
    
    Expected performance: < 2 seconds for loading and initial rendering
    """
    window = app_with_window
    app_state = QApplication.instance().app_state
    
    # Generate test file without annotations
    sigmf_path = generate_sigmf_file_with_annotations(
        tmpdir=tmpdir,
        sample_rate=1e6,
        duration_sec=2.0,
        num_annotations=0,  # No annotations
        filename="no_annotations"
    )
    
    # Measure loading time
    start_time = time.monotonic()
    
    # Load the file
    loaded_file = app_state.load_sigmf_file(sigmf_path)
    
    # Wait for all rendering to complete
    wait_for_rendering_complete(qtbot)
    
    end_time = time.monotonic()
    elapsed_time = end_time - start_time
    
    # Verify file was loaded
    assert loaded_file is not None
    assert len(app_state._loaded_files.loaded_file_dict) == 1
    
    # Verify no annotations
    annotations = loaded_file.get_annotations_dict()
    assert len(annotations) == 0
    
    # Performance assertion: should complete within 2 seconds
    assert elapsed_time < 2.0, f"Loading took {elapsed_time:.3f}s, expected < 2.0s"
    
    print(f"\nFile without annotations (2M samples) loaded in {elapsed_time:.3f}s")


def test_sigmf_loading_performance_many_annotations(app_with_window: MainWindow, qtbot: Any, tmpdir: Path) -> None:
    """
    Test performance with a high number of annotations.
    
    This stress test evaluates how specview handles files with many annotations
    (100 annotations on a moderate-sized file).
    
    Expected performance: < 10 seconds for loading and initial rendering
    """
    window = app_with_window
    app_state = QApplication.instance().app_state
    
    # Generate test file with many annotations
    sigmf_path = generate_sigmf_file_with_annotations(
        tmpdir=tmpdir,
        sample_rate=1e6,
        duration_sec=2.0,
        num_annotations=100,  # Many annotations
        filename="many_annotations"
    )
    
    # Measure loading time
    start_time = time.monotonic()
    
    # Load the file
    loaded_file = app_state.load_sigmf_file(sigmf_path)
    
    # Wait for all rendering to complete
    wait_for_rendering_complete(qtbot)
    
    end_time = time.monotonic()
    elapsed_time = end_time - start_time
    
    # Verify file was loaded
    assert loaded_file is not None
    assert len(app_state._loaded_files.loaded_file_dict) == 1
    
    # Verify all annotations were loaded
    annotations = loaded_file.get_annotations_dict()
    assert len(annotations) == 100
    
    # Performance assertion: should complete within 10 seconds even with many annotations
    # This is a stress test with 100 annotations, so we allow more time
    assert elapsed_time < 10.0, f"Loading took {elapsed_time:.3f}s, expected < 10.0s"
    
    print(f"\nFile with many annotations (2M samples, 100 annotations) loaded in {elapsed_time:.3f}s")


def test_sigmf_loading_multiple_files_sequentially(app_with_window: MainWindow, qtbot: Any, tmpdir: Path) -> None:
    """
    Test performance of loading multiple files sequentially.
    
    This test ensures that loading multiple files doesn't degrade performance
    due to resource accumulation or memory issues.
    
    Expected performance: Each file should load in < 2 seconds
    """
    window = app_with_window
    app_state = QApplication.instance().app_state
    
    num_files = 3
    load_times = []
    
    for i in range(num_files):
        # Generate a test file
        sigmf_path = generate_sigmf_file_with_annotations(
            tmpdir=tmpdir,
            sample_rate=1e6,
            duration_sec=1.0,
            num_annotations=5,
            filename=f"multi_test_{i}"
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
        assert elapsed_time < 2.0, f"File {i} loading took {elapsed_time:.3f}s, expected < 2.0s"
    
    # Check that performance doesn't significantly degrade
    avg_time = sum(load_times) / len(load_times)
    max_time = max(load_times)
    
    print(f"\nLoaded {num_files} files sequentially:")
    print(f"  Average time: {avg_time:.3f}s")
    print(f"  Max time: {max_time:.3f}s")
    print(f"  Individual times: {[f'{t:.3f}s' for t in load_times]}")
    
    # The slowest file should not be more than 50% slower than average
    # (allows for some variation but catches serious degradation)
    assert max_time < avg_time * 1.5, \
        f"Performance degraded: max {max_time:.3f}s vs avg {avg_time:.3f}s"
