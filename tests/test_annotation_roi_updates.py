"""
Test annotation ROI updates propagate to LoadedAnnotationDict
"""
import pytest
import numpy as np
from pathlib import Path
import sigmf

from specview.loaded_file_mgmt import LoadedFilesCollection, LoadedFile, LoadedAnnotationDict


def test_update_frequency_range():
    """Test that update_frequency_range_Hz properly updates annotation fields"""
    # Create a simple SigMF file in memory
    smf = sigmf.SigMFFile()
    smf.set_global_field(sigmf.SigMFFile.DATATYPE_KEY, 'cf32_le')  # Complex float32
    smf.set_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY, 1e6)  # 1 MHz sample rate
    smf.add_capture(start_index=0, metadata={})
    
    # Add an annotation
    smf.add_annotation(start_index=100, length=500, metadata={
        sigmf.SigMFFile.FLO_KEY: 2.4e9,
        sigmf.SigMFFile.FHI_KEY: 2.4e9 + 100e3,
    })
    
    # Create LoadedFilesCollection and mock a file
    lfc = LoadedFilesCollection()
    
    # We need to create a LoadedFile, but it requires a file path
    # For this test, we'll create the annotation dict directly
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir) / "test.sigmf-data"
        
        # Create dummy data file
        dummy_data = np.zeros(1000, dtype=np.complex64)
        dummy_data.tofile(tmppath)
        
        # Save metadata
        smf.tofile(tmppath)
        
        # Load the file
        meta_path = tmppath.with_suffix('.sigmf-meta')
        loaded_file = lfc.load_file(meta_path)
        
        # Get the annotation
        annotations = loaded_file.get_annotations_dict()
        assert len(annotations) == 1
        
        ann_id = list(annotations.keys())[0]
        ann = annotations[ann_id]
        
        # Verify initial frequency range
        freq_range = ann.get_frequency_range_Hz()
        assert freq_range is not None
        assert freq_range[0] == 2.4e9
        assert freq_range[1] == 2.4e9 + 100e3
        
        # Update frequency range
        new_lo = 2.5e9
        new_hi = 2.5e9 + 200e3
        ann.update_frequency_range_Hz(new_lo, new_hi)
        
        # Verify the update
        freq_range = ann.get_frequency_range_Hz()
        assert freq_range is not None
        assert freq_range[0] == new_lo
        assert freq_range[1] == new_hi


def test_update_time_range_relative_to_capture():
    """Test that update_time_range_relative_to_capture properly updates annotation time fields"""
    # Create a simple SigMF file in memory
    smf = sigmf.SigMFFile()
    smf.set_global_field(sigmf.SigMFFile.DATATYPE_KEY, 'cf32_le')  # Complex float32
    sample_rate = 1e6  # 1 MHz sample rate
    smf.set_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY, sample_rate)
    smf.add_capture(start_index=0, metadata={})
    
    # Add an annotation starting at sample 100 with length 500
    smf.add_annotation(start_index=100, length=500, metadata={})
    
    # Create LoadedFilesCollection
    lfc = LoadedFilesCollection()
    
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir) / "test.sigmf-data"
        
        # Create dummy data file
        dummy_data = np.zeros(1000, dtype=np.complex64)
        dummy_data.tofile(tmppath)
        
        # Save metadata
        smf.tofile(tmppath)
        
        # Load the file
        meta_path = tmppath.with_suffix('.sigmf-meta')
        loaded_file = lfc.load_file(meta_path)
        
        # Get the capture
        captures = list(loaded_file._capture_id_to_capture.keys())
        assert len(captures) == 1
        capture_id = captures[0]
        
        # Get the annotation
        annotations = loaded_file.get_annotations_dict()
        assert len(annotations) == 1
        
        ann_id = list(annotations.keys())[0]
        ann = annotations[ann_id]
        
        # Verify initial time range (start=100, length=500 samples at 1 MHz = 0.0001 to 0.0006 seconds)
        time_range = ann.get_time_range_relative_to_capture(capture_id)
        assert time_range is not None
        expected_start = 100 / sample_rate  # 0.0001 seconds
        expected_end = (100 + 500) / sample_rate  # 0.0006 seconds
        assert abs(time_range[0] - expected_start) < 1e-9
        assert abs(time_range[1] - expected_end) < 1e-9
        
        # Update time range to new values
        new_start_sec = 0.0002  # 200 samples
        new_end_sec = 0.0008    # 800 samples
        ann.update_time_range_relative_to_capture(capture_id, new_start_sec, new_end_sec)
        
        # Verify the update
        time_range = ann.get_time_range_relative_to_capture(capture_id)
        assert time_range is not None
        assert abs(time_range[0] - new_start_sec) < 1e-6
        assert abs(time_range[1] - new_end_sec) < 1e-6
        
        # Also verify the underlying fields
        assert ann[sigmf.SigMFFile.START_INDEX_KEY] == int(new_start_sec * sample_rate)
        assert ann[sigmf.SigMFFile.LENGTH_INDEX_KEY] == int((new_end_sec - new_start_sec) * sample_rate)
