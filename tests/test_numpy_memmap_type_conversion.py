
import numpy as np
from pathlib import Path

def test1(tmp_path: Path):
    N = 10
    x = np.arange(N, dtype=np.int32)
    native_file = tmp_path / "test_native_endian.bin"
    swapped_file = tmp_path / "test_swapped_endian.bin"
    x.tofile(native_file)
    x.byteswap().tofile(swapped_file)

    assert native_file.read_bytes() != swapped_file.read_bytes()

    # Assumes "native" is little-endian and "swapped" is big-endian
    mn = np.memmap(native_file, dtype='<i4', mode='r')
    ms = np.memmap(swapped_file, dtype='>i4', mode='r')
    ms_wrong = np.memmap(swapped_file, dtype='<i4', mode='r')

    assert np.array_equal(x, mn)
    assert np.array_equal(mn, ms)
    assert not np.array_equal(mn, ms_wrong)
    del mn, ms, ms_wrong

    xc = x[::2] + 1j * x[1::2]
    assert xc.dtype == np.complex128

    ## now, can we interpret the memmap as a complex type and have it handle the byte swapping internally?
    # seems like we can't
    #mnc = np.memmap(native_file, dtype='<i4', mode='r').view(dtype='')

def test2(tmp_path: Path):
    """
    Test if complex type byte swapping works correctly with memmap.
    """
    N = 10
    x = np.arange(2*N, dtype=np.float32)
    xc = x[::2] + 1j * x[1::2]
    del x

    assert xc.dtype == np.complex64

    native_file = tmp_path / "test_native_endian.bin"
    swapped_file = tmp_path / "test_swapped_endian.bin"
    xc.tofile(native_file)
    xc.byteswap().tofile(swapped_file)

    assert native_file.read_bytes() != swapped_file.read_bytes()

    # Assumes "native" is little-endian and "swapped" is big-endian
    mn = np.memmap(native_file, dtype='<c8', mode='r')
    ms = np.memmap(swapped_file, dtype='>c8', mode='r')
    ms_wrong = np.memmap(swapped_file, dtype='<c8', mode='r')

    assert np.array_equal(xc, mn)
    assert np.array_equal(mn, ms)
    assert not np.array_equal(mn, ms_wrong)
    print(f"mn: {mn}, ms: {ms}, ms_wrong: {ms_wrong}")


def test3(tmp_path: Path):
    """
    What do we have to do to deal with complex integer types?
    """
    N = 10
    x = np.arange(2*N, dtype=np.int32)

    native_file = tmp_path / "test_native_endian.bin"
    swapped_file = tmp_path / "test_swapped_endian.bin"
    x.tofile(native_file)
    x.byteswap().tofile(swapped_file)

    mn = np.memmap(native_file, dtype='<i4', mode='r')
    ms = np.memmap(swapped_file, dtype='>i4', mode='r')
    ms_wrong = np.memmap(swapped_file, dtype='<i4', mode='r')

    assert np.array_equal(x, mn)
    assert np.array_equal(mn, ms)
    assert not np.array_equal(mn, ms_wrong)
    del mn, ms, ms_wrong

    xc = x[::2] + 1j * x[1::2]
    
    # Note the order: astype() actually turns ints into floats, then view() reinterprets the float array as complex.
    mnc = np.memmap(native_file, dtype='<i4', mode='r').astype(np.float32).view(dtype='complex64')
    print(f"{xc=}")
    print(f"{mnc=}")
    assert np.array_equal(xc, mnc)
