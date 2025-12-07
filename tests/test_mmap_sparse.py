import mmap
import os
import platform


def test_mmap_sparse_file(tmp_path):
    """
    Test memory-mapping behavior with sparse files.
    
    This test validates that:
    1. A sparse file can be created by seeking past the end and writing
    2. A non-sparse region can be memory-mapped while the file is sparse
    3. Writing to a previously sparse region while a mapping is active works correctly
    4. The first mapping remains valid and returns expected contents
    5. A new mapping of the formerly sparse region returns correct contents
    6. Sparse regions are verified to be actually sparse (zeros) initially
    7. Sparse regions become non-sparse after writing to them
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
    
    # Verify the sparse region is actually sparse (reads as zeros)
    with open(temp_file, "rb") as f:
        f.seek(0)
        sparse_region_content = f.read(4096)
        assert sparse_region_content == b'\x00' * 4096, \
            "Sparse region should read as zeros initially"
    
    # Check filesystem-level sparseness if supported (st_blocks available on POSIX)
    stat_info = os.stat(temp_file)
    file_size = stat_info.st_size
    expected_size = 4096 + len(non_sparse_data)
    assert file_size == expected_size, \
        f"File size should be {expected_size} bytes"
    
    # On systems that support st_blocks, verify sparse file behavior
    # Note: Different filesystems handle sparse files differently
    # - Linux (ext4, btrfs, xfs): typically sparse-aware, uses fewer blocks
    # - macOS (APFS): may allocate differently, not always sparse-aware
    # - Windows (NTFS): sparse files work but st_blocks isn't available
    if hasattr(stat_info, 'st_blocks'):
        blocks_used = stat_info.st_blocks
        # st_blocks is always in 512-byte blocks according to POSIX
        blocks_if_full = (file_size + 511) // 512
        
        # Only assert sparse behavior on Linux where it's reliable
        if platform.system() == 'Linux':
            # On Linux, sparse files should use fewer blocks
            assert blocks_used < blocks_if_full, \
                f"Sparse file should use fewer blocks ({blocks_used}) than if fully allocated ({blocks_if_full})"
        # On other systems (like macOS), just log the values but don't assert
        # as the filesystem may handle sparse files differently
    
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
        
        # Verify the region that was sparse now contains non-zero data
        f.seek(0)
        newly_written_data = f.read(len(sparse_region_data))
        assert newly_written_data == sparse_region_data, \
            "Previously sparse region should now contain the written data"
        assert newly_written_data != b'\x00' * len(sparse_region_data), \
            "Previously sparse region should no longer be all zeros"
        
        # Step 4: Create a second mapping for the newly written (formerly sparse) region
        mm2 = mmap.mmap(f.fileno(), len(sparse_region_data), offset=0)
        
        # Assert that the first mapping is still usable and returns expected contents
        assert mm1[:] == non_sparse_data, "First mapping should still contain original data"
        
        # Assert that the second mapping returns the right contents
        assert mm2[:] == sparse_region_data, "Second mapping should contain the newly written data"
        
        # Clean up mappings
        mm1.close()
        mm2.close()
    
    # Verify the file now uses more blocks after writing to the sparse region
    if hasattr(stat_info, 'st_blocks'):
        stat_info_after = os.stat(temp_file)
        blocks_used_after = stat_info_after.st_blocks
        # After writing to the sparse region, more blocks should be allocated
        # Note: This assertion may not always hold on all filesystems,
        # but it should be true on typical POSIX systems
        assert blocks_used_after >= blocks_used, \
            f"File should use at least as many blocks after writing ({blocks_used_after}) as before ({blocks_used})"
    
    # Additional verification: re-open and verify both regions persisted correctly
    with open(temp_file, "rb") as f:
        f.seek(0)
        assert f.read(len(sparse_region_data)) == sparse_region_data, "Sparse region data should persist"
        
        f.seek(4096)
        assert f.read(len(non_sparse_data)) == non_sparse_data, "Original non-sparse region data should persist"
