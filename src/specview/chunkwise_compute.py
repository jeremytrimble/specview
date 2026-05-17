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
from multiprocessing.pool import MapResult, Pool
import struct
import logging
from pydantic import BaseModel, Field
import os
import time
import dataclasses
from functools import lru_cache

from specview.monotonic_axis import MonotonicAxis
log = logging.getLogger("chunkwise_compute")

import threading
from PyQt6.QtWidgets import QApplication
from .sigmf_util import SigmfDataType

chunkwise_computations_cache_dir = Path(user_cache_dir("sigvu", "jeremytrimble", ensure_exists=True)) / "ccache"

RangeComputedCallback = typing.Callable[["ChunkwiseComputedArray", int, int, np.ndarray], None]

def identity_xform(arr: np.ndarray) -> np.ndarray:
    return arr

class ChunkwiseComputedArray:
    # TODO: XXX this needs a better implementation that cannot hang the caller
    # turns out we need to load data from a QRunnable anyway so there is no need to be callback-based
    def get_range_blocking(self, start:int, stop:int) -> npt.NDArray|None:
        """
        Returns a view of the requested range.  This may block to allow
        background computation of the requested range if it is not yet
        available.
        """
        raise NotImplementedError("Must be implemented in subclass")

    # TODO: consider removing this method as we don't use it currently
    def get_range_callback(self, start: int, stop: int, cb: RangeComputedCallback) -> None:
        """
        Asynchronously computes the requested range and invokes the callback when done.
        """
        raise NotImplementedError("Must be implemented in subclass")

    def get_shape_and_dtype(self) -> tuple[tuple[int, ...], np.dtype]:
        """
        Returns the shape and dtype of the computed array represented by this class.
        The dtype will be either np.float32 or np.complex64, depending on the input file type.
        """
        raise NotImplementedError("Must be implemented in subclass")

    def get_range_if_available(self, start:int, stop:int) -> npt.NDArray|None:
        """
        Immediately returns a view of the requested range if it is already
        computed and available, or None if it is not yet computed.
        """
        raise NotImplementedError("Must be implemented in subclass")

    @staticmethod
    def _get_input_data(signal_file:Path, sigmf_datatype:SigmfDataType, num_input_channels:int, start_sample:int, num_samples: int) -> np.ndarray:
        """
        Returns a (read-only) ndarray-like object containing the requested range
        of samples from the input signal file with a dtype that is suitable for direct numpy use.

        The shape will be (num_samples, num_input_channels).  The returned array
        may be a memmap or a transformed view of a memmap, depending on the
        input file type, but this should be transparent to the caller.  The
        returned array will be read-only.
        """

        signal_file_size_bytes = signal_file.stat().st_size
        total_num_input_samples = signal_file_size_bytes // (sigmf_datatype.sample_size_bytes * num_input_channels)

        if total_num_input_samples * sigmf_datatype.sample_size_bytes * num_input_channels != signal_file_size_bytes:
            log.warning(f"Signal file size {signal_file_size_bytes} is not a multiple of (samplesize={sigmf_datatype.sample_size_bytes} times num_input_channels={num_input_channels}).  Some samples may be truncated.")

        byte_offset = start_sample * sigmf_datatype.sample_size_bytes * num_input_channels
        map_length = num_samples * sigmf_datatype.sample_size_bytes * num_input_channels

        if byte_offset + map_length > signal_file_size_bytes:
            reduced_num_samples = (signal_file_size_bytes - byte_offset) // (sigmf_datatype.sample_size_bytes * num_input_channels)
            if reduced_num_samples <= 0:
                raise ValueError(f"Requested range exceeds signal file size: {byte_offset + map_length} > {signal_file_size_bytes}")
            else:
                log.warning(f"Requested range exceeds signal file size: {byte_offset + map_length} > {signal_file_size_bytes}.  Reducing num_samples from {num_samples} to {reduced_num_samples}.")
                num_samples = reduced_num_samples

        if sigmf_datatype in (SigmfDataType.cf32_le, SigmfDataType.cf32_be, SigmfDataType.cf64_le, SigmfDataType.cf64_be):
            match sigmf_datatype:
                case SigmfDataType.cf32_le:
                    memmap_dtype = np.dtype('<c8')
                case SigmfDataType.cf32_be:
                    memmap_dtype = np.dtype('>c8')
                case SigmfDataType.cf64_le:
                    memmap_dtype = np.dtype('<c16')
                case SigmfDataType.cf64_be:
                    memmap_dtype = np.dtype('>c16')
            xform = identity_xform
            mmap_shape = (num_samples, num_input_channels)

        elif not sigmf_datatype.is_complex:
            # all of the real types are trivially memmappable, so we can just use the memmap directly
            xform = identity_xform

            # e: endianness
            if sigmf_datatype.name.endswith('_le'):
                e = '<'
            elif sigmf_datatype.name.endswith('_be'):
                e = '>'
            else:
                e = ''

            # sz: size in bytes of the sample
            if "64" in sigmf_datatype.name:
                sz = '8'
            elif "32" in sigmf_datatype.name:
                sz = '4'
            elif "16" in sigmf_datatype.name:
                sz = '2'
            elif "8" in sigmf_datatype.name:
                sz = '1'
            else:
                raise ValueError(f"Unsupported SigMF datatype: {sigmf_datatype}")   # should be impossible
            
            # su: signed ("i") or unsigned ("u")
            if "i" in sigmf_datatype.name:
                su = 'i'
            elif "u" in sigmf_datatype.name:
                su = 'u'
            elif "f" in sigmf_datatype.name:
                su = 'f'
            else:
                raise ValueError(f"Unsupported SigMF datatype: {sigmf_datatype}")   # should be impossible

            memmap_dtype = np.dtype(f"{e}{su}{sz}")
            mmap_shape = (num_samples, num_input_channels)

        else:
            # complex integer types:  numpy doesn't support these innately so we use a transform function to convert the memmap to a usable numpy array
            match sigmf_datatype:
                case SigmfDataType.ci32_le:
                    memmap_dtype = np.dtype('<i4')
                case SigmfDataType.ci32_be:
                    memmap_dtype = np.dtype('>i4')
                case SigmfDataType.ci16_le:
                    memmap_dtype = np.dtype('<i2')
                case SigmfDataType.ci16_be:
                    memmap_dtype = np.dtype('>i2')
                case SigmfDataType.ci8:
                    memmap_dtype = np.dtype('i1')
                case SigmfDataType.cu32_le:
                    memmap_dtype = np.dtype('<u4')
                case SigmfDataType.cu32_be:
                    memmap_dtype = np.dtype('>u4')
                case SigmfDataType.cu16_le:
                    memmap_dtype = np.dtype('<u2')
                case SigmfDataType.cu16_be:
                    memmap_dtype = np.dtype('>u2')
                case SigmfDataType.cu8:
                    memmap_dtype = np.dtype('u1')
                case _:
                    raise ValueError(f"Unsupported SigMF datatype: {sigmf_datatype}")   # should be impossible

            # Note the order of operations: astype() actually turns ints into floats, then view() reinterprets the float array as complex.
            def convert_components_to_complex_and_reshape(arr: np.ndarray) -> np.ndarray:
                # convert to float32 and view as complex64
                print(f"about to convert {arr.shape} of {arr.dtype} to complex64")
                arr = arr.astype(np.float32).view(np.complex64)
                # reshape to (num_samples, num_input_channels)
                arr = arr.reshape((num_samples, num_input_channels))

                # TODO now: apply scaling here!

                return arr
            xform = convert_components_to_complex_and_reshape
            mmap_shape = (2*num_samples * num_input_channels,)

        mm = np.memmap(signal_file, dtype=memmap_dtype, mode='r', offset=byte_offset, shape=mmap_shape)
        a = xform(mm)   # apply transforms if necessary, which may create a separate array or a view of the memmap
        a.setflags(write=False)  # make read-only
        assert a.shape == (num_samples, num_input_channels), f"Unexpected shape: {a.shape} != {(num_samples, num_input_channels)}"

        return a


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

