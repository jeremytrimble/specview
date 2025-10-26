"""
Test utilities module for specview tests.

This module provides reusable utilities for generating test data and files.
"""

import numpy as np
from pathlib import Path
from typing import Optional
from sigmf import SigMFFile
import pytest


def generate_sigmf_file(
    tmpdir: Path,
    sample_rate: float = 1e6,
    duration: float = 2.0,
    num_annotations: int = 2,
    filename: str = "test",
    signal_type: str = "cf32_le",
    center_frequency: float = 2.4e9,
    generate_signal: bool = False,
) -> Path:
    """
    Generate a SigMF file with configurable parameters for testing.
    
    This function creates both the metadata (.sigmf-meta) and data (.sigmf-data) files
    according to the SigMF specification. The data file contains either zeros or a 
    simple test signal depending on the generate_signal parameter.
    
    Parameters
    ----------
    tmpdir : Path
        Directory where the SigMF files will be created. Typically a pytest tmpdir fixture.
    sample_rate : float, optional
        Sample rate in Hz. Default is 1e6 (1 MHz).
    duration : float, optional
        Duration of the recording in seconds. Default is 2.0 seconds.
    num_annotations : int, optional
        Number of annotations to add to the file. Default is 2.
        Annotations are evenly distributed across the recording.
    filename : str, optional
        Base filename (without extension). Default is "test".
    signal_type : str, optional
        SigMF data type string. Default is "cf32_le" (complex float32 little-endian).
        Supported types: "cf32_le", "cf64_le".
    center_frequency : float, optional
        Center frequency in Hz. Default is 2.4e9 (2.4 GHz).
    generate_signal : bool, optional
        If True, generates a simple test signal (complex exponential).
        If False (default), fills the data file with zeros.
    
    Returns
    -------
    Path
        Path to the generated .sigmf-meta file.
    
    Examples
    --------
    >>> # Generate a simple SigMF file with defaults
    >>> meta_path = generate_sigmf_file(tmpdir)
    
    >>> # Generate a file with custom parameters
    >>> meta_path = generate_sigmf_file(
    ...     tmpdir,
    ...     sample_rate=10e6,
    ...     duration=5.0,
    ...     num_annotations=5,
    ...     filename="custom_test",
    ...     generate_signal=True
    ... )
    
    Notes
    -----
    - The function creates two captures, splitting the recording in half
    - Annotations are distributed evenly across the recording
    - Each annotation has frequency bounds (FLO/FHI) of ±100 kHz around center frequency
    - Temporary files are created in tmpdir and should be cleaned up by pytest
    """
    # Convert tmpdir to Path if needed
    tmpdir = Path(tmpdir)
    
    # Calculate total number of samples
    total_num_samples = int(sample_rate * duration)
    
    # Create data file with zeros or generated signal
    data_path = tmpdir / f"{filename}.sigmf-data"
    
    if generate_signal:
        # Generate a simple test signal (complex exponential)
        t = np.arange(total_num_samples) / sample_rate
        # Create a tone at offset frequency
        tone_freq = 50e3  # 50 kHz offset
        signal = np.exp(2j * np.pi * tone_freq * t).astype(np.complex64)
        signal.tofile(data_path)
    else:
        # Fill with zeros
        np.zeros(total_num_samples, dtype=np.complex64).tofile(data_path)
    
    # Create SigMF metadata
    smf = SigMFFile()
    smf.set_global_field(SigMFFile.DATATYPE_KEY, signal_type)
    smf.set_global_field(SigMFFile.SAMPLE_RATE_KEY, sample_rate)
    smf.set_data_file(str(data_path))
    
    # Add two captures (split the recording in half)
    samples_per_capture = total_num_samples // 2
    smf.add_capture(start_index=0, metadata={SigMFFile.FREQUENCY_KEY: center_frequency})
    smf.add_capture(
        start_index=samples_per_capture,
        metadata={SigMFFile.FREQUENCY_KEY: center_frequency}
    )
    
    # Add annotations evenly distributed across the recording
    if num_annotations > 0:
        # Calculate annotation parameters
        annotation_duration_samples = total_num_samples // (num_annotations * 3)
        spacing = (total_num_samples - annotation_duration_samples) // max(1, num_annotations - 1) if num_annotations > 1 else 0
        
        for i in range(num_annotations):
            if num_annotations == 1:
                start_idx = total_num_samples // 4
            else:
                start_idx = i * spacing
            
            # Ensure annotations don't exceed the total sample count
            if start_idx + annotation_duration_samples <= total_num_samples:
                smf.add_annotation(
                    start_index=start_idx,
                    length=annotation_duration_samples,
                    metadata={
                        SigMFFile.FLO_KEY: center_frequency - 100e3,
                        SigMFFile.FHI_KEY: center_frequency + 100e3,
                        SigMFFile.LABEL_KEY: f"Annotation {i+1}",
                    }
                )
    
    # Save metadata file
    meta_path = tmpdir / f"{filename}.sigmf-meta"
    smf.tofile(str(meta_path))
    
    return meta_path


# Test for the generator function itself
def test_generate_sigmf_file_basic(tmpdir):
    """Test basic SigMF file generation with default parameters."""
    meta_path = generate_sigmf_file(tmpdir)
    
    # Verify files were created
    assert meta_path.exists()
    assert (meta_path.parent / "test.sigmf-data").exists()
    
    # Load and verify the file
    import sigmf
    smf = sigmf.sigmffile.fromfile(str(meta_path))
    
    # Check global fields
    assert smf.get_global_field(SigMFFile.SAMPLE_RATE_KEY) == 1e6
    assert smf.get_global_field(SigMFFile.DATATYPE_KEY) == "cf32_le"
    
    # Check captures
    captures = smf.get_captures()
    assert len(captures) == 2
    
    # Check annotations
    annotations = smf.get_annotations()
    assert len(annotations) == 2


def test_generate_sigmf_file_custom_parameters(tmpdir):
    """Test SigMF file generation with custom parameters."""
    meta_path = generate_sigmf_file(
        tmpdir=tmpdir,
        sample_rate=5e6,
        duration=1.0,
        num_annotations=3,
        filename="custom",
        generate_signal=True
    )
    
    # Verify custom filename
    assert meta_path.name == "custom.sigmf-meta"
    
    # Load and verify
    import sigmf
    smf = sigmf.sigmffile.fromfile(str(meta_path))
    
    # Check custom parameters
    assert smf.get_global_field(SigMFFile.SAMPLE_RATE_KEY) == 5e6
    assert len(smf.get_annotations()) == 3
    
    # Verify sample count matches duration
    expected_samples = int(5e6 * 1.0)
    assert smf.sample_count == expected_samples


def test_generate_sigmf_file_no_annotations(tmpdir):
    """Test SigMF file generation with no annotations."""
    meta_path = generate_sigmf_file(
        tmpdir=tmpdir,
        num_annotations=0
    )
    
    import sigmf
    smf = sigmf.sigmffile.fromfile(str(meta_path))
    
    # Should have no annotations
    assert len(smf.get_annotations()) == 0
    
    # Should still have captures
    assert len(smf.get_captures()) == 2
