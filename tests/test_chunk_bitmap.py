from pathlib import Path
from specview.chunkwise_compute import ChunkBitmap

def test_chunk_bitmap2_basic_operations(tmpdir):
    # Create a temporary file path for testing
    temp_path = Path(tmpdir) / "bitmap.dat"
    
    # Test initialization
    num_chunks = 20
    bitmap = ChunkBitmap(num_chunks, temp_path)
    
    # Test length
    assert len(bitmap) == num_chunks
    
    # Test setting bits and checking if they're set
    bitmap.set_chunks([0])
    bitmap.set_chunks([5])
    bitmap.set_chunks([19])

    assert bitmap.is_chunk_set(0)
    assert bitmap.is_chunk_set(5)
    assert bitmap.is_chunk_set(19)
    assert not bitmap.is_chunk_set(1)
    assert not bitmap.is_chunk_set(18)
    
    # Test clearing bits
    #bitmap.clear_chunk(5)
    #assert not bitmap.is_chunk_set(5)
    assert bitmap.is_chunk_set(0)  # Others should remain unchanged
    assert bitmap.is_chunk_set(19)
    
    # Test these don't cause problems, should log a warning
    bitmap.is_chunk_set(20)
    bitmap.is_chunk_set(-1)
        
    # Test persistence by creating a new bitmap object with same file
    bitmap.flush()
    bitmap.close()
    
    bitmap2 = ChunkBitmap(num_chunks, temp_path)
    assert bitmap2.is_chunk_set(0)
    assert bitmap2.is_chunk_set(5)
    assert bitmap2.is_chunk_set(19)

    assert bitmap2.find_chunks_not_set([0,1,5,19,18]) == {1,18}
    
    bitmap2.close()

def test_chunk_bitmap2_size_mismatch(tmpdir):
    # Test that the file is recreated if size doesn't match
    temp_path = Path(tmpdir) / "bitmap.dat"
    
    # Create initial bitmap with 10 chunks
    bitmap1 = ChunkBitmap(10, temp_path)
    bitmap1.set_chunks([0])
    bitmap1.flush()
    bitmap1.close()
    
    # Create new bitmap with different number of chunks
    bitmap2 = ChunkBitmap(20, temp_path)
    assert len(bitmap2) == 20
    assert not bitmap2.is_chunk_set(0)  # Should be reset
    
    bitmap2.close()

def test_chunk_bitmap2_wait_for_bits(tmpdir):
    temp_path = Path(tmpdir) / "bitmap.dat"
    bitmap = ChunkBitmap(10, temp_path)
    
    # Test immediate timeout
    assert not bitmap.wait_for_bits_set([1, 2], timeout_sec=0)
    
    # Test successful wait
    bitmap.set_chunks([1, 2])
    assert bitmap.wait_for_bits_set([1, 2], timeout_sec=0.1)
    
    # Test partial completion
    assert not bitmap.wait_for_bits_set([1, 2, 3], timeout_sec=0.1)
    
    bitmap.close()