@dataclass(frozen=True)
class TimeDomainComputationSpec(abc.ABC):
    computation_type: TimeDomainComputationType
    def get_cache_tag_tuples(self) -> list[tuple[str, typing.Any]]:
        return [("computation_type", str(self.computation_type))]

@dataclass(frozen=True)
class RawTimeDomainComputationSpec(TimeDomainComputationSpec):
    computation_type: TimeDomainComputationType = TimeDomainComputationType.RAW

@dataclass(frozen=True)
class MagnitudeTimeDomainComputationSpec(TimeDomainComputationSpec):
    computation_type: TimeDomainComputationType = TimeDomainComputationType.MAGNITUDE_DB

@dataclass(frozen=True)
class RealComponentTimeDomainComputationSpec(TimeDomainComputationSpec):
    computation_type: TimeDomainComputationType = TimeDomainComputationType.REAL

@dataclass(frozen=True)
class ImagComponentTimeDomainComputationSpec(TimeDomainComputationSpec):
    computation_type: TimeDomainComputationType = TimeDomainComputationType.IMAG

@dataclass(frozen=True)
class FMDemodTimeDomainComputationSpec(TimeDomainComputationSpec):
    computation_type: TimeDomainComputationType = TimeDomainComputationType.FM_DEMOD

#@dataclass(frozen=True)
#class AMDemodTimeDomainComputationSpec(TimeDomainComputationSpec):
#    computation_type: TimeDomainComputationType = TimeDomainComputationType.AM_DEMOD
#    #TODO: are there any other parameters we want here?

