import mmap


def test_mmap_sparse_file(tmp_path):
    """
    Test memory-mapping behavior with sparse files.
    
    This test validates that:
    1. A sparse file can be created by seeking past the end and writing
    2. A non-sparse region can be memory-mapped while the file is sparse
    3. Writing to a previously sparse region while a mapping is active works correctly
    4. The first mapping remains valid and returns expected contents
    5. A new mapping of the formerly sparse region returns correct contents
    """
    # Create a temporary file path
    temp_file = tmp_path / "sparse_test.dat"
    
    # Step 1: Create a sparse file
    # We'll create a file with sparse region at the beginning, then write data further in
    with open(temp_file, "wb") as f:
        # Seek past the beginning to create a sparse region (first 4096 bytes will be sparse)
        f.seek(4096)
        # Write some data in a non-sparse region
        non_sparse_data = b"FIRST_REGION_DATA_CONTENT_123"
        f.write(non_sparse_data)
        f.flush()
    
    # Step 2: Memory-map the non-sparse region
    with open(temp_file, "r+b") as f:
        # Map the region where we wrote non_sparse_data (starting at offset 4096)
        mm1 = mmap.mmap(f.fileno(), len(non_sparse_data), offset=4096)
        
        # Verify the first mapping contains the expected data
        assert mm1[:] == non_sparse_data, "First mapping should contain the data we wrote"
        
        # Step 3: While the first mapping is active, write to the previously sparse region
        # We need to write to a different part of the file (the sparse region)
        f.seek(0)
        sparse_region_data = b"SPARSE_REGION_NOW_FILLED_456"
        f.write(sparse_region_data)
        f.flush()
        
        # Step 4: Create a second mapping for the newly written (formerly sparse) region
        mm2 = mmap.mmap(f.fileno(), len(sparse_region_data), offset=0)
        
        # Assert that the first mapping is still usable and returns expected contents
        assert mm1[:] == non_sparse_data, "First mapping should still contain original data"
        
        # Assert that the second mapping returns the right contents
        assert mm2[:] == sparse_region_data, "Second mapping should contain the newly written data"
        
        # Clean up mappings
        mm1.close()
        mm2.close()
    
    # Additional verification: re-open and verify both regions persisted correctly
    with open(temp_file, "rb") as f:
        f.seek(0)
        assert f.read(len(sparse_region_data)) == sparse_region_data, "Sparse region data should persist"
        
        f.seek(4096)
        assert f.read(len(non_sparse_data)) == non_sparse_data, "Original non-sparse region data should persist"
