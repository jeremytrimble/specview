from specview.chunkwise_compute import (
    CacheManager, TimeDomainChunkwiseComputedArray,
    RawTimeDomainComputationSpec, 
    RealComponentTimeDomainComputationSpec,
    ImagComponentTimeDomainComputationSpec,
    ProcessingPoolManager, ChunkwiseComputedArray
)
import numpy as np
from pathlib import Path
import pytest
from contextlib import closing
import threading



def generate_numpy_binary_file(path: Path, num_samples: int):
    """Generate a binary file with the specified number of complex64 samples."""
    data = (np.random.rand(num_samples) + 1j * np.random.rand(num_samples)).astype(np.complex64)
    data.tofile(path)

def test_print_cplx64_itemsize():
    dt = np.dtype(np.complex64)
    print(f"np.complex64.itemsize = {dt.itemsize}")
    assert dt.itemsize == 8


def test_chunkwise_computation(tmpdir):
    """Test chunkwise computation on a generated binary file."""
    num_samples = 2_000_000
    chunk_size = 100_000
    input_signal_file = Path(tmpdir / "input_signal.bin")
    generate_numpy_binary_file(input_signal_file, num_samples)

    cache_manager = CacheManager( Path(tmpdir / "cachemgr") )

    # Define a computation spec (e.g., compute real part)
    #comp_spec = RealComponentTimeDomainComputationSpec()
    comp_spec = ImagComponentTimeDomainComputationSpec()

    ppm = ProcessingPoolManager()

    with closing(ppm):
        # Create the chunkwise computed array
        computed_array = TimeDomainChunkwiseComputedArray(
            signal_file=input_signal_file,
            signal_file_datatype=np.dtype(np.complex64),
            num_channels=1,
            chunk_size_samples=chunk_size,
            comp_spec=comp_spec,
            cache_manager=cache_manager,
            processing_pool_manager=ppm,
        )

        assert computed_array.get_shape_and_dtype() == ((num_samples,1), np.float32)

        evt = threading.Event()
        saved = {}
        def cb(array: ChunkwiseComputedArray, start_idx: int, end_idx: int, array_data: np.ndarray):
            print(f"Callback received data from {start_idx} to {end_idx}")
            assert array_data.shape == (end_idx - start_idx, 1)
            assert array_data.dtype == np.float32
            saved["data"] = array_data 
            evt.set()

        start_sample = 1*100_000 + 12345
        end_sample = 3*100_000 + 12345
        computed_array.get_range_callback(start_sample, end_sample, cb)  # Just to test the callback
        evt.wait(timeout=3)
        assert evt.is_set()

        data = saved["data"]
        assert data.shape == (end_sample - start_sample, 1)
        assert data.dtype == np.float32 
        assert np.allclose(data[:,0], np.imag(np.fromfile(input_signal_file, dtype=np.complex64, count=(end_sample - start_sample), offset=start_sample*8)))
        