class ProcessingPoolManager:
    _instance: ProcessingPoolManager | None = None

    def __init__(self):
        self._pool: Pool | None = None
        self._num_processes = max(1, cpu_count() - 2)  # Leave some CPUs free

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

    def map_async_with_callback(self, func, args_list, callback) -> MapResult:
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
    def __init__(self, num_chunks: int, file_path: Path):
        expected_size = (num_chunks + 7) // 8
        if file_path.exists():
            if file_path.stat().st_size != expected_size:
                file_path.unlink()  # delete the file if size mismatch
                make_file = True
            else:
                make_file = False
        else:
            make_file = True

        if make_file:
            with open(file_path, 'wb') as f:
                f.write(b'\0' * expected_size)

        self._cond = threading.Condition()
        self._mmap = np.memmap(file_path, dtype=np.uint8, mode='r+', shape=(expected_size,))
        self._num_chunks = num_chunks
        self._file_path = file_path
        self._chunks_set = set()
        for chunk_index in range(num_chunks):
            byte_index = chunk_index // 8
            bit_index = chunk_index % 8
            if (self._mmap[byte_index] & (np.uint8(1) << bit_index)) != 0:
                self._chunks_set.add(chunk_index)

    def set_chunks(self, chunk_indices: typing.Iterable[int]) -> None:
        with self._cond:
            new_being_set = set(chunk_indices) - self._chunks_set
            for chunk_index in new_being_set:
                if 0 <= chunk_index < self._num_chunks:
                    byte_index = chunk_index // 8
                    bit_index = chunk_index % 8
                    self._mmap[byte_index] |= (np.uint8(1) << bit_index)
                    self._chunks_set.add(chunk_index)
                    self._cond.notify_all()
                else:
                    log.warning(f"ChunkBitmap.set_chunks: chunk index {chunk_index} out of range")
    def find_chunks_not_set(self, chunk_indices: typing.Iterable[int]) -> set[int]:
        with self._cond:
            return set(chunk_indices).difference(self._chunks_set)
    def is_chunk_set(self, chunk_index: int) -> bool:
        with self._cond:
            return chunk_index in self._chunks_set
    def __len__(self) -> int:
        return self._num_chunks
    def flush(self) -> None:
        self._mmap.flush()
    def close(self) -> None:
        self._mmap._mmap.close()
    def wait_for_bits_set(self, chunk_indices: typing.Iterable[int], timeout_sec: float|None=None) -> bool:
        """
        Wait until all specified chunk indices are set, or until timeout.
        Returns True if all specified chunks are set, False if timeout occurred.
        """
        start_time = time.monotonic()
        deadline = start_time + timeout_sec if timeout_sec is not None else None
        wait_set = set(chunk_indices)
        with self._cond:
            while True:

                to_remove = wait_set.intersection(self._chunks_set)
                wait_set -= to_remove

                if not wait_set:
                    return True

                else:
                    timeout = None
                    if deadline is not None:
                        now = time.monotonic()
                        timeout = max(0, deadline - now)
                        if timeout <= 0:
                            return False
                    self._cond.wait(timeout=timeout)

def compute_num_chunks(total_samples: int, chunk_size_samples: int) -> int:
    return (total_samples + chunk_size_samples - 1) // chunk_size_samples

def compute_total_num_elements_in_shape(shape: tuple[int, ...]) -> int:
    total = 1
    for dim in shape:
        total *= dim
    return total    

