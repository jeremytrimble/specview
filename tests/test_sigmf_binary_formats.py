"""
Test generating and loading SigMF files with all supported binary formats.

This test module generates SigMF files containing data in all 20 sigmf-supported
binary formats and verifies that specview can successfully open and load them.
"""

import pytest
import numpy as np
from pathlib import Path
from sigmf import SigMFFile
from specview.loaded_file_mgmt import LoadedFilesCollection
from specview.chunkwise_compute import (
    RawTimeDomainComputationSpec,
    FrequencyDomainComputationSpec,
    FFTLength,
)


# All 20 supported SigMF data types
SIGMF_DATA_TYPES = [
    # Complex float formats
    'cf32_le', 'cf32_be', 'cf64_le', 'cf64_be',
    # Complex signed integer formats
    'ci32_le', 'ci16_le', 'ci8',
    # Complex unsigned integer formats
    'cu32_le', 'cu16_le', 'cu8',
    # Real float formats
    'rf32_le', 'rf32_be', 'rf64_le', 'rf64_be',
    # Real signed integer formats
    'ri32_le', 'ri16_le', 'ri8',
    # Real unsigned integer formats
    'ru32_le', 'ru16_le', 'ru8',
]


def get_numpy_dtype_for_sigmf(sigmf_dtype: str) -> np.dtype:
    """
    Convert a SigMF data type string to the corresponding NumPy dtype.
    
    Args:
        sigmf_dtype: SigMF data type string (e.g., 'cf32_le', 'ri16_le')
    
    Returns:
        NumPy dtype object
    """
    # Parse the SigMF data type string
    # Format: [c|r][f|i|u][8|16|32|64][_le|_be|]
    # c = complex, r = real
    # f = float, i = signed int, u = unsigned int
    # 8,16,32,64 = bit width
    # _le = little endian, _be = big endian, no suffix = native/little endian for 8-bit
    
    is_complex = sigmf_dtype.startswith('c')
    
    # Extract type character and bit width
    if sigmf_dtype[1] == 'f':  # float
        type_char = 'f'
    elif sigmf_dtype[1] == 'i':  # signed int
        type_char = 'i'
    elif sigmf_dtype[1] == 'u':  # unsigned int
        type_char = 'u'
    else:
        raise ValueError(f"Unknown type character in {sigmf_dtype}")
    
    # Extract bit width
    bit_width = ''
    for char in sigmf_dtype[2:]:
        if char.isdigit():
            bit_width += char
        else:
            break
    bit_width = int(bit_width)
    byte_width = bit_width // 8
    
    # Determine endianness
    if sigmf_dtype.endswith('_be'):
        endian = '>'
    elif sigmf_dtype.endswith('_le') or bit_width == 8:
        endian = '<'
    else:
        endian = '<'  # default to little endian
    
    # Build numpy dtype string
    if is_complex:
        # For complex types, we use numpy's complex dtype
        if type_char == 'f':
            if bit_width == 32:
                return np.dtype(f'{endian}c8')  # complex64
            elif bit_width == 64:
                return np.dtype(f'{endian}c16')  # complex128
        # For complex integer types, we need structured dtype with two components
        base_dtype = np.dtype(f'{endian}{type_char}{byte_width}')
        return np.dtype([('r', base_dtype), ('i', base_dtype)])
    else:
        # Real types are straightforward
        return np.dtype(f'{endian}{type_char}{byte_width}')


def generate_test_data(sigmf_dtype: str, num_samples: int = 1000) -> np.ndarray:
    """
    Generate test data appropriate for the given SigMF data type.
    
    Args:
        sigmf_dtype: SigMF data type string
        num_samples: Number of samples to generate
    
    Returns:
        NumPy array with test data
    """
    np_dtype = get_numpy_dtype_for_sigmf(sigmf_dtype)
    is_complex = sigmf_dtype.startswith('c')
    is_float = sigmf_dtype[1] == 'f'
    is_unsigned = sigmf_dtype[1] == 'u'
    
    # Generate appropriate test data
    if is_complex:
        if is_float:
            # Complex float: generate sinusoidal data
            t = np.arange(num_samples)
            # Simple sinusoid at normalized frequency
            real_part = np.cos(2 * np.pi * 0.1 * t)
            imag_part = np.sin(2 * np.pi * 0.1 * t)
            data = real_part + 1j * imag_part
            
            # Convert to the specific dtype
            if 'c8' in str(np_dtype) or '32' in sigmf_dtype:
                return data.astype(np.complex64)
            else:
                return data.astype(np.complex128)
        else:
            # Complex integer: generate structured array
            if is_unsigned:
                # Unsigned: values from 0 to 255 (for 8-bit) or scaled appropriately
                bit_width = int(''.join(c for c in sigmf_dtype[2:] if c.isdigit()))
                max_val = (2 ** bit_width) // 2  # Use half range for variety
                real_part = np.random.randint(0, max_val, num_samples, dtype=np_dtype.fields['r'][0])
                imag_part = np.random.randint(0, max_val, num_samples, dtype=np_dtype.fields['i'][0])
            else:
                # Signed: use full range
                bit_width = int(''.join(c for c in sigmf_dtype[2:] if c.isdigit()))
                max_val = (2 ** (bit_width - 1)) // 2
                real_part = np.random.randint(-max_val, max_val, num_samples, dtype=np_dtype.fields['r'][0])
                imag_part = np.random.randint(-max_val, max_val, num_samples, dtype=np_dtype.fields['i'][0])
            
            # Create structured array
            data = np.zeros(num_samples, dtype=np_dtype)
            data['r'] = real_part
            data['i'] = imag_part
            return data
    else:
        # Real data
        if is_float:
            # Real float: simple sinusoid
            t = np.arange(num_samples)
            data = np.sin(2 * np.pi * 0.1 * t)
            return data.astype(np_dtype)
        else:
            # Real integer
            if is_unsigned:
                bit_width = int(''.join(c for c in sigmf_dtype[2:] if c.isdigit()))
                max_val = (2 ** bit_width) // 2
                return np.random.randint(0, max_val, num_samples, dtype=np_dtype)
            else:
                bit_width = int(''.join(c for c in sigmf_dtype[2:] if c.isdigit()))
                max_val = (2 ** (bit_width - 1)) // 2
                return np.random.randint(-max_val, max_val, num_samples, dtype=np_dtype)


