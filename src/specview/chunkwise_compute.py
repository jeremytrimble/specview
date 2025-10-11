from __future__ import annotations
import numpy as np
import numpy.typing as npt
import typing
from pathlib import Path 
from platformdirs import user_cache_dir
from hashlib import sha256
from enum import Enum, IntEnum
import abc
from dataclasses import dataclass
from multiprocessing import cpu_count
from multiprocessing.pool import Pool, AsyncResult
import struct
import logging
from pydantic import BaseModel, Field
import os
log = logging.getLogger("chunkwise_compute")

from scipy.signal import ShortTimeFFT


chunkwise_computations_cache_dir = Path(user_cache_dir("sigvu", "jeremytrimble", ensure_exists=True)) / "ccache"

RangeComputedCallback = typing.Callable[["ChunkwiseComputedArray", int, int, np.ndarray], None]

class ChunkwiseComputedArray:
    def get_range_blocking(self, start: int, stop: int) -> npt.NDArray:
        raise NotImplementedError("Must be implemented in subclass")

    def get_range_callback(self, start: int, stop: int, cb: RangeComputedCallback) -> None:
        raise NotImplementedError("Must be implemented in subclass")

    def get_shape_and_dtype(self) -> tuple[tuple[int, ...], np.dtype]:
        raise NotImplementedError("Must be implemented in subclass")


class CacheManager:
    def __init__(self, base_path: Path):
        self._cache_base_path = base_path
        self._cache_base_path.mkdir(parents=True, exist_ok=True)
    
    def get_cache_path_from_tag(self, tag: str) -> Path:
        # TODO: later, add LRU management of cache entries
        return self._cache_base_path / tag

    @classmethod
    def get_default_cache_manager(cls) -> CacheManager:
        default_cache_dir = Path(user_cache_dir("specview", "jeremytrimble", ensure_exists=True)) / "ccache"
        return CacheManager(default_cache_dir)

    @classmethod
    def get_cache_tag_tuples_for_file(cls, file_path: Path) -> str:
        """Generate a cache tag for a given file based on its path, size, and modification time."""
        file_path = file_path.resolve()
        stat = file_path.stat()
        return [("file_path", str(file_path)), ("file_size", str(stat.st_size)), ("file_mtime", str(int(stat.st_mtime)))]

    @classmethod
    def get_cache_tag_from_tuples(cls, prefix:str, tuples: list[tuple[str, str]]) -> str:
        hash_input = ""
        h = sha256()
        for key, val in tuples:
            hash_input += f"{key}:{val}"
        h.update( hash_input.encode('utf-8') )
        return f"{prefix}_{h.hexdigest()}"

class TimeDomainComputationType(IntEnum):
    RAW = 0
    MAGNITUDE_DB = 1
    REAL = 2
    IMAG = 3
    FM_DEMOD = 4
    #AM_DEMOD = 5

@dataclass
class TimeDomainComputationSpec(abc.ABC):
    computation_type: TimeDomainComputationType
    def get_cache_tag_tuples(self) -> list[tuple[str, typing.Any]]:
        return [("computation_type", str(self.computation_type))]

@dataclass
class RawTimeDomainComputationSpec(TimeDomainComputationSpec):
    computation_type: TimeDomainComputationType = TimeDomainComputationType.RAW

@dataclass
class MagnitudeTimeDomainComputationSpec(TimeDomainComputationSpec):
    computation_type: TimeDomainComputationType = TimeDomainComputationType.MAGNITUDE_DB

@dataclass
class RealComponentTimeDomainComputationSpec(TimeDomainComputationSpec):
    computation_type: TimeDomainComputationType = TimeDomainComputationType.REAL

@dataclass
class ImagComponentTimeDomainComputationSpec(TimeDomainComputationSpec):
    computation_type: TimeDomainComputationType = TimeDomainComputationType.IMAG