class TimeDomainChunkwiseComputedArray(ChunkwiseComputedArray):
    def __init__(self, signal_file: Path, sigmf_datatype: SigmfDataType, num_channels: int, comp_spec: TimeDomainComputationSpec, chunk_size_samples=1_000_000, cache_manager: CacheManager | None = None, processing_pool_manager:ProcessingPoolManager|None=None):

        if cache_manager is None:
            cache_manager = CacheManager.get_default_cache_manager()

        self._processing_pool_manager = processing_pool_manager
        if self._processing_pool_manager is None:
            self._processing_pool_manager = ProcessingPoolManager.get_instance()

        self._signal_file = signal_file
        self._sigmf_datatype = sigmf_datatype
        self._num_channels = num_channels
        self._chunk_size_samples = chunk_size_samples
        self._comp_spec = comp_spec

        # Note: we assume that axis 0 is the one that will be computed chunkwise
        num_input_samples = self._signal_file.stat().st_size // (self._sigmf_datatype.sample_size_bytes * self._num_channels)
        self._input_shape = (num_input_samples, self._num_channels)
        self._output_shape = (num_input_samples, self._num_channels)

        if comp_spec.computation_type in (TimeDomainComputationType.REAL, TimeDomainComputationType.IMAG, TimeDomainComputationType.FM_DEMOD, TimeDomainComputationType.MAGNITUDE_DB): #, TimeDomainComputationType.AM_DEMOD):
            self._output_dtype = np.dtype(np.float32)
        elif comp_spec.computation_type in (TimeDomainComputationType.RAW,):
            if self._sigmf_datatype.is_complex:
                self._output_dtype = np.dtype(np.complex64)
            else:
                self._output_dtype = np.dtype(np.float32)
        else:
            raise ValueError(f"Unsupported computation type: {comp_spec.computation_type}")

        self._num_output_chunks = compute_num_chunks(self._output_shape[0], self._chunk_size_samples)

        # Note: this is only needed if we have nontrivial computation to do in this class
        cache_tag_tuples = cache_manager.get_cache_tag_tuples_for_file(signal_file) + comp_spec.get_cache_tag_tuples()
        self._state_dir = cache_manager.get_cache_path_from_tag( cache_manager.get_cache_tag_from_tuples( prefix=self._signal_file.resolve().name, tuples=cache_tag_tuples ) )
        self._state_dir.mkdir(parents=True, exist_ok=True)

        self._chunk_bitmap_path = self._state_dir / f"bitmap"
        # A chunk index will be set in _chunk_bitmap if computation has been completed
        self._chunk_bitmap: ChunkBitmap = ChunkBitmap(num_chunks=self._num_output_chunks, file_path=self._chunk_bitmap_path)
        # A chunk index will be set in _chunks_being_computed if computation has been started
        self._chunks_being_computed: set[int] = set()
        self._cbc_cond = threading.Condition()

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
        """
        Returns the shape and dtype of the computed array represented by this class.
        The shape will be (num_samples, num_channels).
        The dtype will be either np.float32 or np.complex64, depending on the input file type.
        """
        return self._output_shape, self._output_dtype

    def map_sample_to_chunk(self, sample_index: int) -> int:
        return sample_index // self._chunk_size_samples

    def map_chunk_to_sample_range(self, chunk_index: int) -> tuple[int, int]:
        start_sample = chunk_index * self._chunk_size_samples
        end_sample = min(start_sample + self._chunk_size_samples, self._output_shape[0])
        return start_sample, end_sample

    def get_range_blocking(self, start:int, stop:int) -> npt.NDArray|None:
        if start < 0 or stop > self._output_shape[0] or start >= stop:
            raise ValueError("Invalid range")

        start_chunk = self.map_sample_to_chunk(start)
        end_chunk = self.map_sample_to_chunk(stop - 1)  # inclusive

        chunks_i_need = range(start_chunk, end_chunk + 1)
        chunks_not_yet_computed = self._chunk_bitmap.find_chunks_not_set(chunks_i_need)

        log.debug(f"TimeDomainCCA.get_range_blocking: Getting {len(chunks_i_need)} chunks for range {start}-{stop}")

        if chunks_not_yet_computed:
            ppm = self._processing_pool_manager
            assert ppm is not None
            map_result: MapResult | None = None
            with self._cbc_cond:
                chunks_to_compute = chunks_not_yet_computed - self._chunks_being_computed
                if chunks_to_compute:
                    requests = [self._generate_chunk_computation_request(ci) for ci in chunks_to_compute]
                    # perform the computation in the parallel process pool.
                    # once it has completed successfully, we can read the data from the memmap
                    start_time = time.monotonic()
                    map_result = ppm.map_async_with_callback(self._perform_chunk_computation, requests, callback=None)
                    self._chunks_being_computed.update(chunks_to_compute)
            if map_result is not None:
                map_result.wait()
                end_time = time.monotonic()
                if not map_result.successful():
                    raise RuntimeError("Error during chunk computation") from map_result.get()
                self._chunk_bitmap.set_chunks(chunks_to_compute)
                log.debug(f"TimeDomainCCA.get_range_blocking: Computed {len(chunks_to_compute)} chunks for range {start}-{stop} in {end_time - start_time:.2f} seconds")
            self._chunk_bitmap.wait_for_bits_set( chunks_i_need )   # TODO: use timeout here?
        #else: all chunks were computed already, so just create a view on the mmap

        # create the view of the requested range
        rv = self._output_memmap[ start:stop, :]
        rv.setflags(write=False)  # make read-only
        return rv

    def get_range_callback(self, start:int, stop:int, cb: RangeComputedCallback):
        if start < 0 or stop > self._output_shape[0] or start >= stop:
            raise ValueError("Invalid range")

        start_chunk = self.map_sample_to_chunk(start)
        end_chunk = self.map_sample_to_chunk(stop - 1)  # inclusive

        chunks_i_need = range(start_chunk, end_chunk + 1)
        chunks_not_yet_computed = self._chunk_bitmap.find_chunks_not_set(chunks_i_need)

        chunks_to_compute = set()
        with self._cbc_cond:
            chunks_to_compute = chunks_not_yet_computed - self._chunks_being_computed
            if chunks_to_compute:
                self._chunks_being_computed.update(chunks_to_compute)

        def on_computation_complete(results_whocares: list[None]) -> None:
            # Mark chunks as computed
            if chunks_to_compute:
                self._chunk_bitmap.set_chunks(chunks_to_compute)
                self._chunk_bitmap.flush()
            self._chunk_bitmap.wait_for_bits_set( chunks_i_need )   # TODO: use timeout here?

            # create the view of the requested range
            rv = self._output_memmap[ start:stop, :]
            rv.setflags(write=False)  # make read-only

            # Invoke the callback
            cb(self, start, stop, rv)

        log.debug(f"TimeDomainCCA.get_range_callback: Computing {len(chunks_to_compute)} chunks for range {start}-{stop}")
        if chunks_to_compute:
            log.debug(f"Computing {len(chunks_to_compute)} chunks for range {start}-{stop}")
            requests = [self._generate_chunk_computation_request(ci) for ci in chunks_to_compute]
            ppm = self._processing_pool_manager
            assert ppm is not None
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
            "sigmf_datatype": self._sigmf_datatype.name,
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
        sigmf_datatype = SigmfDataType[request["sigmf_datatype"]]
        num_channels = request["num_channels"]
        comp_spec: TimeDomainComputationSpec = request["comp_spec"]
        output_file = Path(request["output_file"])
        output_dtype = np.dtype(request["output_dtype"])

        num_input_samples = signal_file.stat().st_size // (sigmf_datatype.sample_size_bytes * num_channels)

        num_samples_to_read = end_sample - start_sample

        # For time domain computations, the input and output shapes are the
        # same, so the start and end sample indices for the input are the same
        # as for the output.
        data = cls._get_input_data(signal_file, sigmf_datatype, num_channels, start_sample, num_samples_to_read)

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