def create_sigmf_file(tmpdir, sigmf_dtype: str, num_samples:int) -> Path:
    """
    Create a SigMF file with the specified data type.
    
    Args:
        tmpdir: Pytest temporary directory fixture
        sigmf_dtype: SigMF data type string
        num_samples: Number of samples to generate
    
    Returns:
        Path to the created .sigmf-meta file
    """
    
    # Generate test data
    data = generate_test_data(sigmf_dtype, num_samples)
    
    # Create data file
    data_filename = tmpdir / f"test_{sigmf_dtype}.sigmf-data"
    data.tofile(str(data_filename))
    
    # Create metadata file
    smf = SigMFFile()
    smf.set_global_field(SigMFFile.DATATYPE_KEY, sigmf_dtype)
    smf.set_global_field(SigMFFile.SAMPLE_RATE_KEY, 1e6)  # 1 MHz sample rate
    smf.set_global_field(SigMFFile.VERSION_KEY, "1.0.0")
    
    # Add a capture segment
    smf.add_capture(
        start_index=0,
        metadata={
            SigMFFile.FREQUENCY_KEY: 2.4e9,  # 2.4 GHz
        }
    )
    
    # Set data file and save metadata
    smf.set_data_file(str(data_filename))
    meta_filename = tmpdir / f"test_{sigmf_dtype}.sigmf-meta"
    smf.tofile(str(meta_filename))
    
    return Path(meta_filename)


