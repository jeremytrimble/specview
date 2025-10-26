"""
Performance tests for specview.

This module contains tests that measure the performance of loading and
rendering SigMF files to ensure the application maintains acceptable
performance characteristics.
"""

import time
import pytest
from pathlib import Path

from test_utils import generate_sigmf_file
from specview.loaded_file_mgmt import LoadedFilesCollection


def test_sigmf_loading_performance(tmpdir):
    """
    Test the performance of loading a SigMF file.
    
    This test measures the time taken to load a moderately-sized SigMF file
    with multiple captures and annotations, ensuring that loading times
    remain within acceptable bounds.
    """
    # Generate a test SigMF file with realistic parameters
    # 10 MHz sample rate, 5 seconds duration = 50 million samples
    meta_path = generate_sigmf_file(
        tmpdir=tmpdir,
        sample_rate=10e6,
        duration=5.0,
        num_annotations=10,
        filename="performance_test",
        generate_signal=False,  # Use zeros for faster generation
    )
    
    # Measure loading time
    lfc = LoadedFilesCollection()
    
    start_time = time.perf_counter()
    loaded_file = lfc.load_file(meta_path)
    end_time = time.perf_counter()
    
    loading_time = end_time - start_time
    
    # Verify the file was loaded correctly
    assert loaded_file is not None
    assert len(lfc.loaded_file_dict) == 1
    
    # Verify annotations were loaded
    annotations = loaded_file.get_annotations_dict()
    assert len(annotations) == 10
    
    # Verify captures were loaded
    captures = loaded_file.sigmf_file.get_captures()
    assert len(captures) == 2
    
    # Performance assertion: loading should complete in reasonable time
    # For a 5-second recording at 10 MHz (50M samples), loading should be fast
    # This is a generous threshold to avoid flaky tests on different hardware
    max_loading_time = 5.0  # seconds
    assert loading_time < max_loading_time, (
        f"Loading took {loading_time:.2f}s, which exceeds the maximum "
        f"allowed time of {max_loading_time}s"
    )
    
    # Log the actual loading time for monitoring
    print(f"\nLoading time: {loading_time:.3f} seconds")
    print(f"Samples loaded: {50_000_000:,}")
    print(f"Annotations loaded: {len(annotations)}")
    print(f"Captures loaded: {len(captures)}")


def test_sigmf_loading_performance_large_file(tmpdir):
    """
    Test the performance of loading a large SigMF file.
    
    This test measures the time taken to load a larger SigMF file
    to ensure scalability.
    """
    # Generate a larger test file
    # 20 MHz sample rate, 2 seconds duration = 40 million samples
    meta_path = generate_sigmf_file(
        tmpdir=tmpdir,
        sample_rate=20e6,
        duration=2.0,
        num_annotations=50,
        filename="large_performance_test",
        generate_signal=False,
    )
    
    # Measure loading time
    lfc = LoadedFilesCollection()
    
    start_time = time.perf_counter()
    loaded_file = lfc.load_file(meta_path)
    end_time = time.perf_counter()
    
    loading_time = end_time - start_time
    
    # Verify the file was loaded correctly
    assert loaded_file is not None
    annotations = loaded_file.get_annotations_dict()
    assert len(annotations) == 50
    
    # Performance assertion
    max_loading_time = 5.0  # seconds
    assert loading_time < max_loading_time, (
        f"Loading large file took {loading_time:.2f}s, which exceeds the maximum "
        f"allowed time of {max_loading_time}s"
    )
    
    print(f"\nLarge file loading time: {loading_time:.3f} seconds")
    print(f"Annotations loaded: {len(annotations)}")


def test_sigmf_file_with_signal_generation(tmpdir):
    """
    Test loading a SigMF file with generated signal data.
    
    This test verifies that files with actual signal data (not just zeros)
    can be loaded and processed correctly.
    """
    # Generate a file with actual signal data
    meta_path = generate_sigmf_file(
        tmpdir=tmpdir,
        sample_rate=1e6,
        duration=1.0,
        num_annotations=5,
        filename="signal_test",
        generate_signal=True,  # Generate actual signal
    )
    
    lfc = LoadedFilesCollection()
    loaded_file = lfc.load_file(meta_path)
    
    # Verify the file was loaded
    assert loaded_file is not None
    
    # Verify annotations
    annotations = loaded_file.get_annotations_dict()
    assert len(annotations) == 5
    
    # Verify all annotations have the required fields
    for ann in annotations.values():
        assert 'core:sample_start' in ann
        assert 'core:sample_count' in ann
        assert 'core:freq_lower_edge' in ann
        assert 'core:freq_upper_edge' in ann
        assert 'core:label' in ann