# Takes a tuple of (start_sample, end_sample) and returns an ndarray of the
# input samples in that range. The end_sample is exclusive, i.e., the range is
# [start_sample, end_sample).
FetchInputSamplesCallback = typing.Callable[[int, int], np.ndarray]

@dataclasses.dataclass
class InputSampleRange:
    start_sample_idx: int       # the first sample index in the true input signal that is required to compute a given frame (inclusive), will always be >= 0
    end_sample_idx: int         # the last sample index in the true input signal that is required to compute a given frame (exclusive), will always be <= num_input_samples
    left_padding_samples: int   # number of padding samples (not part of the true signal) to the left of start_sample that are needed for the windowing function
    right_padding_samples: int  # number of padding samples (not part of the true signal) to the right of end_sample that are needed for the windowing function

    @property
    def window_length_samples(self) -> int:
        return self.end_sample_idx - self.start_sample_idx + self.left_padding_samples + self.right_padding_samples

class STFTWindowCalculator:
    """
    The input samples for each frame are computed as:
    half_win = win_length_samples // 2

    frame[p] corresponds to input samples:
    start_sample = p * hop_samples - half_win
    end_sample = start_sample + win_length_samples

    frame is computed as:
    frame[p,:] = STFT( win * input_samples[start_sample:end_sample], NFFT=NFFT) 
    """

    def __init__(self, 
        # Input Parameters
        num_input_samples: int,
        sample_rate_Hz: float,

        # Calculation Parameters
        NFFT: int,
        win_type: WindowType,
        win_length_samples: int,
        hop_samples: int,
    ):
        self.num_input_samples = num_input_samples
        self.sample_rate_Hz = sample_rate_Hz

        self.NFFT = NFFT
        self.win_length_samples = win_length_samples
        self.win_type = win_type
        self.hop_samples = hop_samples

        self._half_win = self.win_length_samples // 2

    @classmethod
    @lru_cache(maxsize=1)
    def get_window(cls, win_type: WindowType, win_length_samples: int) -> np.ndarray:
        arr = window_type_to_array(win_type, win_length_samples)
        arr.setflags(write=False)  # make read-only
        return arr

    @property
    def delta_f_Hz(self) -> float:
        """
        Return the frequency resolution of the STFT in Hz.
        This is equal to the sample rate divided by the FFT size.
        """
        return self.sample_rate_Hz / self.NFFT

    @property
    def frame_period_sec(self) -> float:
        """
        Return the time difference between adjacent frames in seconds.
        This could also be called the "frame period".
        """
        return self.hop_samples / self.sample_rate_Hz

    @property
    def num_frames(self) -> int:
        """
        Return the number of frames that can be computed from the input samples.
        """
        return (self.num_input_samples + self.hop_samples - 1) // self.hop_samples

    def calculate_input_sample_range_for_frame(self, frame_index: int) -> InputSampleRange|None:
        """
        Given a frame index, return the start and end input sample indices that are required to compute that frame.
        The end index is exclusive, i.e., the range is [start_sample, end_sample).
        If the frame index is out of bounds, return None.
        """

        if frame_index < 0 or frame_index >= self.num_frames:
            return None

        start_sample = frame_index * self.hop_samples - self._half_win
        end_sample = start_sample + self.win_length_samples

        if start_sample < 0:
            left_padding = -start_sample
            realsig_start_sample = 0
        else:
            left_padding = 0
            realsig_start_sample = start_sample

        if end_sample > self.num_input_samples:
            right_padding = end_sample - self.num_input_samples
            realsig_end_sample = self.num_input_samples
        else:
            right_padding = 0
            realsig_end_sample = end_sample

        return InputSampleRange(
            start_sample_idx=realsig_start_sample,
            end_sample_idx=realsig_end_sample,
            left_padding_samples=left_padding,
            right_padding_samples=right_padding
        )

    def calculate_input_sample_range_for_frame_range(self, start_frame: int, end_frame: int) -> InputSampleRange|None:
        """
        Given a range of frame indices [start_frame, end_frame), return the start and end input sample indices that are required to compute that range of frames.
        The end index is exclusive, i.e., the range is [start_sample, end_sample).
        If the frame range is out of bounds, return None.
        """

        if start_frame < 0 or end_frame > self.num_frames or start_frame >= end_frame:
            return None

        start_range = self.calculate_input_sample_range_for_frame(start_frame)
        end_range = self.calculate_input_sample_range_for_frame(end_frame - 1)

        if start_range is None or end_range is None:
            return None

        return InputSampleRange(
            start_sample_idx=start_range.start_sample_idx,
            end_sample_idx=end_range.end_sample_idx,
            left_padding_samples=start_range.left_padding_samples,
            right_padding_samples=end_range.right_padding_samples
        )

    def calculate_stft_frames_given_required_input_data(
        self,
        input_data: np.ndarray,     # type is expected to be either float32 or complex64
        input_sample_base_idx: int,
        start_frame: int,
        end_frame: int,
        #out: np.ndarray|None = None    #TODO: support this?
    ) -> np.ndarray:
        """
        Given the input data and the base index of the input data, compute the STFT frames for the given frame range [start_frame, end_frame).
        The input_data is assumed to be a 1D array of complex samples.
        The input_sample_base_idx is the index of the first sample in input_data relative to the original input signal.

        The returned array has 2 dimensions: [num_frames, NFFT], where num_frames = end_frame - start_frame.
        """

        first_sample_idx_available = input_sample_base_idx
        last_sample_idx_available = input_sample_base_idx + len(input_data)

        # Calculate the required input sample range for the given frame range
        required_range = self.calculate_input_sample_range_for_frame_range(start_frame, end_frame)
        if required_range is None:
            raise ValueError(f"Frame range [{start_frame}, {end_frame}) is out of bounds.")

        if required_range.start_sample_idx < first_sample_idx_available or required_range.end_sample_idx > last_sample_idx_available:
            raise ValueError(f"Required input sample range [{required_range.start_sample_idx}, {required_range.end_sample_idx}) is not covered by the provided input_data range [{first_sample_idx_available}, {last_sample_idx_available}).")

        incoming_samples = np.zeros(self.win_length_samples, dtype=input_data.dtype)


        # Compute STFT frames
        output_frames = np.empty((end_frame - start_frame, self.NFFT), dtype=np.complex64 if np.iscomplexobj(input_data) else np.float32)

        do_window = False
        if self.win_type != WindowType.RECTANGULAR:
            window = self.get_window(self.win_type, self.win_length_samples)
            windowed_samples = np.empty_like(incoming_samples, dtype=np.complex64 if np.iscomplexobj(input_data) else np.float32)
            do_window = True

        for stft_idx,frame_index in enumerate(range(start_frame, end_frame)):
            frame_range = self.calculate_input_sample_range_for_frame(frame_index)
            assert frame_range is not None, f"Frame index {frame_index} is out of bounds."  # This should never happen due to the earlier check

            # Extract the relevant samples from input_data
            start_idx = frame_range.start_sample_idx - input_sample_base_idx
            end_idx = frame_range.end_sample_idx - input_sample_base_idx
            frame_samples = input_data[start_idx:end_idx]

            # Apply windowing and compute FFT
            incoming_samples[:] = 0 # this pads with zeros to the left and/or right as required
            incoming_samples[frame_range.left_padding_samples:frame_range.left_padding_samples + len(frame_samples)] = frame_samples

            if do_window:
                windowed_samples[:] = incoming_samples * window  # apply windowing function
                input_to_fft = windowed_samples
            else:
                input_to_fft = incoming_samples

            stft_frame = np.fft.fftshift(np.fft.fft(input_to_fft, n=self.NFFT))
            # TODO: compute magnitude here and always return float32?
            output_frames[stft_idx] = stft_frame

        return output_frames

    def calculate_stft_frames_using_callback(self, start_frame: int, end_frame: int, fetch_input_samples_callback: FetchInputSamplesCallback) -> np.ndarray:
        """
        Given a range of frame indices [start_frame, end_frame), fetch the required input samples using the provided callback and compute the STFT frames for that range.
        The fetch_input_samples_callback is a function that takes a start and end sample index and returns the corresponding input samples as a 1D numpy array.
        """
        # Calculate the required input sample range for the given frame range
        required_range = self.calculate_input_sample_range_for_frame_range(start_frame, end_frame)
        if required_range is None:
            raise ValueError(f"Frame range [{start_frame}, {end_frame}) is out of bounds.")
        
        # Fetch the required input samples using the callback
        input_data = fetch_input_samples_callback(required_range.start_sample_idx, required_range.end_sample_idx)
        input_sample_base_idx = required_range.start_sample_idx

        return self.calculate_stft_frames_given_required_input_data(input_data, input_sample_base_idx, start_frame, end_frame)


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

    def get_stft_window_calculator(self, num_input_samples: int, sample_rate_Hz: float) -> STFTWindowCalculator:
        return STFTWindowCalculator(
            num_input_samples=num_input_samples,
            sample_rate_Hz=sample_rate_Hz,
            NFFT=self.NFFT,
            win_length_samples = int(self.NFFT),
            win_type = self.win,
            hop_samples = self.hop_in_samples,
        )