@dataclass
class FMDemodTimeDomainComputationSpec(TimeDomainComputationSpec):
    computation_type: TimeDomainComputationType = TimeDomainComputationType.FM_DEMOD

#@dataclass
#class AMDemodTimeDomainComputationSpec(TimeDomainComputationSpec):
#    computation_type: TimeDomainComputationType = TimeDomainComputationType.AM_DEMOD
#    #TODO: are there any other parameters we want here?

class ProcessingPoolManager:
    _instance: ProcessingPoolManager | None = None

    def __init__(self):
        self._pool: Pool | None = None
        self._num_processes = max(1, cpu_count() - 2)  # Leave one CPU free

    @classmethod
    def get_instance(cls) -> ProcessingPoolManager:
        if cls._instance is None:
            cls._instance = ProcessingPoolManager()
        return cls._instance

    def get_pool(self) -> Pool:
        if self._pool is None:
            self._pool = Pool(processes=self._num_processes)
        return self._pool

    def _pool_error_handler(self, e: Exception) -> None:
        log.exception(f"Error in processing pool: {e}")

    def map_async_with_callback(self, func, args_list, callback) -> AsyncResult:
        """
        Runs `func` on each item in `args_list` in the processing pool.
        When all are complete, `callback` is called with the list of results.
        """
        pool = self.get_pool()
        return pool.map_async(func, args_list, callback=callback, error_callback=self._pool_error_handler)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool.join()
            self._pool = None