@pytest.mark.parametrize("sigmf_dtype", SIGMF_DATA_TYPES)
@pytest.mark.parametrize("nfft", [FFTLength.N256, FFTLength.N512, FFTLength.N1024])
@pytest.mark.parametrize("sample_count", [10000, int(10e6)])
def test_sigmf_format_generation_and_loading(tmpdir, sigmf_dtype, nfft:FFTLength, sample_count:int):
    """
    Test generating and loading a SigMF file with a specific binary format.
    
    This test:
    1. Generates a SigMF file with test data in the specified format
    2. Loads the file using LoadedFilesCollection (specview's file loading mechanism)
    3. Verifies that the file loads successfully
    4. Verifies that basic metadata is correctly preserved
    """
    # Create the SigMF file
    meta_path = create_sigmf_file(tmpdir, sigmf_dtype, sample_count)
    
    # Verify files were created
    assert meta_path.exists(), f"Metadata file not created for {sigmf_dtype}"
    data_path = meta_path.with_suffix('.sigmf-data')
    assert data_path.exists(), f"Data file not created for {sigmf_dtype}"
    
    # Load the file using specview's LoadedFilesCollection
    lfc = LoadedFilesCollection()
    loaded_file = lfc.load_file(meta_path)
    
    # Verify the file loaded successfully
    assert loaded_file is not None, f"Failed to load SigMF file with format {sigmf_dtype}"
    
    # Verify basic metadata
    assert loaded_file.sigmf_file is not None, f"SigMF file object is None for {sigmf_dtype}"
    
    # Check that the data type matches
    loaded_dtype = loaded_file.sigmf_file.get_global_field(SigMFFile.DATATYPE_KEY)
    assert loaded_dtype == sigmf_dtype, f"Data type mismatch: expected {sigmf_dtype}, got {loaded_dtype}"
    
    # Check sample rate
    sample_rate = loaded_file.sigmf_file.get_global_field(SigMFFile.SAMPLE_RATE_KEY)
    assert sample_rate == 1e6, f"Sample rate mismatch for {sigmf_dtype}"
    
    # Check that we have at least one capture
    captures = loaded_file.sigmf_file.get_captures()
    assert len(captures) > 0, f"No captures found for {sigmf_dtype}"
    
    # Check capture frequency
    first_capture = captures[0]
    frequency = first_capture.get(SigMFFile.FREQUENCY_KEY)
    assert frequency == 2.4e9, f"Frequency mismatch for {sigmf_dtype}"
    
    # Verify sample count
    read_sample_count = loaded_file.sigmf_file.sample_count
    assert read_sample_count == sample_count, f"Sample count mismatch for {sigmf_dtype}: expected {sample_count}, got {read_sample_count}"
    
    # Exercise time-domain chunkwise computed array
    time_cca = loaded_file.get_time_chunkwise_computed_array(comp_spec=RawTimeDomainComputationSpec())
    assert time_cca is not None, f"Failed to get time chunkwise computed array for {sigmf_dtype}"
    
    # Get shape and dtype
    time_shape, time_dtype = time_cca.get_shape_and_dtype()
    assert time_shape[0] == sample_count, f"Time array shape mismatch for {sigmf_dtype}: expected {sample_count} samples, got {time_shape[0]}"
    
    # Request a small range of data (blocking)
    time_data = time_cca.get_range_blocking(0, 100)
    assert time_data is not None, f"Failed to get time data for {sigmf_dtype}"
    assert time_data.shape[0] == 100, f"Time data shape mismatch for {sigmf_dtype}"

    # Request a the end of the time data
    max_sample = time_shape[0]
    start_sample = max(0, max_sample - 100)
    time_data = time_cca.get_range_blocking(start_sample, max_sample)
    assert time_data is not None, f"Failed to get time data for {sigmf_dtype}"
    assert time_data.shape[0] == 100, f"Time data shape mismatch for {sigmf_dtype}"

    
    # Exercise frequency-domain chunkwise computed array
    freq_comp_spec = FrequencyDomainComputationSpec(NFFT=nfft)
    int_nfft = int(nfft.value)
    freq_cca = loaded_file.get_freq_chunkwise_computed_array(selected_channel=0, comp_spec=freq_comp_spec)
    assert freq_cca is not None, f"Failed to get frequency chunkwise computed array for {sigmf_dtype}"
    
    # Get shape and dtype
    freq_shape, freq_dtype = freq_cca.get_shape_and_dtype()
    assert freq_shape[1] == int_nfft, f"Frequency array shape mismatch for {sigmf_dtype}: expected {int_nfft} frequency bins, got {freq_shape[1]}"
    assert freq_dtype == np.float32, f"Frequency array dtype mismatch for {sigmf_dtype}"
    
    # Request a small range of frequency data (blocking)
    freq_data = freq_cca.get_range_blocking(0, 10)
    assert freq_data is not None, f"Failed to get frequency data for {sigmf_dtype}"
    assert freq_data.shape == (10, int_nfft), f"Frequency data shape mismatch for {sigmf_dtype}: expected (10, {int_nfft}), got {freq_data.shape}"

    # Request the end of the frequency data
    max_frame = freq_shape[0]
    start_frame = max(0, max_frame - 10)
    print(f"Requesting last 10 frames of frequency data, which are: {start_frame} to {max_frame}")
    freq_data = freq_cca.get_range_blocking(start_frame, max_frame)
    assert freq_data is not None, f"Failed to get frequency data for {sigmf_dtype}"
    assert freq_data.shape == (10, int_nfft), f"Frequency data shape mismatch for {sigmf_dtype}: expected (10, {int_nfft}), got {freq_data.shape}"



def test_all_sigmf_formats_count():
    """
    Verify that we're testing all 20 SigMF formats.
    """
    assert len(SIGMF_DATA_TYPES) == 20, f"Expected 20 data types, found {len(SIGMF_DATA_TYPES)}"


def test_sigmf_format_categories():
    """
    Verify that we have the correct distribution of format types.
    """
    complex_types = [dt for dt in SIGMF_DATA_TYPES if dt.startswith('c')]
    real_types = [dt for dt in SIGMF_DATA_TYPES if dt.startswith('r')]
    
    assert len(complex_types) == 10, f"Expected 10 complex types, found {len(complex_types)}"
    assert len(real_types) == 10, f"Expected 10 real types, found {len(real_types)}"
    
    float_types = [dt for dt in SIGMF_DATA_TYPES if 'f' in dt]
    int_types = [dt for dt in SIGMF_DATA_TYPES if 'i' in dt or 'u' in dt]
    
    # We have 8 float types (4 complex + 4 real)
    assert len(float_types) == 8, f"Expected 8 float types, found {len(float_types)}"
    # We have 12 integer types (6 complex + 6 real)
    assert len(int_types) == 12, f"Expected 12 integer types, found {len(int_types)}"