DEFAULT_FREQ_COMPUTATION_SPEC = FrequencyDomainComputationSpec()

class FrequencyDomainChunkwiseComputedArray(ChunkwiseComputedArray):
    def __init__(self, signal_file: Path, sigmf_datatype: SigmfDataType, num_input_channels: int, target_output_channel:int, sample_rate_Hz:float, comp_spec: FrequencyDomainComputationSpec, chunk_size_bins=128*1024, cache_manager: CacheManager | None = None, processing_pool_manager:ProcessingPoolManager|None=None):
        if cache_manager is None:
            cache_manager = CacheManager.get_default_cache_manager()

        self._processing_pool_manager = processing_pool_manager
        if self._processing_pool_manager is None:
            self._processing_pool_manager = ProcessingPoolManager.get_instance()

        self._signal_file = signal_file
        self._sigmf_datatype = sigmf_datatype
        self._num_input_channels = num_input_channels
        self._target_output_channel = target_output_channel
        self._chunk_size_frames = max( 64, chunk_size_bins//comp_spec.NFFT )
        self._input_sample_rate_Hz = sample_rate_Hz
        self._comp_spec = comp_spec

        # Note: we assume that axis 0 is the one that will be computed chunkwise
        num_input_samples = self._signal_file.stat().st_size // (self._sigmf_datatype.sample_size_bytes * self._num_input_channels )
        self._input_shape = (num_input_samples, self._num_input_channels)

        # Note: we compute only a single output channel
        self._stft_win_calc = comp_spec.get_stft_window_calculator(num_input_samples, self._input_sample_rate_Hz)
        num_output_frames = self._stft_win_calc.num_frames
        self._output_shape = (num_output_frames, self._stft_win_calc.NFFT)
        self._output_dtype = np.dtype(np.float32)   # Note: currently always float32 since we just compute magnitude

        self._num_output_chunks = compute_num_chunks(self._output_shape[0], self._chunk_size_frames)

        # Note: this is only needed if we have nontrivial computation to do in this class
        cache_tag_tuples = cache_manager.get_cache_tag_tuples_for_file(signal_file) + comp_spec.get_cache_tag_tuples() + [("target_output_channel", str(target_output_channel)) ]
        self._state_dir = cache_manager.get_cache_path_from_tag( cache_manager.get_cache_tag_from_tuples( prefix=self._signal_file.resolve().name, tuples=cache_tag_tuples ) )
        self._state_dir.mkdir(parents=True, exist_ok=True)

        self._chunk_bitmap_path = self._state_dir / f"bitmap"
        # A chunk index will be set in _chunk_bitmap if computation has been completed
        self._chunk_bitmap: ChunkBitmap = ChunkBitmap(num_chunks=self._num_output_chunks, file_path=self._chunk_bitmap_path) # A chunk index will be set in _chunks_being_computed if computation has been started
        self._chunks_being_computed: set[int] = set()
        self._cbc_cond = threading.Condition()

        self._output_file = self._state_dir / f"data.bin"
        if not self._output_file.exists():
            # Create an empty file of the right size
            with open(self._output_file, 'wb') as f:
                f.seek( compute_total_num_elements_in_shape(self._output_shape) * self._output_dtype.itemsize - 1 )
                f.write(b'\0')
                f.flush()
        #log.critical(f"about to open read-only memmap with shape: {self._output_shape}, dtype: {self._output_dtype}, file: {self._output_file}")
        self._output_memmap = np.memmap(self._output_file, dtype=self._output_dtype, mode='r', shape=self._output_shape)

    def get_shape_and_dtype(self) -> tuple[tuple[int, ...], np.dtype]:
        """
        Returns the shape and dtype of the computed array represented by this class.
        The shape will be (num_frames, num_bins).
        The dtype will be np.float32 for the magnitude squared of the FFT (power spectral density).
        """
        return self._output_shape, self._output_dtype

    def map_sample_to_chunk(self, sample_index: int) -> int:
        return sample_index // self._chunk_size_frames

    def map_chunk_to_frame_range(self, chunk_index: int) -> tuple[int, int]:
        start_frame = chunk_index * self._chunk_size_frames
        end_frame = min(start_frame + self._chunk_size_frames, self._output_shape[0])
        return start_frame, end_frame

    def get_range_if_available(self, start:int, stop:int) -> npt.NDArray|None:
        """
        Returns the data for the specified range if it has already been computed, or None if it has not.
        """
        if start < 0 or stop > self._output_shape[0] or start >= stop:
            raise ValueError("Invalid range")

        start_chunk = self.map_sample_to_chunk(start)
        end_chunk = self.map_sample_to_chunk(stop - 1)  # inclusive

        if self._chunk_bitmap.find_chunks_not_set( range(start_chunk, end_chunk + 1) ):
            return None

        # create the view of the requested range
        rv = self._output_memmap[ start:stop, :]
        return rv

    def get_range_blocking(self, start:int, stop:int) -> npt.NDArray|None:
        if start < 0 or stop > self._output_shape[0] or start >= stop:
            raise ValueError("Invalid range")

        start_chunk = self.map_sample_to_chunk(start)
        end_chunk = self.map_sample_to_chunk(stop - 1)  # inclusive

        chunks_i_need = range(start_chunk, end_chunk + 1)
        chunks_not_yet_computed = self._chunk_bitmap.find_chunks_not_set(chunks_i_need)

        if chunks_not_yet_computed:
            ppm = self._processing_pool_manager
            assert ppm is not None
            map_result: MapResult | None = None
            with self._cbc_cond:
                chunks_to_compute = chunks_not_yet_computed - self._chunks_being_computed
                if chunks_to_compute:
                    requests = [self._generate_chunk_computation_request(ci) for ci in chunks_to_compute]
                    # perform the computation in the parallel process pool.
                    # once it has completed successfully, we can read the data from the memmap
                    start_time = time.monotonic()
                    map_result = ppm.map_async_with_callback(self._perform_chunk_computation, requests, callback=None)
                    self._chunks_being_computed.update(chunks_to_compute)
            if map_result is not None:
                map_result.wait()
                end_time = time.monotonic()
                if not map_result.successful():
                    raise RuntimeError("Error during chunk computation") from map_result.get()
                self._chunk_bitmap.set_chunks(chunks_to_compute)
                log.debug(f"FreqDomainCCA.get_range_blocking: Computed {len(chunks_to_compute)} chunks for range {start}-{stop} in {end_time - start_time:.2f} seconds")
            self._chunk_bitmap.wait_for_bits_set( chunks_i_need )   # TODO: use timeout here?
        #else: all chunks were computed already, so just create a view on the mmap

        # create the view of the requested range
        rv = self._output_memmap[ start:stop, :]
        rv.setflags(write=False)  # make read-only
        return rv

    def get_range_callback(self, start:int, stop:int, cb: RangeComputedCallback):
        if start < 0 or stop > self._output_shape[0] or start >= stop:
            raise ValueError("Invalid range")

        start_chunk = self.map_sample_to_chunk(start)
        end_chunk = self.map_sample_to_chunk(stop - 1)  # inclusive

        chunks_i_need = range(start_chunk, end_chunk + 1)
        chunks_not_yet_computed = self._chunk_bitmap.find_chunks_not_set(chunks_i_need)

        chunks_to_compute = set()
        with self._cbc_cond:
            chunks_to_compute = chunks_not_yet_computed - self._chunks_being_computed
            if chunks_to_compute:
                self._chunks_being_computed.update(chunks_to_compute)

        def on_computation_complete(results_whocares: list[None]) -> None:
            # Mark chunks as computed
            if chunks_to_compute:
                self._chunk_bitmap.set_chunks(chunks_to_compute)
                self._chunk_bitmap.flush()
            self._chunk_bitmap.wait_for_bits_set( chunks_i_need )   # TODO: use timeout here?

            # create the view of the requested range
            rv = self._output_memmap[ start:stop, :]

            # Invoke the callback
            cb(self, start, stop, rv)

        if chunks_to_compute:
            log.debug(f"Computing {len(chunks_to_compute)} chunks for range {start}-{stop}")
            requests = [self._generate_chunk_computation_request(ci) for ci in chunks_to_compute]
            ppm = self._processing_pool_manager
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
            "sigmf_datatype": self._sigmf_datatype.name,
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
        sigmf_datatype = SigmfDataType[request["sigmf_datatype"]]
        num_input_channels = request["num_input_channels"]
        target_output_channel = request["target_output_channel"]
        input_sample_rate_Hz = request["input_sample_rate_Hz"]
        comp_spec: FrequencyDomainComputationSpec = request["comp_spec"]
        output_file = Path(request["output_file"])
        output_shape = request["output_shape"]
        output_dtype = np.dtype(request["output_dtype"])

        num_input_samples = signal_file.stat().st_size // (sigmf_datatype.sample_size_bytes * num_input_channels)

        stft_win_calc = comp_spec.get_stft_window_calculator(num_input_samples, input_sample_rate_Hz)
        nfft = stft_win_calc.NFFT

        # data fetching function that matches FetchInputSamplesCallback signature
        def fisc(start_sample:int, end_sample:int) -> np.ndarray:
            num_samples = end_sample - start_sample
            a = cls._get_input_data(signal_file, sigmf_datatype, num_input_channels, start_sample, num_samples)
            return a[:, target_output_channel]

        S = stft_win_calc.calculate_stft_frames_using_callback(
            start_frame = start_frame,
            end_frame = end_frame,
            fetch_input_samples_callback=fisc,
        )

        num_frames, num_bins = S.shape
        assert num_bins == nfft, f"Expected {nfft} bins, got {num_bins}"
        assert num_frames == (end_frame - start_frame), f"Expected {end_frame - start_frame} frames, got {num_frames}"

        mag_dB = 20 * np.log10(np.abs(S) + 1e-12)  # Add small value to avoid log(0)
        S = mag_dB.astype(output_dtype)

        #log.critical(f"about to write computed chunk {chunk_index} to memmap with shape: {output_shape}, dtype: {output_dtype}, file: {output_file}, frame range: {start_frame}-{end_frame}, S shape: {S.shape}, S dtype: {S.dtype}")   
        # Confusingly: "r+" means read/write, file must exist, if we were to say "w+" it seems to change the file size or possibly make it sparse
        output_memmap = np.memmap(output_file, dtype=output_dtype, mode='r+', shape=output_shape)
        output_memmap[start_frame:end_frame, :] = S
        output_memmap.flush()

    @property
    def time_axis(self) -> MonotonicAxis:
        num_output_frames, _ = self._output_shape
        return MonotonicAxis(
            slope = self._stft_win_calc.frame_period_sec,
            intercept = 0.0,
            num_points = num_output_frames,
        )
            
    def get_freq_axis_assuming_center_frequency(self, center_freq_Hz:float=0.0) -> MonotonicAxis:
        # TODO: double check this math -- is center bin correct?
        lo_freq_Hz = -(self._stft_win_calc.delta_f_Hz * self._stft_win_calc.NFFT//2)
        lo_freq_Hz += center_freq_Hz
        return MonotonicAxis(
            slope = self._stft_win_calc.delta_f_Hz,
            intercept = lo_freq_Hz,
            num_points = self._stft_win_calc.NFFT,
        )

    @property
    def delta_t_per_frame(self) -> float:
        return self._stft_win_calc.frame_period_sec