class ChunkBitmap:
    def __init__(self, num_chunks: int):
        self._num_chunks = num_chunks
        self._bitmap = bytearray((num_chunks + 7) // 8)
    def set_chunk(self, chunk_index: int) -> None:
        if 0 <= chunk_index < self._num_chunks:
            byte_index = chunk_index // 8
            bit_index = chunk_index % 8
            self._bitmap[byte_index] |= (1 << bit_index)
    def clear_chunk(self, chunk_index: int) -> None:
        if 0 <= chunk_index < self._num_chunks:
            byte_index = chunk_index // 8
            bit_index = chunk_index % 8
            self._bitmap[byte_index] &= ~(1 << bit_index)
    def is_chunk_set(self, chunk_index: int) -> bool:
        if 0 <= chunk_index < self._num_chunks:
            byte_index = chunk_index // 8
            bit_index = chunk_index % 8
            return (self._bitmap[byte_index] & (1 << bit_index)) != 0
        raise IndexError(f"Chunk index {chunk_index} out of range")
    def __len__(self) -> int:
        return self._num_chunks
    def __iter__(self):
        for chunk_index in range(self._num_chunks):
            yield self.is_chunk_set(chunk_index)
    def to_file(self, file_path: Path) -> None:
        header = struct.pack("<I", self._num_chunks)  # Write number of chunks as uint32
        with open(file_path, 'wb') as f:
            f.write(header)
            f.write(self._bitmap)
    @classmethod
    def from_file(cls, file_path: Path) -> ChunkBitmap:
        with open(file_path, 'rb') as f:
            header = f.read(4)
            if len(header) < 4:
                raise ValueError("Invalid bitmap file: too short")
            num_chunks = struct.unpack("<I", header)[0]
            bitmap_data = f.read()
            expected_size = (num_chunks + 7) // 8
            if len(bitmap_data) < expected_size:
                raise ValueError("Invalid bitmap file: bitmap data too short")
            cb = cls(num_chunks)
            cb._bitmap = bytearray(bitmap_data[:expected_size])
            return cb

def compute_num_chunks(total_samples: int, chunk_size_samples: int) -> int:
    return (total_samples + chunk_size_samples - 1) // chunk_size_samples

def compute_total_num_elements_in_shape(shape: tuple[int, ...]) -> int:
    total = 1
    for dim in shape:
        total *= dim
    return total    

class TimeDomainChunkwiseComputedArray(ChunkwiseComputedArray):
    def __init__(self, signal_file: Path, signal_file_datatype: np.dtype, num_channels: int, comp_spec: TimeDomainComputationSpec, chunk_size_samples=1_000_000, cache_manager: CacheManager | None = None, processing_pool_manager:ProcessingPoolManager|None=None):

        if cache_manager is None:
            cache_manager = CacheManager.get_default_cache_manager()

        self._processing_pool_manager = processing_pool_manager
        if self._processing_pool_manager is None:
            self._processing_pool_manager = ProcessingPoolManager.get_instance()

        self._signal_file = signal_file
        self._signal_file_datatype = signal_file_datatype
        self._num_channels = num_channels
        self._chunk_size_samples = chunk_size_samples
        self._comp_spec = comp_spec

        # Note: we assume that axis 0 is the one that will be computed chunkwise
        num_input_samples = self._signal_file.stat().st_size // (self._signal_file_datatype.itemsize * self._num_channels)
        self._input_shape = (num_input_samples, self._num_channels)
        self._output_shape = (num_input_samples, self._num_channels)

        if comp_spec.computation_type in (TimeDomainComputationType.REAL, TimeDomainComputationType.IMAG, TimeDomainComputationType.FM_DEMOD, TimeDomainComputationType.MAGNITUDE_DB): #, TimeDomainComputationType.AM_DEMOD):
            self._output_dtype = np.dtype(np.float32)
        elif comp_spec.computation_type in (TimeDomainComputationType.RAW,):
            self._output_dtype = self._signal_file_datatype
        else:
            raise ValueError(f"Unsupported computation type: {comp_spec.computation_type}")

        self._num_output_chunks = compute_num_chunks(self._output_shape[0], self._chunk_size_samples)

        # Note: this is only needed if we have nontrivial computation to do in this class
        cache_tag_tuples = cache_manager.get_cache_tag_tuples_for_file(signal_file) + comp_spec.get_cache_tag_tuples()
        self._state_dir = cache_manager.get_cache_path_from_tag( cache_manager.get_cache_tag_from_tuples( prefix=self._signal_file.resolve().name, tuples=cache_tag_tuples ) )
        self._state_dir.mkdir(parents=True, exist_ok=True)

        self._chunk_bitmap_path = self._state_dir / f"bitmap"
        if self._chunk_bitmap_path.exists():
            self._chunk_bitmap: ChunkBitmap = ChunkBitmap.from_file(self._chunk_bitmap_path)
        else:
            self._chunk_bitmap = ChunkBitmap(self._num_output_chunks)
            self._chunk_bitmap.to_file(self._chunk_bitmap_path)

        self._output_file = self._state_dir / f"data.bin"
        if not self._output_file.exists():
            # Create an empty file of the right size
            with open(self._output_file, 'wb') as f:
                #f.truncate( compute_total_num_elements_in_shape(self._output_shape) * self._output_dtype.itemsize )
                #os.ftruncate(f.fileno(), compute_total_num_elements_in_shape(self._output_shape) * self._output_dtype.itemsize)
                f.seek( compute_total_num_elements_in_shape(self._output_shape) * self._output_dtype.itemsize - 1 )
                f.write(b'\0')
                f.flush()
        self._output_memmap = np.memmap(self._output_file, dtype=self._output_dtype, mode='r', shape=self._output_shape)

    def get_shape_and_dtype(self) -> tuple[tuple[int, ...], np.dtype]:
        return self._output_shape, self._output_dtype

    def map_sample_to_chunk(self, sample_index: int) -> int:
        return sample_index // self._chunk_size_samples

    def map_chunk_to_sample_range(self, chunk_index: int) -> tuple[int, int]:
        start_sample = chunk_index * self._chunk_size_samples
        end_sample = min(start_sample + self._chunk_size_samples, self._output_shape[0])
        return start_sample, end_sample

    def get_range_callback(self, start:int, stop:int, cb: RangeComputedCallback):
        if start < 0 or stop > self._output_shape[0] or start >= stop:
            raise ValueError("Invalid range")

        start_chunk = self.map_sample_to_chunk(start)
        end_chunk = self.map_sample_to_chunk(stop - 1)  # inclusive

        chunks_to_compute = []
        for chunk_index in range(start_chunk, end_chunk + 1):
            if not self._chunk_bitmap.is_chunk_set(chunk_index):
                chunks_to_compute.append(chunk_index)

        def on_computation_complete(results_whocares: list[None]) -> None:
            # Mark chunks as computed
            if chunks_to_compute:
                for chunk_index in chunks_to_compute:
                    self._chunk_bitmap.set_chunk(chunk_index)
                self._chunk_bitmap.to_file(self._chunk_bitmap_path)

            # create the view of the requested range
            rv = self._output_memmap[ start:stop, :]

            # Invoke the callback
            cb(self, start, stop, rv)

        if chunks_to_compute:
            log.debug(f"Computing {len(chunks_to_compute)} chunks for range {start}-{stop}")
            requests = [self._generate_chunk_computation_request(ci) for ci in chunks_to_compute]
            ppm = ProcessingPoolManager.get_instance()
            ppm.map_async_with_callback(self._perform_chunk_computation, requests, on_computation_complete)
        else:
            log.debug(f"All chunks already computed for range {start}-{stop}, invoking callback directly")
            on_computation_complete([])

    def _generate_chunk_computation_request(self, chunk_index: int) -> dict[str, typing.Any]:
        start_sample, end_sample = self.map_chunk_to_sample_range(chunk_index)
        return {
            "chunk_index": chunk_index,
            "start_sample": start_sample,
            "end_sample": end_sample,
            "signal_file": str(self._signal_file),
            "signal_file_datatype": str(self._signal_file_datatype),
            "num_channels": self._num_channels,
            "comp_spec": self._comp_spec,
            "output_file": str(self._output_file),
            "output_dtype": str(self._output_dtype),
        }   

    @classmethod
    def _perform_chunk_computation(cls, request: dict[str, typing.Any]) -> None:
        chunk_index = request["chunk_index"]
        start_sample = request["start_sample"]
        end_sample = request["end_sample"]
        signal_file = Path(request["signal_file"])
        signal_file_datatype = np.dtype(request["signal_file_datatype"])
        num_channels = request["num_channels"]
        comp_spec: TimeDomainComputationSpec = request["comp_spec"]
        output_file = Path(request["output_file"])
        output_dtype = np.dtype(request["output_dtype"])

        num_input_samples = signal_file.stat().st_size // (int(signal_file_datatype.itemsize) * num_channels)
        input_shape = (num_input_samples, num_channels)

        num_samples_to_read = end_sample - start_sample

        # Use read-only memmap to access the input data
        data = np.memmap(signal_file, dtype=signal_file_datatype, mode='r', 
                        offset=start_sample * signal_file_datatype.itemsize * num_channels,
                        shape=(num_samples_to_read, num_channels))

        if comp_spec.computation_type == TimeDomainComputationType.RAW:
            output_data = data
        elif comp_spec.computation_type == TimeDomainComputationType.MAGNITUDE_DB:
            output_data = 20 * np.log10(np.abs(data))
        elif comp_spec.computation_type == TimeDomainComputationType.REAL:
            output_data = np.real(data)
        elif comp_spec.computation_type == TimeDomainComputationType.IMAG:
            output_data = np.imag(data)
        elif comp_spec.computation_type == TimeDomainComputationType.FM_DEMOD:
            # FM demodulation using phase difference
            phase = np.angle(data)
            phase_diff = np.diff(phase, axis=0, prepend=phase[0:1, :])
            output_data = phase_diff
        #elif comp_spec.computation_type == TimeDomainComputationType.AM_DEMOD:
        #    # AM demodulation using magnitude
        #    output_data = np.abs(data)
        else:
            raise ValueError(f"Unsupported computation type: {comp_spec.computation_type}")

        output_shape = (num_input_samples, num_channels)
        with open(output_file, 'r+b') as f:
            f.seek(start_sample * output_dtype.itemsize * num_channels)
            output_data.astype(output_dtype).tofile(f)



class WindowType(str, Enum):
    HAMMING = "hamming"
    HANN = "hann"
    BLACKMAN = "blackman"
    RECTANGULAR = "rectangular"
    # TODO: add other windows?

class FFTLength(int, Enum):
    N128 = 128
    N256 = 256
    N512 = 512
    N1024 = 1024
    N2048 = 2048
    N4096 = 4096
    N8192 = 8192
    N16384 = 16384

class HopSize(float, Enum):
    HOP_50 = 0.50
    HOP_75 = 0.75
    HOP_90 = 0.90
    HOP_100 = 1.00

def window_type_to_array(window: WindowType, win_len:int) -> np.ndarray:
    if window == WindowType.HAMMING:
        return np.hamming(win_len)
    elif window == WindowType.HANN:
        return np.hanning(win_len)
    elif window == WindowType.BLACKMAN:
        return np.blackman(win_len)
    elif window == WindowType.RECTANGULAR:
        return np.ones(win_len)
    else:
        raise ValueError(f"Unsupported window type: {window}")

class FrequencyDomainComputationSpec(BaseModel):
    NFFT: FFTLength = Field(default=FFTLength.N1024, description="Number of FFT points")
    win: WindowType = Field(default=WindowType.HAMMING, description="Window type for STFFT")
    hop: HopSize = Field(default=HopSize.HOP_90, description="Hop size for STFFT")
    #fs: float = Field(default=1.0, description="Sampling frequency in Hz")
    #fft_mode: str = Field(default="centered", description="FFT mode, e.g., 'centered' or 'unshifted'")

    @property
    def hop_in_samples(self) -> int:
        return int(self.NFFT * self.hop)

    def get_cache_tag_tuples(self) -> list[tuple[str, typing.Any]]:
        return [("NFFT", str(self.NFFT)), ("win", str(self.win)), ("hop", f"{self.hop.value:.3f}")]

    def get_stft_object(self, fs: float) -> ShortTimeFFT:
        # From scipy docs: The stft is represented by a complex-valued matrix
        # S[q,p] where the p-th column represents an FFT with the window
        # centered at the time t[p] = p * delta_t = p * hop * T where T is the
        # sampling interval of the input signal. The q-th row represents the
        # values at the frequency f[q] = q * delta_f with delta_f = 1 / (mfft *
        # T) being the bin width of the FFT.
        #
        # S[q,p] = S[bin, frame]
        return ShortTimeFFT(
            win=window_type_to_array(self.win, int(self.NFFT)),
            hop=self.hop_in_samples,
            fs=fs,
            fft_mode="centered",
            scale_to="psd",
        )

class FrequencyDomainChunkwiseComputedArray(ChunkwiseComputedArray):
    def __init__(self, signal_file: Path, signal_file_datatype: np.dtype, num_input_channels: int, target_output_channel:int, sample_rate_Hz:float, comp_spec: FrequencyDomainComputationSpec, chunk_size_samples=1_000_000, cache_manager: CacheManager | None = None, processing_pool_manager:ProcessingPoolManager|None=None):
        if cache_manager is None:
            cache_manager = CacheManager.get_default_cache_manager()

        self._processing_pool_manager = processing_pool_manager
        if self._processing_pool_manager is None:
            self._processing_pool_manager = ProcessingPoolManager.get_instance()

        self._signal_file = signal_file
        self._signal_file_datatype = signal_file_datatype
        self._num_input_channels = num_input_channels
        self._target_output_channel = target_output_channel
        self._chunk_size_samples = chunk_size_samples
        self._input_sample_rate_Hz = sample_rate_Hz
        self._comp_spec = comp_spec

        # Note: we assume that axis 0 is the one that will be computed chunkwise
        num_input_samples = self._signal_file.stat().st_size // (self._signal_file_datatype.itemsize * self._num_input_channels )
        self._input_shape = (num_input_samples, self._num_input_channels)

        # Note: we compute only a single output channel
        self._stfft_obj = comp_spec.get_stft_object(self._input_sample_rate_Hz) 
        num_output_frames = self._stfft_obj.p_num(num_input_samples)

        # Note: can parameterize these by computation spec later if we need to vary parameters
        self._output_shape = (num_output_frames, self._stfft_obj.mfft)
        self._output_dtype = np.dtype(np.float32)

        self._num_output_chunks = compute_num_chunks(self._output_shape[0], self._chunk_size_samples)

        # Note: this is only needed if we have nontrivial computation to do in this class
        cache_tag_tuples = cache_manager.get_cache_tag_tuples_for_file(signal_file) + comp_spec.get_cache_tag_tuples() + [("target_output_channel", str(target_output_channel)) ]
        self._state_dir = cache_manager.get_cache_path_from_tag( cache_manager.get_cache_tag_from_tuples( prefix=self._signal_file.resolve().name, tuples=cache_tag_tuples ) )
        self._state_dir.mkdir(parents=True, exist_ok=True)

        self._chunk_bitmap_path = self._state_dir / f"bitmap"
        if self._chunk_bitmap_path.exists():
            self._chunk_bitmap: ChunkBitmap = ChunkBitmap.from_file(self._chunk_bitmap_path)
        else:
            self._chunk_bitmap = ChunkBitmap(self._num_output_chunks)
            self._chunk_bitmap.to_file(self._chunk_bitmap_path)

        self._output_file = self._state_dir / f"data.bin"
        if not self._output_file.exists():
            # Create an empty file of the right size
            with open(self._output_file, 'wb') as f:
                #os.ftruncate(f.fileno(), compute_total_num_elements_in_shape(self._output_shape) * self._output_dtype.itemsize)
                f.seek( compute_total_num_elements_in_shape(self._output_shape) * self._output_dtype.itemsize - 1 )
                f.write(b'\0')
                f.flush()
        #log.critical(f"about to open read-only memmap with shape: {self._output_shape}, dtype: {self._output_dtype}, file: {self._output_file}")
        self._output_memmap = np.memmap(self._output_file, dtype=self._output_dtype, mode='r', shape=self._output_shape)

    def get_shape_and_dtype(self) -> tuple[tuple[int, ...], np.dtype]:
        return self._output_shape, self._output_dtype

    def map_sample_to_chunk(self, sample_index: int) -> int:
        return sample_index // self._chunk_size_samples

    def map_chunk_to_frame_range(self, chunk_index: int) -> tuple[int, int]:
        start_sample = chunk_index * self._chunk_size_samples
        end_sample = min(start_sample + self._chunk_size_samples, self._output_shape[0])
        return start_sample, end_sample

    def get_range_callback(self, start:int, stop:int, cb: RangeComputedCallback):
        if start < 0 or stop > self._output_shape[0] or start >= stop:
            raise ValueError("Invalid range")

        start_chunk = self.map_sample_to_chunk(start)
        end_chunk = self.map_sample_to_chunk(stop - 1)  # inclusive

        chunks_to_compute = []
        for chunk_index in range(start_chunk, end_chunk + 1):
            if not self._chunk_bitmap.is_chunk_set(chunk_index):
                chunks_to_compute.append(chunk_index)

        def on_computation_complete(results_whocares: list[None]) -> None:
            # Mark chunks as computed
            if chunks_to_compute:
                for chunk_index in chunks_to_compute:
                    self._chunk_bitmap.set_chunk(chunk_index)
                self._chunk_bitmap.to_file(self._chunk_bitmap_path)

            # create the view of the requested range
            rv = self._output_memmap[ start:stop, :]

            # Invoke the callback
            cb(self, start, stop, rv)

        if chunks_to_compute:
            log.debug(f"Computing {len(chunks_to_compute)} chunks for range {start}-{stop}")
            requests = [self._generate_chunk_computation_request(ci) for ci in chunks_to_compute]
            ppm = ProcessingPoolManager.get_instance()
            ppm.map_async_with_callback(self._perform_chunk_computation, requests, on_computation_complete)
        else:
            log.debug(f"All chunks already computed for range {start}-{stop}, invoking callback directly")
            on_computation_complete([])

    def _generate_chunk_computation_request(self, chunk_index: int) -> dict[str, typing.Any]:
        start_frame, end_frame = self.map_chunk_to_frame_range(chunk_index)
        return {
            "chunk_index": chunk_index,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "signal_file": str(self._signal_file),
            "signal_file_datatype": str(self._signal_file_datatype),
            "num_input_channels": self._num_input_channels,
            "target_output_channel": self._target_output_channel,
            "input_sample_rate_Hz": self._input_sample_rate_Hz,
            "comp_spec": self._comp_spec,
            "output_file": str(self._output_file),
            "output_shape": self._output_shape,
            "output_dtype": str(self._output_dtype),
        }   

    @classmethod
    def _perform_chunk_computation(cls, request: dict[str, typing.Any]) -> None:
        try:
            cls._perform_chunk_computation_inner(request)
        except Exception as e:
            log.exception(f"Error computing chunk {request.get('chunk_index', 'unknown')}: {e}")
            raise 

    @classmethod
    def _perform_chunk_computation_inner(cls, request: dict[str, typing.Any]) -> None:
        chunk_index = request["chunk_index"]
        start_frame = request["start_frame"]
        end_frame = request["end_frame"]
        signal_file = Path(request["signal_file"])
        signal_file_datatype = np.dtype(request["signal_file_datatype"])
        num_input_channels = request["num_input_channels"]
        target_output_channel = request["target_output_channel"]
        input_sample_rate_Hz = request["input_sample_rate_Hz"]
        comp_spec: FrequencyDomainComputationSpec = request["comp_spec"]
        output_file = Path(request["output_file"])
        output_shape = request["output_shape"]
        output_dtype = np.dtype(request["output_dtype"])

        num_input_samples = signal_file.stat().st_size // (int(signal_file_datatype.itemsize) * num_input_channels)
        input_shape = (num_input_samples, num_input_channels)

        stfft_obj = comp_spec.get_stft_object(input_sample_rate_Hz)
        nfft = stfft_obj.mfft

        input_data = np.memmap(signal_file, dtype=signal_file_datatype, mode='r', offset=0, shape=input_shape)
        data_channel = input_data[:, target_output_channel]

        # Compute STFT
        S = stfft_obj.stft(data_channel, p0=start_frame, p1=end_frame)
        num_bins, num_frames = S.shape
        assert num_bins == nfft
        assert num_frames == (end_frame - start_frame)

        mag_dB = 20 * np.log10(np.abs(S) + 1e-12)  # Add small value to avoid log(0)
        S = mag_dB.astype(output_dtype)

        #log.critical(f"about to write computed chunk {chunk_index} to memmap with shape: {output_shape}, dtype: {output_dtype}, file: {output_file}, frame range: {start_frame}-{end_frame}, S shape: {S.shape}, S dtype: {S.dtype}")   
        # Confusingly: "r+" means read/write, file must exist, if we were to say "w+" it seems to change the file size or possibly make it sparse
        output_memmap = np.memmap(output_file, dtype=output_dtype, mode='r+', shape=output_shape)
        output_memmap[start_frame:end_frame, :] = S.T
        output_memmap.flush()
